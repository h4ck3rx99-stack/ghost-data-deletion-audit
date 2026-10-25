# Submission Guide — Ghost Data Still Exists

Everything below is what to upload and how to assemble the two things only you can
produce (the code zip is already built and verified — see step 1).

**Submit at this exact URL:**
https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists

## Verified status (re-checked before this guide)
- Sample status **100%** (TUNE 100%, HOLD 100%); step recall 63.7%, precision 74.5%, field 74.7%, exact sequences 31.2%.
- Full run: 518 rows, COMPLETE 199 / INCOMPLETE 309 / NOT_APPLICABLE 10; `python code/validate.py output.csv` → VALID.
- `code.zip` was extracted into a clean folder with only `dataset/` beside it and, with **no `.env` and no network**, reproduced an `output.csv` **identical** to the committed one.

## The four submission items

### 1. `code.zip`  — ALREADY BUILT: `_dist/code.zip`
Contains the runnable `code/` tree, `code/README.md`, `requirements.txt`, `AGENTS.md`,
the `code/evaluation/` reports, and the committed `code/vision_data/` cache (so the
run is offline). It does **not** contain `dataset/`, `.env`, `__pycache__`, or the LLM
text cache (`code/.cache/`). The grader runs it from a root that has `dataset/` beside `code/`:
```
pip install -r requirements.txt
python code/main.py          # writes output.csv at that root
```
If you prefer to rebuild it yourself, from the repo root:
```bash
python - <<'PY'
import zipfile
from pathlib import Path
inc=[]
for p in Path('code').rglob('*'):
    if p.is_dir() or '__pycache__' in p.parts: continue
    r=p.as_posix()
    if r.startswith('code/.cache/'): continue   # LLM text cache; vision_data/ ships
    inc.append(p)
inc+=[Path(x) for x in ('requirements.txt','README.md','AGENTS.md') if Path(x).exists()]
with zipfile.ZipFile('code.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in inc: z.write(p, p.as_posix())
print('wrote code.zip', len(inc), 'files')
PY
```

### 2. `output.csv`  — at the repo root (already present)
518 rows, sorted by case_id. Upload the file as-is.

### 3. `chat_transcript`  — the agent trace ZIP
Per `agent_trace_instructions.md`, assemble `agent-trace.zip`:
1. Make a folder `agent-trace/` with a subfolder per tool: `agent-trace/claude-code/` and `agent-trace/codex/`.
2. **Claude Code:** copy this project's session files from
   `%USERPROFILE%\.claude\projects\C--hackerrank-orchestrate-october26\` (the `*.jsonl`
   session files) into `agent-trace/claude-code/`. Also run `/export` in each Claude
   Code session and save the readable export alongside them.
3. **Codex:** copy the challenge `rollout-*.jsonl` files from
   `%USERPROFILE%\.codex\sessions\<date>\` into `agent-trace/codex/`. Do **not** copy
   `auth.json`, `config.toml`, or credential stores.
4. Review for secrets (API keys/tokens), then zip the `agent-trace/` folder → `agent-trace.zip`.
   `log.txt` (repo root) is the per-turn conversation log and can be included too.

### 4. AI interview  — talking points
- **Architecture:** deterministic core (identity resolution → multi-shape evidence parsing → per-case resource discovery + state at `audit_at` → category→policy treatment → exact step ordering → validator), with a swappable, cached, token-logged vision backend used once offline.
- **Investigation:** reported statuses are treated as claims; state is reconstructed from the latest evidence ≤ `audit_at`; identity expanded with historical identifiers; replication drift reads as PRESENT.
- **Remediation planning:** category drives delete/redact/anonymize; data flows disabled and restores blocked before dependent records; retained (security/legal-hold) records preserved.
- **Evaluation:** TUNE/HOLD hold-out split, 3 custom cases, policy tests; the step-level ceiling is the born-anonymized `analytics_*`/deleted `account_*` records with no participant-visible owner link (shown unrecoverable three ways), so no overfit heuristic was added.

## Do NOT include in any upload
`dataset/`, `.env`, virtualenvs, `__pycache__`, `code/.cache/llm/`, API keys, or real
personal data.
