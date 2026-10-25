# Step-gap investigation

All investigation used participant-facing `dataset/` files. Public sample answers
were used only for evaluation; prediction code does not read them. Vision extraction
was not run and its committed cache was not changed.

## Baseline and retained fix

| Metric | Before | After |
|---|---:|---:|
| Sample status | 100.0% | 100.0% |
| Exact sequence | 28.1% | 31.2% |
| Step recall | 62.7% | 63.7% |
| Step precision | 72.9% | 74.5% |
| Field accuracy | 74.1% | 74.7% |

TUNE: status 100%, sequence 41.7%, recall 72.8%, precision 83.9%, field 80.7%.
HOLD is unchanged: status 100%, sequence 0%, recall 42.1%, precision 51.1%, field 60.4%.
The regenerated 518-case output is unchanged and passes the contract validator.
Three custom cases and six policy/parser tests pass.

**General rule:** a negative lookup from before the deletion request does not
verify that request's deletion, so require a readback on or after `requested_at`
before emitting an already-absent record's verification.

The rule uses request/evidence timestamps, not case IDs, user IDs, resource IDs,
sample labels, or an arbitrary age threshold. Older positive records still yield
findings, remediation, and future verification. A readback exactly at the request
time qualifies. Regression tests exercise account, search, and export records.
This filter does not by itself establish completeness when all evidence is stale;
the pipeline's existing empty-COMPLETE behavior remains a limitation.

## Item 2: extra versus missing steps

| Sample | Actual difference | Evidence and outcome |
|---|---|---|
| case_17 | One extra verification | `account_6523` is absent in `evidence_67`, captured March 10; the request is August 19. The request-window rule removes this stale check; the sequence now matches. |
| case_18 | Two missing verifications | Missing `account_5521` and `audit_record_6645`; findings and remediation already match. |
| case_29 | One missing verification | Missing `account_7012`; all eight finding/remediation steps match. |
| case_30 | One missing verification | Missing `account_4163`; all eight finding/remediation steps match. |

Only one sample-discovered absent record predates its request; none of the 518
evaluation requests has such a record. Accordingly the fix changes one sample
sequence and no full-dataset row. No extra records were removed from cases 18,
29, or 30 to manufacture an improvement.

## Item 1: temporal linkage rejected

`system_activity.csv` has eight columns: activity ID, event time/type, source and
target system, resource ID, reported result, and details. Its 1,466 deletion-worker
rows have no user identifier, request ID, batch ID, trace ID, or correlation key in
their details. The 12 explicit `LINK_RESOURCE_IDENTITY` rows do not link the missing
account/anonymized-profile targets examined here.

Concrete ambiguities, using both request CSVs and only in-window evidence to
identify known users:

- September 5: six requests are reported that day and six account-worker events
  occur. `account_7015` and the expected `account_6440` occur one second apart
  (`activity_3660`/`activity_3661`); no subject-keyed worker event that day anchors
  the case_21 subject.
- September 2: six requests and six account-worker candidates; case_25's subject
  likewise has no keyed worker event that day. `account_3136` cannot be uniquely
  selected from the other candidates by a shared identifier.
- August 30: case_28's keyed support/flow/backup events occur well after multiple
  account candidates. `support_2351` (user_28, `activity_3535`) and `support_4707`
  (user_27, `activity_3536`) occur just 15 seconds apart. Nearby events are not a
  subject boundary. Across known-user worker events bounded at September 15 noon,
  ten successive known-user pairs within 60 seconds belong to different users.
- Several COMPLETE targets, including `account_6440`, `account_3136`,
  `analytics_5335`, and `analytics_1895`, have identifier-free state records but no
  registry link. Other expected account IDs, such as `account_001`, `account_002`,
  and `account_004`, have no parsed record at all; their cited SQL snapshot does
  not supply an identifier-to-resource link for those IDs.

**Decision:** do not add nearest-time, same-day, worker-order, or numbered-ID
linking. A shared request/batch token, explicit identity link, or additional
in-window business evidence is needed. A workflow SUCCESS/DELETE claim is also
insufficient to prove resulting absence. No prediction change was made for item 1.

## Remaining cutoff and coverage limitations

- The existing resolver's security fallback can include a record captured after
  `audit_at` in an INCOMPLETE plan. For example cases 29/30 currently obtain their
  security resource from `evidence_02` (September 17), after their September 15
  cutoff. The empty future-verification citation makes this invisible to the
  current citation-only validator; it does not make the discovery time-valid.
- The global registry also records identifier links without retaining their
  timestamps. Filtering only the chosen state snapshot does not fully prevent
  future identity information from affecting discovery.
- Neither pre-existing behavior was extended to recover missing sample steps.
  They require a separate temporal-provenance fix and metric review; current
  validator success should not be described as proof of full semantic compliance.
- No scanned-PDF or image extraction was attempted. The existing text-PDF parser
  already gives 100% sample status; the committed vision cache stayed unchanged.
