"""Summarize LLM token usage from usage_log.jsonl into per-model and overall
totals (for usage_report.md). Run: python code/evaluation/usage.py"""
import json
from collections import defaultdict
from pathlib import Path

LOG = Path(__file__).resolve().parent / "usage_log.jsonl"
# USD per 1M tokens (paid-tier reference; $0 within the free-tier quota).
PRICE = {"gemini-2.5-flash": (0.30, 2.50), "gemini-2.0-flash": (0.10, 0.40)}


def summarize():
    if not LOG.exists():
        return {"calls": 0, "models": {}, "in": 0, "out": 0, "cost": 0.0}
    per = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "kinds": defaultdict(int)})
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        m = per[r["model"]]
        m["calls"] += 1
        m["in"] += r.get("in_tokens", 0)
        m["out"] += r.get("out_tokens", 0)
        m["kinds"][r.get("kind", "generic")] += 1
    total_in = sum(m["in"] for m in per.values())
    total_out = sum(m["out"] for m in per.values())
    cost = 0.0
    for model, m in per.items():
        pin, pout = PRICE.get(model, (0.0, 0.0))
        cost += m["in"] / 1e6 * pin + m["out"] / 1e6 * pout
    return {"calls": sum(m["calls"] for m in per.values()),
            "models": per, "in": total_in, "out": total_out, "cost": cost}


if __name__ == "__main__":
    s = summarize()
    print(f"calls={s['calls']} in={s['in']} out={s['out']} est_cost=${s['cost']:.4f}")
    for model, m in s["models"].items():
        print(f"  {model}: {m['calls']} calls, in={m['in']}, out={m['out']}, kinds={dict(m['kinds'])}")
