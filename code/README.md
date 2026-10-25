# Ghost Data Still Exists — Deletion Audit Agent

Audits whether a user's personal data was actually deleted. For each of the 518
requests in `dataset/deletion_requests.csv` it decides
`COMPLETE | INCOMPLETE | NOT_APPLICABLE` and emits an ordered
findings → remediation → verification plan, grounded in the supplied evidence at
each case's `audit_at`. Reported workflow statuses are treated as claims; state is
reconstructed from evidence.

## Setup

- Python 3.11+, `pypdf` (only extra dependency):
  ```
  pip install -r requirements.txt     # at repo root; just pypdf
  ```
- No API key is required for the deterministic core, which produces `output.csv`
  on its own. The optional LLM steps (multilingual intent fallback + image/
  scanned-PDF extraction) use a swappable backend, configured via a gitignored
  `.env` at the repo root:
  ```
  # Option A — OpenRouter (cloud, free vision models) — used for the submitted run:
  OPENROUTER_API_KEY=your_key_here
  # OPENROUTER_MODEL=google/gemma-4-31b-it:free          # primary (default)
  # OPENROUTER_FALLBACK=nvidia/nemotron-3.5-super-vl:free # fallback on 429 (default)

  # Option B — Gemini (cloud, free tier):
  # GEMINI_API_KEY=your_key_here
  # GEMINI_MODEL=gemini-flash-latest

  # Option C — local Ollama (free, no key); needs `ollama serve` + pulled models:
  # LLM_BACKEND=ollama
  # OLLAMA_MODEL=llama3.2                    # text (intent)
  # OLLAMA_VISION_MODEL=llama3.2-vision      # a capable vision model for extraction
  ```
  The vision extraction (`code/vision.py`) runs once and caches results as committed
  JSON under `code/vision_data/`, so `python code/main.py` needs no key or network.
  Extracted values are strictly validated against the dataset and anything that does
  not match is dropped. The backend fails safe — if a call errors, the pipeline
  falls back to the deterministic result. (A small local `llava:7b` was too weak;
  Gemini keys here were project-denied — OpenRouter's free vision models worked.)

## Run (one command)

```
python code/main.py
```

Run this from the repository root, with the challenge `dataset/` folder sitting
**beside** the `code/` folder (i.e. `./dataset/` and `./code/` are siblings). The
agent resolves all paths relative to that root, reads `dataset/`, writes
`output.csv` at the repo root (518 rows, sorted by `case_id`), and prints sanity
stats. No network or API key is needed — the vision results are read from the
committed cache in `code/vision_data/`.

Other commands:
```
python code/main.py --sample                              # -> code/evaluation/sample_pred.csv
python code/evaluation/main.py code/evaluation/sample_pred.csv   # score vs 32 samples (TUNE/HOLD)
python code/validate.py output.csv                        # schema / ordering / evidence-time checks
python code/evaluation/custom_cases.py                    # 3 participant-authored cases
python code/vision.py                                     # one-time image/PDF extraction (needs key)
```

## How it works

| Module | Role |
|---|---|
| `loaders.py` | Resolve request email → `user_id`; expand all current + historical identifiers. |
| `evidence.py` | Parse every evidence shape (JSON, SQLite SQL incl. primary/replica drift, 5 log dialects, handover TXT, legal-hold PDF) into uniform records; merge cached vision facts. |
| `resolve.py` | Global resource→user registry; per-case discovery; state from latest evidence ≤ `audit_at`. |
| `decide.py` | Multilingual intent classifier; per-resource state→operation mapping; decision + exact step ordering. |
| `llm.py` | Swappable, cached, token-logged Gemini backend (REST; swap to Ollama by implementing `generate`). |
| `vision.py` | Image + scanned-PDF fact extraction, cached to committed JSON (offline at run time). |
| `main.py` | Orchestrates and writes `output.csv`. |
| `evaluation/` | Scorer, custom cases, and the required reports. |

Determinism: the core uses no LLM. Gemini is used only for unclear intents and
media extraction, both cached to disk so reruns cost nothing. Secrets come from
`.env` only. All paths resolve relative to the repo root (Windows/macOS/Linux).

See `../HANDOFF.md` for status and the documented unkeyed-absent-account limitation.
