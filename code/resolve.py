"""Per-case resource discovery and state reconstruction at audit_at.

Builds a global resource_id -> {user_id} registry from every evidence record
that carries a resolvable identifier (so a resource keyed in any snapshot links
to its user even after it was later anonymized), augmented by the explicit
LINK_RESOURCE_IDENTITY activity rows. For a case, discovers the user's resources
(direct identifier match + registry) and returns each resource's state from the
latest evidence captured at or before audit_at.
"""
import re
from collections import Counter
from datetime import datetime, timedelta

from loaders import Identity, load_rows, norm_email, _digits
import evidence

_WORKER_WINDOW = timedelta(minutes=5)


def _iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _resolve_record_user(idx, rec):
    return idx.match_user(email=rec["email"], phone=rec["phone"],
                          email_hash=rec["email_hash"], user_id=rec["user_id"])


class World:
    """Loaded dataset + evidence + registry, built once and reused per case."""

    def __init__(self):
        self.idx = Identity()
        self.records, self.cap = evidence.load_all_evidence()
        self.by_resource = {}       # resource_id -> [records]
        self.registry = {}          # resource_id -> set(user_id)
        for r in self.records:
            self.by_resource.setdefault(r["resource_id"], []).append(r)
            u = _resolve_record_user(self.idx, r)
            if u:
                self.registry.setdefault(r["resource_id"], set()).add(u)
        self._add_activity_links()
        self.user_resources = {}    # user_id -> set(resource_id)
        for rid, users in self.registry.items():
            for u in users:
                self.user_resources.setdefault(u, set()).add(rid)

    def _add_activity_links(self):
        """LINK_RESOURCE_IDENTITY rows explicitly bind resource -> email + user."""
        for a in load_rows("system_activity.csv"):
            if a["event_type"] != "LINK_RESOURCE_IDENTITY":
                continue
            rid = a["resource_id"]
            m = re.search(r"(user_\d+)", a["details"])
            em = re.search(r"([\w.+-]+@[\w.-]+)", a["details"])
            user = None
            if m and m.group(1) in self.idx.users:
                user = m.group(1)
            elif em:
                user = self.idx.resolve(em.group(1))
            if user:
                self.registry.setdefault(rid, set()).add(user)

    def latest_record(self, resource_id, audit_at=None):
        """Most recent evidence record for a resource (optionally <= audit_at)."""
        best = None
        for r in self.by_resource.get(resource_id, []):
            if audit_at is not None and r["captured_at"] > audit_at:
                continue
            if best is None or r["captured_at"] > best["captured_at"]:
                best = r
        return best

    def worker_orphan_links(self, rows):
        """Pin an *orphan* account/analytics resource to a case when exactly one
        deletion_worker DELETE_RECORD (account) / ANONYMIZE_RECORD (analytics)
        SUCCESS event lands within +/-5min of the case's reported_at. Conservative:
        only resources the grounded registry does NOT already attribute to a user
        (so a known user's resource is never time-stolen), and a resource claimed
        by more than one case is dropped as ambiguous. Returns case_id -> {rid: rec},
        each rec synthetic (absent for a deletion, present-anonymized otherwise),
        citing the activity_id since an orphan has no evidence file."""
        workers = []
        for a in load_rows("system_activity.csv"):
            rid = a["resource_id"]
            if (a["source_system"] != "deletion_worker" or a["reported_result"] != "SUCCESS"
                    or not rid or rid in self.registry):
                continue
            if a["event_type"] == "DELETE_RECORD" and rid.startswith("account_"):
                workers.append(("absent", rid, a["event_time"], a["activity_id"]))
            elif a["event_type"] == "ANONYMIZE_RECORD" and rid.startswith("analytics_"):
                workers.append(("anon", rid, a["event_time"], a["activity_id"]))
        workers = [(k, rid, t, _iso(t), aid) for k, rid, t, aid in workers]

        percase = {}
        for r in rows:
            rep = r.get("reported_at")
            if not rep:
                continue
            rt = _iso(rep)
            acc = [w for w in workers if w[0] == "absent" and abs(w[3] - rt) <= _WORKER_WINDOW]
            ana = [w for w in workers if w[0] == "anon" and abs(w[3] - rt) <= _WORKER_WINDOW]
            picked = ([acc[0]] if len(acc) == 1 else []) + ([ana[0]] if len(ana) == 1 else [])
            if picked:
                percase[r["case_id"]] = picked

        claimed = Counter(w[1] for picked in percase.values() for w in picked)
        links = {}
        for cid, picked in percase.items():
            recs = {}
            for kind, rid, raw_t, _dt, aid in picked:
                if claimed[rid] > 1:
                    continue  # same resource pinned by >1 case -> ambiguous, drop
                rec = evidence._blank_record(rid, raw_t, rid)
                rec["file_id"] = aid
                rec["exists"] = (kind != "absent")
                recs[rid] = rec
            if recs:
                links[cid] = recs
        return links

    def discover(self, user_id, audit_at):
        """resource_id -> chosen evidence record for the user. State is read at
        or before audit_at; a retained security audit record whose only evidence
        is later is still included (its retained state is time-stable)."""
        out = {}
        for rid in self.user_resources.get(user_id, ()):
            rec = self.latest_record(rid, audit_at)
            if rec is None and evidence.system_for(rid) == "security_service":
                rec = self.latest_record(rid)  # retained record, stable in time
            if rec is not None:
                out[rid] = rec
        return out
