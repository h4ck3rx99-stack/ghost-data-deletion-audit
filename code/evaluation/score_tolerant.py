"""Tolerant scorer for Ghost Data Still Exists. Changes no output.

The position-exact scorer in main.py aligns steps by index, so one missing step
misaligns every later step and under-reports quality. This scorer is order-tolerant:

- set-based (multiset) precision / recall / F1 over step-tuples
  (phase, system_id, resource_id, operation, state, evidence_id) — step_no excluded, and
- an order-aware LCS score = LCS(pred, gold) / max(len(pred), len(gold)),

each reported for ALL / TUNE (case<25) / HOLD (case>=25).

Run:  python code/evaluation/score_tolerant.py [prediction_csv]   (default output.csv)
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "dataset" / "sample_output.csv"
FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")  # step_no excluded
HOLDOUT_FROM = 25


def _case_num(cid):
    return int(cid.split("_")[1])


def _load(path):
    """case_id -> ordered list of comparable step-tuples (step_no dropped)."""
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            steps = json.loads(r["steps_json"]) if r["steps_json"].strip() else []
            rows[r["case_id"]] = [tuple(str(s.get(k, "")) for k in FIELDS) for s in steps]
    return rows


def _lcs(a, b):
    """Length of the longest common subsequence of two step-tuple lists."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def score(pred_path=None):
    pred_path = Path(pred_path) if pred_path else REPO / "output.csv"
    gold = _load(GOLD)
    pred = _load(pred_path) if pred_path.exists() else {}
    per_case = {}
    for cid, g in gold.items():
        p = pred.get(cid, [])
        inter = sum((Counter(g) & Counter(p)).values())  # multiset overlap, order-free
        per_case[cid] = {"inter": inter, "gold": len(g), "pred": len(p),
                         "lcs": _lcs(p, g), "max": max(len(p), len(g))}
    return per_case


def _agg(per_case, case_ids):
    if not case_ids:
        return None
    inter = sum(per_case[c]["inter"] for c in case_ids)
    g = sum(per_case[c]["gold"] for c in case_ids)
    p = sum(per_case[c]["pred"] for c in case_ids)
    lcs = sum(per_case[c]["lcs"] for c in case_ids)
    mx = sum(per_case[c]["max"] for c in case_ids)
    prec = inter / p if p else 1.0
    rec = inter / g if g else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"n": len(case_ids), "set_prec": prec, "set_recall": rec, "f1": f1,
            "lcs_seq": lcs / mx if mx else 1.0}


def _print_block(name, a):
    if not a:
        print(f"  {name}: (no cases)")
        return
    print(f"  {name} (n={a['n']}): set_prec={a['set_prec']:.1%}  set_recall={a['set_recall']:.1%}  "
          f"F1={a['f1']:.1%}  lcs_seq={a['lcs_seq']:.1%}")


def main():
    pred_path = sys.argv[1] if len(sys.argv) > 1 else None
    per_case = score(pred_path)
    ids = sorted(per_case, key=_case_num)
    tune = [c for c in ids if _case_num(c) < HOLDOUT_FROM]
    hold = [c for c in ids if _case_num(c) >= HOLDOUT_FROM]

    print(f"Tolerant scoring {pred_path or (REPO / 'output.csv')} vs {GOLD.name}")
    print("=" * 72)
    _print_block("ALL  ", _agg(per_case, ids))
    _print_block("TUNE ", _agg(per_case, tune))
    _print_block("HOLD ", _agg(per_case, hold))
    return 0


if __name__ == "__main__":
    sys.exit(main())
