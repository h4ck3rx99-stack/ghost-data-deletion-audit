"""Output validator for Ghost Data Still Exists.

Checks output.csv against the submission contract: header, row count, one row per
case, sorted by case_id, valid JSON arrays, consecutive step numbers from 1,
allowed phases/operations/states, correct phase ordering, and that cited evidence
IDs exist and are not captured after the case's audit_at.

    python code/validate.py [output_csv]
"""
import csv
import json
import sys
from pathlib import Path

from loaders import REPO, DATASET, load_rows

PHASES = {"FINDING", "REMEDIATION", "VERIFICATION"}
OPS = {
    "FINDING": {"REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII",
                "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"},
    "REMEDIATION": {"DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD",
                    "REDACT_RECORD", "ANONYMIZE_RECORD"},
    "VERIFICATION": {"VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT",
                     "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
                     "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"},
}
STATES = {"PRESENT", "ABSENT", "ANONYMIZED", "REDACTED", "ACTIVE", "DISABLED", "BLOCKED"}
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}


def validate(path):
    path = Path(path)
    errors = []
    requests = {r["case_id"]: r for r in load_rows("deletion_requests.csv")}
    evidence_cap = {r["file_id"]: r["captured_at"] for r in load_rows("evidence_files.csv")}
    # activity/audit ids are also valid evidence citations
    valid_ids = set(evidence_cap)
    valid_ids |= {r["activity_id"] for r in load_rows("system_activity.csv")}
    valid_ids |= {r["audit_id"] for r in load_rows("user_audit_log.csv")}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header != ["case_id", "deletion_status", "steps_json"]:
            errors.append(f"bad header: {header}")
        rows = list(reader)

    seen = []
    for row in rows:
        if len(row) != 3:
            errors.append(f"row has {len(row)} cols: {row[:1]}")
            continue
        cid, status, steps_json = row
        seen.append(cid)
        if status not in STATUSES:
            errors.append(f"{cid}: bad status {status}")
        try:
            steps = json.loads(steps_json)
        except Exception as e:
            errors.append(f"{cid}: steps_json not JSON ({e})")
            continue
        if status == "NOT_APPLICABLE" and steps:
            errors.append(f"{cid}: NOT_APPLICABLE must have []")
        if status == "INCOMPLETE" and not steps:
            errors.append(f"{cid}: INCOMPLETE must have non-empty steps")
        audit_at = requests.get(cid, {}).get("audit_at", "9999")
        last_phase = -1
        for i, s in enumerate(steps, 1):
            if s.get("step_no") != i:
                errors.append(f"{cid}: step_no {s.get('step_no')} != {i}")
            ph = s.get("phase")
            if ph not in PHASES:
                errors.append(f"{cid}: bad phase {ph}")
                continue
            if PHASE_ORDER[ph] < last_phase:
                errors.append(f"{cid}: phase order violated at step {i}")
            last_phase = PHASE_ORDER[ph]
            if s.get("operation") not in OPS[ph]:
                errors.append(f"{cid}: op {s.get('operation')} invalid for {ph}")
            if s.get("state") not in STATES:
                errors.append(f"{cid}: bad state {s.get('state')}")
            ev = s.get("evidence_id", "")
            if status == "COMPLETE" and not ev:
                errors.append(f"{cid}: COMPLETE step {i} must cite a non-empty evidence_id")
            if ev:
                if ev not in valid_ids:
                    errors.append(f"{cid}: evidence {ev} does not exist")
                elif ev in evidence_cap and evidence_cap[ev] > audit_at:
                    errors.append(f"{cid}: evidence {ev} captured after audit_at")

    expected = set(requests)
    if set(seen) != expected:
        errors.append(f"case set mismatch: missing={len(expected - set(seen))} "
                      f"extra={len(set(seen) - expected)}")
    if seen != sorted(seen, key=lambda c: int(c.split('_')[1])):
        errors.append("rows not sorted by case_id")
    if len(rows) != len(requests):
        errors.append(f"row count {len(rows)} != {len(requests)}")
    return errors


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else REPO / "output.csv"
    errors = validate(path)
    if errors:
        print(f"INVALID ({len(errors)} issues):")
        for e in errors[:50]:
            print("  -", e)
        return 1
    print(f"VALID: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
