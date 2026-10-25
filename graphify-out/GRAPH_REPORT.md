# Graph Report - hackerrank-orchestrate-october26  (2026-10-25)

## Corpus Check
- 30 files · ~27,486 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 2, .csv 2, .jsonl 1)

## Summary
- 288 nodes · 512 edges · 14 communities (12 shown, 2 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `177437f9`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- evidence.py
- vision.py
- AGENTS.md
- Ghost Data Still Exists
- llm.py
- Agent Trace Instructions
- The four submission items
- code/main.py
- score_tolerant.py
- json
- HANDOFF — Ghost Data Still Exists
- Ghost Data Still Exists — Deletion Audit Agent
- CLAUDE.md
- .claude/CLAUDE.md

## God Nodes (most connected - your core abstractions)
1. `build_steps()` - 19 edges
2. `PolicyCases` - 12 edges
3. `load_rows()` - 12 edges
4. `Identity` - 12 edges
5. `World` - 12 edges
6. `classify()` - 11 edges
7. `_log_records()` - 11 edges
8. `norm_email()` - 11 edges
9. `load_vision_records()` - 11 edges
10. `6. Project Contract` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Next steps` --references--> `build_steps()`  [INFERRED]
  HANDOFF.md → code/decide.py
- `Completed: per-record policy treatment` --references--> `classify()`  [INFERRED]
  HANDOFF.md → code/decide.py
- `Current scores (VERIFIED this run)` --references--> `World`  [INFERRED]
  HANDOFF.md → code/resolve.py
- `What vision does now` --references--> `_media_bytes()`  [INFERRED]
  HANDOFF.md → code/vision.py
- `What vision does now` --references--> `load_vision_records()`  [INFERRED]
  HANDOFF.md → code/vision.py

## Import Cycles
- None detected.

## Communities (14 total, 2 thin omitted)

### Community 0 - "evidence.py"
Cohesion: 0.12
Nodes (20): _apply_field(), _apply_state(), _blank_record(), _bool_flag(), _flatten_scalars(), _is_user_ref(), _json_records(), walk() (+12 more)

### Community 1 - "vision.py"
Cohesion: 0.14
Nodes (8): Identity, _dataset_resource_ids(), extract_all(), load_vision_records(), _media_bytes(), _parse(), _targets(), What vision does now

### Community 2 - "AGENTS.md"
Cohesion: 0.07
Nodes (26): 0. TLDR For The Agent, 1. What This Repo Is, 2. Log File — Location And Lifecycle, 3. Session Start, 4.1 Challenge And Submission Link, 4. Challenge Rules, 5.1 Session Start Entry, 5.2 Per-Turn Entry (+18 more)

### Community 3 - "Ghost Data Still Exists"
Cohesion: 0.10
Nodes (18): Allowed Operations, Evaluation, Files Provided, Ghost Data Still Exists, Input, Required Output, Rules, Submission (+10 more)

### Community 4 - "llm.py"
Cohesion: 0.07
Nodes (10): LLM backends (built, swappable, cached, token-logged), Summary of the submitted run, Token Usage & Cost Report — Ghost Data Still Exists, GeminiBackend, get_backend(), GroqBackend, load_env(), _log_usage() (+2 more)

### Community 5 - "Agent Trace Instructions"
Cohesion: 0.14
Nodes (13): Agent Trace Instructions, Before you start, Claude Code, Create the ZIP, Export a readable transcript, Google Antigravity, macOS or Linux, OpenAI Codex (+5 more)

### Community 6 - "The four submission items"
Cohesion: 0.22
Nodes (8): 1. `code.zip`  — ALREADY BUILT: `_dist/code.zip`, 2. `output.csv`  — at the repo root (already present), 3. `chat_transcript`  — the agent trace ZIP, 4. AI interview  — talking points, Do NOT include in any upload, Submission Guide — Ghost Data Still Exists, The four submission items, Verified status (re-checked before this guide)

### Community 7 - "code/main.py"
Cohesion: 0.12
Nodes (11): authorizes_deletion(), build_steps(), classify(), _identifiable(), _is_attachment(), _retained(), _step(), main() (+3 more)

### Community 8 - "score_tolerant.py"
Cohesion: 0.29
Nodes (7): _agg(), _case_num(), _lcs(), _load(), main(), _print_block(), score()

### Community 9 - "json"
Cohesion: 0.11
Nodes (17): main(), _synthetic(), _agg(), _case_num(), load_output(), main(), _norm(), _print_block() (+9 more)

### Community 10 - "HANDOFF — Ghost Data Still Exists"
Cohesion: 0.07
Nodes (23): Accuracy (current), Category generalization guarantee, Evaluation Report — Ghost Data Still Exists, Failures found and improvements made, Full-dataset run (518), Known limitation (main step-level ceiling), Three participant-authored evaluation cases, Tolerant (order-free) scoring (+15 more)

### Community 11 - "Ghost Data Still Exists — Deletion Audit Agent"
Cohesion: 0.40
Nodes (4): Ghost Data Still Exists — Deletion Audit Agent, How it works, Run (one command), Setup

## Knowledge Gaps
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_steps()` connect `code/main.py` to `json`, `HANDOFF — Ghost Data Still Exists`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `build_steps()` (e.g. with `Category generalization guarantee` and `Next steps`) actually correct?**
  _`build_steps()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `evidence.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11948790896159317 - nodes in this community are weakly interconnected._
- **Why does `HANDOFF — Ghost Data Still Exists` connect `HANDOFF — Ghost Data Still Exists` to `vision.py`, `code/main.py`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Should `vision.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14210526315789473 - nodes in this community are weakly interconnected._
- **Why does `World` connect `HANDOFF — Ghost Data Still Exists` to `evidence.py`, `json`, `vision.py`, `code/main.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Should `AGENTS.md` be split into smaller, more focused modules?**
  _Cohesion score 0.07407407407407407 - nodes in this community are weakly interconnected._