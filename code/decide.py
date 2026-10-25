"""Decision + ordered step building for Ghost Data Still Exists.

Turns a case's discovered resources (from resolve.World) into a deletion_status
and an ordered steps list. Deterministic; the request-text intent check is a
multilingual keyword pass (LLM fallback is wired later).
"""

from loaders import load_rows

# ---- intent: does request_text authorize deletion? --------------------------
# Precise deletion verbs (multilingual). "remove" alone is excluded because it
# also appears in "remove me from marketing".
_DELETE_VERB = (
    "delet", "erase", "erasure", "wipe",  # "delet" stem covers delete/deleting/deleted/deletion
    "close my account", "close the account", "account closure", "account-deletion",
    "remove my account", "remove the account", "remove my profile", "remove my personal",
    "remove my name", "remove my data", "remove records", "removal of my",
    "eliminaci", "eliminar", "supresi", "suprimir", "borrar",      # es
    "exclus", "excluir", "apagar", "remover a conta",              # pt
    "supprim", "effacer", "suppression",                           # fr
    "löschen", "löschung", "entfernen sie mein",                   # de
    "削除", "消去", "抹消",                                          # ja
    "삭제", "지워",                                                  # ko
)
# Explicit "keep the account / non-deletion action" signals.
_KEEP_SIGNAL = (
    "do not close", "don't close", "do not delete", "don't delete",
    "keep the account", "keep my account", "leave my profile", "leave my account",
    "leave my purchase", "without removing", "continue using the service",
    "i still use it", "still need the account", "i still want", "still want receipts",
    # negated deletion -> non-deletion
    "not a request to erase", "not a request to delete", "not a deletion request",
    "not asking to delete", "not asking you to delete", "rather than delete",
    "rather than deleting", "instead of deleting", "do not want to delete", "not to delete",
)
_NONDELETE_ACTION = (
    "promotional emails", "marketing lists", "unsubscribe", "opt out", "opt-out",
    "download my account", "portable format", "information request",
    "what personal information you hold", "send me a copy", "copy of the information",
    "copy of last year", "resetting the login", "reset the login",
    "change the email address", "correct it", "misspelled", "out of date",
    "replace it with", "a copy of the information",
)


def authorizes_deletion(text, backend=None):
    t = (text or "").lower()
    if any(k in t for k in _KEEP_SIGNAL):
        return False
    has_delete = any(k in t for k in _DELETE_VERB)
    has_nondelete = any(k in t for k in _NONDELETE_ACTION)
    if has_nondelete and not has_delete:
        return False
    if has_delete:
        return True
    # Genuinely unclear text. On this dataset the deterministic default (deletion,
    # given the workflow context) beats an LLM second-guess, so the LLM fallback is
    # opt-in via INTENT_LLM=1. Enable it only where an LLM is known to help.
    import os
    if backend is not None and not has_nondelete and os.environ.get("INTENT_LLM") == "1":
        import llm
        return llm.is_deletion_request(text, backend)
    return True  # default: deletion workflow context


# ---- per-resource classification -------------------------------------------
_DELETE_SYS = {"account_service", "search_service", "export_service",
               "cache_service", "marketing_platform"}
_REDACT_SYS = {"support_platform", "email_delivery_service", "identity_service"}
_POLICY_ACTIONS = {r["data_category"]: r["required_action"]
                   for r in load_rows("deletion_rules.csv")}


def _identifiable(rec):
    return bool(rec["email"] or rec["phone"] or rec["email_hash"] or rec["name"])


def _is_attachment(rec):
    return rec.get("category") == "SUPPORT_ATTACHMENT" or rec["resource_id"].startswith("object_")


def _retained(rec, audit_at):
    ru = rec.get("retention_until")
    if ru and len(ru) >= 10 and ru[4] == "-":  # ISO date -> compare directly
        return ru >= audit_at
    return True  # no/opaque period -> assume still within retention


def classify(rec, audit_at):
    """Return (is_violation, find, remediate, verify) where each of the last
    three is (operation, state) or None."""
    sys = rec["system_id"]
    if rec.get("state_conflict"):
        return False, None, None, None, "conflicting_state"
    if sys in ("backup_service", "integration_service"):
        flag = "restore_allowed" if sys == "backup_service" else "enabled"
        if rec[flag] is None:
            return False, None, None, None, "unknown_" + flag
    if sys == "backup_service":
        if rec["restore_allowed"]:
            return True, ("REPORT_RESTORE_RISK", "ACTIVE"), ("BLOCK_RESTORE", "BLOCKED"), ("VERIFY_RESTORE_BLOCKED", "BLOCKED"), None
        return False, None, None, ("VERIFY_RESTORE_BLOCKED", "BLOCKED"), None
    if sys == "integration_service":
        if rec["enabled"]:
            return True, ("REPORT_ACTIVE_DATA_FLOW", "ACTIVE"), ("DISABLE_DATA_FLOW", "DISABLED"), ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"), None
        return False, None, None, ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"), None
    action = _POLICY_ACTIONS.get(rec.get("category"))
    # shortcut: uncategorized records keep system defaults until evidence identifies their type.
    if action is None:
        if _is_attachment(rec) or sys in _DELETE_SYS:
            action = "DELETE"
        elif sys in _REDACT_SYS:
            action = "REDACT"
        elif sys == "analytics_platform":
            action = "ANONYMIZE"
        elif sys == "security_service":
            action = "RETAIN"
    if action == "RETAIN":
        if _retained(rec, audit_at):
            return False, None, None, ("VERIFY_RECORD_PRESENT", "PRESENT"), None
        return False, None, None, None, None  # expired -> nothing to retain
    if action == "DELETE":
        if rec["exists"]:
            return True, ("REPORT_REMAINING_RECORD", "PRESENT"), ("DELETE_RECORD", "ABSENT"), ("VERIFY_RECORD_ABSENT", "ABSENT"), None
        return False, None, None, ("VERIFY_RECORD_ABSENT", "ABSENT"), None
    if action in ("REDACT", "ANONYMIZE"):
        state = "REDACTED" if action == "REDACT" else "ANONYMIZED"
        verify = ("VERIFY_RECORD_" + state, state)
        if _identifiable(rec):
            return True, ("REPORT_EXPOSED_PII", "PRESENT"), (action + "_RECORD", state), verify, None
        return False, None, None, verify, None
    return False, None, None, None, None


# ---- ordering ---------------------------------------------------------------
_FIND_OPS = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII",
             "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"]
_REM_OPS = ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD",
            "REDACT_RECORD", "ANONYMIZE_RECORD"]
_VER_OPS = ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
            "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]


def _step(phase, sysid, rid, op, state, ev):
    return {"step_no": 0, "phase": phase, "system_id": sysid,
            "resource_id": rid, "operation": op, "state": state, "evidence_id": ev}


def build_steps(discovered, audit_at, requested_at=None, diagnostics=None):
    """discovered: resource_id -> evidence record. Returns (status, steps)."""
    findings, remediations, verifications = [], [], []
    unresolved = []
    for rid, rec in discovered.items():
        sysid = rec["system_id"]
        is_v, find, rem, ver, reason = classify(rec, audit_at)
        if reason:
            unresolved.append({"resource_id": rid, "reason": reason, "evidence_ids": [rec["file_id"]]})
        # A negative lookup before the request does not verify this deletion.
        if (ver == ("VERIFY_RECORD_ABSENT", "ABSENT") and not rec["exists"]
                and requested_at and rec["captured_at"] < requested_at):
            ver = None
        if find:
            findings.append(_step("FINDING", sysid, rid, find[0], find[1], rec["file_id"]))
        if is_v and rem:
            remediations.append(_step("REMEDIATION", sysid, rid, rem[0], rem[1], ""))
        if ver:
            verifications.append(_step("VERIFICATION", sysid, rid, ver[0], ver[1], ""))

    incomplete = bool(findings or unresolved)
    if not incomplete:
        # COMPLETE: each verification cites evidence proving the state at audit_at;
        # a record provable only by later evidence cannot be cited, so it is dropped.
        kept = []
        for v in verifications:
            rec = discovered[v["resource_id"]]
            if rec["captured_at"] <= audit_at:
                v["evidence_id"] = rec["file_id"]
                kept.append(v)
        verifications = kept

    def order(steps, ops):
        steps.sort(key=lambda s: (ops.index(s["operation"]), s["system_id"], s["resource_id"]))

    order(findings, _FIND_OPS)
    order(remediations, _REM_OPS)
    order(verifications, _VER_OPS)
    steps = (findings + remediations + verifications) if incomplete else verifications
    for i, s in enumerate(steps, 1):
        s["step_no"] = i
    # A discovered record that yields no finding and no usable proof is unresolved
    # (INCOMPLETE). But an empty discovery means nothing was found to remain, so it
    # stays COMPLETE rather than becoming a contract-invalid INCOMPLETE with no steps.
    if discovered and not findings and not verifications:
        unresolved.append({"resource_id": "", "reason": "no_verifiable_state", "evidence_ids": []})
    if diagnostics is not None:
        diagnostics.extend(unresolved)
    status = "INCOMPLETE" if incomplete or unresolved else "COMPLETE"
    return status, steps
