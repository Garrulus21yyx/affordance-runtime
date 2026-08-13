# Target AgentLoop Authority Map

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-13
> **Scope:** target GUI AgentLoop only
> **Implementation truth:** [Implementation Status](implementation-status.md)

## Decision

The target GUI loop is an observation-grounded rolling-horizon agent. It does
not run the business-workflow `TaskSpec -> TaskPlan -> Coordinator` pipeline and
does not require an exact page target before the first observation.

```text
UserRequest
  -> Thin Intake
  -> TaskGoal + bounded IntentContext(context_only)
  -> AgentLoop
       observe -> WorldObservation
       -> internal ActionSpace(TaskGoal legality + current availability)
       -> LocalObjectiveProposalPort (only when no objective is active)
       -> Runtime admission -> one local_objective_state
       -> disposable AgentContext
       -> AgentPolicy.decide (current action/control only)
       -> one typed AgentDecision
       -> context/action membership admission
       -> ActionIntent
       -> risk/confirmation
       -> currentness check
       -> private bind
       -> execute once
       -> fresh observation
       -> ActionEvaluation + TaskEvaluation
       -> serial AgentLoopState
       -> continue/reobserve/ask/wait/done/abort
       -> AskUser pause -> admitted next TaskGoal revision -> same session
```

`TaskSpec`, `TaskPlan`, `TaskPlanAuthority`, `StateKernel`, and `Coordinator`
remain the canonical contracts and owners for the separate transactional
workflow runtime. They are not an ingress or hidden capability of `AgentLoop`.

## Authority and lifecycle owners

| Stage | Owner | Authoritative input | Output | Explicitly not owned here |
|---|---|---|---|---|
| task boundary | `TaskGoal` | thin intake | allowed/forbidden effects, risk, success boundary | DOM ID, E-ref, coordinate, route |
| task clarification | `TargetRuntime + AgentRunSession` | matching `UserInputRequest` + intake-admitted next revision | one-shot task revision and stale-projection invalidation | free-form patching, effect inference, physical reset |
| supplemental context | `IntentContext` | bounded source excerpts | context-only hints | task/effect authority |
| observed world | `WorldEnvironment` | current environment | `WorldObservation` | task semantics |
| legal actions | `ActionSpaceBuilder` | `TaskGoal + WorldObservation` | current internal `ActionSpace` | model, benchmark, LocalObjective |
| rolling semantic proposal | `LocalObjectiveProposalPort` | TaskGoal + bounded post-observation context | authority-free LocalObjective proposal or typed failure | admission, retained state, action choice |
| rolling relevance | one `LocalObjective` lifecycle | admitted proposal + current evidence | relevance/evidence/member state | whole-task planning, effect grants |
| model presentation | `ContextBuilder` | read-only current state | disposable `AgentContext` | retained truth, identity authority |
| choice | `AgentPolicy` | one AgentContext | typed context-bound action/control decision | objective construction, binding, executor route, completion truth |
| admission | AgentLoop decision/action admission | context identity + current ActionSpace | admitted selection or typed rejection | prompt compliance |
| execution route | currentness/binder/risk chain | admitted selection + fresh world | `BoundActionRequest` | model coordinates/selector |
| physical effect | environment executor | bound request | one result + post-action acquisition | semantic completion |
| effect/task truth | evaluators | result + fresh world + TaskGoal | action/task evaluations | executor receipt or model narration |
| benchmark | harness | manifest + public outcomes | measurements/evidence | production branches or task semantics |

## Identity timing

- Before observation: only task/source identities exist.
- At clarification: only the same task's exactly-next revision may replace task
  meaning; the matching AskUser root is consumed once and every old
  task-relative context/action projection becomes stale.
- At observation: Runtime may issue semantic entity IDs and private binding IDs.
- When `LocalObjectiveProposalPort` proposes a LocalObjective, it supplies only
  typed semantics; Runtime assigns objective, scope, and step identities after
  validation. The proposal is never an Agent action tool.
- In one AgentContext: the projection may issue call-local E-refs.
- At selection: Runtime accepts only the current ActionSpace member.
- Before execution: target and binding are revalidated against the current world.
- After a fresh observation: old E-refs, ActionSpace IDs, action IDs, and bindings
  are stale. A semantic LocalObjective may persist, but its entity resolution is
  recomputed.

No intake or planner may invent an exact DOM/entity target. No E-ref or model
point becomes durable identity.

`LocalObjectiveProposalPort` is an explicit AgentLoop composition dependency,
not a hidden `AgentPolicy` capability. Runtime validates its proposal against
the exact post-observation context and installs it in the sole
`local_objective_state` slot. The recurrent `AgentDecision` algebra contains no
objective constructor.

## LocalObjective and evidence

Set, sequence, and aggregate execution reducers are local rolling-horizon
variants, not TaskPlans. They share one `local_objective_state` lifecycle
slot. Their selectors are re-evaluated against each fresh observation.

DOM, derived geometry, and visual evidence use the same obligation lifecycle:

```text
LocalObjective evidence need
  -> source-capability router
  -> typed evidence result
  -> objective reducer
```

The source changes assurance and provider metadata only. It does not change
scope ownership, identity, action authority, binding, or completion rules.

## Projection rule

Projections are one-way and disposable. Runtime never reconstructs authoritative
task, objective, world, or binding state from AgentContext, a tool catalog,
E-ref, screenshot mark, tool result, benchmark row, or diagnostic trace.

Provider protocol adapters parse a model response exactly once into the typed
contract for that phase: either an authority-free `LocalObjective` proposal or
an action/control `AgentDecision`. They do not serialize either typed value back
to JSON for a second parser. The public context identity is validated against
the private current context whenever a protocol needs private grounding data.

The retained execution chain is deliberately short:

```text
TaskGoal boundary
  + current observation/action-space identity
  + optional current LocalObjective identity
  + admitted action
  + one result
  + fresh evaluation
```

No transitive provenance graph is required for ordinary GUI actions. Additional
lineage is retained only when a declared high-risk/material/evaluation contract
requires it.
No durable ledger, event replay, or projection-derived state is part of this
short-loop authority chain.

## Closed phase boundaries

The model-facing phases are disjoint:

```text
OBJECTIVE_PROPOSAL
  offered: one bounded LocalObjective proposal contract + non-effectful inspect/ask
  forbidden: click/fill/select/submit and current action IDs

ACTION_SELECTION
  offered: current Runtime action/control tools
  forbidden: predicate/scope/quantifier/aggregate/objective constructors
```

Changing predicate, scope, aggregate, or evidence-provider semantics therefore
does not change the recurrent action schema. Changing action presentation does
not change the LocalObjective contract. Both are disposable projections; only
Runtime-admitted `local_objective_state` and current ActionSpace membership are
authoritative.

## Removed wrong coupling

The following target-loop path was introduced and removed on 2026-08-13:

```text
AgentLoop.reset
  -> LLMIntentCompiler
  -> TaskSpecAuthority
  -> StrictTaskPlanner
  -> TaskPlanAuthority
  -> active StepSpec.execution
```

It was invalid for this loop because it duplicated semantic interpretation,
required workflow-style exact resource identity before GUI discovery, added
provider calls before the first decision, and made action-policy behavior depend
on a hidden preparer capability. Its preparer, decorator capability forwarding,
semantic-control mode, plan-progress state, and execution-control projection are
not compatibility paths; they are deleted from the target loop.

## Change admission

Before modifying a schema or state contract:

1. name the violated end-to-end invariant;
2. identify its single authoritative owner;
3. find the first boundary that loses, duplicates, or reinterprets it;
4. repair that owner/boundary once;
5. delete displaced paths in the same migration;
6. change a wire schema only when the canonical typed contract truly changed.

Benchmark cases are witnesses for shared properties. They do not authorize task
names, prose keyword routing, fixed candidate counts, or benchmark-specific
production branches.

## Exit properties

- AgentLoop has no `TaskSpec`, `AdmittedTaskSpec`, `TaskPlan`, or `TaskProgress`
  ingress/state.
- `AgentDecision` and recurrent action-tool catalogs contain no LocalObjective
  constructor or predicate/scope/aggregate transport.
- LocalObjective proposal and action selection are separate typed calls with
  separate schemas and exactly one parse each.
- No exact GUI target identity is required before `WorldObservation`.
- One fresh observation invalidates all call-local and route identities.
- Every dispatch is a current ActionSpace member and uses a current private
  binding.
- LocalObjective changes relevance and obligations but never grants an effect.
- Set/sequence/aggregate are variants of one local execution lifecycle.
- DOM/derived/vision evidence differ by source, not by lifecycle authority.
- AgentContext and grounded tools are disposable projections, never round-trip
  authority.
