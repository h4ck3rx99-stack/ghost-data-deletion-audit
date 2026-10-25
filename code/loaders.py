"""Dataset + identity resolution for Ghost Data Still Exists.

Resolves a request email to a user_id and expands the user's full set of
current and historical identifiers (emails, phones, email_hashes, names) so
evidence that still carries an old identifier can be matched. All matching is
case-insensitive; phones compare on digits only.
"""
import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "dataset"


def _digits(s):
    return re.sub(r"\D", "", s or "")


def norm_email(s):
    return (s or "").strip().lower()


def load_rows(name):
    with open(DATASET / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Identity:
    """Index over user_identities.csv + user_audit_log.csv."""

    def __init__(self):
        self.users = {}            # user_id -> current identity dict
        self.email_to_user = {}    # norm email -> user_id (current + historical)
        self.phone_to_user = {}    # digits -> user_id
        self.hash_to_user = {}     # email_hash -> user_id
        self._ids_for_user = {}    # user_id -> dict of sets
        self._build()

    def _build(self):
        for r in load_rows("user_identities.csv"):
            uid = r["user_id"]
            self.users[uid] = r
            ids = {"emails": set(), "phones": set(), "hashes": set(), "names": set()}
            if r.get("email"):
                ids["emails"].add(norm_email(r["email"]))
            if r.get("phone"):
                ids["phones"].add(_digits(r["phone"]))
            if r.get("email_hash"):
                ids["hashes"].add(r["email_hash"].strip().lower())
            if r.get("name"):
                ids["names"].add(r["name"].strip().lower())
            self._ids_for_user[uid] = ids

        # historical values: both old and new belong to the user
        for r in load_rows("user_audit_log.csv"):
            uid = r["user_id"]
            ids = self._ids_for_user.setdefault(
                uid, {"emails": set(), "phones": set(), "hashes": set(), "names": set()})
            field = r["field_name"]
            for val in (r.get("old_value"), r.get("new_value")):
                if not val:
                    continue
                if field == "email":
                    ids["emails"].add(norm_email(val))
                elif field == "phone":
                    ids["phones"].add(_digits(val))
                elif field == "email_hash":
                    ids["hashes"].add(val.strip().lower())
                elif field == "name":
                    ids["names"].add(val.strip().lower())

        for uid, ids in self._ids_for_user.items():
            for e in ids["emails"]:
                self.email_to_user.setdefault(e, uid)
            for p in ids["phones"]:
                if p:
                    self.phone_to_user.setdefault(p, uid)
            for h in ids["hashes"]:
                self.hash_to_user.setdefault(h, uid)

    def resolve(self, email):
        """Request email (current or historical) -> user_id, or None."""
        return self.email_to_user.get(norm_email(email))

    def identifiers(self, user_id):
        """All identifiers for a user, for exact evidence matching."""
        return self._ids_for_user.get(user_id, {"emails": set(), "phones": set(),
                                                 "hashes": set(), "names": set()})

    def match_user(self, *, email=None, phone=None, email_hash=None, user_id=None):
        """Which user an evidence identifier belongs to (exact match only)."""
        if user_id and user_id in self.users:
            return user_id
        if email:
            u = self.email_to_user.get(norm_email(email))
            if u:
                return u
        if email_hash:
            u = self.hash_to_user.get(email_hash.strip().lower())
            if u:
                return u
        if phone:
            u = self.phone_to_user.get(_digits(phone))
            if u:
                return u
        return None
