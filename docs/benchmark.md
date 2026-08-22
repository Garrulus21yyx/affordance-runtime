# Benchmark

## Status

Current status: **single-ActionPolicy control path plus C8 stages 1–6 implemented provider-free /
generated diagnostics, fresh audit, and live closure gates blocked**. Prior
Planner/Auditor G0–G6 artifacts remain historical scoped evidence for the superseded mission path; they do not
authorize another live run.

This file contains only the current benchmark contract and next execution order. Chronological run evidence is archived
in [`history/benchmark-pre-milestone-convergence-2026-08-22.md`](history/benchmark-pre-milestone-convergence-2026-08-22.md).
The target runtime, deletion map, recovery state machine, migration order, and replacement acceptance invariants are in
[`single-action-policy-convergence.md`](single-action-policy-convergence.md).

No live run is authorized merely because implementation or unit tests pass.

Current public case evidence is `target-loop-case.v11`. The exact-field decoder also accepts pre-mission v6-v9.
Mission-shaped v10 files remain readable only as raw archived JSON and are deliberately not decoded into the v11
type; preserving an artifact is not a compatibility promise for its removed control vocabulary.

### Reopened BrowserGym transition gate

The new gate proves `dispatch → causal stable World → StepResult` without using Task-7 or OSM-specific branches:

- a link whose click returns before a 300 ms JavaScript-delayed navigation must capture the destination as the click's
  `after_world`;
- next ActionPolicy invocation is impossible before navigation commit, DOMContentLoaded, quiet-window satisfaction,
  and post capture;
- destination error content is carried by the click transition trace rather than attributed to the following action;
- navigation timeout and unstable acquisition are typed and admit no World;
- a mechanically non-navigation button skips the navigation-start lease;
- source inspection and timing tests reject a fixed long sleep as the synchronization owner.

Until this gate, the full provider-free suite, static checks, durable evidence, and a fresh-context review agree, do not
run Task-7 live again. The OSM broken route is environment/data failure and ActionPolicy route efficiency is a separate
quality dimension; neither may be used to patch or waive the transition invariant.

Implementation verification on 2026-08-22 (not closure): the generic real-Playwright delayed-navigation, pending,
DOM-instability, non-navigation fast-path, trace-forwarding, and next-policy-stop witnesses pass under both the normal
test interpreter and the pinned BrowserGym Python 3.12 interpreter. After the single-policy migration, the repository
partitions pass 1,425 tests with 19 skips and the independent fresh-context re-review reports no P0/P1/P2. Explicitly
authorized live witnesses remain outstanding. Ruff, compileall, and diff checks pass. Whole-repository
mypy remains a known pre-existing red baseline (310 errors in 39 files); the changed BrowserGym files add no new mypy
diagnostics beyond their prior baseline.

### Reopened Observation Delivery and AgentWorkspace gate

Later live evidence falsified two assumptions that the earlier six-page initial-World diagnostic did not test:

1. a global task/plan lexical Top-k over current public scalar facts does not guarantee that an exact result produced by
   the preceding GUI action is placed in the next model request;
2. append-oriented `recent_steps` with a fixed history cap is not a total bounded workspace and can fail before any
   provider request after useful results have already appeared.

The active provider-free gate therefore proves the full transition-to-request path:

```text
causal before/after World
→ one typed PublicWorldDelta
→ versioned existing regions and cached unchanged outline
→ exact LatestEffect/CurrentFindings/ChangedRegions delivery
→ total WorkspaceReducer
→ RequestAdmission as sole capacity authority
→ provider request or typed local context_capacity
```

This gate must use generic generated/property cases plus the six real-page diagnostics. Task-7 and the text `33km` are
regression witnesses only; production tests and code may not branch on them. C8–C9 implementation, full checks, durable
provider-free evidence, and a new independent fresh-context review must agree before any live witness is authorized.

Implementation checkpoint on 2026-08-22 (not C8–C9 closure): stages 1–6 freeze `PublicWorldDelta`, `RegionVersion`,
`CurrentFinding`, `SemanticEvent`, `ActivitySummary`, `AgentWorkspace`, and `AgentLoopProfile`; one
`WorldTransitionProjector` now supplies exact target/fact additions, removals, modifications, stable region membership,
and before/after lineage. Runtime action evaluation, observation evaluation, current delivery index, Monitor, compact
continuity, and trace share that projection. The existing `WorldDeliveryIndex` now versions stable regions, reuses
unchanged cached outlines, and keeps exact current membership. Default production delivery is change-first and carries
the latest exact GUI effect across local reads/searches; it no longer produces global lexical `EvidenceCandidates`.
`RunState` now stores a bounded `AgentWorkspace` rather than append-only recent history. A total reducer retains only
four detailed steps, exact bounded semantic events and working facts, aggregates ordinary activity by family, and does
not fail after 1,000 differing reads; Full Trace retains all 1,000 raw steps. The old history renderer, independent
history byte cap, RunState pre-cap, `EpisodeHistoryCapacityError`, and `fact_change_count` projection are removed.
`RequestAdmission` now owns complete request allocation, workspace fitting, estimation, and local
`context_capacity`; irreducible requests reach no provider. The provider Binder only serializes admitted requests.
`EpisodeMonitor` now owns exactly three information digests and two counters. Different query/region observations with
no World/Findings/Facts increment form one streak, threshold crossing produces one recovery, and recurrence returns
operational `control_stalled` without changing TaskEvaluation semantics. `AgentLoopProfile(30, 8, 1)` caps the old turn
budget rather than increasing it. Focused properties, Ruff, compileall, and the full provider-free suite pass with
1,438 tests and 19 skips. No live or Task-7 run was performed, no prompt or historical budget was increased, and
remaining C8 diagnostics and fresh-audit gates stay open.

Run17 recorded `CASE_FINISHED`, `cleanup_status=succeeded`, and `report_status=exported`; it does not reopen cleanup.
The existing persist-before-cleanup order and bounded cleanup/viewer contracts remain unchanged. A future
`cleanup_timeout` must be handled as a separate lifecycle witness rather than folded into C8–C9.

## Purpose

Benchmarks measure whether the single GUI runtime generalizes across real pages while preserving authority, recovery,
cost, and long-horizon continuity. Tests and architecture review protect contracts; live benchmark results remain the
final capability evidence.

Primary questions:

1. Does the agent complete supported tasks through the official native evaluator?
2. Does World delivery remain compact, understandable, and recoverable on real pages?
3. Does the exact public effect of the latest GUI action appear before the ordinary page outline without a model search
   call?
4. Are currently legal controls automatically discoverable without repeated region reads?
5. Can current public evidence be used directly, with an optional exact working note only when it must survive a view
   change?
6. Does arbitrary ordinary step growth remain bounded through one total AgentWorkspace reducer and one request-capacity
   owner?
7. Can one continuous ActionPolicy complete the task without mandatory Planner, milestone, Auditor, or MissionState
   transitions?
8. Do stalls, route regression, provider failure, uncertain dispatch, cleanup, and viewer failure terminate or recover
   through typed bounded paths?
9. Are token, latency, model-call, and unnecessary-action costs competitive with a compact single-agent baseline?

## Cohorts

### W0 — environment readiness

W0 verifies official dependency registration, six site health checks, reset, STOP/native-evaluator invocation, pinned
container images, and a durable readiness manifest. W0 is already complete; it is not rerun unless the environment or
official dependency commit changes.

### W1a — provider-free contracts

W1a exercises the architecture without a real model:

- one BrowserGym session across milestone episodes and no second reset;
- complete decision/receipt/state-transition algebra;
- native-tool wire and representation-only normalization;
- one before/after public World delta consumed consistently by outcome, delivery, Monitor, continuity, and trace;
- changed-region version/cache behavior, latest-effect salience, World/Action recovery, and ref currentness;
- current evidence use without mandatory pin/audit and optional exact working-note retention;
- total AgentWorkspace reduction under arbitrary ordinary step growth and whole-request admission by one capacity owner;
- information-delta activity aggregation and operational `CONTROL_STALLED` without task-semantic blocking;
- closed capacity/tool/provider/internal exception classification;
- direct GoalCompiler/CoreAgentLoop composition with no mission fallback;
- route/effect/protocol stall recovery;
- durable result, cleanup deadline, transport retry, and viewer fail-open behavior.

### W1b-World — six real-page diagnostics

Read-only provider-free diagnostics use these frozen official cases as heterogeneous page witnesses:

| Task | Site family | Primary stress |
|---:|---|---|
| 0 | shopping_admin | navigation, report form, result table |
| 7 | map | search, directions form, dynamic route result |
| 21 | shopping | dense commerce content and actions |
| 27 | reddit | searchbox and repeated feed structure |
| 44 | gitlab | very large structured application page |
| 266 | wikipedia + map | multi-site content and navigation |

These cases verify general contracts; production code may not branch on task id, site label, text witness, selector, or
expected output.

For each page the diagnostic captures at least one generic typed transition in addition to the initial World. It must
prove that added/modified public values enter `LatestEffect` and `CurrentFindings` where eligible, changed regions are
exact or completely paged, unchanged regions reuse cached versions, local read/search does not erase the effect, and
agent-browser-style serialized diff does not reveal a public addition absent from the typed delta/delivery manifest.

### W1b-Agent — live compatibility smokes

Live cases begin only after W1a and W1b-World close. Run one explicitly requested witness at a time, persist the case
result before cleanup, and diagnose the first shared contract failure before continuing. A single successful witness
does not close W1b.

### W2 — frozen hard cohort

W2 is the predeclared 12-case WebArena-Verified Hard cohort. Each case has an isolated TaskGoal/GoalPlan, working set,
session, and trace. No cross-case long-term memory or recall is allowed. W2 starts only after W1b closure.

## Active C8–C9 provider-free gates

### C8 — transition and incremental-delivery properties

Generated typed Worlds and held-out real-page transitions must prove:

- `PublicWorldDelta` is complete for every supported public addition, removal, and modification and binds one exact
  before/after lineage;
- ActionOutcome, Monitor, ObservationDelivery, SemanticEvent projection, and trace consume that same delta object or
  exact serialized value, rather than independently rebuilding change;
- every added/modified public value enters the next `LatestEffect`, or a bounded changed-region page plus typed cursor;
- local `read_region`, `search_page_content`, and `find_controls` do not clear the latest external effect;
- a later GUI effect supersedes the prior effect only after its exact public values are retained in a bounded
  `SemanticEvent`;
- unchanged region digests reuse their cached outline; changed region versions increase; navigation/document-lineage
  change invalidates stale refs and old cache membership;
- rendering/fitting never authorizes a target absent from the current complete ActionSpace;
- an independent serialized public-snapshot diff detects no addition/removal absent from the typed delta, except an
  explicitly documented non-semantic serialization difference;
- no second browser session, DOM walker, RegionIndex, selector/ref registry, action registry, or Agent loop is created.

Required regression shape:

```text
form submit or Go-like action
→ result/status/table text appears in after World
→ next ordinary request begins with the exact public change
→ zero content-search/read calls required for first visibility
```

The witness values and labels are generated or held out. An assertion tied only to `Distance: 33km` is insufficient.

### C9 — bounded-workspace and capacity properties

Property/state-machine tests must prove:

- four or fewer latest steps retain detail; older significant GUI effects, public results, working-note changes, typed
  failures, and recovery transitions retain exact bounded SemanticEvents;
- 1,000 ordinary supported steps, including non-identical read/search arguments, always return a reduced workspace or
  one typed irreducible capacity result; ordinary accumulation never raises a history exception;
- repeated no-information reads/searches/waits update one bounded `ActivitySummary` family rather than append entries;
- a precise public result remains available after leaving the latest-four window and after a local search-view change;
- a whole address is retained exactly and is not mechanically split into inferred business fields;
- `RequestAdmission` is the only component that allocates/adjudicates capacity for the complete request;
- RunState, history, renderer, and provider Binder contain no independent model-history cap or pruning authority;
- local irreducible overflow is `context_capacity`, `provider_attempts=0`; only grounded tool-resolution failure is
  `invalid_tool_arguments`; transport failure is `provider_unavailable`; unexpected Runtime failure is
  `internal_error`;
- World/finding/working-fact digests unchanged across observation-only activity produce one generic stall family even
  when query or region changes;
- the configured recovery threshold produces RECOVERY once, recurrence produces operational `CONTROL_STALLED`, and
  TaskEvaluation remains `INCOMPLETE|UNKNOWN`;
- Full Trace retains every raw step and is not read back as model workspace.

Profile values are recorded in each artifact. They may vary by declared experiment profile, but may not depend on task
id, site, page label, expected answer, or known trajectory.

## Superseded milestone-path gates (historical scoped evidence)

G0–G6 below describe what the current mission implementation previously proved. They are retained to prevent loss of
useful regression evidence while the code is removed, but they are not the acceptance gates for the target baseline.
The active migration and closure gates are C0–C9 and the acceptance invariants in
[`single-action-policy-convergence.md`](single-action-policy-convergence.md).

### G0 — single-path structural gate

Repository search and architecture tests must prove:

- one `CoreAgentLoop`, ActionSpace, Binder, executor, World authority, and native evaluator path;
- no production `execute_subtask`, Manager-owned `entry_scope_key`, ordinary state-change Manager review, or
  `yield_subtask` alias;
- no old `find_actions/find_content/open_region` tools after the rename migration;
- no compact-JSON product path after provider parity is established;
- no benchmark projection that reconstructs Runtime facts from trace, instrumentation, class names, or mission data.

### G1 — state and lifecycle properties

Property/state-machine tests must cover:

- every `DecisionKind` through StepResult, RunState, history, trace, snapshot, and benchmark;
- legal and illegal complete/partial/unknown/cancelled receipt batches;
- rejection of `RUNNING` with yield or terminal failure facts;
- atomic and compound dispatch conservation, including partial and `SENT_UNKNOWN` receipts;
- hard episode cap 15 enforced at every entry point;
- one transport retry for side-effect-free Planner/Auditor calls and zero GUI replay;
- result commit before cleanup/viewer export;
- persistence fault injection produces `HARNESS_PERSISTENCE`;
- cleanup deadline and idempotent already-closed success;
- queue full/closed/broken, dead/hung child, network failure, flush, close, and repeated close are fail-open.

### G2 — milestone scheduling and replay

Archived traces that previously reached useful GUI states are replayed provider-free. Required properties:

- report navigation, form fill, submit, and result read stay inside one milestone episode;
- directions form fill, submit, result read, and evidence capture stay inside one milestone episode;
- intermediate navigation/search/field-change/read/pin does not call the Planner;
- an admitted outcome with a ready successor mechanically advances without a Planner call;
- Planner calls occur only at START, typed NEEDS_REPLAN, or ROADMAP_EXHAUSTED_NOT_FINALIZABLE;
- planner call count is bounded by roadmap/milestone transitions rather than page transitions;
- Runtime hard cap remains 15 and does not silently expand.

Archived witnesses prove only the exact dispatch/local-tool steps actually present in those traces. Separate complete
typed counterexamples cover report navigation→fields→submit→search/read and directions fields→submit→search/read→pin;
neither proof fabricates missing archived steps.

### G3 — discovery and evidence delivery

For every W1b-World page:

- supported-public Actor normalization is lossless;
- every offered target appears in the delivery manifest or is recoverable through the declared path;
- automatic ActionCandidates contain a valid first control route when one exists;
- executable controls are found through `find_controls`, content through `search_page_content`, and known content
  through `read_region`;
- same-item probe matching requires label, allowed role, required operation, and next-manifest membership;
- required-evidence ranking properties place a matching exact public scalar in default EvidenceCandidates; the
  six-page initial-world diagnostic separately proves a default current scalar F-ref can be pinned and retained;
- `F-ref → pin_fact → WorkingFact → search/view change → retained value` is provider-free verified;
- folded views retain structural closure and beat a separately measured, non-authoritative full-delivery baseline;
- no private binding, selector, hidden evaluator state, credential, or stale local ref leaks.

Cost subgates for the six-page provider-free diagnostic:

- stable Tool Schema total: at most 2,000 estimated tokens;
- compact episode history: at most 1,500 estimated tokens in ordinary delivery;
- new-page admitted request: target p50 at most 8,000 and p95 at most 12,000 estimated tokens;
- complex pages must record a nonzero full-delivery baseline and show material reduction without failing recovery.

### G4 — recovery behavior

Held-out, non-site-specific tests must prove:

- first same-page/effect repetition without progress continues, second recovers, third yields;
- focus/hover/appearance/screenshot-only change is not operational progress;
- fresh structural result evidence is progress even before pinning;
- `A → B → A` without new formal progress, public result evidence, or working facts recovers; repeating the cycle yields;
- interleaved local reads, searches, and rejected calls cannot erase the route trail;
- producer and consumer use the same typed attempt signature;
- operation mismatch exposes supported operations and blocks exact immediate repeat;
- successful reuse of the same functional region for a different candidate remains legal.

### G5 — finalization authority

- deterministic admission distinguishes `CONTINUE_EVIDENCE`, formal `SATISFIED|UNSATISFIED`, and `SEMANTIC_AUDIT`;
- missing/stale/non-scalar evidence and zero-change/no-new-evidence never call Auditor;
- semantic Auditor runs only for evidence-complete business uncertainty;
- Auditor unknown/unsatisfied returns bounded guidance to the same milestone without clearing World or WorkingFacts;
- exhausted Auditor failure returns `AUDIT_UNAVAILABLE`, preserves World/WorkingFacts, and performs no GUI replay;
- Auditor input excludes full World, screenshots, trajectory, action/tool contracts, reasoning, transcripts, expected
  answers, and rewards;
- natural-language final answers are accepted when current admitted evidence is sufficient; universal pinning is not
  required;
- no LLM Finalizer is present in manager-guided mode;
- STOP is sent at most once;
- `SENT` and `SENT_UNKNOWN` with acquired post-state invoke the native evaluator once and never replay STOP;
- benchmark status derives from post-STOP native evaluation and committed receipts.

### G6 — independent review

After implementation and all provider-free gates pass, a fresh-context reviewer receives only the current docs, diff,
tests, and evidence. The reviewer must find no P0/P1 contract gap, old control path, duplicated authority, or gate that
can pass while the claimed invariant is false.

## Historical provider-free verification of the superseded path

| Gate | Current evidence | Result |
|---|---|---|
| G0 | production negative search plus architecture authority tests | passed |
| G1 | state/lifecycle properties plus behavioral transport-retry scope and persist-before-retry ordering | passed |
| G2 | archived and typed continuous-route replay; three mechanical Planner triggers; accepted-tail revision matrix | passed |
| G3 | run8: six PageMaps; p50 7,660.5, max 8,768; nonzero larger full baselines; every page exact F-ref pin/change/retention; zero provider/dispatch | passed |
| G4 | held-out monitor, route-cycle, evidence-progress, and typed attempt-signature tests | passed |
| G5 | strict Planner vocabulary/schema; deterministic route matrix; Auditor UNKNOWN/UNSAT/failure retention and frequency; serialized oracle exclusion; formal final SAT/UNSAT Supervisor paths | passed |
| full repository/static checks | 1,487 passed, 19 skipped; Ruff, compileall, and diff check clean | passed |
| G6 fresh-context review | independent full-tree audit found no P0/P1/P2; independently confirmed 1,487 passed, 19 skipped and run8 evidence | passed |

The authoritative G3 artifact is
`evidence/w1b-world-planner-auditor-provider-free-20260822-run8/w1b-world-summary.json`. No live model or
W1b-Agent run was performed.

## Live W1b acceptance

Live execution is separately authorized. For each run report:

- official task id, site family, seed, model/profile, prompt/catalog/context versions;
- official success and native-evaluator result;
- GUI decisions and physical dispatch receipts;
- ActionPolicy ordinary/recovery, representation-repair, and transport-retry calls; Planner/Auditor counts must be zero
  after migration;
- per-role prompt/completion/reasoning tokens and latency;
- request component estimates for task/plan, latest effect, changed regions, cached outline, AgentWorkspace, tool schema,
  and images;
- public-delta counts, changed/unchanged region reuse, latest-effect bytes/tokens, recoverability, ActionCandidate
  recall/rank, repeated-read rate, navigation excess, and no-progress rate;
- recent-detail, SemanticEvent, ActivitySummary, WorkingFact, workspace-fit, and whole-request-admission costs;
- optional working-note events, typed recoveries, direct final-response lifecycle, and hard-cap exits;
- primary failure, recovery failures, secondary cleanup/viewer failures, and durable-result status.

For a short single-site report task, engineering targets are:

- total provider tokens: target 50k–80k, ordinary upper bound 100k;
- ordinary prompt p95 below 12k;
- zero full-context semantic repair;
- zero Planner and Auditor calls;
- no repeated unchanged region read before a valid control/evidence alternative is offered.

These are cost targets, not success substitutions.

## Required artifacts

Every case writes:

```text
run manifest
traces/<case-id>/trace.jsonl          # private, complete, local authority
artifacts/<content-addressed media>
run-results.sqlite3                   # durable case truth
cases/<case-id>.json                  # optional materialized view
summary.json                          # optional aggregate view
```

Public reports exclude prompts, model responses, selectors, coordinates, credentials, hidden state, oracle answers,
reward payloads, and screenshots unless explicitly approved. Trace-write failure invalidates benchmark evidence but
does not change Runtime control behavior.

## Execution order

1. Preserve the implemented single-ActionPolicy control migration and superseded mission evidence; do not reopen the
   removed Manager/Auditor chain.
2. Freeze `CurrentFinding`, `SemanticEvent`, `ActivitySummary`, `AgentWorkspace`, `PublicWorldDelta`, region-version,
   and whole-request-admission contracts.
3. Produce one typed public World delta and migrate ActionOutcome, delivery, Monitor, history continuity, and trace to
   consume it; delete competing fact/change projections.
4. Upgrade the existing RegionIndex with version/digest/cache state and replace global EvidenceCandidates delivery with
   `LatestEffect + CurrentFindings + ChangedRegions + ActionCandidates + cached PageOutline + RecoveryDirectory`.
5. Implement total `WorkspaceReducer`; migrate RunState to store AgentWorkspace rather than unbounded model history;
   retain all raw steps only in Full Trace.
6. Remove `EpisodeHistoryCapacityError`, the fixed history byte cap, RunState pre-cap, provider-side fitting, old history
   renderer, and compatibility delivery paths.
7. Make `RequestAdmission` the sole capacity owner, close exception classification, and make Monitor's information-delta
   state machine terminate as operational `CONTROL_STALLED` without task-semantic blocking.
8. Run C8–C9 generated properties, held-out transition cases, and six-page W1b-World diagnostics; persist complete
   provider-free artifacts.
9. Run full tests/static checks and an independent fresh-context review of current docs, code, tests, and evidence.
10. Only after an explicit user request, run one W1b-Agent live witness and one held-out witness; close W1b only when
    success, latest-result salience, bounded recovery, token cost, code, docs, and evidence agree.
