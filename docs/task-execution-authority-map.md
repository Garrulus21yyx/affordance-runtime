# Target AgentLoop Authority Map

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-15
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
are historical names for the deleted transactional workflow runtime. They are
not an ingress, compatibility layer, or hidden capability of `AgentLoop`.

## Authority and lifecycle owners

| Stage | Owner | Authoritative input | Output | Explicitly not owned here |
|---|---|---|---|---|
| task boundary | `TaskGoal` | thin intake | allowed/forbidden effects, risk, success boundary | DOM ID, E-ref, coordinate, route |
| task clarification | `TargetRuntime + AgentRunSession` | matching `UserInputRequest` + intake-admitted next revision | one-shot task revision and stale-projection invalidation | free-form patching, effect inference, physical reset |
| supplemental context | `IntentContext` | bounded source excerpts | context-only hints | task/effect authority |
| observed world | `WorldEnvironment` | current environment | `WorldObservation`, including source-owned structural documents and media | task semantics, action authority |
| BrowserGym structural representation | BrowserGym `SurfaceAdapter` | bounded current AX tree + rendering | semantic targets plus a separate bounded structure document with explicit target links | bindings for structure-only nodes, Actor formatting |
| raw screenshot acquisition | BrowserGym environment | current captured viewport | independently selectable visual source containing media only | semantic interpretation, bindings, actions |
| legal actions | `ActionSpaceBuilder` | `TaskGoal + WorldObservation` | current internal `ActionSpace` | model, benchmark, deleted workflow/LocalObjective code |
| public action candidates | `ContextBuilder` | current action page + public grounded targets | referentially closed `AgentContext.actions` options | legality, private binding, durable identity, screen coordinates |
| concrete action rows and flat tools | `GroundedToolCompiler` | complete closed action candidates | shared semantic skeleton, minimal exact public ToolSpec, private resolution table | world lookup, legality, provider grouping, fuzzy matching |
| Actor epistemic projection | `ContextBuilder` + `ActorWorldSnapshot` | bounded current public source structure, semantic targets, facts, evidence, coverage and media | one disposable structure-preserving Actor world | legality, candidate derivation, binding, retained state |
| provider action serialization | `GroundedPolicyContextBinder` + provider transport | ActorWorldSnapshot + already compiled public ToolSpecs | flat Actor request | world pruning, candidate grouping, selector choice, resolver data |
| provider-call reconciliation | `ProviderCallNormalizer` | raw provider call + immutable compiled catalog | exact call, proven equivalent normalized call, or typed bounded repair/rejection | world/ActionSpace lookup, silent non-equivalent substitution, admission |
| exact tool resolution | grounded catalog resolver | reconciled exact call + exact emitted schema + private compiler table | existing typed `SelectAction` | normalization, fuzzy search, repair, world lookup, admission |
| model presentation | `ContextBuilder` | read-only current state + latest canonical `ControlTransition` | disposable `AgentContext` with one ActorWorldSnapshot and optional bounded `last_transition` | retained truth, identity authority, a second transition owner |
| provider response validation telemetry | grounded provider adapter | typed redacted structured-output violations | bounded stage/code/path and repair outcome | raw provider payload, action repair, world truth |
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
- In one AgentContext: the projection may issue call-local E-refs.
- At selection: Runtime accepts only the current ActionSpace member.
- Before execution: target and binding are revalidated against the current world.
- After a fresh observation: old E-refs, ActionSpace IDs, action IDs, and
  bindings are stale.

No intake or planner may invent an exact DOM/entity target. No E-ref or model
point becomes durable identity.

## Current action-candidate chain

The model does not join a task requirement, entity table, action group, or bare
target enum. The implemented existing-action path has one compiler projection:

```text
WorldObservation + internal ActionSpace/current page
  -> bounded internal ModelWorldView + one call-local grounding index
  -> ActorWorldSnapshot from source structure + public world evidence
  -> ContextBuilder.close_action_candidates
  -> AgentContext.actions option
       canonical operation
       + complete bounded target semantics/grounding
       + exact business schema
       + destination mode and complete destination candidates
       + public consequence projection
       + private current action lookup identity
  -> GroundedToolCompiler
       concrete destination rows
       -> technical partitions
       -> recursive shared skeleton
       -> deterministic minimal semantic selector or explicit E-ref fallback
       -> flat ToolSpec + private exact-resolution table
  -> GroundedPolicyContextBinder serializes ActorWorldSnapshot + flat ToolSpecs only
  -> model returns only the emitted semantic/grounding selector fields
       + declared business values
  -> ProviderCallNormalizer preserves harmless wire variance and may reconcile
       one uniquely identified row only under the same authority-equivalence digest;
       otherwise it returns bounded field errors / did_you_mean and dispatches nothing
  -> resolver validates the exact emitted schema and queries the private table
  -> SelectAction with exact current action/destination identity
  -> Runtime admission against the still-current internal ActionSpace
```

`AgentContext.actions` is a disposable view, not another ActionSpace. The
compiler consumes only those closed candidates; it does not join `target_id` or
`destination_id` through `AgentContext.world` or the grounding index. The
provider binder receives an already closed `ActorWorldSnapshot` and already
compiled `ToolSpec` objects; it neither prunes the world nor groups or
reinterprets candidates. The Actor request contains no `actions.entities`,
`actions.groups`, action IDs, canonical target IDs, backend selectors, private
destination tables, or resolver entries. Actionable and non-actionable nodes
use the same source-preserving world representation. Tool semantics never cause
a node or fact to disappear, because the world answers what exists and the
tools independently answer what is callable.

Target and destination choice use the bounded generic semantic-facet algebra.
The compiler recursively intersects complete records, then chooses the smallest
injective facet set by deterministic path count, encoding size, and canonical
path priority. Singleton tools have no target selector. One varying path emits
one enum; a complete multi-path Cartesian set emits independent fields; a
sparse set emits one atomic semantic choice containing only real tuples. Thus
two identically labelled "加入购物车" buttons scoped by different products emit
only `within_label`, and a verified grid emits
`semantic_grid_coordinate="(1,-2)"` without exposing its E-ref.

Required destinations mechanically expand to real `(option, destination)`
rows before factoring. One-source/one-destination constants disappear;
source/destination fields are independent only for a complete admitted
Cartesian product; sparse pairs are atomic. The initial optional-destination
algebra fails typed as `UNSUPPORTED_DESTINATION_MODE`, and an empty required
domain fails as `DESTINATION_UNAVAILABLE` with zero dispatch.

E-ref is used only when no supported public facet can identify every row. The
fallback requires a complete injective same-context mapping whose non-constant
endpoints are rendered in current grounding. Target-only fallback uses
`grounding_ref`; complete endpoint products may use qualified source and
destination refs; sparse pairs use atomic `grounding_pair`. Missing, duplicate,
stale, or unrendered refs fail as `GROUNDING_FALLBACK_UNAVAILABLE`. A visible
mark not enumerated by the selected tool remains evidence and is not callable.

Changing any emitted semantic or grounding selector changes the selected
concrete row. A value outside every current exact enum is therefore a semantic
selection failure, not a format repair. Native and compact transports fail
closed on an invalid choice. If the model mixes a compiler-generated
same-operation tool name with an explicit selector that uniquely identifies a
real row under the same authority-equivalence digest, the pre-resolver
normalizer may reconcile that representation and records telemetry. If the
alternative changes risk, effects, destination/parameter/verification contract
or is ambiguous, Runtime returns a bounded `did_you_mean` repair and requires a
new model call; it does not execute the inferred alternative. If a valid
selector was supplied but a business argument needs repair, the repair schema
pins every selector field and the resolver verifies them again. Business
properties and required fields are copied generically from the closed candidate
schema without `fill`/`select` branches or `text`/`value` renaming.

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

## Deleted LocalObjective branch

`LocalObjectiveProposalPort`, its objective model transport, the
`local_objective_state` reducer, and the surrounding workflow plan/runtime
owners are physically absent after T3. The ordinary target loop has one
reasoning phase, `AgentPolicy.decide`; there is no dormant extension point,
compatibility import, or alternate authority path.

This deletion records why the experiment is not part of the normative chain.
Earlier set/sequence/aggregate work attempted to make a
model-authored LocalObjective a separate pre-action phase. Live evidence showed
that the phase duplicated planning, exposed a large Runtime execution DSL to
the model, and could stop action selection before the GUI was used. The useful
general rule survives elsewhere: DOM, derived geometry, and visual evidence may
use different typed providers, but source choice cannot change action legality,
identity, binding, risk, or completion authority.

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

Provider protocol adapters parse a model response exactly once into an
action/control `AgentDecision`. They do not serialize that typed value back to
JSON for a second parser. The public context identity is validated against the
private current context whenever a protocol needs private grounding data.

The retained execution chain is deliberately short:

```text
TaskGoal boundary
  + current observation/action-space identity
  + admitted action
  + one result
  + fresh evaluation
```

No transitive provenance graph is required for ordinary GUI actions. Additional
lineage is retained only when a declared high-risk/material/evaluation contract
requires it.
No durable ledger, event replay, or projection-derived state is part of this
short-loop authority chain.

## Closed model boundary

The current target model phase is singular:

```text
ACTION_SELECTION
  offered: current Runtime action/control tools
  forbidden: predicate/scope/quantifier/aggregate/objective constructors
```

Changing evidence-provider semantics does not change the recurrent action
schema. Current ActionSpace membership remains authoritative; the Actor world
and tools are disposable projections.

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
- Target product and benchmark composition expose no LocalObjective proposal
  phase; the residual branch is deleted rather than restored as a second model
  call.
- No exact GUI target identity is required before `WorldObservation`.
- One fresh observation invalidates all call-local and route identities.
- Every dispatch is a current ActionSpace member and uses a current private
  binding.
- DOM/derived/vision evidence differ by source, not by lifecycle authority.
- AgentContext and grounded tools are disposable projections, never round-trip
  authority.
