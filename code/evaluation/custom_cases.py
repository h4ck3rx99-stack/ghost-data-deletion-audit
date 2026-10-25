"""Three participant-authored evaluation cases (beyond the 32 samples).

Each exercises a distinct capability and asserts the expected behaviour against
the real dataset. Run:  python code/evaluation/custom_cases.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # import pipeline modules

from resolve import World
from decide import authorizes_deletion, build_steps


def _run(world, email, text, audit_at):
    if not authorizes_deletion(text):
        return "NOT_APPLICABLE", []
    user = world.idx.resolve(email)
    if user is None:
        return "INCOMPLETE", []
    return build_steps(world.discover(user, audit_at), audit_at)


def main():
    world = World()
    passed = 0

    # 1. Historical-email match: an OLD email (from user_audit_log) must resolve
    #    to the same user as the current email and discover the same resources.
    hist = "nadia.petrescu@yahoo.com"       # historical email of user_10 (nadia.ionescu)
    curr = "nadia.ionescu@yahoo.com"
    u_hist, u_curr = world.idx.resolve(hist), world.idx.resolve(curr)
    ok1 = u_hist is not None and u_hist == u_curr
    print(f"[1] historical-email match: {hist} -> {u_hist}, {curr} -> {u_curr}  "
          f"{'PASS' if ok1 else 'FAIL'}")
    passed += ok1

    # 2. NOT_APPLICABLE: a non-deletion request must yield NOT_APPLICABLE with [].
    status2, steps2 = _run(world, curr,
                           "Please correct the spelling of my name. Do not delete anything.",
                           "2026-09-15T12:00:00Z")
    ok2 = status2 == "NOT_APPLICABLE" and steps2 == []
    print(f"[2] non-deletion intent -> {status2} steps={len(steps2)}  {'PASS' if ok2 else 'FAIL'}")
    passed += ok2

    # 3. Tombstone + retention: a deleted account with a tombstone still exposing
    #    PII must be reported as INCOMPLETE with a tombstone REDACT and a retained
    #    security audit verified PRESENT.
    status3, steps3 = _run(world, "addo.kofi@gmail.com",   # user_542, tombstone_9178
                           "Please delete my account; keep only the internal reference.",
                           "2026-09-15T12:00:00Z")
    ops3 = {(s["system_id"], s["operation"]) for s in steps3}
    ok3 = (status3 == "INCOMPLETE"
           and ("identity_service", "REDACT_RECORD") in ops3
           and ("security_service", "VERIFY_RECORD_PRESENT") in ops3)
    print(f"[3] tombstone+retention -> {status3}, has tombstone REDACT & security PRESENT  "
          f"{'PASS' if ok3 else 'FAIL'}")
    passed += ok3

    print(f"\n{passed}/3 custom cases passed")
    return 0 if passed == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
