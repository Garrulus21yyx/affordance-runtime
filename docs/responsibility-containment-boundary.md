# Responsibility Containment Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** target module ownership and dependency direction

## 1. Ownership map

| Owner | Owns | Must not own |
|---|---|---|
| `AgentLoop` | serial turn sequencing and small loop state | surface parsing, policy reasoning, evaluation algorithms, telemetry persistence |
| `task/` | TaskGoal, bounded IntentContext and planning contracts | current route, model projection, binding or execution |
| `AgentPolicy` | next semantic decision | raw binding payload, execution, task completion |
| `TaskPlanner` | optional high-level Milestone hypothesis | GUI actions, binding, completion authority |
| `ObjectivePolicy` | current LocalObjective from task/plan/world | selector, route, action execution |
| `VerifiedTaskState` | validated milestone status, current frontier, evidence refs and unresolved obligations for one run | plan truth, action selection, persistence, replay |
| `TaskProgressAuditor` | evidence-scoped milestone/frontier promotion proposals | GUI action choice, task completion, local retry containment |
| `SurfaceRegistry` | adapter discovery/selection for observation | task meaning or route execution result |
| `SurfaceAdapter` | truthful observation, bindings, supported execution | global task planning or completion |
| `WorldEnvironment` acquisition boundary | reset initial acquisition, capability-aware capture, execute outcome with typed post acquisition | evidence assurance inflation, policy recovery, exception-as-capability protocol |
| `WorldFusion` | semantic entity/fact fusion and conflicts | action execution or user confirmation |
| `ActionSpaceBuilder` | current legal semantic options and barrier metadata | model choice or backend execution |
| `ActionRelevancePolicy` | DIRECT/ENABLING/INFORMATION/OTHER ranking and paging hints | legality, capability, risk lowering or completion |
| `RouteSelector` | choose one current binding for a semantic action | effectful fallback execution |
| `ActionBinder` | ActionIntent + current binding → BoundActionRequest | confirmation semantics or evaluation |
| `RiskPolicy` | ALLOW/NEEDS_CONFIRMATION/BLOCK | executor capability discovery or token registry |
| `confirmation/` | semantic request/decision contracts and human-readable summary | surface payloads, BrowserSession, HTTP transport, registry |
| `AgentRunSession` | one in-memory run, pending confirmation, consumption and continuation counts | persistence, global lookup, cross-process resume |
| `AgentLoopState` | authoritative current run control state and bounded transition suffix/total | durable log, replay reconstruction, surface/evaluator algorithms |
| `ControlTransition` accounting | one privacy-safe typed control boundary per accepted decision | state authority, event bus, persistence, low-level event taxonomy |
| `ProgressController` | local semantic-attempt digest and declared postcondition repetition containment | planner, milestone promotion, general task progress |
| `Executor` | one BoundActionRequest → ActionResult | effect/task success judgment |
| `ActionEvaluator` | before/request/result/after → effect status | task completion |
| `WorldEvidenceIndex` | current fact IDs and controlled artifact refs for one observation | artifact values, global provenance, or persistence |
| `evaluation/validation.py` | exact action/task lineage, criterion, and current evidence validation | effect inference, action execution, or model calls |
| `evaluation/output_validation.py` | requested-output membership and declared path/SHA-256 integrity | artifact storage, receipts, or legacy TaskSpec |
| `TaskEvaluator` | TaskGoal/EvaluationSpec + world/turns → task status | action dispatch |
| `task_evaluation_policy.py` | COMPLETE/INCOMPLETE/UNKNOWN/BLOCKED → loop control | task inference, observation, or execution |
| `LoopPolicy` | continue/reobserve/ask/stop | domain observation or execution |
| `TurnRecorder` | optional projection of transitions/current state for telemetry | admission, execution, transition/state authority |
| `BindingCache` / Skill sidecars | currentness-checked hints and offline-evaluated templates | bypassing ActionSpace/RiskPolicy/evaluation or online publication |
| `model_boundary/` | disposable AgentContext, one-way projection, ContextIdentity, budgets, paging, model-safe views and typed future provider failures | Runtime state, concrete adapters, binders/executors, provider SDKs or fixtures |

## 2. Dependency direction

```text
contracts
↑
surface adapters   policy   evaluators
        ↑            ↑         ↑
        └────── unified world ──┘
                       ↑
                   AgentLoop
                       ↑
                integrations/CLI
```

Core contracts do not import adapters, legacy StateKernel/delta/committer
types, benchmarks, or integrations. Surface modules may depend on contracts but
not on AgentLoop internals.

## 3. State boundary

Only `AgentLoop` mutates `AgentLoopState` in the target serial MVP. Functions
return domain results directly; they do not emit a universal internal command
language. Observation/action/evaluation records are immutable values referenced
by bounded recent ControlTransitions. Every accepted policy decision yields one
root transition; the exact total survives recent-window truncation.

Trace or recorder persistence is best effort and not part of state commit.
ControlTransition is in-memory run accounting and cannot be replayed to rebuild
AgentLoopState. VerifiedTaskState, when P5-E adds it, is a specialized field of
that state rather than another aggregate/store.

The reopened M4.5-B contract requires ordered physical execution/acquisition attempts,
expected/actual acquisition origins, strict probe totals and epoch-matched
evaluations in that accounting owner. AgentRunSession owns terminal latching and
non-re-entry; confirmation lifetime and current-risk closure stay in AgentLoop.
Benchmark Runtime/component/watchdog/cleanup/integrity precedence stays in the
target-loop projection owners. Neither projection can mutate Runtime authority.

## 4. Anti-god-object rule

`ActionIntent` and `BoundActionRequest` cannot absorb authorization proof graphs,
plan state, trace, recovery policy, task completion, or audit artifacts. `AgentLoop` cannot absorb
surface extraction, policy, evaluators, or confirmation UI. File/function LOC
is a review signal only, never an automatic build failure or split command.
Split decisions follow semantic authority, cohesive change reasons, dependency
direction and independent testability. A valid split moves a complete
responsibility; extracting arbitrary helpers merely to lower LOC is forbidden.

## 5. Migration containment

Current `ActionContract`, `ProgressStage`, `RecoveryStage`, `StateKernel`, and
`RuntimeCommitter` remain baseline owners until their vertical replacement is
default. New target modules cannot depend on them; temporary projectors point
legacy → new only. Old owner-specific tests are deleted with the owner after
default cutover.

The current DOM target path follows this boundary: `DomSurfaceAdapter` owns
`BrowserSession`; `UnifiedWorldEnvironment` owns adapter composition;
`ActionSpaceBuilder` owns membership; `ActionBinder` owns the current private
binding; and `TaskEvaluator` alone returns COMPLETE. `agent/` has no adapter or
browser import. The old ActionBatch helper remains an explicit compatibility
edge and is not part of this target call path.

The Visual-only target path follows the same boundary. `VisualSurfaceAdapter`
orchestrates screenshot acquisition and typed region proposals;
`surfaces/visual/contracts.py` owns immutable screenshot/viewport/region
identity; `currentness.py` owns pure comparison; and `execution.py` owns the
single point primitive. `BrowserSession` supplies only a narrow screenshot plus
viewport capture and pointer call. Visual modules do not import `agent/`, DOM
adapters, benchmark task definitions, or legacy transaction owners. File length
may prompt responsibility review but does not determine whether this ownership
is valid.

The WoT target path retains the existing TD/security parser as its sole
description authority. `surfaces/wot/contracts.py` owns immutable private route
identity and deployment scope; `transport.py` owns HTTP and credential
late-binding; `currentness.py` owns pure TD/affordance comparison; and
`adapter.py` owns SurfaceObservation/ActionResult orchestration and run-local
rate timestamps. It does not import AgentLoop, DOM/Visual adapters, benchmark
tasks, old ActionContract, or transaction owners. Physical/remote risk is
Runtime configuration, not TD authority.

P5-D keeps semantic subject canonicalization in `risk/`, confirmation contracts
and summaries in `confirmation/`, continuation state in `agent/session.py`, and
effect-certainty continuation in `agent/post_action_policy.py`. `AgentLoop`
sequences these owners. Dependency tests reject surface imports from
risk/confirmation/agent and AgentLoop imports from adapters; LOC does not
replace those semantic dependency gates.

P5-D6.1 keeps the task-risk floor and semantic subject in `risk/`, destination
admission in `world/action_space.py`, bounded secret-free presentation in
`confirmation/summary.py`, terminal immutability in `agent/session.py`, exact
execution lineage in `evaluation/lineage.py`, and task-status control in
`agent/task_evaluation_policy.py`. Confirmation presentation reads semantic
world labels only; it never reads an `ActionBinding` payload.

P5-M0 places model-safe values and projections in `model_boundary/`, current
evidence indexing and proposal validation in `evaluation/`, and only the
sequencing calls in AgentLoop. Source-local target IDs remain source-local;
the three-surface policy-view test proves shared semantic action vocabulary and
private-route isolation, not semantic fusion or cross-surface target identity.

P5-M0.1 keeps `ContextIdentity` and authoritative revisions inside Runtime and
projects only an opaque `context_id`. LocalObjective relevance may rank/page
already-legal actions but cannot add an action, lower risk or affect completion.
The implemented split keeps policy routing in `agent/decision_control.py`, the
single execution cycle in `agent/execution_cycle.py`, bounded projection in
`model_boundary/`, and relevance/paging in `world/`. AgentLoop is reviewed by
orchestration responsibility and collaborator direction, not a 300-line gate.
P5-M0.1.1 adds only narrow owners: `agent/observation_control.py` enforces fresh
acquisition identity, `model_boundary/task_projection.py` owns truthful task
sections, and `world/evidence_refs.py` canonicalizes value-free public evidence
identity. No ContextStore, page database, revision service or new Runtime state
aggregate was introduced.
P5-M1 places the provider-neutral request/response port, canonical serializer,
fixed authority prompt, strict parser and policy adapter in `model_policy/`.
That package imports neither concrete surfaces nor Binder/Executor; AgentLoop
continues to depend only on the `AgentPolicy` protocol. Raw responses stop at
the parser and raw provider failures stop at the policy boundary.
P5-M1.1 keeps provider HTTP, credentials, response extraction and
`ModelCallRecord` in the existing `model_port.py` owner. The thin bridge owns
only system/user composition, canonical schema selection, typed failure mapping
and secret-free metadata copying; it forces zero retries, rejects fallback and
is bounded by the policy deadline.
P5-M2 keeps criterion normalization, current evidence records, mechanical
checking, applicability and final status composition in `evaluation/`.
`model_evaluator/` owns only the strict semantic proposal schema and its thin
existing-ModelPort bridge; it cannot execute actions or emit task status.
P5-M2.1 adds `evaluation/action_verification.py` as the sole Runtime-derived
post-action obligation owner. `model_boundary/evaluator_views.py` owns the
semantic criterion/evidence request projection; its visible catalog is the
complete allowed-ref set for that judge call.
The target dependency gates additionally forbid AgentPolicy→binder/executor/
surface, model_boundary→concrete surface, confirmation→private binding,
evaluation→execution, telemetry→decision and production core→benchmark imports.
P5-M3 adds `benchmarks/target_loop/` as a harness-only owner. It may construct
fresh target-loop composition, count forwarded calls, compare post-run oracles,
and serialize secret-free reports. It may not execute actions, import the old
Coordinator, expose private bindings, or influence policy/evaluator inputs.
Target production core and surface adapters do not import this package.
P5-M3.1 keeps mutable counters in harness-only `instrumentation.py`, declarative
oracles in immutable manifests, and report hashing in `attestation.py`.
`real_adapter_support.py` composes existing public adapters and owns only fixture
resource lifecycle; it does not copy adapters or execute around Runtime.
P5-M3.2 adds `benchmarks/external_smoke/` as an optional, preflight-first owner.
It owns only the reviewed manifest, mechanical verifier adapter contract,
attestation evidence comparison, execution gates, and secret-free reporting.
It is not imported by target production core or surfaces, cannot call Binder or
Executor directly, and cannot place benchmark oracle material in AgentContext.
The existing BrowserGym package remains isolated; its target-loop
`WorldEnvironment` lifecycle wrapper is now closed only for the pinned,
reviewed MiniWoB mechanical profile. It cannot itself admit a live run.
P5-M3.3 adds `benchmarks/model_conformance/` as a diagnostic-only owner for
exact profile identity, levels, grounding variants, complexity, classification
and secret-free attestation. It may call the existing ModelPort and target-loop
public composition but cannot change ActionSpace, parser, admission, risk or
evaluation. `model_policy/grounding.py` derives a bounded guide only from
already-public serialized AgentContext; the default bridge does not enable it.
Production core never imports model-conformance diagnostics.

P5-M3.5 keeps v2 ownership split without creating a second legality system:
`model_policy/grounding.py` exposes profile selection, `grounding_v2.py`
projects only serialized public AgentContext, and benchmark recurrent modules
measure/replay decisions through production control. AgentLoop does not import
grounding selection; production core does not import conformance; expected
answers never enter AgentContext; parser, ActionSpace and admission remain
unchanged.

P5-M3.6 adds no production owner. The two-stage route and dynamically narrowed
payload schemas live only in model-conformance. A route proposal cannot execute
or enter AgentLoop state; the complete stage-two object still passes the
canonical strict parser and existing Runtime control. Production policy,
factory, AgentLoop, ActionSpace, admission, and target adapters do not import
the diagnostic package. Dynamic schema narrowing is provider guidance, never a
second legality authority.

P5-M3.4 moves the two production grounding variants and their profile versions
into `model_policy/grounding.py`; benchmark diagnostic variants remain in
`benchmarks/model_conformance/grounding.py`. `schema_identity.py` owns only the
canonical deterministic schema digest. The decision matrix and cutover checker
remain benchmark-only: they cannot select production grounding, repair model
output, modify ActionSpace/admission, or influence AgentLoop behavior.

At the P5-M4 baseline, six narrow benchmark owners split the normal snapshot
path: `browsergym_environment` owned reset/step cache composition,
`browsergym_projection` owned bounded structural
projection, `browsergym_binding` owns short-lived private handles,
`browsergym_execution` owns canonical-to-official action conversion,
`browsergym_verifier` owns current official status, and `composition` owns the
TaskGoal/evaluator wiring. The BrowserGym page and bids never cross this
package boundary. Pacing and live execution are benchmark-only; they do not
enter model-policy core or AgentLoop. The scripted conformance decision port
uses only serialized public context and cannot read task IDs or expected action
sequences.

M4.5-A preserves those mechanics owners while replacing the public cache relay.
`browsergym_environment` now orchestrates prepared logical reset, execute-
returned post acquisition and independent capture; `browsergym_backend` owns
the pinned page/thread and read-only current-world operation. AgentLoop learns
no task IDs and adds no backend-specific recovery branch.

M4.6-A narrows BrowserGym currentness authority further. The exact owner map is:

- `browsergym_semantic_profile` alone owns the current finite observable and
  executable role algebra, semantic action, primitive, currentness state fields
  and primitive availability requirements;
- `browsergym_semantics` alone owns immutable canonical AX controls: computed
  role, accessible name, typed role state, availability, owner-scoped public and
  private select domains, public/currentness fingerprints, exact duplicate
  removal and typed same-BID/node/owner conflict rejection;
- `browsergym_currentness` alone performs the pure captured-versus-live
  comparison and returns bounded adapter-local reasons;
- `browsergym_backend` owns only owner-thread pinned observation reads,
  frame-safe BID physical availability/native option reads and physical step;
- `browsergym_projection` owns WorldObservation/target/fact assembly only, and
  `browsergym_binding` owns the immutable private binding plus public-label to
  native-value dispatch mapping.

The former semantic owners were deleted: projection no longer derives the
role/action/state/options/fingerprint algebra, binding no longer constructs a
semantic fingerprint, backend no longer reconstructs role/name/state with a
DOM heuristic, and whole-page option reuse is removed. No BrowserGym page,
locator, element handle, BID, selector, native option value or private
fingerprint crosses into public world/model facts.

## P5-M4.2 narrow owners

P5-M4.2 adds three narrow owners without changing those imports:
`browsergym_action_evaluator` owns only fill/select public postconditions;
`agent/progress_control` owns run-scoped semantic digests and
execute/suppress/terminate disposition; `agent/session_snapshot` owns a
read-only privacy-safe in-flight view. Progress projection cannot modify
ActionSpace, choose a replacement action, import benchmark IDs, retain raw
parameters, bind BrowserGym routes, or resume a timed-out session.

`benchmarks/external_breadth` owns registry census, offline capability labels,
deterministic manifest selection, serial orchestration, typed post-run
classification, and privacy-bounded evidence. It reuses the existing
BrowserGym environment and target-loop runner. Neither inventory nor task ID
enters TaskGoal, AgentContext, ActionSpace, or policy metadata. Campaign
classification cannot change Runtime, adapter projection, progress control,
prompt, retry, fallback, or the next action. Atomic progress is observational
only and is never resume, skip, replay, or backfill authority.

P5-M4.4 keeps failure origin in the surface-neutral target-loop benchmark
contract and component wrappers. `external_breadth` owns only MiniWoB taxonomy,
source-bound requirements, offline overlays, local probes, and rerun readiness.
Neither capability readiness nor diagnostic disposition enters AgentContext,
ActionSpace, BrowserGym adapter behavior, Runtime admission, or policy control.

## P5-M4.5 and P5-E narrow owners

M4.5-A keeps operational observation capability/outcome contracts in `world/`,
adapter implementation in its environment owner, and capture selection/budget
sequencing in `agent/observation_control.py`. Evidence assurance remains in
WorldObservation/evaluation owners. No owner may infer capability from evidence
quality or turn a typed unavailable result into a generic recovery transaction.

M4.5-B must converge on one narrow pure control reducer under `agent/`.
AgentLoop supplies typed serial inputs and `AgentLoopState` remains current-state
authority; the reducer validates legal transitions but cannot execute, evaluate,
persist, replay or reconstruct state. Session snapshot, model history and
benchmark reports consume one-way projections instead of reassembling truth.

The convergence contract makes reducer facts decision-scoped and monotonic: execution,
acquisition, after identity, evaluation and progress are staged independently;
`Turn` is only a read-only compatibility projection. AgentLoop owns the single
confirmation closure path, `session_snapshot.py` reads current evaluation only
from AgentLoopState, and `benchmarks/target_loop/case_projection.py` alone owns
benchmark-specific typed precedence. Model projection does not import or serve
the benchmark projection.

P5-E reuses `task/planning_contracts.py`. VerifiedTaskState/milestone promotion
and TaskProgressAuditor stay under task/evaluation ownership; ObjectivePolicy
derives LocalObjective from the verified frontier. `agent/progress_control.py`
continues to own only local fill/select repetition containment. Neither auditor
nor controller may choose a replacement action, modify ActionSpace legality, or
substitute for AgentPolicy/TaskPlanner.
