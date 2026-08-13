# Task Intake, Planning, and Agent Action Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-13
> **Authority:** [Canonical GUI Agent Execution Architecture](task-execution-authority-map.md)

## Boundary

The target GUI loop separates task semantics, planning, and recurrent action
selection:

```text
UserRequest
  -> TaskGoal                         thin external target-loop input
  -> TaskSpecAuthority
  -> admitted TaskSpec                stable task/effect/completion meaning
  -> initial WorldObservation
  -> TaskPlanGeneratorPort
  -> TaskPlanAuthority
  -> admitted TaskPlan<StepSpec>      persistent execution semantics
  -> current action/control tools
  -> AgentPolicy                      next action only
```

`TaskGoal` contains the public instruction, allowed/forbidden effects, risk,
evaluation boundary, public inputs, outputs, and budgets. `TaskSpec` and
`TaskPlan` contain typed task and step semantics. None of these contracts may
contain a DOM ID, Runtime entity ID, E-ref, current action ID, binding, private
selector, or screen point.

The first observation precedes TaskPlan proposal so the planner can use current
public world evidence. A planned selector remains semantic and future-resolvable;
it does not become a current entity until Runtime resolves it against an
observation.

## Planning contract

The planner is an explicit Runtime composition dependency, not a hidden
capability attached to `AgentPolicy`.

```text
PlanningRequest(admitted TaskSpec, current observation, budget, prior plan issue?)
  -> TaskPlanGeneratorPort
  -> authority-free PlanProposal
  -> TaskPlanAuthority structural/semantic admission
  -> admitted TaskPlan or typed rejection
```

The planner may be implemented by rules, one model call, multiple internal
model stages, a parent agent, or an accepted skill. These are provider choices;
they do not change the canonical output or the main Agent action interface.

Each `StepSpec.execution` contains one bounded semantic execution variant:

- entity: resolve one semantic selector and perform one action obligation;
- set: close a scope, classify predicate membership, and confirm every admitted
  member obligation;
- aggregate: close source evidence, derive COUNT/SUM/MIN/MAX deterministically,
  and satisfy one destination obligation.

Ordered work uses dependent TaskPlan steps. It is not serialized as an embedded
action sequence in the recurrent Agent call.

## Observation refresh

For every new observation Runtime:

1. keeps the admitted TaskPlan and semantic active-step meaning;
2. invalidates prior E-refs, entity/action resolution, ActionChoice IDs, and
   private bindings;
3. rematerializes or refreshes the active step execution state;
4. re-enumerates scope and re-evaluates required evidence;
5. rebuilds current ActionSpace and ActionChoiceCatalog;
6. projects a new disposable AgentContext.

The Agent never recreates the active step after refresh.

## Main Agent decision contract

The recurrent Agent may return only:

- select one currently offered action with ordinary action parameters;
- request an observation or another current action page;
- ask the user;
- propose done;
- wait;
- abort.

It cannot return a LocalObjective, TaskPlan step, predicate AST, quantifier,
scope declaration, aggregate program, route, binding, or completion
certificate. Those belong to planning and Runtime reducers.

Action tools are disposable projections of current `ActionChoiceCatalog`
membership. A tool result resolves privately to the retained current choice; it
does not reconstruct task or plan authority.

## Evidence and completion

DOM/AX facts, derived layout facts, and visual assessments enter the same typed
evidence-obligation lifecycle. Their source and assurance differ; their scope,
identity, action admission, effect, and completion owners do not.

Action dispatch, action effect, step completion, and task completion remain
separate:

- executor owns dispatch truth;
- ActionEvaluator owns item/effect truth;
- active step reducer owns step obligations and stability;
- TaskEvaluator owns terminal task truth.

## Forbidden duplicate paths

The target loop must not introduce or retain:

- a second TaskPlan/TaskProgram/LocalObjective semantic owner;
- an Agent decision that installs execution semantics;
- model-facing set/sequence/aggregate constructors in action tools;
- a hidden planner attached to AgentPolicy decorators;
- pre-observation exact GUI target identities;
- TaskPlan semantics reconstructed from AgentContext, E-refs, tools, or traces;
- separate DOM and visual objective lifecycles;
- task-name or benchmark-case routing in Runtime code;
- a compatibility core that dual-reads old and new semantic owners.

Unsupported semantics return typed planning/evidence outcomes or request user
clarification. They do not fall back to prose rules, hidden IDs, or coordinates.
