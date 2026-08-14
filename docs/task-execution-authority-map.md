# Target AgentLoop Authority Map

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-14
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
       -> exactly one root ControlTransition
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
| public action candidates | `ContextBuilder` | current action page + public grounded targets | referentially closed `AgentContext.actions` options | legality, private binding, durable identity, screen coordinates |
| rolling semantic proposal | `LocalObjectiveProposalPort` | TaskGoal + bounded post-observation context | authority-free LocalObjective proposal or typed failure | admission, retained state, action choice |
| rolling relevance | one `LocalObjective` lifecycle | admitted proposal + current evidence | relevance/evidence/member state | whole-task planning, effect grants |
| model presentation | `ContextBuilder` | read-only current state + latest canonical `ControlTransition` | disposable `AgentContext`, including an optional bounded `last_transition` projection | retained truth, identity authority, a second transition owner |
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

## Current action-candidate chain

The model must not join a task requirement, an entity list and a separate bare
target enum. One current model-boundary projection closes every offered action
over the public semantics needed to distinguish its target:

```text
WorldObservation + internal ActionSpace/current page
  -> ModelWorldView + one call-local grounding index
  -> ContextBuilder.close_action_candidates
  -> AgentContext.actions option
       operation + complete public target selector + private-binding lookup key
  -> GroundedPolicyContextBinder actions.groups
       shared target semantics once + minimal differing semantic choices
  -> GroundedToolCatalog schema + opaque action binding
  -> model returns only operation + semantic choice + declared business value
  -> Runtime admission against the still-current internal ActionSpace
```

`AgentContext.actions` is a disposable view, not another ActionSpace. The
catalog consumes `option.operation` and `option.selection_key` from that view; it
must not rebuild them by joining `target_id` through
`context.grounding.target_refs`. In the provider message, actionable entity
semantics occur under compact `actions.groups` and are excluded from
`world.entities`; the latter contains contextual, currently non-actionable
entities only. Each group hoists fields common to every legal candidate and
exposes the smallest bounded public facet set that uniquely distinguishes the
candidates. The tool enum repeats only those semantic choices as a validation
constraint; it is not a second semantic projection.

This candidate section exists only in `ACTION_SELECTION`. The
`OBJECTIVE_PROPOSAL` binder does not publish `actions.groups` and does not
remove those entities from its contextual world. Objective proposal therefore
cannot acquire click/fill/select authority through the shared context binder.

Target choice follows one bounded facet algebra: `role`, `label`, scalar or
short scalar-list public state, and one public parent scope as `within.role /
within.label`. This is not a model-authored selector DSL. Runtime removes fields
common to a group and finds a deterministic minimal distinguishing subset. For
two identically labelled "加入购物车" buttons scoped by different products, the
model sees the button semantics once and chooses only `MacBook Air` or
`MacBook Pro`. A verified domain grid coordinate is the same generic state
facet and becomes a choice such as `(1,-2)`. Screen points, bounding boxes, DOM
selectors, action IDs and binding IDs are never action arguments. Construction
metadata such as row/column indices and confidence is omitted. Only candidates
that remain publicly indistinguishable after the supported facets receive an
explicit call-local E-ref fallback.

Changing a semantic choice changes the selected GUI entity. Therefore a target outside
the current tool enum is a semantic-selection failure, not a format-only
argument repair. Compact structured output constrains `target` to current
group choices. Native-tool output fails closed on an invalid choice and cannot
invoke argument repair to substitute another target. If a valid target was
selected but another business argument needs repair, the repair schema pins
that exact choice and Runtime verifies it again after repair.

This division is consistent with current GUI-agent research, but is an
engineering inference rather than a claim that those systems use this exact
schema. [UI-TARS](https://arxiv.org/abs/2501.12326) standardizes atomic GUI
operations while treating grounding as a separate localization problem;
[GUI-Actor](https://arxiv.org/abs/2506.03143) reports that text-generating raw
coordinates weakens spatial-semantic alignment and instead separates semantic
intent from region localization. Here the Runtime-owned binding table provides
that separation without training a new grounding model: the general model
selects a public semantic difference, and Runtime resolves the exact current
entity and executor route.

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

The transition-to-context chain is also unique and one-way:

```text
WorldObservation / execution receipt / ActionEvaluation / TaskEvaluation
                              |
                              v
               exactly one root ControlTransition
                              |
                    public bounded projection
                              v
            AgentContext.last_transition (optional view)
```

`ControlTransition` remains the only canonical accounting object for one
accepted policy decision. A typed delta or digest computed while closing that
transition is owned by that same root and cannot be persisted, updated, or
interpreted as a parallel transition authority. `AgentTransitionDigestView` is
only the disposable model-facing projection; Runtime cannot reconstruct the
root transition or current state from it.

The implemented P0 stores no internal digest. The root retains its matching
decision-start `before_task_evaluation`; `ContextBuilder` compares it with the
root's final TaskEvaluation and projects the latest root directly. The latest
root is excluded from `AgentContext.history`, which contains only older bounded
anchors. Confirmation and user-input continuation use the existing reducer to
replace that same immutable root once and consume its source identity.

`AgentContext.progress` answers what is verified or unresolved now.
`AgentContext.last_transition` answers how the most recent accepted decision
led to the current observation/evaluation. It does not duplicate the current
world, current action page, current progress snapshot, or current control
instruction. Runtime-owned `control_feedback` remains the sole projection of
next-decision constraints; it is not copied into the past-tense transition
view.

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
