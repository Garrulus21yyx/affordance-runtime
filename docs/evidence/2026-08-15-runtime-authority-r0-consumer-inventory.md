# R0 Runtime authority consumer inventory and atomic migration map

> **Date:** 2026-08-15
> **Baseline inspected:** `7cfd310`
> **Worktree:** pre-existing uncommitted authority-convergence documentation was retained as review input
> **Scope:** repository-wide causal surface from observation request through current AgentLoop state and outward projections
> **Status:** `R0_REVIEW_COMPLETE / CONTRACT_ALGEBRA_FROZEN / CONSUMER_INVENTORY_COMPLETE / ATOMIC_MIGRATION_MAP_READY / R1_IMPLEMENTATION_READY / A.2_STILL_OPEN / LIVE_NOT_RUN`
> **Implementation boundary:** this record freezes contracts and migration/deletion gates; it does not claim that R1, R2, or R3 types or owners exist in production

> **Disposition update (2026-08-15):** R1 has implemented the acquisition
> portion of this map. See [R1 acquisition convergence](2026-08-15-runtime-authority-r1-closure.md).
> The tables below remain the immutable pre-cutover inventory; R2/R3 entries are
> still pending.

## 1. Review method and bounded conclusion

The review mechanically searched production and tests for definitions,
constructors, imports, factory/composition sites, direct `WorldFusion` use,
both `StaticEnvironment` implementations, public exports, benchmark wrappers,
session/result snapshots, and every named value in the R0 prompt. It then read
the owners and exceptional paths rather than treating file counts as proof.

The known reopenings still have one shared explanation:

```text
locally typed request/result facts
-> locally valid but narrower phase DTO
-> another narrower control summary
-> model/feedback/benchmark consumer cannot address the original fact
-> consumer reconstructs from status, whole-world digest, surface, or receipts
```

The two mechanisms are (a) replacement of exact phase aggregates by copied
subsets and (b) duplicate acquisition composition roots. They jointly explain
the provider-request, residual-stage, need-fulfilment, fallback, no-gain,
planless-failure, capability-order, route-source, static-fixture, and
summary-backed-transition reopenings. No event store, ledger, graph database,
workflow framework, or new automation engine is needed to close them.

R0 is documentation/audit complete. The implementation remains open. No live
benchmark was run.

## 2. Current implemented call chain

The following is current code truth, not the target diagram:

```text
TargetRuntime.start/run
-> AgentLoop.start
   -> WorldEnvironment.reset(TaskGoal)
      -> UnifiedWorldEnvironment OR BrowserGymEnvironment OR StaticEnvironment
      -> ObservationAcquisition(status, origin, observation, reason,
                                optional plan, source results)
   -> require_initial_observation
   -> AgentLoopState(current WorldObservation)
-> loop
   -> TaskEvaluator -> TaskEvaluation
   -> ActionSpaceBuilder.build -> ActionSpace
   -> ContextBuilder -> AgentContext + observation capability projection
   -> AgentPolicy -> AgentDecision
   -> ActionSpaceBuilder.try_admit_selection -> ActionAdmissionResult
      -> AdmittedActionSelection OR AdmissionIssue
   -> RiskPolicy
   -> ActionBinder.bind -> BoundActionRequest
   -> execute_cycle adds verification needs by replacing BoundActionRequest
   -> WorldEnvironment.execute
      -> ExecutionOutcome(ActionResult, mandatory post ObservationAcquisition)
   -> validate_fresh_acquisition
      -> FreshAcquisition (drops exact acquisition request/plan/source/need facts)
   -> optional independent fallback
      -> FreshAcquisition merged with primary counts/status
   -> ActionEvaluator -> ActionEvaluation
   -> TaskEvaluator -> TaskEvaluation
   -> ControlTransitionScope
      -> AdmissionSummary + ExecutionSummary + AcquisitionSummary
      -> ControlTransition
   -> ControlReducer -> AgentLoopState
-> AgentResult
   -> exact bounded ControlTransition suffix
   + compatibility Turn suffix
   + counts/status/result projections
-> AgentContext.last_transition / history, session snapshot, benchmark CaseFacts
```

There is no production `ActionAdmissionOutcome`, `EvaluationOutcome`,
`AcquisitionStage`, `ProviderActivation`, or `FreshObservationOutcome` type.
Those names are target contracts only.

### 2.1 Current observation composition roots

The generic path is:

```text
UnifiedWorldEnvironment._select
-> ObservationOrchestrator.select
-> initialize every adapter + one reset per physical environment (reset only)
-> selected_observation_requests
-> acquire per source or grouped acquisition
-> optional select_after_baseline and residual activation
-> SourceAcquisitionResult assembly
-> WorldFusion.fuse
-> ObservationAcquisition finalization
```

The BrowserGym path is separately:

```text
BrowserGymEnvironment.reset/capture/execute
-> ObservationOrchestrator.select
-> BrowserGym raw reset/capture/step
-> _project structural source
-> ObservationOrchestrator.select_after_baseline
-> optional visual provider branch
-> SourceAcquisitionResult assembly
-> new WorldFusion().fuse
-> ObservationAcquisition finalization
```

The two roots use the same selector and fusion classes, but each owns lifecycle
initialization, activation ordering, exceptional-path conversion, fusion
invocation, and final aggregate construction. Sharing helper classes does not
make them one state machine.

## 3. Current owners, target owners, and disposition

| Phase/fact | Current production owner(s) | Current exact value | R0 disposition | Frozen sole owner after cutover |
|---|---|---|---|---|
| task meaning | intake / `TaskGoal` | `TaskGoal` | `KEEP_AS_AUTHORITY_CONSUMER` | intake / `TaskGoal` |
| source selection | `ObservationOrchestrator` | `ObservationSelectionResult` / `ObservationSelectionPlan` | `KEEP_AS_AUTHORITY_CONSUMER` | `ObservationOrchestrator` |
| acquisition lifecycle | `UnifiedWorldEnvironment`, `BrowserGymEnvironment`; static substitutes bypass both | partial `ObservationAcquisition` | `MIGRATE_TO_COMPOSITION` | one `AcquisitionCoordinator` exposed by product `WorldEnvironment` |
| physical grouped capture | grouped `SurfaceAdapter`; BrowserGym private raw capture | selected result(s) or BrowserGym local source results | `MOVE_TO_OWNER` | backend/group adapter behind coordinator |
| fusion | `WorldFusion` | `WorldFusionResult` | `KEEP_AS_AUTHORITY_CONSUMER`; compose exact result | `WorldFusion` |
| current world | `WorldFusion` constructs `WorldObservation`; `AgentLoopState` installs current instance | `WorldObservation` | `KEEP_AS_AUTHORITY_CONSUMER` | `WorldFusion` for construction; `AgentLoopState` for current slot |
| legal actions | `ActionSpaceBuilder` | `ActionSpace` | `KEEP_AS_AUTHORITY_CONSUMER` | `ActionSpaceBuilder` |
| action admission | `ActionSpaceBuilder.try_admit*`, page/risk owners; later reduced to `AdmissionSummary` | `ActionAdmissionResult`, then summary | `MIGRATE_TO_COMPOSITION` | Runtime admission boundary returning exact `ActionAdmissionOutcome` |
| private bind | `ActionBinder` / `RouteSelector` | `BoundActionRequest` | `KEEP_AS_AUTHORITY_CONSUMER` | `ActionBinder` plus currentness/route owners |
| dispatch | selected adapter | `ActionResult` | `KEEP_AS_AUTHORITY_CONSUMER` | selected surface executor |
| execution closure | caller plus each `WorldEnvironment`; type is in `world/acquisition.py` and omits request | partial `ExecutionOutcome` | `MOVE_TO_OWNER` | `execution/ExecutionCoordinator` |
| action/task evaluation | evaluator calls assembled in `decision_control.py` and `execution_cycle.py` | separate `ActionEvaluation` / `TaskEvaluation` | `MIGRATE_TO_COMPOSITION` | `evaluation/EvaluationCoordinator` returning `EvaluationOutcome` |
| decision closure | `ControlTransitionScope`, then `ControlReducer`; summaries are independently writable | summary-backed `ControlTransition` | `MIGRATE_TO_COMPOSITION` | transition reducer over exact phase outcomes |
| current control state | `ControlReducer` projected into `AgentLoopState` | `AgentLoopState` | `KEEP_AS_AUTHORITY_CONSUMER` | `ControlReducer` / `AgentLoopState` |
| model views | context/world/tool/transition projectors | `*View`, `AgentTransitionDigestView` | `REPLACE_WITH_VIEW` source input only; remain projections | projector only |
| result/session/benchmark | `AgentResult`, `PartialEpisodeSnapshot`, `CaseFacts`, instrumentation/reporting | bounded DTOs | `REPLACE_WITH_VIEW` | projection owners only |

`AttemptReceipt` remains ordered observability/accounting evidence. It is not a
phase aggregate and cannot reconstruct one. Receipt equality checks may verify
that an exact outcome and physical counter agree, but Runtime control cannot
use a receipt in place of the outcome.

## 4. Frozen target algebra

This section is implementation-ready and normative for R1/R2. Names may move
to their final owner packages, but fields, legal shapes, and correlations may
not be weakened.

### 4.1 ObservationAcquisition

```text
ObservationAcquisition
  acquisition_id: run-scoped unique monotonic identity
  origin: RESET | INDEPENDENT_CAPTURE | POST_ACTION
  request: exact original WorldObservationRequest
  stage: AcquisitionStage
  selection_plan: exact ObservationSelectionPlan | None
  activations: ordered tuple[ProviderActivation]
    ProviderActivation
      request: exact SelectedObservationRequest
      result: exact SelectedObservationResult
  fusion_outcome: exact WorldFusionResult | None
  status: ACQUIRED | CAPABILITY_UNAVAILABLE | FAILED | CANCELLED
  reason: typed AcquisitionReason

derived, never independently writable:
  per_need_outcomes = deterministic plan/request-correlated fold of activations
  observation = fusion_outcome.observation when fusion succeeded, otherwise None
```

`AcquisitionReason` is a typed record with a closed `kind`, bounded stable
`code`, reached phase, and the relevant failed source/unresolved need IDs. Its
closed kinds are `UNAVAILABLE`, `INITIALIZATION_FAILURE`, `SOURCE_FAILURE`,
`FUSION_FAILURE`, `CANCELLATION`, `ALL_NEEDS_FULFILLED`, and
`UNRESOLVED_NEEDS`. A free string alone is not the reason authority.

Selected provider results add a typed `CANCELLED` terminal result. A selected
request has at most one terminal result; cancellation before provider dispatch
has no activation, while cancellation after dispatch retains completed
activations and typed cancelled results for requests whose dispatch status is
known. Host cancellation is re-raised only after the decision-scoped aggregate
has been closed.

| `AcquisitionStage` | Legal exact shape | Top-level status |
|---|---|---|
| `PRE_SELECTION_UNAVAILABLE` | request; no plan, activations, or fusion | `CAPABILITY_UNAVAILABLE` |
| `INITIALIZATION_FAILED` | request + final plan; no provider activation or fusion | `FAILED` |
| `SOURCE_ACQUISITION_FAILED` | request + plan + one terminal activation per selected request; no fusion | `CAPABILITY_UNAVAILABLE` only when every blocking result is typed unavailable, otherwise `FAILED` |
| `FUSION_FAILED` | request + plan + complete selected activations + exact failed fusion outcome | `FAILED` |
| `CANCELLED` | request plus exactly the plan/activation/fusion prefix reached before cancellation; no later fact fabricated | `CANCELLED` |
| `ACQUIRED_ALL_NEEDS_FULFILLED` | request + plan + complete activations + successful fusion; every plan need fulfilled | `ACQUIRED` |
| `ACQUIRED_WITH_UNRESOLVED_NEEDS` | request + plan + complete activations + successful fusion; at least one need explicitly unresolved | `ACQUIRED` |

Reset always has an explicit initial-grounding request and follows selection.
Residual stage two may change the final immutable plan before finalization, but
the acquisition ID and original request do not change. Unselected offers live
in the plan; they do not need fabricated activations.

### 4.2 Freshness and fallback

```text
FreshObservationOutcome
  acquisition: exact ObservationAcquisition
  expected_origin: AcquisitionOrigin
  freshness: FRESH | REUSED | NOT_ACQUIRED | ORIGIN_MISMATCH

LinkedAcquisition
  relationship: POST_ACTION_FALLBACK
  primary_acquisition_id
  acquisition: exact independent ObservationAcquisition
```

Freshness wraps and never narrows acquisition authority. A fallback is a new
linked acquisition with the same verification needs. Primary and fallback
remain separately reachable; the observation actually consumed by evaluation
is named explicitly.

### 4.3 Action admission

```text
ActionAdmissionOutcome =
  ADMITTED(exact AdmittedActionSelection, exact risk disposition)
  | REJECTED(exact typed AdmissionIssue or typed risk rejection)
  | CONFIRMATION_REQUIRED(exact selection, exact risk assessment,
                          exact ConfirmationRequest)
```

It replaces `AdmissionSummary`; it does not replace `ActionSpace`, decision,
or binding authority.

### 4.4 ExecutionOutcome

```text
ExecutionOutcome
  request: exact BoundActionRequest
  result: exact ActionResult
  post_acquisition: exact ObservationAcquisition | None
```

Required invariants:

- result request identity and backend route match the exact request;
- `NOT_SENT` has `post_acquisition is None`;
- `SENT` and `SENT_UNKNOWN` retain one primary post acquisition, including a
  failed, unavailable, or cancelled acquisition;
- post-acquisition or evaluation failure cannot rewrite dispatch truth;
- cancellation before dispatch is a typed `NOT_SENT/CANCELLED` result;
  cancellation after the dispatch boundary is `SENT_UNKNOWN/CANCELLED`;
- a proven `NOT_SENT` reroute creates a new linked `ExecutionOutcome`; it never
  mutates the first request/result and never permits more than one effectful
  dispatch.

### 4.5 EvaluationOutcome

```text
EvaluationOutcome
  evaluation_id: run-scoped unique monotonic identity
  before_observation: exact WorldObservation
  execution: exact ExecutionOutcome | None
  observation_trigger: exact ObservationAcquisition | None
  consumed_acquisition: exact primary or linked fallback acquisition
  after_observation: exact consumed WorldObservation
  action_evaluation: exact ActionEvaluation | None
  task_evaluation: exact TaskEvaluation
  semantic_delta: None until the separately admitted future owner exists
```

Exactly one of `execution` and `observation_trigger` is the causal trigger.
For an action, `ActionEvaluation` exists only after `SENT`/`SENT_UNKNOWN` and
matches the execution request plus before/after observation identities. The
consumed acquisition must derive the after observation. A fallback is named,
not substituted into the primary execution. Evaluation exceptions and
cancellation retain the reached exact inputs/outcomes before propagation.

### 4.6 ControlTransition and AgentLoopState

```text
ControlTransition
  transition_id / sequence
  before observation and before task evaluation
  exact AgentDecision
  exact ActionAdmissionOutcome when applicable
  exact decision outcome union:
    observation acquisition(s)
    | execution attempt outcome(s) + optional linked fallback
    | page/user/wait/done/abort typed outcome
  exact EvaluationOutcome when applicable
  exact progress/control result
  pending kind and resulting AgentLoop status
```

The transition is finalized once per accepted policy decision. Confirmation
and user-input continuation replace the same root slot once under the source
transition identity. `AgentLoopState` remains current-state authority and is
not replayed from transitions. `AdmissionSummary`, `ExecutionSummary`,
`AcquisitionSummary`, and compatibility `Turn` are deleted in R2.

## 5. Information-loss and reconstruction audit

| Boundary | Source fact available before boundary | Current loss or reconstruction | Category |
|---|---|---|---|
| selected provider request -> result | acquisition ID, lifecycle, offer, selection, assigned needs | `SelectedObservationResult` is paired only by caller dictionaries; public root retains only narrowed source result | contract loss |
| acquisition finalization | original request, acquisition ID, plan, activations, fusion result | `ObservationAcquisition` stores no request/acquisition ID/stage/fusion result | architecture defect |
| acquisition -> freshness | plan, source results, per-need results | `FreshAcquisition` stores observation/status/reason/count/origin/kind only | projection used as authority |
| primary + fallback | two exact acquisitions and lineage | `post_action_fallback_result` merges observation/status/counts into one `FreshAcquisition` | fallback identity loss |
| execution | exact bound request and result | current `ExecutionOutcome` stores result only and always stores a post acquisition | caller-side reconstruction / invalid `NOT_SENT` shape |
| admission -> transition | exact admitted selection or issue/risk result | `AdmissionSummary(status, reason)` | admission authority loss |
| execution -> transition | request, result, post acquisition | `ExecutionSummary` copies selected result fields; adapter evidence and exact request disappear | execution authority loss |
| acquisition -> transition | request/plan/need/fusion facts | `AcquisitionSummary` copies status/origin/reason/count/kind | acquisition authority loss |
| evaluation | exact acquisition/execution consumed | separate evaluations retain IDs but no aggregate names the consumed acquisition | lineage ambiguity |
| request-evidence feedback | exact requested `ObservationNeedResult` | compares `policy_observation_result_digest` over whole world, ActionSpace, task evaluation | verification defect |
| capability projection | purposes for equivalent offers | dict keyed only by modality/assurance overwrites purposes by input order | projection algebra defect |
| binding -> post source | exact binding source observation lineage | generic environment maps surface to lowest-cost owned offer | lineage reconstruction |
| BrowserGym post-selection exception | selected plan/request reached | broad `failed_acquisition` returns planless failure | exceptional-path loss |
| control -> compatibility | exact transition summaries | `as_turn()` reconstructs a new `ActionResult` without adapter evidence | compatibility reconstruction |
| session/benchmark snapshots | exact transition/acquisition facts | bounded counts/status/reason only | acceptable projection only if it never re-enters Runtime |

## 6. Exceptional, cancellation, partial, fallback, and reroute paths

### 6.1 Observation paths in current code

| Path | Current behavior | Required R1 behavior |
|---|---|---|
| no offer / no sufficient source / budget exhausted | planless unavailable acquisition | `PRE_SELECTION_UNAVAILABLE` with exact request and typed reason |
| adapter initialization or physical reset throws | generic root retains plan/source failures; BrowserGym reset helpers can be planless | `INITIALIZATION_FAILED` with request + final plan |
| grouped/single provider throws | generic catches `Exception` and fabricates failed selected results | preserve exact selected requests and one terminal activation per source |
| required source unavailable/failed | root returns unavailable/failed without fusion | `SOURCE_ACQUISITION_FAILED` with complete activations |
| optional source fails but fusion succeeds | acquired with optional/unresolved reason | `ACQUIRED_WITH_UNRESOLVED_NEEDS`; explicit per-need outcomes |
| provider acquired but semantic need unresolved | acquired with unresolved reason | same, without conflating physical success and epistemic fulfilment |
| fusion returns inconclusive | current root drops exact `WorldFusionResult`; BrowserGym helper may also drop plan/results | `FUSION_FAILED` retaining exact fusion outcome |
| cancellation during reset/capture/provider/fusion | start/control receipt records cancellation; acquisition aggregate is not closed | close `CANCELLED` prefix aggregate, attach to active scope, then re-raise |
| residual stage two | generic and BrowserGym independently re-plan/activate | one coordinator advances the same acquisition ID and final plan |

### 6.2 Execution and evaluation paths in current code

| Path | Current behavior | Required R2 behavior |
|---|---|---|
| stale/unsupported/invalid pre-dispatch | `NOT_SENT` plus fabricated unavailable post acquisition | exact request/result and `post_acquisition=None` |
| adapter step succeeds | `SENT` plus primary post acquisition | exact request/result/primary acquisition |
| adapter throws after dispatch | BrowserGym maps to `SENT_UNKNOWN` plus failed post acquisition; generic exceptions may escape | exact `SENT_UNKNOWN` result and typed primary post acquisition/cancellation truth |
| post acquisition fails | dispatch truth survives, then independent fallback may run | keep primary; link fallback separately; name consumed acquisition |
| result lineage mismatch | attempt receipt sanitizes identity; caller terminates | exact malformed outcome remains bounded evidence; no summary becomes truth |
| proven `NOT_SENT` reroute | first summary retained, optional fresh capture/readmission/new request | two exact linked execution outcomes; at most one crosses dispatch |
| `SENT`/`SENT_UNKNOWN` | no reroute | unchanged |
| action evaluation invalid/fails/cancels | separate partial fields in ephemeral scope, exception/cancellation finalized as summary-backed transition | `EvaluationOutcome` closes reached facts or typed cancellation before propagation |
| task evaluation invalid/fails/cancels | same | same |

## 7. Duplicate composition-root responsibility table

| Responsibility | `UnifiedWorldEnvironment` | `BrowserGymEnvironment` | Final owner |
|---|---:|---:|---|
| selection | yes (`_select`, `_post_action_plan`) | yes (`reset`, `capture`, `execute`, `_project`) | `ObservationOrchestrator` called only by one coordinator |
| lifecycle initialization | yes (adapter init + physical reset owners) | yes (prepared initial raw + logical reset/task state) | acquisition coordinator; backend only performs private reset mechanics |
| provider activation | yes (`_acquire_selected`) | yes (structural projection + visual branch) | coordinator over adapter/group port |
| physical group reuse | yes through `GroupedObservationAdapter` | yes through one BrowserGym raw frame | grouped backend adapter |
| per-need satisfaction | generic adapters return selected results; coordinator converts them | BrowserGym computes results itself | provider adapter reports; coordinator validates/folds |
| fusion | injected `WorldFusion` | constructs `WorldFusion()` directly | injected `WorldFusion` called by coordinator |
| aggregate finalization | yes | yes | acquisition coordinator only |

BrowserGym finally retains backend open/close, physical reset/current capture,
DOM/AX/screenshot/BID extraction, private bindings/currentness, browser action
translation/step, and task-state source projection. It does not retain source
selection, semantic activation policy, fusion, or public acquisition/execution
aggregate construction.

## 8. Projection backflow audit

### 8.1 No proven production backflow

- `ActorWorldSnapshot`, `AgentContext`, action/tool views, and E-refs are used
  for model presentation and current-context admission only; exact Runtime
  membership is checked against current `ActionSpace` and private tables.
- `AgentTransitionDigestView` is produced from the latest transition and is not
  passed to reducer, binding, execution, fusion, currentness, or evaluation.
- `PartialEpisodeSnapshot`, `CaseFacts`, metrics, reports, and immutable run
  artifacts are outward benchmark/reporting projections. No product path reads
  them to choose a source, action, route, or completion.
- `AttemptReceipt` enters accounting/reducer consistency checks but is not a
  model/benchmark projection. It remains observability evidence, not a phase
  outcome.

### 8.2 Proven authority substitution that must be removed

- `FreshAcquisition` and `AcquisitionSummary` are lossy values consumed by
  Runtime control, so their names do not make them harmless projections.
- `ExecutionSummary` is used by `ControlReducer` lifecycle decisions in place
  of exact execution outcomes.
- compatibility `Turn` is exposed in `AgentResult` and used by many tests; its
  reconstructed `ActionResult` proves it is a second schema even though it is
  read-only.
- request-evidence no-gain consumes a whole-world/result digest because the
  exact need outcome is unavailable. This is consumer reconstruction, not a
  legitimate projection.

Mechanical R3 rule: any type whose name ends in `View`, `Digest`, `Summary`,
`Telemetry`, `Snapshot`, or is benchmark-specific is forbidden in parameter
annotations and imports of Runtime admission, binding, currentness, execution,
acquisition/fusion, evaluation, transition-reducer, and current-state owner
modules. Explicit, reviewed exceptions are outward projector inputs only; none
may construct or update an authority aggregate.

## 9. Constructor and consumer inventory

Classification meanings are exactly those requested by R0.

### 9.1 Production constructors and owners

| Files | Construction/consumption | Classification | Atomic disposition |
|---|---|---|---|
| `world/acquisition.py` | defines request/plan/provider/source/acquisition plus misplaced execution aggregate | `MIGRATE_TO_COMPOSITION` + `MOVE_TO_OWNER` | R1 replace acquisition root; R2 move execution type to `execution/` |
| `world/observation_orchestrator.py` | sole production `ObservationSelectionPlan` constructor | `KEEP_AS_AUTHORITY_CONSUMER` | retain selector; it never finalizes acquisition |
| `world/orchestrator.py` | constructs source results, acquisitions, executions; selects, activates, fuses, finalizes | `MIGRATE_TO_COMPOSITION` | becomes one coordinator façade; execution moves in R2 |
| `surfaces/dom/adapter.py`, `surfaces/visual/adapter.py`, `surfaces/wot/adapter.py`, `surfaces/http_json/adapter.py` | consume selected requests and return selected results | `KEEP_AS_AUTHORITY_CONSUMER` | retain provider role; add cancellation result support |
| `surfaces/browsergym/environment.py` | second plan/source/acquisition/execution constructor and fusion caller | `MOVE_TO_OWNER` | reduce to backend/group adapter + executor mechanics |
| `surfaces/browsergym/acquisition.py` | planless failure and fabricated `NOT_SENT` post acquisition helpers | `DELETE_WITH_OWNER` | delete after BrowserGym cutover |
| `agent/observation_control.py` | constructs/consumes `FreshAcquisition`, merges fallback, writes acquisition summaries | `MIGRATE_TO_COMPOSITION`; class `DELETE_WITH_OWNER` | consume exact `FreshObservationOutcome` and linked fallback |
| `actions/action_space.py` | sole `ActionAdmissionResult` / `AdmittedActionSelection` constructor | `KEEP_AS_AUTHORITY_CONSUMER` | exact result becomes part of admission outcome |
| `actions/binder.py` | sole production `BoundActionRequest` constructor | `KEEP_AS_AUTHORITY_CONSUMER` | retain |
| surface adapters | construct `ActionResult` | `KEEP_AS_AUTHORITY_CONSUMER` | retain dispatch owner |
| `agent/execution_cycle.py` | caller reassembles request/result/freshness/fallback/evaluations and summaries | `MOVE_TO_OWNER` | delegate execution/evaluation closure and compose exact outcomes |
| `agent/decision_control.py` | caller assembles observation/evaluation facts; whole-world no-gain | `MIGRATE_TO_COMPOSITION` | consume exact acquisition need outcome and `EvaluationOutcome` |
| `agent/control_transition.py` | sole production root constructor but creates four summary/compatibility schemas | `MIGRATE_TO_COMPOSITION`; summaries/Turn `DELETE_WITH_OWNER` | exact phase composition only |
| `agent/control_reducer.py` | consumes summaries/receipts as lifecycle authority | `MIGRATE_TO_COMPOSITION` | validate exact outcome union; receipts consistency-only |
| `agent/state.py` | owns current state; derives `recent_turns` | state `KEEP_AS_AUTHORITY_CONSUMER`; `recent_turns` `DELETE_WITH_OWNER` | retain current state, remove Turn projection |
| `agent/result.py` | exports exact transitions and compatibility turns | `REPLACE_WITH_VIEW` | retain exact transition/result views; delete Turn field or version it away atomically |
| `agent/context/*projection*.py`, `context_builder.py` | outward world/capability/transition views | `REPLACE_WITH_VIEW` | keep projector; source exact aggregates; forbid backflow |
| `agent/session_snapshot.py` | bounded in-flight projection | `REPLACE_WITH_VIEW` | keep telemetry-only; project from exact root |
| `benchmarks/target_loop/instrumentation.py`, `case_projection.py`, codecs/reporting | wrapper and reporting projections | `REPLACE_WITH_VIEW` | adapt to exact aggregates; never become Runtime input |
| `benchmarks/external_smoke/case_environment.py` | delegates direct BrowserGym world and owns benchmark verifier | environment `MIGRATE_TO_COMPOSITION`; verifier `KEEP_AS_AUTHORITY_CONSUMER` | compose BrowserGym backend through product coordinator; keep benchmark oracle outside product |
| `world/__init__.py`, `world/environment.py`, `execution/__init__.py`, `agent/__init__.py` | public exports and protocol annotations | `MOVE_TO_OWNER` | export execution/evaluation from correct packages; remove summary/Turn exports |

### 9.2 Direct construction sites

Mechanical constructor search found:

- `ObservationAcquisition(...)` in production only in
  `world/orchestrator.py`, `surfaces/browsergym/environment.py`,
  `surfaces/browsergym/acquisition.py`, and
  `benchmarks/support/static_environment.py`; test-side direct constructors are
  in `tests/support/agent/static_environment.py`,
  `tests/integration/world/test_observation_acquisition_lifecycle.py`,
  `tests/integration/world/test_unified_source_orchestration.py`, and
  `tests/integration/agent/test_confirmation_continuation.py`.
- `ExecutionOutcome(...)` in production only in `world/orchestrator.py`, both
  BrowserGym environment/acquisition modules, and benchmark static support;
  test-side direct constructors are the copied static environment and
  `tests/integration/world/test_observation_acquisition_lifecycle.py`.
- `ControlTransition(...)` outside its production owner appears only in
  `tests/benchmarks/agent/test_control_state_machine_properties.py` and
  `tests/unit/runtime/test_transition_digest_projection.py`.
- `ExecutionSummary(...)` outside its owner appears only in
  `tests/benchmarks/agent/test_control_state_machine_properties.py`.
- `AcquisitionSummary(...)` outside production owner/reducer appears only in
  the same state-machine property test.
- direct compatibility `Turn(...)` outside its owner appears in
  `tests/unit/model/test_model_policy_views.py`; other Turn consumers receive
  it through `AgentResult.turns` or `ControlTransition.as_turn()`.

These are complete for the inspected Python tree at `7cfd310`.

### 9.3 Two StaticEnvironment implementations and all consumers

`src/affordance_runtime/benchmarks/support/static_environment.py` and
`tests/support/agent/static_environment.py` are byte-for-byte identical. Both
accept a compatibility `observations` queue, infer which values are independent
versus post-action, construct planless acquisitions, fabricate post acquisition
for `NOT_SENT`, and bypass selection/provider/fusion.

Both implementations are `DELETE_WITH_OWNER`. Replace them with one scripted
`SurfaceAdapter`/group adapter used behind the production coordinator. The
following consumers are `MIGRATE_TO_COMPOSITION` unless explicitly noted as a
unit-only authority test:

```text
src/affordance_runtime/benchmarks/model_conformance/runtime_decision_matrix.py
src/affordance_runtime/benchmarks/target_loop/support.py
tests/benchmarks/runtime/test_target_loop_benchmark_runner.py
tests/conformance/model/test_m2_model_boundary_closure.py
tests/conformance/model/test_model_policy_admission.py
tests/conformance/world/test_world_evidence_validation.py
tests/integration/agent/test_agent_loop.py
tests/integration/agent/test_agent_progress_loop.py
tests/integration/agent/test_confirmation_continuation.py
tests/integration/agent/test_confirmation_reselection.py
tests/integration/agent/test_control_feedback_runtime_integration.py
tests/integration/agent/test_control_transition.py
tests/integration/agent/test_control_transition_failures.py
tests/integration/agent/test_session_snapshot_authority.py
tests/integration/agent/test_terminal_session_immutability.py
tests/integration/agent/test_user_input_continuation.py
tests/integration/evaluation/test_task_evaluation_loop_policy.py
tests/integration/model/test_live_model_policy_smoke.py
tests/integration/model/test_model_policy_http_bridge.py
tests/integration/model/test_model_policy_ollama_bridge.py
tests/integration/model/test_model_policy_runtime_integration.py
tests/integration/task/test_dynamic_semantic_task_progression.py
tests/integration/world/test_observation_acquisition_lifecycle.py
tests/integration/world/test_unified_source_orchestration.py
tests/unit/actions/test_action_evaluation_lineage.py
tests/unit/actions/test_action_paging.py
tests/unit/agent/test_agent_decision_context.py
tests/unit/agent/test_target_runtime_facade.py
tests/unit/evaluation/test_task_evaluation_validation.py
tests/unit/model/test_model_backed_agent_policy.py
tests/unit/model/test_model_port_decision_bridge.py
tests/unit/runtime/test_negative_claim_coverage_gate.py
tests/unit/task/test_target_task_intake.py
```

Pure unit tests of `TaskEvaluation`, paging, parser, or context contracts may
instead replace the world with a direct immutable `WorldObservation` because
they make no acquisition claim. Any AgentLoop, execution, acquisition,
fallback, transition, session, result, integration, or benchmark assertion
must go through the scripted adapter and production coordinator.

### 9.4 Direct WorldFusion test fixtures

Fusion-owner tests remain `KEEP_AS_AUTHORITY_CONSUMER`: the fusion sections of
`tests/integration/world/test_unified_source_orchestration.py`,
`tests/integration/world/test_actor_world_graph_a1.py`,
`tests/unit/world/test_world_graph_a1.py`, and conformance tests whose subject
is fusion/source/evidence correctness. They are allowed to call `WorldFusion`
directly because fusion is their unit under test.

The following direct-fusion files use a fused world merely as a fixture for a
downstream owner. They are `MIGRATE_TO_COMPOSITION` when testing AgentLoop or
cross-phase lineage, and may use a small immutable world builder only when the
test is strictly local to its downstream owner:

```text
src/affordance_runtime/benchmarks/model_conformance/runtime_decision_matrix.py
src/affordance_runtime/benchmarks/target_loop/evaluation_support.py
src/affordance_runtime/benchmarks/target_loop/support.py
tests/benchmarks/runtime/test_external_smoke_mechanical_verifier.py
tests/benchmarks/runtime/test_target_loop_benchmark_runner.py
tests/integration/agent/test_agent_loop.py
tests/integration/agent/test_agent_progress_loop.py
tests/integration/agent/test_confirmation_reselection.py
tests/integration/agent/test_control_transition_failures.py
tests/integration/model/test_model_policy_runtime_integration.py
tests/integration/runtime/test_live_semantic_evaluator_smoke.py
tests/integration/task/test_dynamic_semantic_task_progression.py
tests/support/world/__init__.py
tests/unit/actions/test_action_paging.py
tests/unit/agent/test_agent_progress_control.py
tests/unit/agent/test_control_feedback_public_digests.py
tests/unit/evaluation/test_criterion_adjudication.py
tests/unit/model/test_model_world_projection.py
tests/unit/risk/test_low_risk_inconclusive_policy.py
tests/unit/runtime/test_negative_claim_coverage_gate.py
tests/unit/runtime/test_semantic_judge_http_proof.py
tests/unit/runtime/test_target_output_validation.py
tests/unit/surfaces/browsergym/test_browsergym_action_evaluator.py
tests/unit/task/test_production_task_evaluator.py
```

### 9.5 Transition, compatibility, snapshot, result, and benchmark consumers

| Consumer set | Classification | Required change |
|---|---|---|
| `tests/benchmarks/agent/test_control_state_machine_properties.py` | `MIGRATE_TO_COMPOSITION` | generate exact phase outcomes and model the new state machine; delete summary constructors |
| `tests/integration/agent/test_control_transition.py`, `test_control_transition_failures.py` | `MIGRATE_TO_COMPOSITION` | assert exact request/acquisition/evaluation reachability |
| `tests/unit/runtime/test_transition_digest_projection.py` | `REPLACE_WITH_VIEW` | build exact roots through a test builder; verify lossy view cannot round-trip |
| tests reading `AgentResult.turns` across DOM/Visual/WoT/agent/runtime suites | `DELETE_WITH_OWNER` for Turn assertions; `MIGRATE_TO_COMPOSITION` for semantic assertions | read exact `control_transitions` or an explicit public result view |
| `agent/context/control_transition_projection.py` and `transition_digest_projection.py` | `REPLACE_WITH_VIEW` | source exact root; include exact requested-need outcome in next transition view |
| `agent/session_snapshot.py` | `REPLACE_WITH_VIEW` | keep bounded telemetry; do not expose summary as current state |
| `benchmarks/target_loop/instrumentation.py`, `case_projection.py`, `contracts.py`, codecs/reporting | `REPLACE_WITH_VIEW` | copy typed result facts; no Runtime input or classification override |
| immutable run directories and historical pass-count records | `HISTORICAL_EVIDENCE_ONLY` | never migrate into target contract or edit old evidence |

### 9.6 Public API, factories, and composition

- `app/composition.py` composes the Runtime but receives a supplied
  `WorldEnvironment`; it is `KEEP_AS_AUTHORITY_CONSUMER` and needs no new
  framework.
- `app/cli.py` directly constructs `UnifiedWorldEnvironment`; it remains the
  product composition consumer and is `MIGRATE_TO_COMPOSITION` only for the
  renamed/final coordinator façade.
- `benchmarks/external_smoke/case_environment.py` directly opens and delegates
  `BrowserGymEnvironment`; it is `MIGRATE_TO_COMPOSITION` so the BrowserGym
  backend enters the same product coordinator.
- `world/environment.py` is the public port and is
  `MIGRATE_TO_COMPOSITION`; its execution return imports from `execution/`.
- `world/__init__.py` currently exports `ExecutionOutcome`; this is
  `MOVE_TO_OWNER`. `execution/__init__.py` becomes its only public package
  export. `evaluation/__init__.py` exports `EvaluationOutcome` in R2.
- `agent/__init__.py` exports summaries/Turn today; those exports are
  `DELETE_WITH_OWNER` in the same R2 commit as their classes and tests.

## 10. Atomic R1/R2/R3 file order and deletion gates

No step permits dual-write, read-new/fallback-old, shadow authority, or a
compatibility constructor after its cutover commit.

### R1 — one acquisition coordinator and exact acquisition aggregate

1. `src/affordance_runtime/world/acquisition.py`: implement the frozen stage,
   reason, activation, cancellation, exact request/ID/fusion contract; remove
   legacy constructor defaults in the same change.
2. `src/affordance_runtime/world/observation_orchestrator.py`: preserve sole
   plan ownership; return only selection facts and typed pre-selection failure.
3. `src/affordance_runtime/world/surface_adapter.py` and DOM/Visual/WoT/HTTP
   adapters: close selected-result cancellation and correlation contracts.
4. `src/affordance_runtime/world/orchestrator.py`: become the sole acquisition
   coordinator for reset, independent, residual stage two, post-action source
   acquisition, grouped reuse, fusion, and finalization; use binding source
   lineage rather than surface/minimum-cost reconstruction.
5. `src/affordance_runtime/surfaces/browsergym/environment.py`: retain only
   backend/group adapter and executor responsibilities; remove selection,
   fusion, and public acquisition finalization.
6. `src/affordance_runtime/surfaces/browsergym/acquisition.py`: delete planless
   public acquisition/execution helpers.
7. `src/affordance_runtime/benchmarks/external_smoke/case_environment.py`,
   BrowserGym support factories, and `app/cli.py`: compose the backend through
   the same coordinator.
8. `src/affordance_runtime/agent/observation_control.py`: replace
   `FreshAcquisition` with exact `FreshObservationOutcome`; preserve primary
   and linked fallback separately.
9. `src/affordance_runtime/agent/context/acquisition_projection.py`: union
   equivalent offer purposes deterministically and preserve order invariance.
10. Delete both static environments and add one contract-faithful scripted
    adapter under test/benchmark support; migrate every consumer in section
    9.3.
11. Update `world/__init__.py`, environment protocol, BrowserGym exports, and
    all acquisition tests atomically.

R1 deletion gate: `FreshAcquisition`, BrowserGym public reset/capture
acquisition state machine, BrowserGym fusion/finalization, both static
environments, compatibility `observations` input, planless constructors, and
all old-constructor tests are absent. Architecture search proves only the
coordinator constructs `ObservationAcquisition` in production.

### R2 — exact execution, evaluation, and control composition

1. `src/affordance_runtime/execution/contracts.py` and
   `execution/__init__.py`: move/implement exact `ExecutionOutcome`; delete its
   definition/export from `world/acquisition.py` and `world/__init__.py`.
2. Add the smallest cohesive `execution/coordinator.py` (or place the role in
   the existing world façade if ownership remains explicit): correlate exact
   request/result/post acquisition and linked bounded reroute outcomes.
3. `world/environment.py`, `world/orchestrator.py`, surface executors, and
   BrowserGym backend: adopt the exact execution port; `NOT_SENT` returns no
   post acquisition.
4. `evaluation/contracts.py`, `evaluation/__init__.py`, and a small existing or
   new evaluation coordinator: implement exact `EvaluationOutcome`; do not add
   `SemanticDelta` beyond the frozen empty extension slot.
5. `agent/execution_cycle.py` and `agent/decision_control.py`: delegate closure,
   retain exact primary/fallback/consumed acquisition, and stop caller-side
   request/result/evaluation assembly.
6. `agent/control_transition.py`: compose exact admission/execution/acquisition/
   evaluation outcomes; delete `AdmissionSummary`, `ExecutionSummary`,
   `AcquisitionSummary`, `Turn`, `as_turn`, and summary accumulators.
7. `agent/control_reducer.py`: validate exact outcome algebra and ordering;
   keep receipts consistency-only.
8. `agent/state.py`, `agent/result.py`, `agent/session_snapshot.py`, context
   transition projections, public exports, and benchmark instrumentation:
   migrate consumers and remove compatibility Turn.
9. Migrate the direct transition/property tests in sections 9.2 and 9.5; delete
   tests whose only purpose was summary/Turn reconstruction.

R2 deletion gate: no summary/Turn class, export, constructor, parameter, or
test remains; `ExecutionOutcome` exists only under `execution`; every action
transition reaches its exact request/result/primary/fallback/evaluation values.

### R3 — one-way projections and contract-faithful verification topology

1. `agent/context/transition_digest_projection.py` and
   `control_transition_projection.py`: project exact requested-need outcome,
   exact dispatch result, and consumed acquisition without exposing private
   routes or full observations.
2. `agent/decision_control.py` and `world/public_semantic_digest.py`: compute
   no-gain from the exact need outcome plus relevant canonical change; remove
   whole-world substitution.
3. `context/acquisition_projection.py`: property-test order-independent purpose
   union and truthful availability.
4. `agent/session_snapshot.py`, `agent/result.py`, benchmark case projection,
   instrumentation, codecs, reporting, and manifests: remain outward DTOs and
   consume exact roots only.
5. Complete the static/direct-fusion consumer migration; keep direct owner-unit
   tests only where the named owner itself is under test.
6. Update architecture, status, public exports, documentation governance, and
   package topology together.

R3 deletion gate: no projection type is imported by an authority owner, no
benchmark/session/result DTO enters Runtime behavior, exact `request_evidence`
feedback is visible in the next context, and no fixture bypasses the lifecycle
it claims to verify.

## 11. Planned architecture redlines

| Phase | Planned mechanical redline |
|---|---|
| R1 | AST/import test allows production `ObservationAcquisition(...)` only in the one acquisition owner; BrowserGym cannot import `ObservationOrchestrator` or `WorldFusion`; no test/benchmark `StaticEnvironment`; no planless success/failure constructor |
| R1 | every `ProviderActivation.request.acquisition_id` equals root ID; plan selections and activations correlate exactly; source/group called at most once |
| R2 | `ExecutionOutcome` module is `execution`; world package cannot define/export it; `NOT_SENT -> post_acquisition is None` |
| R2 | `ControlTransition` source contains no `Summary`, `Turn`, `as_turn`, or reconstructed `ActionResult`; reducer APIs accept exact outcome unions only |
| R2 | every dispatched evaluation references the exact execution and consumed acquisition; cancellation closes a typed prefix before propagation |
| R3 | forbidden projection-suffix imports into authority package/module allowlist; benchmark modules are unreachable from product owners |
| R3 | model views have no constructor or parser back to `TaskGoal`, `WorldObservation`, `ActionSpace`, admission, binding, acquisition, execution, evaluation, transition, or state |
| R3 | static/scripted loop tests instantiate the production coordinator with adapters; direct fusion is allowed only in fusion-owner tests |

## 12. Property/model-based acceptance matrix

Known examples remain witnesses. They are not primary proof.

| Property/model | Generated dimensions | Falsifiable invariant |
|---|---|---|
| acquisition state machine | stage, origin, 0–2 sources, required/optional, result status, cancellation phase | exactly one legal shape; reached facts never disappear; unsupported shape fails typed |
| request/activation correlation | request/plan/source/need permutations | one root ID; selected request exactly once; no extra/missing result; needs partition exactly |
| order invariance | offer, source-result, purpose input order | same selection/capability union/fused authority for equivalent sets |
| grouped physical reuse | shared/distinct group and owner combinations | each physical group invoked at most once per acquisition |
| partial fulfilment | all subsets of fulfilled needs and optional failures | physical success never implies need success; acquired stage distinguishes all/unresolved |
| exceptional paths | pre-selection, init, provider, fusion, post acquisition, evaluation failures | typed stage/reason and exact reached prefix retained |
| cancellation model | before/after provider dispatch, fusion, action dispatch, evaluation | before dispatch `NOT_SENT`; after dispatch `SENT_UNKNOWN`; aggregate closed before propagation |
| execution correlation | request/result backend/ID/status combinations | exact identity and legal post-acquisition shape; dispatch truth monotonic |
| reroute model | first error, refresh success/failure, alternate availability, second result | only proven `NOT_SENT`; two exact outcomes; at most one effectful dispatch |
| fallback model | primary/fallback status and freshness combinations | distinct IDs/links; primary never overwritten; evaluation names consumed acquisition |
| evaluation model | action vs observation trigger, primary/fallback consumed, evaluator outcomes | one trigger; before/after/current lineage exact; no action evaluation without dispatch |
| transition reducer model | seven decisions, admission outcomes, continuations, terminal states | one root per accepted decision; legal monotonic transition; terminal absorbing; continuation consumes root once |
| projection non-interference | arbitrary bounded view truncation/order | changing/dropping projection fields cannot change Runtime state or reconstruct an authority value |
| fixture topology | scripted source outcomes across all stages | loop/benchmark uses production coordinator; no production branch per generated case |

Held-out adversarial families after implementation: plan-present init failure;
two sources with one unresolved need; optional source failure plus successful
fusion; cancellation between group results; fusion failure after all source
results; `NOT_SENT` with no post observation; `SENT_UNKNOWN` with failed primary
and successful linked fallback; request-evidence source acquired but need
unresolved; equivalent offers in reversed order; binding surface with multiple
owned offers; and malformed projection attempts. None may require a new
production branch.

## 13. Contradictions between code, status, and target documents

| Claim/document | Source-proven code truth at `7cfd310` | Resolution |
|---|---|---|
| documentation governance describes `ObservationAcquisition` as closed request-correlated | root lacks request, acquisition ID, stage, fusion outcome | governance text is target terminology, not implementation; status must say R1 not implemented |
| target docs name `ActionAdmissionOutcome` | no production type exists; exact `ActionAdmissionResult` narrows to `AdmissionSummary` | R2 target only |
| target docs name `EvaluationOutcome` | no production type exists | R2 target only |
| docs say `ExecutionOutcome` retains exact request and no post for `NOT_SENT` | current type stores only result and mandatory post; helpers fabricate unavailable post | R2 target only |
| `ControlTransition` described as lossless/exact | stores independent summaries and compatibility reconstruction | closure withdrawn; R2 required |
| A.2 says selector owner converged | selector class is sole plan constructor, but two production roots call it and independently finalize acquisition | selection component retained; lifecycle closure open |
| BrowserGym described as backend under unified world | benchmark composition delegates BrowserGym directly as a `WorldEnvironment` | R1 composition migration required |
| StaticEnvironment described as integrated on new contracts | two identical planless lifecycle implementations bypass selector/provider/fusion | delete/migrate in R1 |
| request-evidence no-gain intended to be need-specific | code compares whole-world/ActionSpace/task-evaluation digest | R3 migration required |
| capability view intended order-invariant | dict comprehension overwrites equivalent modality/assurance purposes | R1/R3 repair required |
| post-action source intended to follow binding lineage | generic path resolves surface owner then minimum-cost offer | R1 repair required |
| cancellation intended closed | receipts/root status exist, but no cancelled acquisition/execution/evaluation aggregate is returned | R1/R2 algebra required |

## 14. Current-practice comparison and bounded inference

Primary sources were rechecked on 2026-08-15:

- [OpenAI Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use)
  returns the updated screen in `computer_call_output`, correlates it with the
  same `call_id`, and carries response lineage via `previous_response_id`.
- [Anthropic Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
  defines a unique tool-use ID, requires one corresponding `tool_result`, keeps
  image/text/error in that correlated result, and requires result adjacency.
- [BrowserGym at fixed commit `9e779f0`](https://github.com/ServiceNow/BrowserGym/blob/9e779f087de9a65668b6974d11f9ce9816026e96/browsergym/core/src/browsergym/core/env.py#L616)
  pre-marks one page with BIDs and extracts DOM, AX tree, focused BID, element
  properties, and screenshot in one observation event.
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
  documents one shared internal state schema, separate bounded input/output
  schemas, and explicit reducers for state updates.

Inference, not source quotation: mature computer-use protocols conserve
request/result correlation; BrowserGym supplies shared physical identity; and
mature stateful runtimes separate internal authority from bounded I/O. The
smallest repository-specific response is exact immutable phase composition and
one reducer/coordinator per phase. It does not justify adopting any cited loop,
LangGraph, event sourcing, a ledger, or a workflow platform.

## 15. Fresh-context reviewer decision packet

The seven required answers are uniquely fixed as follows:

1. Authorities: `TaskGoal`; `ObservationSelectionPlan` by
   `ObservationOrchestrator`; closed `ObservationAcquisition` by one coordinator;
   `WorldObservation` by fusion; `ActionSpace`; exact admission outcome;
   `BoundActionRequest`; `ExecutionOutcome`; `EvaluationOutcome`;
   `ControlTransition`; and current `AgentLoopState`.
2. Projections: all model views/digests, compatibility/public result views,
   telemetry, snapshots, and benchmark DTOs are outward-only because they may
   truncate or copy facts and are forbidden inputs to authority owners.
3. Acquisition state machine: exactly the seven stages and legal shapes in
   section 4.1, with typed monotonic cancellation and partial fulfilment.
4. BrowserGym retains backend capture/extraction/BID/private execution and task
   source mechanics only; it loses selection, fusion, and public lifecycle
   finalization.
5. Fallback/cancellation/partial fulfilment are separate linked exact outcomes,
   reached-prefix cancellation facts, and explicit per-need results; none is
   merged into a freshness/summary DTO.
6. R1 changes/deletes acquisition owners and fixtures; R2 changes/deletes
   execution/evaluation/summary/Turn owners; R3 closes projections, no-gain,
   benchmark and test topology.
7. Current code still has second owners/schemas/compatibility paths; the frozen
   target and deletion gates permit none after R1–R3. R0 readiness is not an
   implementation or closure claim.

## 16. Independent fresh-context review result

An independent read-only reviewer with no inherited task context read only
`AGENTS.md`, this inventory, the convergence contract, authority map, current
plan, implementation status, and evolution plan. It answered all seven R0
questions uniquely and returned `PASS`.

The review specifically confirmed that the documents unambiguously distinguish
the current second acquisition roots, bypassing static substitutes, lossy
summary schemas, compatibility `Turn`, planless paths, and misplaced/narrow
execution aggregate from the frozen target that permits none of them. It also
confirmed one answer for the seven acquisition stages, BrowserGym's retained
backend duties, linked fallback/cancellation/partial-fulfilment semantics, and
the exact R1/R2/R3 modification and deletion gates. No corrective documentation
change was requested.
