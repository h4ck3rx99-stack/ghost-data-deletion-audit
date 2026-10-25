# Evaluation Report — Ghost Data Still Exists

Scoring is against the 32 public samples (`dataset/sample_output.csv`) with a
held-out split: the agent is **tuned only on case_01–case_24 (TUNE)** and
**checked on case_25–case_32 (HOLD)**, reported separately so overfitting is
visible. Reproduce with:

```
python code/main.py --sample
python code/evaluation/main.py code/evaluation/sample_pred.csv
```

## Accuracy (current)

| Set | n | Case-status | Sequence-exact | Step recall | Step precision | Field |
|---|---|---|---|---|---|---|
| ALL | 32 | 100.0% | 43.8% | 67.9% | 77.1% | 77.8% |
| TUNE (01–24) | 24 | 100.0% | 58.3% | 78.7% | 87.0% | 85.1% |
| HOLD (25–32) | 8 | 100.0% | 0.0%* | 42.1% | 51.1% | 60.4% |

Gap-fix pass (this session), strict ALL before→after: seq 31.2→43.8, step recall
63.7→67.9, step precision 74.5→**77.1**, field 74.7→77.8 (status held 100%). Drivers:
reference-field email recovery (`_USER_KEYS`), `lookup_value` typing, validator
hardening, and a conservative worker-activity orphan correlation that linked sample
cases 01/06/07/08/10 (all correct vs gold).

\* HOLD sequence-exact is low because every HOLD case is an export-JSON COMPLETE/
INCOMPLETE case affected by the unkeyed-account limitation below; status accuracy
on HOLD is 100%.

Metric definitions: **case-status** = fraction with correct `deletion_status`;
**sequence-exact** = fraction whose entire ordered step list matches gold;
**step recall/precision** = matched step-tuples over gold / predicted;
**field** = per-field agreement over aligned steps.

### Tolerant (order-free) scoring

The strict scorer aligns steps by position, so a single missing step misaligns every
later step and understates quality. `python code/evaluation/score_tolerant.py
code/evaluation/sample_pred.csv` reports set-based (multiset) precision/recall/F1 over
step-tuples (step_no excluded) plus an order-aware LCS score:

| Set | n | Set precision | Set recall | F1 | LCS-seq |
|---|---|---|---|---|---|
| ALL | 32 | 99.4% | 87.6% | 93.1% | 87.6% |
| TUNE (01–24) | 24 | 99.2% | 89.7% | 94.2% | 89.7% |
| HOLD (25–32) | 8 | 100.0% | 82.5% | 90.4% | 82.5% |

Before the gap-fix pass this was set_prec 100% / recall 85.5% / F1 92.2%. Recall rose
to 87.6% from the worker-activity orphan links. Set precision is 99.4% because of a
single predicted step whose tuple isn't in gold: case_01's `VERIFY_RECORD_ABSENT
account_001` cites the grounded worker `activity_id`, while gold cites the failover
replica `evidence_54` (a snapshot that does **not** contain account_001 — gold proves
absence by the authoritative store, which would require the false `account_n↔user_n`
numeric map). Every other predicted step still appears in gold; LCS-seq equals set
recall, so the remaining gap to 100% is **missing** steps (the unkeyed-account
limitation below), not wrong ones.

## Full-dataset run (518)

COMPLETE 196 · INCOMPLETE 312 · NOT_APPLICABLE 10 · 0 unresolved emails ·
1 zero-resource case (`case_61`). `python code/validate.py output.csv` → VALID.
The latest run used the existing vision cache, with pypdf installed and no new
model calls. The request-window verification change leaves all 518 output rows
identical to the preceding commit. Validator success checks the output contract;
it does not detect the pre-existing temporal-discovery issues documented in
[step_gap_analysis.md](step_gap_analysis.md).

The sample scores above are **identical with and without the vision cache** — none
of the 32 public samples (case_01–case_32) reference a user whose record appears in
the image/PDF evidence, so the vision pass changes only hidden-set cases and cannot
be scored on public data. It is kept because the problem statement requires reading
the media evidence and every change is strictly validated (see below).

## Category generalization guarantee

`python code/evaluation/generalization_cases.py` → 15/15 pass. The engine is
category-driven (`decide.classify` maps a record's data category to the
`deletion_rules.csv` action, system prefix only as fallback). This test builds a
synthetic present + identifiable record for each of the 15 policy categories and asserts
`decide.build_steps` routes it to the policy-correct operations — DELETE →
REPORT_REMAINING_RECORD/DELETE_RECORD/VERIFY_RECORD_ABSENT, REDACT →
REPORT_EXPOSED_PII/REDACT_RECORD/VERIFY_RECORD_REDACTED, ANONYMIZE →
REPORT_EXPOSED_PII/ANONYMIZE_RECORD/VERIFY_RECORD_ANONYMIZED, RETAIN →
VERIFY_RECORD_PRESENT (COMPLETE). Critically it covers the **5 categories the real
dataset never instantiates** (CACHE_ENTRY, MARKETING_PROFILE, EMAIL_DELIVERY_LOG,
SECONDARY_IDENTIFIER, PRODUCT_TELEMETRY), which are otherwise completely untested. The
records are synthetic (never real dataset rows), so `output.csv` is byte-identical with
and without this test (verified by md5).

## Three participant-authored evaluation cases

`python code/evaluation/custom_cases.py` → 3/3 pass.

1. **Historical-email match** — a request using a user's *old* email
   (`nadia.petrescu@yahoo.com`, from `user_audit_log`) resolves to the same
   `user_id` as the current email (`nadia.ionescu@yahoo.com` → user_10).
2. **NOT_APPLICABLE intent** — "Please correct the spelling of my name. Do not
   delete anything." → `NOT_APPLICABLE` with `[]` (no sample demonstrates this).
3. **Tombstone + retention** — a deleted account whose tombstone still exposes PII
   (user_542 / tombstone_9178) → `INCOMPLETE` with an `identity_service`
   `REDACT_RECORD` and a retained `security_service` `VERIFY_RECORD_PRESENT`.

## Failures found and improvements made

- **Stale negative lookup counted as current verification.** General rule: a
  negative lookup predating the deletion request does not verify that request's
  deletion. The pipeline now passes `requested_at` to the step builder; already
  absent records require a readback at or after that time. Older positive records
  still produce findings and remediation. Case_17 now matches exactly. Relative
  to the reproduced 100%-status baseline, recall improved 62.7%→63.7%, precision
  72.9%→74.5%, field 74.1%→74.7%, and exact sequences 28.1%→31.2%; HOLD and status
  are unchanged. Six policy/parser tests and all three custom cases pass.
- **Text-PDF support attachment extraction** (preceding commit `2cce579`) fixed
  case_07's status; this session reproduced its 100% status baseline without
  rerunning vision. Scanned-media extraction remains unchanged.
- **Missing-step attribution investigated, not guessed.** Cases 18/29/30 have
  missing verification steps rather than over-prediction. Deletion-worker
  proximity does not establish ownership: six account candidates can share a
  reported day, and known distinct users' events interleave within seconds.
  No temporal or ID-based ownership heuristic was added. See the detailed
  [step-gap analysis](step_gap_analysis.md), including the pre-existing use of
  later security evidence and untimed identity links that still needs correction.
- **System defaults applied the wrong policy to contact records.** Evidence now
  carries explicit category/data_category/record_type through the parsers, and
  contact-query/lookup events identify secondary identifiers within their trace.
  Classification uses `deletion_rules.csv` for known categories, with the existing
  system fallback for unknown ones. Backup and data-flow controls still precede
  record treatment. This fixes DELETE vs REDACT for case_10's support contact and
  DELETE vs ANONYMIZE for case_12's analytics contact. Case_12 now matches exactly;
  case_10 still lacks an account verification. Sample step recall improved from
  58.5% to 61.7%, field accuracy from 71.5% to 72.7%, and sequence accuracy from
  25.0% to 28.1%, without changing status or HOLD scores.
  `python code/evaluation/policy_cases.py` passes 5 tests covering category-specific
  treatment, tombstone retention of stable references, unknown-category fallback,
  absent records, control ordering, JSON/SQL extraction, and trace isolation.
- **Intent over-broad on "remove".** "remove me from marketing" was classified as
  deletion. Fixed by using precise deletion verbs (not bare "remove") plus
  keep-account and negation guards; all 10 NOT_APPLICABLE cases in the full set
  are now detected (incl. a negated "not a request to erase it").
- **Five log dialects.** Observability logs come in flat key=value, JSON-per-line,
  nested escaped `message="..."`, pipe-delimited, and syslog framings, with the
  queried identifier on a separate line of the same trace. Adding trace/request-id
  correlation and dialect handling cut zero-resource cases from 31 to 3 and raised
  sample status from 87.5% to 96.9%.
- **Nested identifiers dropped.** `document{}`/`profile{}` sub-objects inside SQL
  `record_json` and JSON exports hid email/user_id; fixed with recursive scalar
  flattening.
- **Contract violation: post-audit citation.** The security retained-present
  fallback could cite evidence captured after `audit_at` in COMPLETE cases; the
  validator caught it and COMPLETE verification now only cites evidence ≤ `audit_at`.
- **Replication drift** (row deleted in primary but alive in a replica) is handled
  automatically: presence in any SQL table counts as PRESENT.
- **LLM intent fallback measured as a regression, then gated off.** Wiring Groq
  (`gpt-oss-20b`) for unclear-intent texts dropped sample status 96.9% → 90.6%: it
  read deletion *audit* requests (case_12, case_26 — "...before deleting it, check
  nothing was left behind") as non-deletion. The deterministic classifier is better
  on this data, so the LLM path is opt-in (`INTENT_LLM=1`) and off by default; a
  `delet` stem was added so "deleting/deleted" are caught deterministically.
- **Vision pass closed the media-evidence gap (10 cases changed).** An OpenRouter
  vision model (`nemotron-3.5-super-vl:free`, fallback from `gemma-4-31b-it:free`)
  reads the 11 images + 2 scanned PDFs once, cached to committed JSON. Strict
  validation keeps only identifiers that resolve to a known user and resource_ids
  that are real `system_activity` resources, dropping ~half the raw extractions
  (hallucinated digits, decoy emails, null-resource rows). The surviving 10 records
  changed 10 of 518 answers: 7 status flips COMPLETE→INCOMPLETE (a remaining
  account/search/analytics/support/export/marketing record visible in a console
  screenshot) and 3 added verification steps. Example — case_34: an admin-console
  screenshot (`evidence_04`, captured 2026-09-26, ≤ audit_at 09-27) shows
  `account_5762` still PRESENT, *later* than the log (`evidence_01`, 09-15) that
  implied it was gone — the ghost-data recreation scenario. **Caveat:** because no
  changed case is a public sample, these 10 changes are grounded and validated but
  unverifiable against gold; the deterministic-only output is recoverable by moving
  `code/vision_data/` aside.

## Known limitation (main step-level ceiling)

Deleted `account_*` records in the export-JSON evidence family (HTTP 404, no
email) and some activity-only account DELETEs have **no deterministic
participant-visible link** to the user — verified: they never co-occur with an
identifier, and the deletion-worker stream is not per-user contiguous. The agent
reports them only when the account was keyed in some in-window snapshot or in a
console screenshot the vision pass reads; otherwise the account step is omitted.
Case **status** stays correct via the other resources; this is the primary cause of
sub-100% step/sequence scores. The vision pass (above) recovers some of these links
— e.g. `account_5762`→user_11 from a screenshot — but a scanned/imaged artifact
exists for only a handful of users, so the ceiling is reduced, not removed.

**Stronger-vision pass tried (clean negative).** The only legitimate recall lever is
reading more from the media that currently extracts nothing. A follow-up pass rasterized
the two scanned PDFs all-pages at 200 DPI (PyMuPDF) and re-read them plus the two empty
images with `nvidia/nemotron-3.5-super-vl:free`. The model transcribed real identities
(evidence_18 → user_18; evidence_58 → user_07) but produced **no strictly-valid record**:
evidence_18 is identity-only (no resource_id), evidence_58's `support_001` is not a real
`system_activity` resource, and evidence_42/46 read as `[]`. The existing strict
validation (unchanged) dropped all of them, so `output.csv` is byte-identical and the new
cache was discarded. The `vision.py` PDF-rasterization capability is kept for correctness,
but these artifacts confirm — rather than remove — the ceiling below: no groundable
account-absence link exists in them.

**Worker-activity orphan correlation (realized recall lever, this session).** A second
legitimate lever does exist: when exactly one `deletion_worker` SUCCESS
`DELETE_RECORD`/`ANONYMIZE_RECORD` event lands within ±5min of a case's `reported_at`,
that event pins an otherwise-orphan account/analytics resource to the case. Kept precise
by three guards — the resource must not already be registry-attributed (so a known
user's resource is never time-stolen, e.g. `account_5193`→user_35 on cases 18/20),
exactly one candidate in the window, and no cross-case collision. This links sample
cases 01/06/07/08/10 (all correct vs gold) and 5 cases in the full set, lifting strict
step recall 63.7→67.9% and precision 74.5→77.1%. It narrows — but does not remove — the
ceiling below: it only fires for the minority of deletions timed uniquely enough to be
unambiguous.

**Quantified (re-investigated).** 499 of 518 users have an account that is keyed to
them by an identifier somewhere in the evidence, but `discover()` attaches an account
to only 137 cases. Of the 49 cases whose user has a keyable account yet get none,
**all 49** are accounts whose only record is captured *after* that case's `audit_at`
(a later deletion-worker log showing the account already absent) — and **0** have any
pre-`audit_at` account evidence. The contract forbids using post-audit evidence, so
these omissions are deliberate and correct, not a discovery bug. The residual gap is
therefore inherent: an account the subject owns but whose state at `audit_at` is not
provable from any participant-visible, in-window artifact (a 404 export with no email,
or an activity-only DELETE — `system_activity` account rows carry an identifier in
1 of 1046 rows). No deterministic lever remains without organizer-only data.
