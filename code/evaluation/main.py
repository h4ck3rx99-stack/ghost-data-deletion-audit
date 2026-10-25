"""Scorer for Ghost Data Still Exists.

Compares a prediction CSV (default: repo-root output.csv) against the sample
gold (dataset/sample_output.csv) over the case_ids present in gold. Reports
case-status, sequence, step-level and field-level accuracy, split into the
tuning set (case_01..case_24) and the hold-out set (case_25..case_32), plus a
per-case diff for failures.

Run:  python code/evaluation/main.py [prediction_csv]
"""
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "dataset" / "sample_output.csv"
FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")
HOLDOUT_FROM = 25  # case_25..case_32 are the hold-out set


def _case_num(case_id):
    return int(case_id.split("_")[1])


def load_output(path):
    """case_id -> (status, [step-dicts]) from an output-format CSV."""
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            steps = json.loads(r["steps_json"]) if r["steps_json"].strip() else []
            rows[r["case_id"]] = (r["deletion_status"], steps)
    return rows


def _norm(step):
    """Canonical comparable tuple for one step."""
    return tuple(str(step.get(k, "")) for k in FIELDS)


def score(pred_path=None):
    pred_path = Path(pred_path) if pred_path else REPO / "output.csv"
    gold = load_output(GOLD)
    pred = load_output(pred_path) if pred_path.exists() else {}

    per_case = {}
    for case_id, (g_status, g_steps) in gold.items():
        p_status, p_steps = pred.get(case_id, (None, []))
        g_norm = [_norm(s) for s in g_steps]
        p_norm = [_norm(s) for s in p_steps]

        matched = sum(1 for i, g in enumerate(g_norm) if i < len(p_norm) and p_norm[i] == g)
        # field-level over aligned positions, length mismatch counts as misses
        fcorrect = ftotal = 0
        for i, g in enumerate(g_steps):
            ftotal += len(FIELDS)
            if i < len(p_steps):
                for k in FIELDS:
                    if str(p_steps[i].get(k, "")) == str(g.get(k, "")):
                        fcorrect += 1
        per_case[case_id] = {
            "status_ok": p_status == g_status,
            "seq_ok": p_norm == g_norm,
            "step_matched": matched,
            "step_gold": len(g_norm),
            "step_pred": len(p_norm),
            "field_correct": fcorrect,
            "field_total": ftotal,
            "p_status": p_status,
            "g_status": g_status,
        }
    return per_case


def _agg(per_case, case_ids):
    n = len(case_ids)
    if not n:
        return None
    status = sum(per_case[c]["status_ok"] for c in case_ids) / n
    seq = sum(per_case[c]["seq_ok"] for c in case_ids) / n
    sm = sum(per_case[c]["step_matched"] for c in case_ids)
    sg = sum(per_case[c]["step_gold"] for c in case_ids)
    sp = sum(per_case[c]["step_pred"] for c in case_ids)
    fc = sum(per_case[c]["field_correct"] for c in case_ids)
    ft = sum(per_case[c]["field_total"] for c in case_ids)
    recall = sm / sg if sg else 0.0
    precision = sm / sp if sp else 0.0
    return {
        "n": n, "status": status, "seq": seq,
        "step_recall": recall, "step_precision": precision,
        "field": fc / ft if ft else 0.0,
    }


def _print_block(name, a):
    if not a:
        print(f"  {name}: (no cases)")
        return
    print(f"  {name} (n={a['n']}): status={a['status']:.1%}  seq_exact={a['seq']:.1%}  "
          f"step_recall={a['step_recall']:.1%}  step_prec={a['step_precision']:.1%}  field={a['field']:.1%}")


def main():
    pred_path = sys.argv[1] if len(sys.argv) > 1 else None
    per_case = score(pred_path)
    ids = sorted(per_case, key=_case_num)
    tune = [c for c in ids if _case_num(c) < HOLDOUT_FROM]
    hold = [c for c in ids if _case_num(c) >= HOLDOUT_FROM]

    print(f"Scoring {pred_path or (REPO / 'output.csv')} vs {GOLD.name}")
    print("=" * 72)
    _print_block("ALL  ", _agg(per_case, ids))
    _print_block("TUNE ", _agg(per_case, tune))
    _print_block("HOLD ", _agg(per_case, hold))

    fails = [c for c in ids if not per_case[c]["seq_ok"]]
    if fails:
        print("-" * 72)
        print(f"Failures ({len(fails)}):")
        for c in fails:
            d = per_case[c]
            tag = "STATUS" if not d["status_ok"] else "steps"
            print(f"  {c}: {tag}  pred={d['p_status']} gold={d['g_status']}  "
                  f"steps {d['step_matched']}/{d['step_gold']} matched (pred {d['step_pred']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
