"""Policy/parser regressions. Run: python code/evaluation/policy_cases.py"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence
from decide import build_steps, classify

AT = "2026-09-15T12:00:00Z"


class PolicyCases(unittest.TestCase):
    def record(self, rid, category=None, **fields):
        return dict(evidence._blank_record("fixture", AT, rid), category=category, **fields)

    def test_unknown_controls_are_not_complete(self):
        # A discovered record whose control state cannot be resolved is INCOMPLETE.
        for records in ({"backup_1": self.record("backup_1")},
                        {"data_flow_1": self.record("data_flow_1")}):
            issues = []
            self.assertEqual(build_steps(records, AT, diagnostics=issues), ("INCOMPLETE", []))
            self.assertTrue(issues)

    def test_empty_discovery_is_complete(self):
        # Nothing discovered means nothing remains to report: COMPLETE, no steps.
        issues = []
        self.assertEqual(build_steps({}, AT, diagnostics=issues), ("COMPLETE", []))

    def test_result_tokens_in_json_logs_and_txt(self):
        for rid, token, key, value in [
            ("backup_1", "ACTIVE", "restore_allowed", True),
            ("backup_1", "BLOCKED", "restore_allowed", False),
            ("data_flow_1", "ACTIVE", "enabled", True),
            ("data_flow_1", "DISABLED", "enabled", False),
            ("account_1", "NOT_FOUND", "exists", False),
            ("account_1", "ABSENT", "exists", False),
            ("account_1", "DELETED", "exists", False),
            ("analytics_1", "IDENTIFIABLE", "identifiable", True),
        ]:
            with self.subTest(rid=rid, token=token), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "fixture"
                path.write_text(json.dumps({"resource_id": rid, "result": token}), encoding="utf-8")
                self.assertEqual(evidence._json_records(path, "fixture", AT)[0][key], value)
                path.write_text(f'resource_id={rid} result="{token}"', encoding="utf-8")
                self.assertEqual(evidence._log_records(path, "fixture", AT)[0][key], value)
                path.write_text(f'- {AT} | {evidence.system_for(rid)} | {rid} | UNKNOWN | {token} | user_1', encoding="utf-8")
                self.assertEqual(evidence._txt_records(path, "fixture", AT)[0][key], value)

    def test_conflicting_control_state_is_unresolved(self):
        rec = self.record("backup_1", restore_allowed=False)
        evidence._apply_state(rec, "ACTIVE")
        self.assertIsNone(rec["restore_allowed"])
        self.assertEqual(classify(rec, AT)[-1], "conflicting_state")
        for value in (None, "null", "unexpected"):
            self.assertIsNone(evidence._bool_flag(value))

    def test_category_overrides_system_without_deleting_shared_context(self):
        records = [
            self.record("support_1", "SECONDARY_IDENTIFIER", email="test@example.invalid"),
            self.record("support_2", "SUPPORT_MESSAGE", email="test@example.invalid"),
            self.record("support_3", "SUPPORT_ATTACHMENT"),
            self.record("analytics_1", "SECONDARY_IDENTIFIER", email_hash="abc"),
            self.record("analytics_2", "PRODUCT_TELEMETRY", email_hash="abc"),
        ]
        status, steps = build_steps({r["resource_id"]: r for r in records}, AT)
        self.assertEqual(status, "INCOMPLETE")
        self.assertEqual([(s["resource_id"], s["operation"]) for s in steps
                          if s["phase"] == "REMEDIATION"], [
            ("analytics_1", "DELETE_RECORD"), ("support_1", "DELETE_RECORD"),
            ("support_3", "DELETE_RECORD"), ("support_2", "REDACT_RECORD"),
            ("analytics_2", "ANONYMIZE_RECORD"),
        ])
        self.assertTrue(all(s["evidence_id"] == "" for s in steps if s["phase"] != "FINDING"))

    def test_tombstone_keeps_stable_reference_and_unknown_category_falls_back(self):
        rec = self.record("account_1", "ACCOUNT_TOMBSTONE", user_id="user_1")
        self.assertEqual(classify(rec, AT), (False, None, None, ("VERIFY_RECORD_REDACTED", "REDACTED"), None))
        rec["email"] = "test@example.invalid"
        self.assertEqual(classify(rec, AT)[2], ("REDACT_RECORD", "REDACTED"))
        rec["category"] = "UNKNOWN"
        self.assertEqual(classify(rec, AT)[2], ("DELETE_RECORD", "ABSENT"))
        rec["exists"] = False
        self.assertFalse(classify(rec, AT)[0])

    def test_controls_precede_record_treatment(self):
        backup = self.record("backup_1", "BACKUP_ARCHIVE", restore_allowed=True)
        flow = self.record("data_flow_1", "USER_PROFILE", enabled=True)
        contact = self.record("support_1", "SECONDARY_IDENTIFIER")
        _, steps = build_steps({r["resource_id"]: r for r in (backup, flow, contact)}, AT)
        self.assertEqual([s["operation"] for s in steps if s["phase"] == "REMEDIATION"],
                         ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD"])

    def test_absence_verification_requires_readback_since_request(self):
        for prefix in ("account", "search", "export"):
            with self.subTest(system=prefix):
                rec = self.record(prefix + "_1", exists=False)
                rec["captured_at"] = "2026-08-01T12:00:00Z"
                status, steps = build_steps({rec["resource_id"]: rec}, AT, "2026-09-01T12:00:00Z")
                self.assertEqual((status, steps), ("INCOMPLETE", []))
                _, steps = build_steps({rec["resource_id"]: rec}, AT, rec["captured_at"])
                self.assertEqual(steps[0]["operation"], "VERIFY_RECORD_ABSENT")
                self.assertEqual(steps[0]["evidence_id"], "fixture")
                rec["exists"] = True
                status, steps = build_steps({rec["resource_id"]: rec}, AT, "2026-09-01T12:00:00Z")
                self.assertEqual(status, "INCOMPLETE")
                self.assertEqual([s["operation"] for s in steps],
                                 ["REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"])
                self.assertEqual(steps[-1]["evidence_id"], "")

    def test_categories_survive_json_and_both_sql_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.json"
            path.write_text(json.dumps({"data_category": "SECONDARY_IDENTIFIER", "records": [
                {"resource_id": "support_1", "email": "test@example.invalid"},
            ]}), encoding="utf-8")
            self.assertEqual(evidence._json_records(path, "fixture", AT)[0]["category"],
                             "SECONDARY_IDENTIFIER")
            path = Path(tmp) / "records.sql"
            path.write_text("CREATE TABLE typed (resource_id TEXT, record_type TEXT);"
                            "INSERT INTO typed VALUES ('support_2', 'SUPPORT_ATTACHMENT');"
                            "CREATE TABLE replica (resource_id TEXT, record_json TEXT);"
                            "INSERT INTO replica VALUES ('analytics_1', "
                            "'{\"category\":\"SECONDARY_IDENTIFIER\"}');", encoding="utf-8")
            self.assertEqual([r["category"] for r in evidence._sql_records(path, "fixture", AT)],
                             ["SUPPORT_ATTACHMENT", "SECONDARY_IDENTIFIER"])

    def test_contact_trace_does_not_leak_to_other_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.log"
            path.write_text('trace_id=tr-1 event=contact_query_started lookup_key=test@example.invalid\n'
                            'trace_id=tr-2 event=message_read resource_id=support_2 record_type=SUPPORT_MESSAGE\n'
                            'trace_id=tr-1 event=contact_query_completed resource_id=support_1 rows=1\n'
                            'trace_id=tr-3 event=contact_lookup_completed resource_id=analytics_1 rows=1\n',
                            encoding="utf-8")
            records = evidence._log_records(path, "fixture", AT)
            self.assertEqual([r["category"] for r in records],
                             ["SUPPORT_MESSAGE", "SECONDARY_IDENTIFIER", "SECONDARY_IDENTIFIER"])
            self.assertEqual(records[1]["email"], "test@example.invalid")


if __name__ == "__main__":
    unittest.main()
