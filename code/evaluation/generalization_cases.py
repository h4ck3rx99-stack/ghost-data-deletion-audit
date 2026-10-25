"""Generalization test for Ghost Data Still Exists. Touches no prediction code.

The engine is category-driven: decide.classify maps a record's data category to the
deletion_rules.csv required_action first (system prefix only as fallback). This test
proves every one of the 15 policy categories is reachable and routes to the
policy-correct operations — especially the 5 the real evidence never instantiates
(CACHE_ENTRY, MARKETING_PROFILE, EMAIL_DELIVERY_LOG, SECONDARY_IDENTIFIER,
PRODUCT_TELEMETRY), which otherwise go completely untested.

Each category is exercised with a SYNTHETIC, present + identifiable record built via
evidence._blank_record (never a real dataset row), fed through decide.build_steps, and
checked against the action its deletion_rules row declares:

  DELETE    -> REPORT_REMAINING_RECORD / DELETE_RECORD      / VERIFY_RECORD_ABSENT      (INCOMPLETE)
  REDACT    -> REPORT_EXPOSED_PII      / REDACT_RECORD       / VERIFY_RECORD_REDACTED    (INCOMPLETE)
  ANONYMIZE -> REPORT_EXPOSED_PII      / ANONYMIZE_RECORD    / VERIFY_RECORD_ANONYMIZED  (INCOMPLETE)
  RETAIN    -> (present, within retention)                    VERIFY_RECORD_PRESENT      (COMPLETE)

Run:  python code/evaluation/generalization_cases.py   (exit 0 all pass, nonzero on any fail)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence
from decide import build_steps
from loaders import load_rows

AT = "2026-09-15T12:00:00Z"

# Operations expected for each required_action. RETAIN produces no finding/remediation:
# a present, in-retention record is policy-compliant and only gets a presence check.
EXPECTED = {
    "DELETE":    ("INCOMPLETE", ["REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"]),
    "REDACT":    ("INCOMPLETE", ["REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"]),
    "ANONYMIZE": ("INCOMPLETE", ["REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED"]),
    "RETAIN":    ("COMPLETE", ["VERIFY_RECORD_PRESENT"]),
}
# The 5 categories with no evidence instantiation in the real dataset.
NEVER_IN_DATASET = {"CACHE_ENTRY", "MARKETING_PROFILE", "EMAIL_DELIVERY_LOG",
                    "SECONDARY_IDENTIFIER", "PRODUCT_TELEMETRY"}


def _synthetic(category):
    """A present, identifiable record of the given category, on a neutral system so the
    category path (not a backup/integration control short-circuit) is exercised."""
    rec = evidence._blank_record("synthetic_evidence", AT, "synthetic_1")
    rec["system_id"] = "generic_service"   # not backup_service / integration_service
    rec["category"] = category
    rec["email"] = "synthetic.user@example.invalid"
    rec["exists"] = True
    return rec


def main():
    rules = {r["data_category"]: r["required_action"] for r in load_rows("deletion_rules.csv")}
    failures = 0
    print(f"Generalization over {len(rules)} policy categories "
          f"({len(NEVER_IN_DATASET)} never instantiated by real evidence):")
    for category in sorted(rules):
        action = rules[category]
        want_status, want_ops = EXPECTED[action]
        rec = _synthetic(category)
        status, steps = build_steps({rec["resource_id"]: rec}, AT)
        ops = [s["operation"] for s in steps]
        ok = status == want_status and ops == want_ops
        failures += not ok
        tag = "PASS" if ok else "FAIL"
        note = " [synthetic-only]" if category in NEVER_IN_DATASET else ""
        print(f"  {tag}  {category:<22} {action:<9} -> {status} {ops}{note}")
        if not ok:
            print(f"        expected {want_status} {want_ops}")
    missing = NEVER_IN_DATASET - set(rules)
    if missing:
        failures += 1
        print(f"  FAIL  expected categories absent from deletion_rules.csv: {sorted(missing)}")
    total = len(rules)
    print(f"{total - failures}/{total} categories reachable with policy-correct operations")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
