# Runtime authority aggregate convergence

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-15
> **Scope:** end-to-end authority conservation, phase aggregates, composition roots, and projections in the target GUI loop
> **Status:** `R0_REVIEW_COMPLETE / CONTRACT_ALGEBRA_FROZEN / CONSUMER_INVENTORY_COMPLETE / ATOMIC_MIGRATION_MAP_READY / R1_IMPLEMENTATION_READY / A.2_STILL_OPEN / LIVE_NOT_RUN`
> **Target:** [Target AgentLoop Authority Map](task-execution-authority-map.md)
> **Implementation truth:** [Implementation Status](implementation-status.md)
> **R0 evidence:** [Runtime authority R0 consumer inventory](evidence/2026-08-15-runtime-authority-r0-consumer-inventory.md)

## 1. Decision

The target Runtime uses one authoritative chain. “One chain” does not mean one
global god object. It means:

1. every causal phase has exactly one immutable, closed aggregate;
2. a later phase composes the earlier aggregate instead of copying a subset of
   its fields into another authoritative DTO;
3. each aggregate has one construction/state-transition owner;
4. model, telemetry, benchmark and persistence values are one-way projections
   and never return as Runtime authority;
5. a request/result pair keeps one correlation identity and one typed outcome
   across success, partial success, unavailable, failure and cancellation;
6. displaced compatibility owners and their tests are deleted in the same
   migration, without read-new/fallback-old or dual-write periods.

The target chain is:

```text
TaskGoal
  -> ObservationAcquisition
       request -> plan -> provider activations -> fusion outcome
  -> WorldObservation
  -> ActionSpace
  -> AgentContextView + ToolCatalogView       (disposable)
  -> AgentDecision
  -> ActionAdmissionOutcome
  -> BoundActionRequest
  -> ExecutionOutcome
       bound request -> ActionResult -> exact post acquisition, if dispatched
  -> EvaluationOutcome
       before world + execution/observation lineage + evaluations
  -> ControlTransition
       exact decision-scoped aggregate composition + resulting loop status
  -> AgentLoopState
  -> next disposable context views
```

Large media and world payloads are not serialized repeatedly. Immutable object
references or IDs into the same run-scoped owner may be composed. “Closed”
means every authoritative fact remains reachable and correlated, not that bytes
are copied into every object.

## 2. Why the work repeatedly reopened

The A.2 reopenings are not independent defects. They are manifestations of one
missing end-to-end invariant.

### 2.1 Confirmed causal chain

```text
SelectedObservationRequest / SelectedObservationResult
  -> SourceAcquisitionResult                  (request identity narrowed)
  -> ObservationAcquisition                   (acquisition ID/request absent)
  -> FreshAcquisition                         (plan/source/need results absent)
  -> AcquisitionSummary                       (observation and need outcome absent)
  -> AgentTransitionDigestView                (cannot report the requested need)
```

Each type is locally valid, but the sequence is globally lossy. The next
consumer therefore guesses from `status`, `reason_code`, a whole-world digest,
or a fresh observation. That is why a successfully acquired source can be
mistaken for a fulfilled semantic need, an unrelated world change can be
mistaken for information gain, and a post-selection failure can return without
the plan that caused it.

### 2.2 Reopening manifestations

| Manifestation | Category | Shared cause |
|---|---|---|
| provider requests originally received only a reason/source approximation | contract loss | selected request aggregate did not cross the port |
| generic stage two and post-action fallback dropped needs | lifecycle loss | fallback rebuilt a smaller outcome instead of composing the original request |
| source acquisition success was equated with all needs fulfilled | state algebra ambiguity | physical result and epistemic result were not independently closed |
| `FreshAcquisition` drops `selection_plan`, source results and need results | projection used as authority | a convenience DTO replaced the public aggregate |
| `request_evidence` measures whole-world digest gain | consumer reconstruction | the exact requested need result is no longer reachable |
| BrowserGym failures after selection return planless acquisitions | exceptional-path loss | broad exception handling reconstructs a smaller failure value |
| `UnifiedWorldEnvironment` and `BrowserGymEnvironment` both select, activate, fuse and finalize | duplicated composition root | the same lifecycle has two production state machines |
| capability projection overwrites same modality/assurance offers by input order | projection algebra bug | the view reconstructs capability truth with a lossy dictionary key |
| post-action route source is inferred from surface/minimum cost | lineage reconstruction | executed binding lineage is not consumed directly |
| static environments construct planless acquisitions directly | verification defect | most loop tests bypass the production request/plan/result contract |
| `ControlTransition` calls itself lossless while retaining `ExecutionSummary` and `AcquisitionSummary` | documentation and architecture defect | summaries are treated as canonical accounting inputs |

The previous tests were useful regression witnesses, but they proved producer-
local examples rather than conservation through every owner and consumer. A
new counterexample therefore found the next narrowing boundary. Closure is now
withdrawn until the whole causal surface satisfies the properties in section
11.

## 3. Global authority law

### 3.1 Authoritative aggregate versus projection

An authoritative aggregate:

- is typed and immutable at the public boundary;
- contains or references its exact authoritative input;
- closes its supported state/outcome algebra;
- enforces request/result correlation and temporal ordering;
- is constructed or transitioned by one owner;
- may be consumed by Runtime control, admission or evaluation.

A projection:

- has a `View`, `Digest`, `Summary`, `Telemetry` or benchmark-specific name;
- is bounded, public-safe and disposable;
- may omit information with truthful truncation metadata;
- cannot be accepted by Runtime control, admission, binding, execution,
  evaluation, fusion or currentness APIs;
- cannot be used to reconstruct an authoritative aggregate.

No type may be both a lossy projection and a control authority. This forbids
the current `FreshAcquisition` and `AcquisitionSummary` pattern.

### 3.2 Composition, not field repetition

Later aggregates retain the earlier typed value:

```python
@dataclass(frozen=True)
class ExecutionOutcome:
    request: BoundActionRequest
    result: ActionResult
    post_acquisition: ObservationAcquisition | None

@dataclass(frozen=True)
class FreshObservationOutcome:
    acquisition: ObservationAcquisition
    expected_origin: AcquisitionOrigin
    freshness: FreshnessStatus
```

They do not copy `request_id`, dispatch status, origin, reason and selected
need IDs into a second writable representation. Convenience properties may
derive those values but cannot store independent truth.

### 3.3 Closed supported algebra

Unknown or unsupported cases fail typed and deterministically. Open provider,
surface and future-action extensibility does not permit an open lifecycle
algebra or free-text fallback.

No action family, source modality, benchmark or provider gets a private
lifecycle variant. A surface may implement private mechanics behind the same
aggregate port.

## 4. Owners across the whole loop

| Authority | Sole owner | Exact output | Consumers may not do |
|---|---|---|---|
| task meaning | `TaskGoal` / intake | task boundary and revision | infer task meaning from page/tool/benchmark |
| source selection | `ObservationOrchestrator` | immutable `ObservationSelectionPlan` | adapter mutation or fallback selection |
| acquisition state machine | `AcquisitionCoordinator` inside the one product `WorldEnvironment` | closed `ObservationAcquisition` | reconstruct from status/reason |
| backend capture | `SurfaceAdapter` / grouped adapter | request-correlated provider result | select extra sources or claim unobserved need satisfaction |
| alignment/fusion | `WorldFusion` | typed fusion outcome and canonical world | acquire/select sources or invent action legality |
| current world | `WorldObservation` | canonical graph, evidence lineage and source links | Actor/tool projection re-fusion |
| interaction semantics | `InteractionCapabilityRegistry` | canonical action definitions | adapter/model vocabulary forks |
| current legal actions | `ActionSpaceBuilder` / `ActionSpace` | observation-bound options and bindings | tool catalog authorization |
| public action factoring | `GroundedToolCompiler` | ToolSpecs + private exact-resolution relation | provider regrouping or fuzzy legality |
| decision | `AgentPolicy` + Runtime parser | context-bound `AgentDecision` | direct binding/execution/completion |
| admission | Runtime action/control admission | typed admission outcome | provider/adapter self-admission |
| private bind/currentness | `ActionBinder` plus route/currentness owners | `BoundActionRequest` | model selector/coordinate authority |
| dispatch | selected surface executor | `ActionResult` | effect or completion claim |
| execution closure | `ExecutionCoordinator` | exact `ExecutionOutcome` | caller-side request/result reassembly |
| effect/task truth | action/task evaluators | `EvaluationOutcome` | executor/model narration as truth |
| one decision transition | transition reducer | `ControlTransition` composed from exact outcomes | summary reconstruction or telemetry mutation |
| current run state | `AgentLoopState` | serial current control state | replay from transition/model history |
| model presentation | context/tool/transition projectors | disposable views | round-trip back into Runtime authority |

`AcquisitionCoordinator` and `ExecutionCoordinator` are cohesive orchestration
responsibilities, not new frameworks or services. They may be small existing
module owners. The design does not introduce a bus, ledger, event sourcing,
database, distributed workflow engine or graph store.

## 5. ObservationAcquisition target contract

The observation aggregate becomes the only public truth for one acquisition:

```python
@dataclass(frozen=True)
class ProviderActivation:
    request: SelectedObservationRequest
    result: SelectedObservationResult

@dataclass(frozen=True)
class ObservationAcquisition:
    acquisition_id: str
    origin: AcquisitionOrigin
    request: WorldObservationRequest
    stage: AcquisitionStage
    plan: ObservationSelectionPlan | None
    activations: tuple[ProviderActivation, ...]
    fusion: WorldFusionResult | None
    status: AcquisitionStatus
    reason_code: str

    @property
    def observation(self) -> WorldObservation | None: ...
```

`observation` is derived from the fusion outcome; it is not an independently
writable second field. The plan already records unselected offers, so an
unselected source does not need a fabricated acquisition result. Every selected
source has exactly one activation pairing its selected request and result.

The bounded stages are:

| Stage | Required shape |
|---|---|
| `PRE_SELECTION_UNAVAILABLE` | request present; no plan/activation/fusion |
| `INITIALIZATION_FAILED` | request and final plan present when selection occurred; typed init failure |
| `SOURCE_ACQUISITION_FAILED` | plan and all selected activation outcomes present; no successful fusion |
| `FUSION_FAILED` | plan and activation outcomes present; failed typed fusion outcome |
| `CANCELLED` | exact request and every outcome reached before cancellation retained; no later stage fabricated |
| `ACQUIRED_ALL_NEEDS_FULFILLED` | fused world present; every selected need fulfilled |
| `ACQUIRED_WITH_UNRESOLVED_NEEDS` | fused world present; at least one selected need explicitly unresolved |

`CAPABILITY_UNAVAILABLE`, `FAILED`, `CANCELLED` and `ACQUIRED` are top-level statuses,
but stage determines the legal object shape. `ACQUIRED` never means that all
semantic needs were fulfilled.

Cancellation is not swallowed. The owning coordinator first closes a typed
cancelled aggregate/attempt into the active decision scope, then propagates the
host cancellation. A cancellation before provider dispatch records no
activation; cancellation after one or more provider results retains those
results and marks only the unfinished selected requests cancelled.

Reset uses an explicit initial-grounding `WorldObservationRequest`; it does not
become a special planless success path. The acquisition ID is created once by
the coordinator and conserved through both bounded stages and every provider
activation.

### 5.1 Freshness and fallback

Freshness is relative to a prior observation and therefore wraps the original
aggregate:

```text
FreshObservationOutcome
  acquisition = exact original ObservationAcquisition
  expected_origin
  freshness = fresh | reused | not_acquired | origin_mismatch
```

It never replaces the aggregate. Post-action fallback is a second, explicitly
linked independent acquisition with the original verification needs. It is not
merged into a synthetic `FreshAcquisition`. The decision-scoped transition
retains the primary execution acquisition and the bounded fallback separately
and records which observation evaluation consumed.

## 6. Execution, evaluation and transition closure

### 6.1 ExecutionOutcome

The authoritative execution aggregate composes the exact bound request:

```text
ExecutionOutcome
  request: BoundActionRequest
  result: ActionResult
  post_acquisition: ObservationAcquisition | None
```

Invariants:

- request/result identities and backend route match;
- `NOT_SENT` has no fabricated post-action acquisition;
- `SENT` and `SENT_UNKNOWN` retain exactly one typed primary post-action
  acquisition, including failed/unavailable acquisition truth;
- post-action acquisition failure cannot rewrite dispatch truth;
- no hidden executor retry or effectful route fallback occurs;
- a proven `NOT_SENT` route may enter the existing bounded reroute policy as a
  new exact execution attempt, never by mutating the first outcome.

Cancellation before dispatch is typed `NOT_SENT`; cancellation after dispatch
has crossed the uncertainty boundary and is typed `SENT_UNKNOWN`. In both
cases the decision scope retains the exact outcome before host cancellation
propagates.

### 6.2 Temporal and idempotency rules

- acquisition and execution attempt IDs are unique and monotonic within one
  `AgentRunSession`;
- one selected source request has exactly one terminal result;
- one physical acquisition group is invoked at most once per acquisition;
- lifecycle stages only advance; a later fact cannot erase an earlier request,
  plan, activation or dispatch receipt;
- a fallback is a new linked acquisition ID, never mutation/retry of the
  primary acquisition;
- one accepted decision root is finalized once; an admitted confirmation/user
  continuation may replace that exact root slot once under its existing source
  identity, never append a duplicate policy decision.

### 6.3 EvaluationOutcome

One evaluation aggregate correlates:

- before observation identity;
- the exact execution outcome or exact observation acquisition that triggered
  evaluation;
- the after observation identity actually consumed;
- `ActionEvaluation`, when an action was dispatched;
- `TaskEvaluation`;
- later, the comparable `SemanticDelta` owned by the same evaluation boundary.

An evaluator may use a bounded model verifier, but its proposal is validated
against the same observation/evidence lineage before entering the aggregate.

### 6.4 ControlTransition

`ControlTransition` remains decision-scoped, run-scoped, bounded and non-
replayable. It is the exact closure of one accepted decision, not a summary
container:

```text
ControlTransition
  decision
  exact admission outcome, if applicable
  exact decision outcome:
    observation acquisitions, or
    execution attempts + fallback acquisition, or
    page/user/wait/done/abort typed outcome
  exact evaluation outcome, if applicable
  progress/control result
  resulting AgentLoop status
```

`AdmissionSummary`, `ExecutionSummary`, `AcquisitionSummary` and compatibility
`Turn` are deleted after consumers migrate. Attempt receipts remain optional
ordered observability facts; they cannot replace or reconstruct the exact
outcomes.

## 7. Model-facing contract

The model receives three independent one-way views:

```text
ActorWorldView       what exists, with bounded structure/evidence/media
ToolCatalogView      what can be selected now
TransitionView       what the last accepted decision caused
```

The same E-ref may connect a visible entity and a tool during one context, but
neither view repeats or owns the other's full content. Tools factor shared
semantic skeletons and expose only candidate differences. The world view keeps
canonical hierarchy and evidence once; it never flattens DOM/AX/visual/WoT into
parallel dumps.

The Agent remains allowed to issue semantic `request_evidence`. This is
intentional: open semantic uncertainty may be visible to the model but not
mechanically detectable by Runtime. The call names purpose, current public
subject and optional evidence property; it cannot name a source, provider,
selector or route. Runtime admits it against current capability offers,
freshness, subject and no-gain state.

The next transition view must report the result of that exact need:

```text
requested need -> fulfilled | unresolved | unavailable | failed | no_gain
```

No-gain is computed from the requested need outcome and relevant canonical
change, not from an unrelated whole-world digest. A currently satisfied need
returns typed zero-provider `no_gain`. The capability view unions purposes for
equivalent modality/assurance offers and is invariant to offer order.

## 8. One acquisition composition root

`UnifiedWorldEnvironment` (or its renamed coordinator façade) is the sole
product acquisition state machine. It owns:

```text
request -> selection -> lifecycle initialization -> provider activation
        -> optional bounded residual stage -> fusion -> aggregate finalization
```

BrowserGym remains the established backend for browser capture, AX/DOM/BID,
screenshot and execution. It becomes a grouped `SurfaceAdapter`/backend behind
that coordinator. It must not independently select sources, run fusion or
construct a competing `ObservationAcquisition` lifecycle.

Post-action route-source selection follows exact lineage:

```text
BoundActionRequest.binding.source_observation_id
  -> current WorldObservation source manifest
  -> selected offer/source owner
```

It is never inferred from a surface name, input order or lowest cost.

The current duplicated static environments are not accepted contract proofs.
Tests and scripted benchmarks use a contract-faithful scripted
`SurfaceAdapter` behind the same production coordinator. The compatibility
`observations` queue and direct planless acquisition constructors are deleted.
Benchmark-only orchestration remains outside production, but it cannot bypass
the public lifecycle it claims to verify.

## 9. Target package boundaries

The existing owner packages are retained; no new platform layer is required:

```text
app/          intake, composition and public Runtime façade
agent/        AgentLoop, session, decision routing, reducer and current state
world/        acquisition contracts/coordinator, canonical world and fusion
actions/      capability registry, ActionSpace, admission, binding and routing
execution/    BoundActionRequest, ActionResult and exact ExecutionOutcome
evaluation/   action/task evaluation and comparable semantic delta
model/        provider transport and disposable model-facing projections
surfaces/     backend adapters and private primitives
benchmarks/   manifests, runners and evidence only
tests/        contract-faithful adapters, properties and integration tests
```

Concrete cleanup targets:

- move `ExecutionOutcome` out of `world/acquisition.py` into `execution/`;
- replace `agent/observation_control.FreshAcquisition` with a wrapper that
  retains the exact aggregate;
- remove acquisition/execution summaries and `Turn` reconstruction from
  `agent/control_transition.py`;
- remove selection/fusion/finalization from BrowserGym's environment wrapper;
- converge the two copied static environments onto one contract-faithful
  adapter strategy;
- remove old constructors, compatibility inputs and their sole-purpose tests
  in the same commits;
- retain `grounded_tools.v2` as the only product model protocol and keep
  provider transport business-neutral.

## 10. SOTA and mature-practice alignment

This exact cross-surface aggregate schema is this project's engineering
contract; it is not copied from one paper or framework. Its principles align
with current computer-use protocols and mature agent runtimes:

- [OpenAI Computer Use](https://developers.openai.com/api/docs/guides/tools-computer-use)
  pairs each `computer_call` and `computer_call_output` with the same
  `call_id`, returns the updated screenshot as the exact tool result and
  carries response lineage across the loop.
- [Anthropic computer use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
  requires the complete assistant tool-use response to be followed by a
  `tool_result` with the matching `tool_use_id`; image, text and error remain
  parts of that correlated result.
- [BrowserGym's observation implementation](https://github.com/ServiceNow/BrowserGym/blob/9e779f087de9a65668b6974d11f9ce9816026e96/browsergym/core/src/browsergym/core/env.py)
  obtains DOM, AX, focused element, element properties and screenshot from one
  observation event and uses shared BIDs rather than independently reconstructing
  identity downstream.
- [LangGraph's Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
  uses one shared internal state schema with explicit input/output schemas and
  reducers, rather than letting nodes exchange unrelated authoritative DTOs.

The inference for this repository is: exact correlation, one internal state
schema per causal transaction, reducer-owned transitions and separate output
views are current mature practice. It does **not** imply adopting LangGraph,
OpenAI's loop, Anthropic's loop, an event ledger or another automation engine.
BrowserGym/Playwright/OmniParser remain delegated mechanics; the repository
owns only its cross-surface semantic authority and bounded composition.

## 11. Migration and falsifiable exit criteria

### R0 — contract and redline freeze

- freeze the aggregate/state algebras above as the implementation contract;
- inventory every constructor, consumer, exceptional path, projection,
  benchmark and test double;
- add architecture redlines for one acquisition coordinator and non-authority
  of `*View/*Digest/*Summary`;
- do not add new interaction families, StateFact producers or SemanticDelta
  implementation in this slice.

R0 is complete as a documentation and audit slice. The source-proven inventory,
legal shapes, constructor/consumer classification, per-file migration order,
deletion gates and property matrix are recorded in the linked R0 evidence.
This status creates no production shadow types and does not claim that any R1,
R2 or R3 target owner is implemented.

### R1 — acquisition single-path cutover

- implement the closed `ObservationAcquisition` aggregate;
- migrate generic DOM/Visual/WoT/HTTP and BrowserGym grouped acquisition to one
  coordinator;
- conserve request, acquisition ID, plan, every selected activation, need
  result and fusion outcome across all failures;
- fix order-independent capability union and exact binding-source routing;
- delete `FreshAcquisition`, BrowserGym's second lifecycle and direct static
  environment acquisition construction.

### R2 — execution/evaluation/transition composition

- make `ExecutionOutcome` compose exact request/result/post acquisition;
- retain primary and bounded fallback acquisitions separately;
- make `EvaluationOutcome` correlate the exact consumed evidence;
- make `ControlTransition` compose exact outcomes and delete summary owners and
  compatibility `Turn` reconstruction.

### R3 — one-way projections and test topology

- project model feedback from exact aggregates, including requested-need
  outcome;
- guarantee world/tool/transition projections are one-way and order-invariant;
- migrate unit/integration/benchmark fixtures to contract-faithful adapters;
- delete compatibility constructors, duplicate fixtures and stale tests;
- update package/document authority maps together.

Dependent StateFact/relation/SemanticDelta work and new `scroll/press_key`
bindings resume only after R1–R3 satisfy their declared gates. Activate-effect
authority may be implemented independently only if it does not depend on a
lossy transition/acquisition projection.

Closure requires all of the following:

- one causal explanation accounts for every known A.2 reopening;
- every supported acquisition state has one legal aggregate shape;
- request, plan, selected provider requests/results, per-need outcomes, fusion
  and final status are conserved on success, partial success and every failure
  stage;
- one product coordinator owns acquisition; BrowserGym and test fixtures do
  not implement alternate state machines;
- exact execution and evaluation outcomes remain reachable from the matching
  `ControlTransition` without reconstruction from summaries;
- projections cannot be passed to any authority API and are invariant to
  source/offer input order;
- model `request_evidence` feedback identifies the exact requested need result;
- property/model-based tests cover the closed state machine, exceptional paths,
  cancellation, bounded reroute/fallback and partial fulfillment;
- held-out generated structural-only, two-source, partial-need, source-failure,
  fusion-failure, post-action and no-gain cases pass without a new production
  branch per witness;
- a fresh-context independent review finds no second owner or lossy control
  projection;
- implementation, tests, documents and status agree before any closure label;
- benchmark runs follow architecture closure and remain the final generalization
  evidence, not a substitute for these invariants.

## 12. Non-goals

- no event sourcing, ledger, replay, checkpoint or durable workflow platform;
- no graph database or replacement for BrowserGym/Playwright/OmniParser;
- no full history or raw multi-source dump in model context;
- no one-object global Runtime state;
- no benchmark-, provider-, task- or surface-specific lifecycle branch;
- no attempt to enumerate hypothetical future modalities or actions;
- no capability expansion until the shared spine it depends on is conserved.
