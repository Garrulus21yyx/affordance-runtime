# Responsibility Containment Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** target module ownership and dependency direction

## 1. Ownership map

| Owner | Owns | Must not own |
|---|---|---|
| `AgentLoop` | serial turn sequencing and small loop state | surface parsing, policy reasoning, evaluation algorithms, telemetry persistence |
| `AgentPolicy` | next semantic decision | raw binding payload, execution, task completion |
| `TaskPlanner` | optional high-level Milestone hypothesis | GUI actions, binding, completion authority |
| `ObjectivePolicy` | current LocalObjective from task/plan/world | selector, route, action execution |
| `SurfaceRegistry` | adapter discovery/selection for observation | task meaning or route execution result |
| `SurfaceAdapter` | truthful observation, bindings, supported execution | global task planning or completion |
| `WorldFusion` | semantic entity/fact fusion and conflicts | action execution or user confirmation |
| `ActionSpaceBuilder` | current legal semantic options and barrier metadata | model choice or backend execution |
| `RouteSelector` | choose one current binding for a semantic action | effectful fallback execution |
| `ActionBinder` | ActionIntent + current binding → BoundActionRequest | confirmation semantics or evaluation |
| `RiskPolicy` | ALLOW/NEEDS_CONFIRMATION/BLOCK | executor capability discovery or token registry |
| `confirmation/` | semantic request/decision contracts and human-readable summary | surface payloads, BrowserSession, HTTP transport, registry |
| `AgentRunSession` | one in-memory run, pending confirmation, consumption and continuation counts | persistence, global lookup, cross-process resume |
| `Executor` | one BoundActionRequest → ActionResult | effect/task success judgment |
| `ActionEvaluator` | before/request/result/after → effect status | task completion |
| `evaluation/lineage.py` | exact request and before/after observation lineage validation | effect inference or task completion |
| `TaskEvaluator` | TaskGoal/EvaluationSpec + world/turns → task status | action dispatch |
| `task_evaluation_policy.py` | COMPLETE/INCOMPLETE/UNKNOWN/BLOCKED → loop control | task inference, observation, or execution |
| `LoopPolicy` | continue/reobserve/ask/stop | domain observation or execution |
| `TurnRecorder` | optional telemetry | admission, execution, state authority |
| `BindingCache` / Skill sidecars | currentness-checked hints and offline-evaluated templates | bypassing ActionSpace/RiskPolicy/evaluation or online publication |

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
by bounded recent turns.

Trace or recorder persistence is best effort and not part of state commit.

## 4. Anti-god-object rule

`ActionIntent` and `BoundActionRequest` cannot absorb authorization proof graphs,
plan state, trace, recovery policy, task completion, or audit artifacts. `AgentLoop` cannot absorb
surface extraction, policy, evaluators, or confirmation UI. A file-size review
trigger is useful, but split decisions follow responsibility, not class count.

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
adapters, benchmark task definitions, or legacy transaction owners. Current
Visual files are below 350 lines and contain no function above 80 lines.

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
sequences these owners. Target core, risk, confirmation, Visual, and WoT files
remain below 350 lines with functions below 80 lines; dependency tests reject
surface imports from risk/confirmation/agent and AgentLoop imports from adapters.

P5-D6.1 keeps the task-risk floor and semantic subject in `risk/`, destination
admission in `world/action_space.py`, bounded secret-free presentation in
`confirmation/summary.py`, terminal immutability in `agent/session.py`, exact
execution lineage in `evaluation/lineage.py`, and task-status control in
`agent/task_evaluation_policy.py`. Confirmation presentation reads semantic
world labels only; it never reads an `ActionBinding` payload.
