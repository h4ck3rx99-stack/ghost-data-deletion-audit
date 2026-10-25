"""Evidence parsing for Ghost Data Still Exists.

Parses every participant evidence shape (nested JSON, SQLite SQL incl. replicas,
key=value logs with trace correlation, the pipe-delimited handover TXT, and PDF
text) into uniform records:

    {file_id, captured_at, system_id, resource_id,
     email, phone, email_hash, name, user_id,   # identifiers (normalized/None)
     exists, enabled, restore_allowed, retention_until, identifiable, raw_state}

system_id is derived from the resource_id prefix (stable across the dataset).
A record "exists" unless an explicit absence signal is seen (404 / NOT_FOUND /
rows=0 / deletion marker). Presence in any SQL table — including a replica — is
existence, so replication drift reads as PRESENT with no special case.
"""
import csv
import json
import re
import sqlite3
from pathlib import Path

from loaders import DATASET, norm_email, _digits
try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

EVIDENCE_DIR = DATASET / "evidence"

SYSTEM_BY_PREFIX = {
    "account": "account_service",
    "search": "search_service",
    "analytics": "analytics_platform",
    "support": "support_platform",
    "export": "export_service",
    "data_flow": "integration_service",
    "backup": "backup_service",
    "audit_record": "security_service",
    "tombstone": "identity_service",
    "marketing": "marketing_platform",
    "cache": "cache_service",
    "email_delivery": "email_delivery_service",
    "object": "support_platform",
    "legal_hold": "legal_service",
}

# identifier field-name -> normalized key
_EMAIL_KEYS = {"email", "requester_email", "owner_email", "customer_email"}
_PHONE_KEYS = {"phone", "requester_phone", "owner_phone"}
_HASH_KEYS = {"email_hash"}
_NAME_KEYS = {"full_name", "display_name", "requester_name", "name"}
_USER_KEYS = {"customer_reference", "subject_reference", "user_id"}
# keys whose value's identity type is decided by the value itself
_TYPED_KEYS = {"match_key", "lookup_key", "lookup_value", "correlation_key", "subject_key", "subject_selector"}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def system_for(resource_id):
    m = re.match(r"([a-z_]+?)_\d", resource_id or "")
    if not m:
        return None
    return SYSTEM_BY_PREFIX.get(m.group(1))


def _is_user_ref(val):
    return isinstance(val, str) and bool(re.fullmatch(r"user_\d+", val.strip()))


def _blank_record(file_id, captured_at, resource_id):
    return {
        "file_id": file_id, "captured_at": captured_at, "resource_id": resource_id,
        "system_id": system_for(resource_id),
        "email": None, "phone": None, "email_hash": None, "name": None, "user_id": None,
        "exists": True, "enabled": None, "restore_allowed": None,
        "retention_until": None, "identifiable": None, "raw_state": None,
        "category": None,
    }


def _bool_flag(value):
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    return {"true": True, "1": True, "false": False, "0": False}.get(token)


def _apply_state(rec, token):
    """Interpret observed readback state, never a workflow success claim."""
    state = str(token or "").strip().upper()
    rec["raw_state"] = state or rec.get("raw_state")
    if state in {"NOT_FOUND", "ABSENT", "DELETED"}:
        rec["exists"] = False
    if state == "IDENTIFIABLE":
        rec["identifiable"] = True
    flags = {}
    if rec["system_id"] == "integration_service" and state in {"ACTIVE", "DISABLED"}:
        flags["enabled"] = state == "ACTIVE"
    if rec["system_id"] == "backup_service" and state in {"ACTIVE", "BLOCKED"}:
        flags["restore_allowed"] = state == "ACTIVE"
    for key, value in flags.items():
        if rec[key] is not None and rec[key] != value:
            rec["state_conflict"] = True
            rec[key] = None
        else:
            rec[key] = value


def _flatten_scalars(node, into=None):
    """All scalar key/values found anywhere inside a dict/list (nested)."""
    into = {} if into is None else into
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (str, int, float, bool)):
                into[k] = v
            else:
                _flatten_scalars(v, into)
    elif isinstance(node, list):
        for v in node:
            _flatten_scalars(v, into)
    return into


def _apply_field(rec, key, val):
    """Map a raw key/value onto a record's identifier/flag slots."""
    if val is None or val == "" or (isinstance(val, str) and val.lower() in ("null", "none")):
        return
    k = key.lower()
    sval = str(val).strip()
    if k in ("category", "data_category", "record_type"):
        rec["category"] = sval.upper()
        return
    if _is_user_ref(sval):
        rec["user_id"] = sval
        return
    if k in _TYPED_KEYS:  # type decided by the value itself
        if "@" in sval:
            rec["email"] = norm_email(sval)
        elif _HEX64.match(sval.lower()):
            rec["email_hash"] = sval.lower()
        return
    if k in _USER_KEYS:  # value isn't a user_N ref; classify it by its content
        if "@" in sval:
            rec["email"] = norm_email(sval)
        elif _HEX64.match(sval.lower()):
            rec["email_hash"] = sval.lower()
        elif re.fullmatch(r"[+\d][\d ()\-]{6,}", sval):
            rec["phone"] = _digits(sval)
        return
    if k in _EMAIL_KEYS and "@" in sval:
        rec["email"] = norm_email(sval)
    elif k in _PHONE_KEYS:
        rec["phone"] = _digits(sval)
    elif k in _HASH_KEYS:
        rec["email_hash"] = sval.lower()
    elif k in _NAME_KEYS:
        rec["name"] = sval.lower()


# ---------------------------------------------------------------- JSON --------
def _json_records(path, file_id, captured_at):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []

    def walk(node, ctx):
        if isinstance(node, dict):
            if "resource_id" in node and isinstance(node["resource_id"], str):
                rec = _blank_record(file_id, captured_at, node["resource_id"])
                merged = {**ctx, **_flatten_scalars(node)}
                for k, v in merged.items():
                    if isinstance(v, (str, int, float, bool)):
                        _apply_field(rec, k, v)
                # existence / flags
                sc = merged.get("status_code", merged.get("http_status"))
                if sc in (404, "404"):
                    rec["exists"] = False
                if merged.get("account_status") in ("DELETED",):
                    rec["exists"] = True  # tombstone/record present
                if "enabled" in merged:
                    rec["enabled"] = _bool_flag(merged["enabled"])
                if "restore_allowed" in merged:
                    rec["restore_allowed"] = _bool_flag(merged["restore_allowed"])
                if merged.get("download_available") is False:
                    rec["exists"] = False
                if merged.get("retention_until"):
                    rec["retention_until"] = merged["retention_until"]
                _apply_state(rec, merged.get("result"))
                out.append(rec)
                # recurse into children but keep this resource's id out of ctx
                child_ctx = {k: v for k, v in merged.items()
                             if isinstance(v, (str, int, float, bool)) and k != "resource_id"}
                for v in node.values():
                    walk(v, child_ctx)
            else:
                nctx = {**ctx}
                for k, v in node.items():
                    if isinstance(v, (str, int, float, bool)):
                        nctx[k] = v
                for v in node.values():
                    walk(v, nctx)
        elif isinstance(node, list):
            for v in node:
                walk(v, ctx)

    walk(data, {})
    return out


# ----------------------------------------------------------------- SQL --------
def _sql_records(path, file_id, captured_at):
    script = Path(path).read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(script)
    except sqlite3.Error:
        con.close()
        return []
    out = []
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")').fetchall()]
        for row in con.execute(f'SELECT * FROM "{t}"').fetchall():
            d = dict(zip(cols, row))
            if "record_json" in d:  # record_json tables (primary/replica)
                try:
                    inner = json.loads(d["record_json"])
                except Exception:
                    inner = {}
                rid = inner.get("resource_id") or d.get("resource_id")
                if not rid:
                    continue
                rec = _blank_record(file_id, captured_at, rid)
                for k, v in _flatten_scalars(inner).items():
                    _apply_field(rec, k, v)
                if "enabled" in inner:
                    rec["enabled"] = inner["enabled"] in (True, 1)
                if "restore_allowed" in inner:
                    rec["restore_allowed"] = inner["restore_allowed"] in (True, 1)
                if inner.get("subject_selector"):
                    _apply_field(rec, "email", inner["subject_selector"])
                out.append(rec)
            elif "resource_id" in d:  # typed tables
                rec = _blank_record(file_id, captured_at, d["resource_id"])
                for k, v in d.items():
                    if isinstance(v, (str, int, float)):
                        _apply_field(rec, k, v)
                if "enabled" in d:
                    rec["enabled"] = str(d["enabled"]) in ("1", "True", "true")
                if "restore_allowed" in d:
                    rec["restore_allowed"] = str(d["restore_allowed"]) in ("1", "True", "true")
                if d.get("retention_until"):
                    rec["retention_until"] = d["retention_until"]
                out.append(rec)
    con.close()
    return out


# ----------------------------------------------------------------- LOG --------
_KV = re.compile(r'(\w+)=("([^"]*)"|\S+)')


def _parse_kv(line):
    d = {}
    for k, raw, q in _KV.findall(line):
        d[k] = q if raw.startswith('"') else raw
    return d


_IDENT_KEYS = ("lookup_key", "match_key", "correlation_key", "subject_key", "subject_ref",
               "matched_value", "scan_key",
               "email", "requester_email", "owner_email", "customer_email",
               "customer_reference", "subject_reference")
_MESSAGE = re.compile(r'message="(.*)"\s*$')


_TRACE = re.compile(r"\btr-\d+\b")


def _parse_log_line(line):
    """Parse one log line across dialects: flat key=value, a JSON object
    (structured_service_events), a nested escaped message="..." (cloud_runtime),
    and pipe/syslog framings whose trace id is positional."""
    b = line.find("{")
    if b != -1 and line.rstrip().endswith("}"):
        try:
            return json.loads(line[b:])
        except Exception:
            pass
    m = _MESSAGE.search(line)
    if m:
        d = _parse_kv(line[:m.start()])
        d.update(_parse_kv(m.group(1).replace('\\"', '"')))
    else:
        d = _parse_kv(line)
    if "trace_id" not in d and "requestId" not in d:  # pipe/syslog positional id
        tm = _TRACE.search(line)
        if tm:
            d["trace_id"] = tm.group(0)
    return d


def _log_records(path, file_id, captured_at):
    """key=value logs (flat and nested dialects). Correlate a queried identifier
    to its resource via the trace/request id, since the id and the resource can
    be on separate lines of the same trace."""
    lines = [_parse_log_line(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]
    trace_ident = {}  # trace id -> (key, value) of the first identifier seen
    trace_category = {}
    for d in lines:
        tid = d.get("trace_id") or d.get("requestId")
        # Contact-index queries describe secondary identifiers, not shared messages.
        if tid and d.get("event") in ("contact_query_started", "contact_query_completed",
                                      "contact_lookup_started", "contact_lookup_completed"):
            trace_category[tid] = "SECONDARY_IDENTIFIER"
        if not tid or tid in trace_ident:
            continue
        for k in _IDENT_KEYS:
            if d.get(k):
                trace_ident[tid] = (k, d[k])
                break
    out = []
    for d in lines:
        rid = d.get("resource_id")
        if not rid or not system_for(rid):
            continue
        ev = d.get("event", "")
        if ev.endswith("_started"):  # the completed/evaluated/scan line has the state
            continue
        rec = _blank_record(file_id, captured_at, rid)
        for k, v in d.items():
            _apply_field(rec, k, v)
        if not rec["category"]:
            rec["category"] = trace_category.get(d.get("trace_id") or d.get("requestId"))
        if not (rec["email"] or rec["email_hash"] or rec["phone"] or rec["user_id"]):
            tk = trace_ident.get(d.get("trace_id") or d.get("requestId"))
            if tk:
                _apply_field(rec, tk[0], tk[1])
        # existence
        if d.get("http_status") == "404" or d.get("rows") == "0" or d.get("result") == "miss":
            rec["exists"] = False
        # PII scans (cloud_runtime) mark identifiable / attachment presence
        if d.get("matched_value") or d.get("direct_identifiers") not in (None, "0"):
            rec["identifiable"] = True
        if "attachment" in ev:
            rec["category"] = "SUPPORT_ATTACHMENT"
        # integration flow
        if d.get("enabled") is not None:
            rec["enabled"] = _bool_flag(d["enabled"])
        # backup restore risk (two dialects)
        if d.get("restore_allowed") is not None:
            rec["restore_allowed"] = _bool_flag(d["restore_allowed"])
        elif "eligible" in d:
            eligible, blocked = _bool_flag(d.get("eligible")), _bool_flag(d.get("deletion_block"))
            rec["restore_allowed"] = (False if eligible is False or blocked is True else
                                      True if eligible is True and blocked is False else None)
        if d.get("retention_until"):
            rec["retention_until"] = d["retention_until"]
        _apply_state(rec, d.get("result"))
        out.append(rec)
    return out


# ----------------------------------------------------------------- TXT --------
_HANDOVER = re.compile(
    r"-\s*(\S+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*([A-Z_]+)\s*\|\s*(.+?)\s*$")
_ABSENT_STATES = {"NOT_FOUND", "ABSENT", "DELETED"}


def _txt_records(path, file_id, captured_at):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = _HANDOVER.match(line.strip())
        if not m:
            continue
        _ts, system, rid, cat, state, ident = m.groups()
        rec = _blank_record(file_id, captured_at, rid)
        rec["raw_state"] = state
        rec["category"] = cat
        if "@" in ident:
            rec["email"] = norm_email(ident)
        elif _is_user_ref(ident):
            rec["user_id"] = ident.strip()
        _apply_state(rec, state)
        out.append(rec)
    return out


# ----------------------------------------------------------------- PDF --------
def _pdf_text(path):
    if PdfReader is None:
        return ""
    try:
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    except Exception:
        return ""


def _pdf_records(path, file_id, captured_at):
    """Structured facts from the two policy PDFs; other PDFs deferred to vision."""
    text = _pdf_text(path)
    out = []
    # legal hold register rows: "user_NN | ... | Retain until DD Mon YYYY"
    for uid, until in re.findall(r"(user_\d+)\s*\|.*?Retain until ([0-9]{1,2} \w+ \d{4})", text):
        rec = _blank_record(file_id, captured_at, "legal_hold_" + uid)
        rec["user_id"] = uid
        rec["raw_state"] = "ACTIVE_HOLD"
        rec["retention_until"] = until
        out.append(rec)
    if out:
        return out
    # Otherwise a business/customer document (e.g. a support attachment): it shows
    # a present record for each resource id it names, with the customer's identifiers.
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phones = re.findall(r"\+\d[\d ]{6,}\d", text)
    email = norm_email(emails[0]) if emails else None
    phone = _digits(phones[0]) if phones else None
    seen = set()
    for rid in re.findall(r"\b([a-z_]+_\d+)\b", text):
        if rid in seen or system_for(rid) is None:
            continue
        seen.add(rid)
        rec = _blank_record(file_id, captured_at, rid)
        rec["email"], rec["phone"] = email, phone
        rec["identifiable"] = bool(email or phone)
        if rid.startswith(("support_", "object_")):  # an attachment document evidences an attachment
            rec["category"] = "SUPPORT_ATTACHMENT"
        out.append(rec)
    return out


# --------------------------------------------------------------- loader -------
def load_manifest():
    with open(DATASET / "evidence_files.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_all_evidence():
    """Parse every manifest file; return (records, meta) where meta maps
    file_id -> captured_at. Unparseable/media files yield no structured records."""
    records = []
    meta = {}
    for row in load_manifest():
        fid, rel, cap = row["file_id"], row["file_path"], row["captured_at"]
        meta[fid] = cap
        path = DATASET / rel
        if not path.exists():
            continue
        suf = path.suffix.lower()
        try:
            if suf == ".json":
                recs = _json_records(path, fid, cap)
            elif suf == ".sql":
                recs = _sql_records(path, fid, cap)
            elif suf == ".log":
                recs = _log_records(path, fid, cap)
            elif suf == ".txt":
                recs = _txt_records(path, fid, cap)
            elif suf == ".pdf":
                recs = _pdf_records(path, fid, cap)
            else:
                recs = []  # images -> vision step (later)
        except Exception:
            recs = []
        records.extend(recs)
    try:  # merge cached image/scanned-PDF facts (offline; no API at run time)
        import vision
        records.extend(vision.load_vision_records())
    except Exception:
        pass
    return records, meta


if __name__ == "__main__":
    recs, meta = load_all_evidence()
    print(f"{len(recs)} records from {len(meta)} files")
    by_sys = {}
    for r in recs:
        by_sys[r["system_id"]] = by_sys.get(r["system_id"], 0) + 1
    for s, n in sorted(by_sys.items(), key=lambda x: -x[1]):
        print(f"  {s}: {n}")
