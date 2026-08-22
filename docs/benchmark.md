# Benchmark

## Status

Current status: **BrowserGym causal post-action transition REOPENED / live runs blocked**. Prior Planner/Auditor G0–G6
artifacts remain scoped evidence only; Planner lexical admission has a separate known gap.

This file contains only the current benchmark contract and next execution order. Chronological run evidence is archived
in [`history/benchmark-pre-milestone-convergence-2026-08-22.md`](history/benchmark-pre-milestone-convergence-2026-08-22.md).

No live run is authorized merely because implementation or unit tests pass.

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
test interpreter and the pinned BrowserGym Python 3.12 interpreter. The final repository suite passed 1,497 tests with
19 skips; fresh-context review and the separate Planner lexical admission gap remain outstanding. Ruff, compileall,
and diff checks pass. Whole-repository
mypy remains a known pre-existing red baseline (310 errors in 39 files); the changed BrowserGym files add no new mypy
diagnostics beyond their prior baseline.

## Purpose

Benchmarks measure whether the single GUI runtime generalizes across real pages while preserving authority, recovery,
cost, and long-horizon continuity. Tests and architecture review protect contracts; live benchmark results remain the
final capability evidence.

Primary questions:

1. Does the agent complete supported tasks through the official native evaluator?
2. Does World delivery remain compact, understandable, and recoverable on real pages?
3. Are currently legal controls automatically discoverable without repeated region reads?
4. Can exact public evidence be found, pinned when needed, admitted across milestones, and used in the final answer?
5. Does one milestone remain a continuous execution episode rather than page-sized Manager assignments?
6. Do stalls, route regression, provider failure, uncertain dispatch, cleanup, and viewer failure terminate or recover
   through typed bounded paths?
7. Are token, latency, model-call, and unnecessary-action costs competitive with a compact single-agent baseline?

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
- World/Action/Evidence recoverability and ref currentness;
- working-fact and MissionState admission;
- milestone scheduling and removal of page-level assignment;
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

### W1b-Agent — live compatibility smokes

Live cases begin only after W1a and W1b-World close. Run one explicitly requested witness at a time, persist the case
result before cleanup, and diagnose the first shared contract failure before continuing. A single successful witness
does not close W1b.

### W2 — frozen hard cohort

W2 is the predeclared 12-case WebArena-Verified Hard cohort. Each case has an isolated MissionState, working set,
session, and trace. No cross-case long-term memory or recall is allowed. W2 starts only after W1b closure.

## Current normative gates

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

## Current provider-free verification

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
- Planner, ActionPolicy, deliberate-recovery, Auditor, repair, and transport-retry calls;
- per-role prompt/completion/reasoning tokens and latency;
- request component estimates for task/roadmap, delivery view, history, tool schema, and images;
- ActionCandidate recall/rank, content/evidence recovery, repeated-read rate, navigation excess, and no-progress rate;
- milestone boundaries, accepted facts/outcomes, typed recoveries, and hard-cap exits;
- primary failure, recovery failures, secondary cleanup/viewer failures, and durable-result status.

For a short single-site report task, engineering targets are:

- total provider tokens: target 50k–80k, ordinary upper bound 100k;
- ordinary prompt p95 below 12k;
- zero full-context semantic repair;
- no Planner call between intermediate GUI steps;
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

1. Complete and test viewer isolation, cleanup deadline/idempotency, durable result ordering, and side-effect-free role
   transport retry.
2. Implement the milestone contract and continuous-episode Supervisor scheduling.
3. Remove all superseded assignment/tool compatibility paths.
4. Run G0–G5 provider-free properties and archived-trace replay.
5. Run the six W1b-World diagnostics and cost gates.
6. Run full tests, lint, compile/diff checks, then G6 fresh-context review.
7. Only after an explicit user request, run one W1b-Agent live witness.
8. Diagnose against the shared contracts; do not patch a case or increase turns as the first response.
9. Close W1b only after representative live evidence; then freeze and run W2.
