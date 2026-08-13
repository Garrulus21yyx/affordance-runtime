# Task Execution Authority Map

> **Lifecycle:** CURRENT NORMATIVE MIGRATION CONTRACT
> **Updated:** 2026-08-13
> **Scope:** task intake, planning, short-loop execution, evidence, and completion

## Decision

The canonical task-semantic and task-planning contracts are the admitted
`TaskSpec` and `task_plan_contracts.TaskPlan<StepSpec>` surfaces. The target
`AgentLoop` remains the execution-loop destination. Migration reuses the
canonical contracts and authorities without importing the old
`StateKernel/Coordinator` execution core into the target loop.

There must not be a second planner inside `AgentLoop`, Catalog, model transport,
projection, or benchmark code.

```text
UserRequest
  -> TaskSpecAuthority
  -> TaskPlanAuthority
  -> admitted TaskPlan<StepSpec>
  -> AgentLoop plan-progress owner
  -> current StepSpec
  -> current step-execution reducer
  -> scope/evidence resolution
  -> current ActionSpace admission
  -> binding/currentness/risk
  -> execute once
  -> fresh observation/effect evaluation
  -> plan-progress reduction
  -> task completion evaluation
```

The model boundary serializes proposals and projections of these contracts. It
does not define another objective algebra or retain authoritative task state.

## Owner matrix

| Stage | One canonical owner | Authoritative input | Typed output | Must not own it |
|---|---|---|---|---|
| request admission | `TaskSpecAuthority` | request, source envelope, compiler proposal | admitted `TaskSpec` or typed intake outcome | benchmark, Catalog, AgentLoop prompt |
| plan proposal | `TaskPlanGeneratorPort` | admitted TaskSpec + bounded current observation | authority-free `PlanProposal` | model transport schema, ActionSpace |
| plan admission/version | `TaskPlanAuthority` | planning request + proposal | admitted `TaskPlan<StepSpec>` | generator, AgentLoop, projection |
| plan storage/progress after cutover | one AgentLoop plan-progress reducer | admitted plan + validated step evidence | active/completed/failed step state | transition history, Catalog, evaluator proposal |
| current step meaning | active canonical `StepSpec` | admitted plan + plan progress | typed interaction/completion obligations | raw task prose, E-ref, benchmark slug |
| step execution lifecycle | one discriminated step-execution state | current StepSpec + fresh observation | evidence/action/effect/stability disposition | three mutually exclusive AgentLoop slots |
| scope closure | `ScopeEnumeratorPort` | typed scope + observation epoch | candidate universe + coverage | visual classifier, main model |
| predicate/value evidence | evidence router and typed providers | frozen universe + evidence obligation | assessments with source/assurance | Catalog, executor |
| current legal actions | `ActionSpaceBuilder` | TaskSpec effect boundary + current world + current step | internal ActionSpace | planner, provider, benchmark |
| current execution route | binder/currentness/risk chain | admitted selection + current world | bound request or typed rejection | model, screenshot marks, plan |
| physical effect | environment executor | current bound request | one result + post-action acquisition | planner, evaluator |
| item/step effect | action/criterion evaluator | result + fresh evidence + declared obligation | validated effect/criterion outcome | executor receipt alone, model narration |
| task completion | task evaluator | TaskSpec success contract + validated evidence | complete/incomplete/blocked/unknown | TaskPlan exhaustion, benchmark reward inside runtime |
| presentation | ContextBuilder/model transport | read-only projections of the above | disposable context / wire payload | state mutation or semantic admission |
| benchmark | harness | manifest + public runtime outcomes | measurements/evidence | task semantics, routing, action authority |

## Current overlap and required deletion

| Surface | Status | Action |
|---|---|---|
| `task_plan_contracts.TaskPlan<StepSpec>` | canonical | retain and connect to AgentLoop |
| `task.planning_contracts.TaskPlan<Milestone>` | duplicate, no lifecycle owner | deleted 2026-08-13 |
| `task.task_program.TaskProgram` | duplicate whole-task planner | reverted/deleted 2026-08-13 |
| `AgentLoopState.active_step_execution` | one discriminated current-step reducer state | retained as the execution lifecycle; next connect its creation exclusively to active StepSpec |
| dynamic `establish_*_objective` Catalog tools | temporary semantic ingress | delete after TaskSpec/TaskPlan entry is connected; Catalog returns to action/control projection only |
| `TaskGoal` | target-loop duplicate of admitted task meaning | keep only during bounded entry migration, then delete or reduce to an external adapter input |
| `StateKernel/Coordinator` | retained default execution core | do not import into AgentLoop; delete after canonical plan/progress cutover and default switch |

No core compatibility layer may dual-read or dual-write these owners. A
temporary edge adapter must name its source, destination, expiry condition, and
must be deleted with its last caller.

## Change admission and error discovery

Before changing a schema or adding state, every defect must be classified in
this order:

1. identify the violated end-to-end invariant;
2. trace the authoritative datum from producer through every consumer;
3. locate the first stage where it is absent, duplicated, stale, or reinterpreted;
4. fix that owner or boundary once;
5. delete displaced paths in the same migration;
6. only then change a wire schema, and only as a projection consequence of the
   canonical contract change.

A model parse failure is not automatically a schema defect. First determine
whether the model is being asked to create state that belongs to intake,
planning, evidence, binding, or completion authority.

Each architecture change must update this map and pass the ownership tests.
Benchmark witnesses falsify the shared contract; they do not authorize
case-shaped branches.

## Exit properties

- exactly one `TaskPlan` class exists in production source;
- exactly one AgentLoop step-execution slot exists; set, sequence, and aggregate
  are variants of that slot rather than independent authorities;
- no `TaskProgram` or equivalent whole-task owner exists outside canonical
  TaskPlan authority;
- every effectful dispatch traces to one active canonical plan step, one current
  ActionSpace option, one current binding, and one admitted effect boundary;
- observations refresh selector/evidence/binding state without recreating task
  semantics;
- DOM, derived, and visual evidence share the same lifecycle and differ only by
  provider/source assurance;
- Catalog and model schemas contain no domain-state constructors after cutover;
- obsolete types, tools, tests, documents, and imports are absent rather than
  maintained as internal compatibility.
