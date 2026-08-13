# Canonical GUI Agent Execution Architecture

> **Lifecycle:** CURRENT CANONICAL / CUTOVER IMPLEMENTED / LIVE VERIFICATION OPEN
> **Updated:** 2026-08-13
> **Scope:** the only target architecture for task semantics, planning, GUI action
> selection, evidence, execution, and completion
> **Implementation truth:** [Implementation Status](implementation-status.md)
> **Change admission:** [Architecture Governance Track](architecture-governance-track.md)

## 1. Decision

The target GUI agent has one semantic-planning authority and one serial execution
loop. The main Agent chooses only a current action or a control operation. It
never constructs Runtime plan, objective, predicate, scope, aggregate, binding,
or completion state through an action tool call.

The canonical chain is:

```text
UserRequest
  -> thin external intake
  -> TaskGoal
  -> TaskSpecAuthority                         task meaning/effect boundary
  -> admitted TaskSpec
  -> initial observe
  -> WorldObservation                         current world authority
  -> TaskPlanGeneratorPort                    proposal only
  -> TaskPlanAuthority
  -> admitted TaskPlan<StepSpec.execution>    sole task/step semantic authority
  -> PlanProgress selects one active StepSpec
  -> materialize/refresh one StepExecutionState from the active step
  -> resolve scope/selectors/evidence against the current observation
  -> build current ActionChoiceCatalog
  -> project disposable AgentContext + action/control tools
  -> AgentPolicy.decide                       action/control choice only
  -> validate context and current catalog membership
  -> derive ActionIntent
  -> risk/confirmation
  -> currentness check
  -> private bind -> BoundActionRequest
  -> execute once -> ActionResult
  -> fresh post-action observation
  -> ActionEvaluation
  -> refresh StepExecutionState and PlanProgress
  -> TaskEvaluation
  -> continue / reobserve / replan / ask / wait / done / abort
```

This reuses the repository's canonical `TaskSpec`, `TaskPlan`, `StepSpec`, and
planning authorities. It does **not** import the transactional
`Coordinator/StateKernel/RuntimeCommitter` execution core into `AgentLoop`.

## 2. Non-negotiable invariants

1. **One task-semantic owner.** Admitted `TaskPlan<StepSpec.execution>` is the
   only producer of persistent execution semantics.
2. **Action-only Agent boundary.** The main Agent may select current actions or
   control operations; it cannot establish task/objective state.
3. **No pre-observation GUI identity.** `TaskGoal`, `TaskSpec`, and planned
   selectors contain no DOM ID, Runtime entity ID, E-ref, action ID, binding,
   selector string, screen point, or coordinate route.
4. **Semantic persistence, physical rebinding.** Planned semantic selectors may
   survive observations; entity/action/binding resolution never does.
5. **One current execution-state slot.** Entity, set, and aggregate execution
   are variants of one active `StepExecutionState`, not parallel authorities.
6. **Projection is one-way.** AgentContext, E-refs, screenshots, marks, tool
   catalogs, tool results, traces, and benchmark records are disposable views.
   Runtime authority is never reconstructed from them.
7. **Evidence source is not lifecycle authority.** DOM/AX, derived geometry,
   visual classifiers, and open-world visual discovery feed the same evidence
   obligations and reducers.
8. **Current action membership is mandatory.** Every effectful dispatch traces
   to one active step, one current `ActionChoice`, one current `ActionSpace`
   option, and one current private binding.
9. **Dispatch, effect, step completion, and task completion are distinct.**
   Executor, ActionEvaluator, step reducer, and TaskEvaluator own them
   respectively.
10. **Benchmark neutrality.** Benchmark names, task slugs, expected answers,
    fixed candidate counts, and witness-specific branches never enter
    production semantics.

## 3. Canonical owners and contracts

| Stage | Sole owner | Authoritative input | Typed output | Must not own |
|---|---|---|---|---|
| external request boundary | thin intake adapter | user/environment request | `TaskGoal` | GUI identities, plan, route |
| task admission | `TaskSpecAuthority` | request/source proposal | admitted `TaskSpec` or typed rejection | current GUI target, binding |
| observation | `WorldEnvironment` | current environment | `WorldObservation` / typed acquisition failure | task meaning, completion |
| plan proposal | `TaskPlanGeneratorPort` | admitted TaskSpec + bounded current observation | authority-free `PlanProposal` | admission, binding, execution |
| plan admission/version | `TaskPlanAuthority` | planning request + proposal | admitted `TaskPlan<StepSpec>` | current entity identity |
| plan progress | one AgentLoop plan-progress reducer | admitted plan + validated step outcomes | active/completed/failed step state | model narration, benchmark reward |
| active step meaning | active `StepSpec.execution` | admitted plan + progress | semantic selector/predicate/action obligation | E-ref, current binding |
| execution lifecycle | one step-execution reducer | active step + fresh observations/evaluations | `StepExecutionState` disposition | task completion, physical route |
| scope closure | `ScopeEnumeratorPort` | typed scope + observation epoch | candidate universe + coverage | visual classifier, Agent |
| evidence | `EvidenceRouter` + typed providers | frozen evidence obligation | typed assessment + source/assurance | scope closure, action authority |
| legal world actions | `ActionSpaceBuilder` | TaskGoal/TaskSpec effect boundary + current world | internal `ActionSpace` | planning, model choice |
| current semantic choices | `ActionChoiceCatalogBuilder` | active step + current world + ActionSpace | current `ActionChoiceCatalog` | binding, execution, plan mutation |
| model presentation | `ContextBuilder` + tool projector | read-only current state/catalog | disposable AgentContext/tools | retained truth, semantic construction |
| next choice | `AgentPolicy` | one AgentContext | one typed action/control decision | plan/objective state, binding, completion |
| admission | AgentLoop admission | context ID + catalog/action membership | admitted selection or typed rejection | prompt compliance assumptions |
| route/currentness | route selector + `ActionBinder` | admitted selection + fresh world | `BoundActionRequest` | task meaning, effect truth |
| risk | `RiskPolicy` / confirmation owner | semantic intent + current risk facts | allow/confirm/block | execution, task truth |
| dispatch | environment executor | one current bound request | `ActionResult` + post-action acquisition | effect/task success |
| item effect | `ActionEvaluator` | before/request/result/after | validated `ActionEvaluation` | task completion |
| step completion | step-execution reducer | obligations + validated effects + fresh evidence | step disposition/certificate | whole-task truth |
| task completion | `TaskEvaluator` | TaskSpec/TaskGoal completion contract + evidence | complete/incomplete/blocked/unknown | dispatch or plan exhaustion |
| benchmark | harness | manifest + public outcomes | measurements/evidence | production branches or authority |

## 4. Authoritative state model

The short loop retains only the state required to continue safely:

```text
AgentLoopState
  task_identity
  admitted_task_spec_identity
  admitted_task_plan
  plan_progress
  active_step_execution_state     # exactly one discriminated slot
  current_observation
  current_action_choice_catalog   # observation-bound, replaceable
  pending_confirmation | pending_question | pending_unknown_effect
  bounded recent control outcomes
  budgets and terminal status
```

The following are not authoritative state:

- AgentContext and serialized model messages;
- E-ref and screenshot mark assignments;
- projected action tools and their descriptions;
- model chain-of-thought or narration;
- benchmark rows, diagnostic traces, and reports;
- stale ActionSpace, ActionChoice, action IDs, or binding IDs.

### 4.1 Plan lifecycle

```text
ABSENT
  -> PLANNING
  -> ACTIVE
      -> REPLAN_REQUIRED -> PLANNING
      -> COMPLETE
      -> BLOCKED
```

Legal triggers for `REPLAN_REQUIRED` are typed plan issues: an admitted
assumption is invalid, the active selector is unsupported/ambiguous under the
declared budget, a step is unexecutable, or validated task requirements changed.
Provider/schema failure is not itself a new plan and cannot mutate active plan
state.

### 4.2 Active step lifecycle

```text
UNMATERIALIZED
  -> NEED_EVIDENCE | READY | AMBIGUOUS | UNSUPPORTED
READY
  -> ACTION_IN_FLIGHT
  -> EFFECT_CONFIRMED | NO_EFFECT | EFFECT_UNKNOWN
EFFECT_CONFIRMED
  -> NEED_STABILITY_CHECK | COMPLETE
NEED_STABILITY_CHECK
  -> COMPLETE | READY | NEED_EVIDENCE
```

Every fresh observation refreshes or rematerializes this state from the same
active `StepSpec.execution`. It never asks the Agent to recreate the step.

Entity, set, and aggregate differences stay inside this lifecycle:

- entity: one semantic selector and action obligation;
- set: scoped candidate universe, predicate membership, per-member effect
  obligations, and stability closure;
- aggregate: scoped sources, value evidence, deterministic operator/result
  provenance, destination obligation, and destination effect.

Ordered multi-step work is represented by dependent TaskPlan steps, not an
embedded Agent-produced sequence.

## 5. Identity and temporal ordering

| Time | Identities that may exist | Identities forbidden from persisting |
|---|---|---|
| before first observation | request, TaskGoal, TaskSpec, plan/step semantic IDs | entity, E-ref, action, binding, point |
| after observation | observation, semantic entity, source target, ActionSpace option | prior observation routes |
| during planning | plan/step IDs and semantic selectors | DOM IDs/E-refs as planned targets |
| during one AgentContext | context ID, call-local E-refs/tool names | use in later contexts |
| after Agent selection | current ActionChoice/action ID | model-supplied private selector |
| immediately before execution | current binding/request ID | stale binding or point |
| after fresh observation | new observation/entity/action/binding resolution | every prior E-ref/action/binding |

Future-resolvable semantics are allowed. Future physical identity is not. For
example, a plan may contain `label == "0"` before a menu exposes that element;
the step remains semantic and resolves only after a later observation.

## 6. Exact per-turn algorithm

For each loop turn, Runtime performs these steps in order:

1. Validate or acquire the current observation.
2. Evaluate terminal task criteria against that observation.
3. If no admitted plan exists or a typed replan is required, invoke the planning
   port and admit the proposal through `TaskPlanAuthority`.
4. Select the active step from authoritative plan progress.
5. Materialize or refresh the active `StepExecutionState` against the current
   observation.
6. Route unresolved evidence obligations to structural, derived, or visual
   providers; install only typed evidence bound to the same observation/scope.
7. Build the legal `ActionSpace` from the task effect boundary and current
   world.
8. Build the current `ActionChoiceCatalog` by intersecting the active step's
   semantic obligations with the current ActionSpace.
9. If the catalog has one mechanically authorized continuation and the declared
   scheduling policy permits automatic continuation, select it in Runtime;
   otherwise project action/control tools to the Agent.
10. Admit the returned decision against the exact context and catalog identity.
11. Apply risk/confirmation and perform a final currentness check.
12. Bind privately and dispatch at most once.
13. Acquire the typed post-action observation even when dispatch outcome is
    uncertain.
14. Validate ActionEvaluation lineage and update the active step reducer.
15. Update plan progress only from validated step outcomes.
16. Validate TaskEvaluation and continue, replan, ask, wait, finish, or fail
    closed.

No stage may skip directly from a model proposal to binding or execution.

## 7. Main Agent interface

The main Agent's closed decision algebra is:

```text
SelectAction(current_action_ref, ordinary_action_parameters)
RequestObservation(...)
RequestActionPage(...)
AskUser(...)
ProposeDone(...)
Wait(...)
Abort(...)
```

Model-facing action tools are ordinary operations such as:

```text
click(target=E7)
fill(target=E2, text="...")
select(target=E4, value="...")
observe_visual(...)
```

The following are forbidden from the main Agent interface:

```text
establish_local_objective(...)
establish_set_objective(...)
establish_sequence(...)
establish_aggregate(...)
construct_predicate_ast(...)
declare_scope_complete(...)
bind_dom_selector(...)
click_point(...) when a current DOM/AX identity exists
```

Planner proposals may use a bounded typed semantic schema, but that schema is
owned by the planning port and admitted once into `StepSpec.execution`. It is not
part of the recurrent action-policy contract.

## 8. Projection and losslessness

Runtime retains canonical source objects, so model projection does not need to
be lossless. It must instead be referentially closed for the current call.

```text
canonical ActionChoice(action_id, target_id, parameters, ...)
  -> call-local tool + E-ref
  -> Agent returns tool + E-ref + ordinary parameters
  -> private catalog resolves directly to the retained ActionChoice
```

Only that current reference mapping is reversible. Task semantics, plan state,
scope, evidence, binding payloads, and completion state are never encoded into a
tool and reconstructed from the response.

Consequently:

- projection may omit private or irrelevant fields without information loss to
  Runtime;
- a stale context/catalog ID causes typed rejection and zero dispatch;
- tool schema changes follow ActionChoice presentation needs, not changes to
  task-planning or reducer internals;
- E-ref renumbering across observations is harmless.

## 9. Unified evidence lifecycle

```text
StepExecutionState
  -> EvidenceObligation(subject/scope, predicate/value need, assurance)
  -> EvidenceRouter
       -> DOM/AX provider
       -> derived layout/geometry provider
       -> visual predicate classifier
       -> open-world visual region proposer
  -> EvidenceResult(truth/value, source, assurance, observation epoch)
  -> step-execution reducer
```

Provider-specific behavior stops at `EvidenceResult`:

- DOM/AX may provide stable identity, facts, and bindings;
- derived providers may add auditable relations such as lattice coordinates;
- visual classifiers may return TRUE/FALSE/UNKNOWN for provided candidates;
- open-world visual discovery may add observation-only candidates;
- visual point grounding is a last-level route only when no DOM/AX identity
  exists and current policy explicitly permits coordinate execution.

No evidence provider owns scope completeness, plan state, action legality,
binding authority, or task completion.

## 10. Typed fail-closed outcomes

| Condition | Owner/outcome | Dispatch |
|---|---|---|
| task semantics unsupported | TaskSpec/planning rejection or ask user | zero |
| planner provider unavailable | planning deferred/failed, plan unchanged | zero |
| plan proposal invalid | TaskPlanAuthority rejection | zero |
| scope partial/unknown | evidence/closure unresolved | zero for completion-dependent action |
| visual classifier unknown | evidence remains UNKNOWN; inspect/ask/replan | zero for unresolved member |
| selector matches zero/multiple when exactly one required | step ambiguous/unresolved | zero |
| stale observation/context/catalog | admission rejection and reobserve | zero |
| action not in active step choices | admission rejection | zero |
| risk requires confirmation | pending confirmation | zero until confirmed |
| binding/currentness failure | reobserve/reselect route | zero |
| dispatch `SENT_UNKNOWN` | effect resolution; never blind retry | at most the original send |
| effect unknown/no effect | reducer/recovery/replan | no duplicate send without new authority |
| task completion unknown | continue evidence acquisition or block | no finish claim |

## 11. Current repository mapping and convergence

| Surface | Canonical disposition |
|---|---|
| `task_plan_contracts.TaskPlan<StepSpec>` | retain as the sole admitted plan |
| `TaskSpecAuthority` / `TaskPlanAuthority` | retain; expose through an explicit AgentLoop composition seam |
| `task/step_execution.py` | retain as the plan-step-to-runtime-state boundary |
| set/entity/aggregate reducers | retain behind the one active step state |
| target `InternalActionPage` + grounded catalog | retain as the observation-bound current-choice projection |
| generic `ActionChoiceCatalogBuilder` / `StepChoiceFlow` | not an additional target-loop authority; broader-runtime migration remains separate |
| `TaskGoal` | retain as thin external target-loop input/edge adapter |
| `ActionSpaceBuilder`, binder, risk, execution, evaluators | retain unchanged in authority |
| `AgentDecision.EstablishLocalObjective` | delete from the main Agent boundary |
| model-facing LocalObjective/predicate/scope/aggregate schema | delete from recurrent action tools |
| `local_objective_state` as Agent-created state | replace with plan-produced `active_step_execution_state` |
| hidden planner capability attached to AgentPolicy | do not restore; planning is explicit composition |
| Coordinator/StateKernel execution core | do not import into target AgentLoop |
| obsolete objective-specific docs/tests/projections | delete with cutover; no compatibility core path |

The current implementation candidate removes that contradiction. `AgentLoop`
receives an explicit `AgentTaskPlanPreparerPort`, admits TaskSpec/TaskPlan before
the recurrent policy loop, materializes exactly one `active_step_execution`,
and refreshes it after fresh observations. The recurrent decision union and
grounded catalog contain actions/control operations only; the displaced
`LocalObjective` facade, model payload, decision, tool, and state slot were
deleted. The prior exact-head `0/5` run remains historical negative evidence.
Fresh five-case evidence for this candidate is still required, so benchmark
closure and generalization remain open.

## 12. Change-impact protocol

Before changing production code, the author must add a row to the change review
containing:

| Required question | Required answer |
|---|---|
| Which stage in section 3 changes? | exactly one primary owner |
| Which invariant in section 2 is affected? | named invariant(s) |
| What authoritative input/output changes? | canonical types, not wire examples |
| Which consumers are affected? | complete caller list |
| Does the main Agent decision algebra change? | normally no; explicit justification if yes |
| Does any projection become authoritative? | must be no |
| Which old owner/path is deleted? | file/caller and deletion gate |
| What typed exceptional outcomes change? | state/outcome table update |
| What properties prove the change? | invariant/state-machine/boundary tests |
| What real benchmark falsifies it? | witness plus held-out case, never a production branch |

If a proposal cannot identify one owner, it is an architecture review, not a
schema patch. No new state field, Agent decision variant, planning/objective
tool, or model schema may be added before this comparison is complete.

## 13. Verification and exit criteria

Architecture tests must prove properties, not class-name absence alone:

1. the main Agent decision union contains no semantic-state constructor;
2. `model_policy/` action catalogs do not import LocalObjective, predicate,
   scope, or aggregate construction contracts;
3. exactly one admitted TaskPlan owns persistent execution semantics;
4. every active execution state is materialized from the active StepSpec;
5. every fresh observation invalidates old E-ref/action/binding identity and
   re-resolves semantic selectors;
6. every effectful dispatch is a member of active step choices, current
   ActionSpace, and current binding authority;
7. DOM/derived/visual evidence all enter the same reducer contract;
8. projection round trips recover only current ActionChoice references, never
   task or plan authority;
9. unsupported/ambiguous/stale/provider-failed paths produce typed outcomes and
   zero unauthorized dispatch;
10. known witnesses and held-out variations pass without task-shaped production
    branches.

Closure requires agreement among this document, implementation status, tests,
and fresh real benchmark evidence. Deterministic tests alone cannot promote an
implementation to `CURRENT CANONICAL` or `CLOSED`.
