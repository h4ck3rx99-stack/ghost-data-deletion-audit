"""Ghost Data Still Exists — entry point.

Builds predictions for every request and writes repo-root output.csv.

    python code/main.py              # full run -> output.csv (+ sanity stats)
    python code/main.py --sample     # sample run -> code/evaluation/sample_pred.csv
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from loaders import REPO, load_rows
from resolve import World
from decide import authorizes_deletion, build_steps
import llm

STEP_FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")


def _case_num(cid):
    return int(cid.split("_")[1])


def process(rows, world, stats=None, backend=None, diagnostics=None):
    out = []
    worker_links = world.worker_orphan_links(rows)
    for r in rows:
        cid, audit_at = r["case_id"], r["audit_at"]
        if not authorizes_deletion(r["request_text"], backend):
            out.append((cid, "NOT_APPLICABLE", []))
            if stats is not None:
                stats["NOT_APPLICABLE"] += 1
            continue
        user = world.idx.resolve(r["email"])
        if user is None:
            out.append((cid, "INCOMPLETE", []))
            if diagnostics is not None:
                diagnostics.append({"case_id": cid, "resource_id": "", "reason": "unresolved_identity", "evidence_ids": []})
            if stats is not None:
                stats["unresolved"] += 1
            continue
        discovered = world.discover(user, audit_at)
        for rid, rec in worker_links.get(cid, {}).items():
            discovered.setdefault(rid, rec)
        if stats is not None and not discovered:
            stats["zero_resource"] += 1
        issues = []
        status, steps = build_steps(discovered, audit_at, r["requested_at"], issues)
        if diagnostics is not None:
            diagnostics.extend({"case_id": cid, **issue} for issue in issues)
        out.append((cid, status, steps))
        if stats is not None:
            for rec in discovered.values():
                stats["evtypes"][rec["file_id"]] += 1
    return out


def write_output(predictions, path):
    predictions = sorted(predictions, key=lambda p: _case_num(p[0]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for cid, status, steps in predictions:
            ordered = [{k: s[k] for k in STEP_FIELDS} for s in steps]
            w.writerow([cid, status, json.dumps(ordered, ensure_ascii=False)])


def main():
    sample = "--sample" in sys.argv
    world = World()
    backend = llm.get_backend()  # None unless GEMINI_API_KEY is set in .env
    stats = Counter()
    stats["evtypes"] = Counter()
    rows = load_rows("sample_deletion_requests.csv" if sample else "deletion_requests.csv")
    diagnostics = []
    preds = process(rows, world, stats, backend, diagnostics)

    if sample:
        out = REPO / "code" / "evaluation" / "sample_pred.csv"
    else:
        out = REPO / "output.csv"
    write_output(preds, out)
    out.with_suffix(".diagnostics.json").write_text(
        json.dumps(sorted(diagnostics, key=lambda d: (d["case_id"], d["resource_id"], d["reason"])),
                   indent=2) + "\n", encoding="utf-8")

    dist = Counter(p[1] for p in preds)
    print(f"Wrote {len(preds)} rows -> {out}")
    print(f"  status: {dict(dist)}")
    print(f"  NOT_APPLICABLE={stats['NOT_APPLICABLE']}  unresolved_email={stats['unresolved']}  "
          f"zero_resource={stats['zero_resource']}")
    print(f"  distinct evidence files used: {len(stats['evtypes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
