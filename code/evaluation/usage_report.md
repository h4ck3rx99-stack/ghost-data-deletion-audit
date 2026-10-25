# Token Usage & Cost Report — Ghost Data Still Exists

Covers the full-dataset run that produced the root `output.csv` (518 cases).

The latest policy-treatment rerun reused the committed vision cache: **0 new model
calls, 0 input/output tokens, and $0 incremental cost** (0 tokens and $0 per request).
The extraction totals below describe the existing model work used by that cache.

## Summary of the submitted run

| Metric | Value |
|---|---|
| Model providers | OpenRouter (vision only); deterministic core otherwise |
| Vision model | `nvidia/nemotron-3.5-super-vl:free` (fallback from `google/gemma-4-31b-it:free`) |
| Model-call count | 13 (one-time image/scanned-PDF extraction, then cached) |
| Input tokens | 25,062 |
| Output tokens | 25,969 |
| Total tokens | 51,031 |
| Avg tokens / request (over 518) | ~99 |
| Estimated total cost | **$0.00** (OpenRouter free tier) |
| Estimated cost / request | $0.00 |

The 13 model calls are the **one-time** media-extraction pass over the 11 image
and 2 scanned-PDF evidence files. Their results are cached as committed JSON under
`code/vision_data/`, so the per-case decision loop for all 518 cases makes **no**
model calls and reruns of `python code/main.py` cost nothing. The structured core
(CSV, JSON, SQLite SQL, logs, handover text, legal-hold PDF) uses no model at all.

## LLM backends (built, swappable, cached, token-logged)

The code supports five backends behind one `generate()` interface
(`llm.get_backend`): **OpenRouter** (`OPENROUTER_API_KEY`), **Groq** (`GROQ_API_KEY`),
**Ollama** (local, `LLM_BACKEND=ollama`), **Gemini** (`GEMINI_API_KEY`), and **None**
(deterministic). Every call appends `{provider, model, kind, in_tokens, out_tokens}`
to `code/evaluation/usage_log.jsonl`; summarize with `python code/evaluation/usage.py`.

Two jobs exist: **intent fallback** for request texts with no keyword signal (gated
off — see below), and **image/scanned-PDF extraction** (`vision.py`, cached to
committed JSON — used in the submitted run).

**Vision (used).** OpenRouter reads the 11 images + 2 scanned PDFs once. Primary
`google/gemma-4-31b-it:free` is rate-limited on the shared upstream pool, so the
backend falls back to `nvidia/nemotron-3.5-super-vl:free` (429 backoff, 3 tries per
model). Every extracted identifier/resource_id is validated against the dataset
(resource_id must be a real `system_activity` resource; identifiers must resolve to
a known user) and anything else is dropped — 10 of ~20 raw records survived. This
populated the known coverage gaps (marketing_, support attachment/object, and the
unkeyed account ghost-data) and changed 10 of 518 answers. See `evaluation_report.md`.

**Stronger-vision probe (attempted, no change).** A follow-up pass re-read the media
that extracts nothing — the two scanned PDFs (`evidence_18`, `evidence_58`, now
rasterized all-pages at 200 DPI via PyMuPDF and sent as one image) and the images
`evidence_42`/`evidence_46` — with `nvidia/nemotron-3.5-super-vl:free`. 4 model calls,
**11,799 input / 5,678 output tokens, $0** (free tier), logged to `usage_log.jsonl`. The
model read real identities (evidence_18 → user_18; evidence_58 → user_07 + a `support_001`
reference) but **every new record failed strict validation** — evidence_18 has no
resource_id, `support_001` is not a real `system_activity` resource, evidence_42/46
returned `[]`. 0 strictly-valid records were added, so `output.csv` is byte-identical and
the committed vision cache was kept (new cache discarded). The PDF-rasterization fix in
`vision.py` is retained so scanned PDFs are readable, but these artifacts carry no
groundable account-absence link. See `evaluation_report.md`.

**Intent (not used).** Measured on the 32 samples, the LLM fallback (Groq
`openai/gpt-oss-20b`) **lowered** case-status accuracy 96.9% → 90.6% by reading
deletion *audit* requests as non-deletion, and fired 0 times on the full 518. It is
gated behind `INTENT_LLM=1` and left off; the deterministic classifier is better.

Reference pricing (USD per 1M tokens, for when a paid tier is used): OpenRouter free
models $0; Groq `gpt-oss-20b` ~$0.10/$0.50; Gemini flash ~$0.30/$2.50; Ollama local
$0. Because extraction is cached and the per-case loop needs no model, steady-state
per-request cost is **$0.00**.
