# P5-M4.6 evidence-directed short-loop remediation

> Current remediation record. The immutable trigger attribution is
> [P5-M4.5-C MiniWoB-60 diagnostic at `4924ce6`](2026-08-11-p5-m4-5-miniwob-60-diagnostic.md).
> This file may record later implementation and verification identities; the
> baseline JSON and baseline classifications must never be edited or backfilled.

## Trigger identity

```text
trigger_run_id: miniwob-60:e9551acfcd31466e91481ee5923fc9af
trigger_git_sha: 4924ce61748d8efdec4fcc6de494acf8a9f224cc
trigger_result: 60/60 complete; 8/60 success; evidence valid
archive_commit: 5f8d6acf3700831a05d73f93a5c66488a6298fd7
archive_commit_role: docs-only evidence archive, not implementation or run SHA
generalization: NOT_CLAIMED
```

The 6/60 run at `b3b64a2`, rerun-v3 4/60 at `83dc4fa`, and this 8/60
diagnostic are independent records. They are not merged into a trend claim.

## Current queue

```text
M4.6 overall: IN_PROGRESS
M4.6-A canonical AX semantics/currentness: COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE
M4.6-B verifier/task-terminal truth: COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE
M4.6-C semantic inventory truth: NEXT
M4.6-D bounded control no-gain: NOT_STARTED
M4.6-E stable target identity and semantic breadth: NOT_STARTED
M4.7 supported-subset multi-seed: BLOCKED_BY_M4_6_GATES
P5-E verified long-horizon frontier: BLOCKED_BY_BREADTH_GATES
```

Only one M4.6 product slice is implemented before its focused properties and
targeted evidence are recorded. This preserves attribution and avoids changing
currentness, verifier, observation breadth and liveness in one unmeasurable
patch.

## Remediation ledger without event-sourcing semantics

This table is documentation tracking only. It is not Runtime state, an event
ledger, a replay source or execution truth.

| Remediation | Trigger run / Git SHA | Observed cohort | Source mechanism | Claim limit | Implementation SHA | Verification run ID | Exit property |
|---|---|---|---|---|---|---|---|
| M4.6-A canonical AX semantics/currentness | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | no-step cases 18, 35, 48, 50, 55, 58; post-run review found 41 false + 1 terminal stale | AX projection and DOM heuristic probe independently owned role/name/state; whole-page select options and incomplete availability were adjacent same-owner defects | immutable JSON proves the 42 no-step shape, not the per-attempt 41/1 probe payload or a future success-rate gain | `896508eaf7737cd86289f93a30e5737c6b1cdf76` | `NONE` | unchanged canonical binding is current; any bound drift is typed `NOT_SENT` with zero step; probe/accounting identity remains exact |
| M4.6-B verifier/task-terminal truth | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | previous verifier-unknown cases 01, 03, 08, 10, 11, 21, 22, 32, 35, 41, 42, 46, 54, 59 | three-state verifier collapses non-success/non-ongoing combinations into unavailable/task unknown | the baseline does not reveal how many cases are negative terminal, ongoing, malformed or unavailable; the targeted run does not claim performance or generalization | `880e65fef0c2541be9f4b5af121e610f858685db` residual closure; original/run SHA `07895ede392bdff065ba3b4c0a6384ba18904143` | `miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015` | supported verifier algebra is total; raw probe facts preserve presence/type; nonterminal task facts do not erase cross-domain control truth |
| M4.6-C semantic inventory truth | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | zero-target/action cases 04, 05, 07, 14, 17, 26, 28, 33, 34, 36, 38, 43, 44, 47, 49, 52, 57 | executable-role filtering precedes target creation and coverage calculation | baseline does not prove the task-required missing role or that more targets guarantee success | `NONE` | `NONE` | projection coverage and semantic inventory are distinct; recognized omission cannot be reported as represented/empty |
| M4.6-D bounded control no-gain | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` | page shape 07, 14, 17, 26, 28, 33, 34, 38, 43, 44, 49, 52; observation shape 02, 13, 20, 39, 60 | unchanged page only continues; observation freshness uses identity rather than public semantic gain | case JSON stores only the last decision and no per-turn semantic digest | `NONE` | `NONE` | first exact no-gain gives typed feedback; second consecutive identical request/result terminates; Runtime refresh is exempt |
| M4.6-E stable identity/breadth | `miniwob-60:e9551acfcd31466e91481ee5923fc9af` / `4924ce6` (source-only adjacent risk) | no direct baseline cohort for ordinal identity; zero-target cohort remains breadth witness | target ID includes ordinal; observable and executable roles are coupled | neither ordinal identity nor a particular unsupported role was shown to cause a baseline failure | `NONE` | `NONE` | identity survives irrelevant AX order changes; read-only semantics cannot grant unsupported execution; quotas preserve actionable controls |

`Implementation SHA` is filled only after a clean product commit exists.
`Verification run ID` is filled only for a new immutable targeted or full run.
Neither column ever points to the docs-only archive commit.

## Authority and dependency direction

| Owner | Responsibility |
|---|---|
| `browsergym_semantics` | immutable canonical AX control, computed role/name/typed state, availability, owner-scoped public/private option domain, public/private fingerprints, exact deduplication and typed conflict rejection |
| `browsergym_semantic_profile` | finite current BrowserGym observable/executable role algebra, semantic action, primitive, currentness fields and primitive availability conditions |
| `browsergym_currentness` | pure canonical binding/live comparison and bounded adapter-local reason |
| BrowserGym backend | owner-thread pinned observation and frame-safe BID physical reads plus step; no AX role/name inference and no public capture ownership |
| BrowserGym projection | bounded target/fact/binding assembly only |
| BrowserGym binding | immutable private canonical binding and public-label-to-native-value dispatch mapping only |
| BrowserGym verifier | pure external verifier fact classification |
| evaluation contracts | generic canonical `TaskOutcomeFact` and status/evidence matrix |
| task-evaluation control policy | the only `TaskEvaluation`-to-loop disposition owner |
| world semantic projection | generic inventory summary and identity-free public digest |
| agent control liveness | exact page/policy-observation no-gain transition |
| `AgentLoopState` | current task evaluation and bounded liveness state authority |
| AgentResult/session snapshot/CaseFacts | current-epoch bounded one-way task-outcome projection |
| external breadth classification | unique benchmark outcome precedence |
| codec/legacy/model/telemetry projections | downstream-only copies, never inference owners |

No file is split or retained because of a line-count threshold. Responsibility,
authority, cohesion and change coupling decide ownership. Projection,
`ContextBuilder` and benchmark classification must not become god owners.

## Cross-slice non-goals

- no durable ledger, replay, event sourcing or state reconstruction;
- no new StateKernel, transaction platform or generic recovery engine;
- no planner, VerifiedTaskState or TaskProgressAuditor under M4.6;
- no task-specific role aliases or relaxation of semantic/currentness checks;
- no Langfuse/OpenTelemetry authority over Runtime or benchmark facts;
- no rewriting of the 64 baseline JSON files or their typed outcomes;
- no full MiniWoB-60 rerun until the targeted gates identify remaining gaps.

## M4.6-A focused evidence

The product implementation is
`896508eaf7737cd86289f93a30e5737c6b1cdf76`. No new immutable targeted run
artifact was produced, so the ledger Verification run ID remains `NONE`.
These focused commands are verification evidence, not a campaign run ID:

- canonical/currentness/execution/projection properties: `40 passed`;
- all BrowserGym-focused tests: `236 passed, 18 skipped`;
- Python 3.12 pinned real gate with command-scoped local fixture URL:
  `18 passed` in 31.62 seconds, covering click-tab, click-tab-2,
  click-tab-2-hard, click-tab-2-easy, book-flight, choose-list and the
  login-user-popup terminal path;
- focused physical-probe latency witness: six probes, 205.80 ms minimum,
  332.58 ms median and 427.49 ms maximum;
- full repository suite: `2091 passed, 23 skipped` in 76.48 seconds;
- `ruff check .`, `mypy src` (431 source files), main and pinned clean-process
  forward/reverse imports, `git diff --check`, and immutable evidence digest
  `7a3f60c10896fc2f458afc11874bce866987fb9f1e752c8d164ae4b05d80b318`
  all passed.

Fresh-context adversarial review generated held-out duplicate/conflicting BID
and node identity, option-owner/domain, availability, AX order, malformed probe,
terminal re-entry and private-projection variants. It found shared-owner gaps
for option ownership, bidless conflict handling, duplicate native option
values, semantic node identity and explicit BID comparison; each was repaired
in the shared canonicalizer/comparator with no task-specific branch. The final
fresh-context verdict was `VERIFIED`.

This attests only canonical currentness on the declared non-default scope. It
does not claim a MiniWoB success-rate, performance improvement, generalization,
M4.5-B closure, or completion of M4.6-B through M4.6-E or P5-E.

## M4.6-B focused and targeted evidence

The clean product implementation is
`07895ede392bdff065ba3b4c0a6384ba18904143`. The accepted immutable targeted
run is `miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015` under
`docs/evidence/runs/p5-m4-6-b-miniwob-verifier-14-seed7-07895ed-targeted/`.
It is the frozen previous-verifier-unknown cohort, not a full MiniWoB-60 run or
a negative-terminal cohort selected after observing results.

- source-aware verifier properties cover exact bool/numeric validation,
  bool-as-number, NaN/infinity, arbitrary shapes and held-out exact integers
  through `10**10000`; RESET cannot prove terminal status and malformed or
  unsupported combinations fail closed;
- evaluation/evidence properties separate completion proof from neutral
  negative-status proof and reject stale-epoch evidence;
- loop/reducer properties preserve actual Runtime failures, make pure task
  terminal failure absorbing and exactly-once, and produce no synthetic
  `RuntimeFailure(CONTROL, REJECTED)`;
- CaseFacts v8, v6/v7 read-only decoding and classification precedence
  properties prevent status/message/latest-operation or metric inference;
- the command-scoped Python 3.12 pinned real gate passed `13` tests, including
  deterministic `login-user-popup` seed 7 with exactly one SENT and backend
  step, `BLOCKED` terminal task outcome, current neutral evidence, empty
  completion proof, no RuntimeFailure and zero-call terminal re-entry;
- the final full repository suite passed `2115` tests with `26` skipped;
  `ruff check .`, `mypy src` over 433 source files, clean-process imports,
  architecture/documentation gates and `git diff --check` passed;
- fresh-context review generated held-out source/evidence/timing/legacy/privacy
  variants. It found shared exact-large-int and legacy-emission gaps; both were
  fixed in the common classifier/codec, and the final verdict was `VERIFIED`.

The targeted run completed 14/14 with valid evidence, zero acceptance or
harness-integrity errors, zero unclassified outcomes and a clean privacy scan.
Canonical verifier distribution was 12 `TERMINAL_TASK_FAILURE` and 2
`INCOMPLETE`; benchmark distribution was 13 `TASK_FAILED` and 1
`RUNTIME_REJECTED`. All 12 terminal-task-failure cases classified as
`TASK_FAILED` from `canonical_task_outcome` with no RuntimeFailure. The extra
`TASK_FAILED` was an independent canonical session RuntimeFailure after a
running-incomplete fact, so precedence remained orthogonal.

The old diagnostic remains exactly 64 JSON files with digest
`7a3f60c10896fc2f458afc11874bce866987fb9f1e752c8d164ae4b05d80b318`.
No old result or classification was rewritten. M4.6 remains `IN_PROGRESS`,
M4.6-C is `NEXT`, and M4.5-B reviewed closure SHA remains `NONE`. No
performance, success-rate or generalization claim is made.

## M4.6-B residual shared-contract closure

The original M4.6-B implementation and targeted evidence remain bound to
`07895ede392bdff065ba3b4c0a6384ba18904143`. Residual contract implementation
`880e65fef0c2541be9f4b5af121e610f858685db` closes two shared seams without
reinterpreting that run or creating a replacement campaign ID:

- the BrowserGym owner-thread producer preserves the presence and raw type of
  `ready`, `done` and raw-reward facts; `browsergym_verifier` remains the only
  validation and four-state classification owner;
- `post_action_policy` owns cross-domain precedence, so supported terminal task
  truth is absorbing while `SENT_UNKNOWN` or an actual action failure remains
  authoritative over nonterminal task facts; `control_reducer` validates that
  final disposition and constrains only canonical terminal task outcomes.

The producer and AgentLoop witnesses failed before the shared-owner change and
passed afterward. Focused verifier/control/benchmark properties passed 184
tests. The command-scoped Python 3.12 pinned BrowserGym/Playwright gate passed
18 tests, including raw missing/wrong-type producer facts, valid official
ongoing/success/terminal facts and the deterministic terminal task path. The
full repository suite passed `2119` tests with `27` skipped; Ruff, mypy over 433
source files, main and pinned clean-process imports, documentation/architecture
governance and `git diff --check` passed.

An independent fresh-context review generated all seven missing-key subsets,
13 undefined/wrong-type facts, three non-finite values, 12 valid typed truth
states, six malformed containers and 29 task-outcome/dispatch/action/control
stopping combinations. It verified terminal absorption, unknown-effect
no-replay, independent failure precedence and finalized re-entry without a new
production branch. Verdict: `VERIFIED`.

No new targeted run ID was produced. The accepted ID remains
`miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015`, explicitly at the
original implementation SHA. Its evidence directory remained byte-identical
(sorted file-manifest digest
`7c80e6c0533f396268b2531587b27d5420db3fbd72500ad6ebf9a0071df433ae`).
The old diagnostic remains 64 JSON files with digest
`7a3f60c10896fc2f458afc11874bce866987fb9f1e752c8d164ae4b05d80b318`.

## Promotion gate

After M4.6-A through M4.6-E have independent implementation identities and
focused evidence, create a new immutable same-profile MiniWoB-60 record. Only
then may the project decide whether M4.7 receives a predeclared supported-subset
multi-seed manifest and thresholds. M4.5-B remains independently reopened and
implemented-not-verified until its own property, held-out and clean-attestation
gate passes; M4.6 product work must not be reported as B closure evidence.
