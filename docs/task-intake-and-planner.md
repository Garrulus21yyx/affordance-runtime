# Target AgentLoop Intake and Decision Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-15
> **Authority:** [Target AgentLoop Authority Map](task-execution-authority-map.md)

## Boundary

The target GUI loop has a thin intake:

```text
UserRequest -> TaskGoal + bounded IntentContext(context_only)
```

`TaskGoal` owns task instruction, allowed/forbidden effects, risk profile,
evaluation boundary, public inputs, and loop budgets. `IntentContext` is a
bounded reasoning aid and never grants effects or creates targets.

No intake field may contain a DOM ID, Runtime entity ID, E-ref, action ID,
coordinate, selector, binding, or exact GUI target. Those identities do not
exist until the environment returns a `WorldObservation`.

The former workflow `TaskSpecAuthority`, `TaskPlanAuthority`,
`TaskPlan<StepSpec>`, and Coordinator runtime are physically deleted. They are
not a hidden preparer, ingress, or planning layer for `AgentLoop`.

## Observation-grounded execution semantics

After an observation and current ActionSpace exist, `AgentPolicy.decide`
receives the bounded public world plus the complete current action/control
menu. It emits one typed decision; Runtime then performs exact resolution,
admission, currentness and dispatch. The LocalObjective proposal, transport and
set/sequence/aggregate reducer experiment was physically deleted in T3 rather
than retained as a second planning or action-authority path.

Every fresh observation invalidates prior entity/action/binding resolution.
Longer-horizon reasoning remains model work over bounded task, world, progress,
transition and history views; it cannot install a private execution DSL or
expand current ActionSpace authority.

## Evidence

DOM/AX facts, derived layout facts, and visual assessments enter the same typed
evidence obligation/reducer lifecycle. Their source and assurance differ; their
identity, scope, action-admission, effect, and completion owners do not.

Visual providers may discover candidates or assess open-vocabulary predicate
leaves. They cannot declare scope completeness, bind actions, execute points
when a DOM identity exists, or certify task completion.

## Completion

Action dispatch, action effect, and TaskGoal completion are separate outcomes:

- the executor owns dispatch truth;
- `ActionEvaluator` owns item/effect confirmation;
- `TaskEvaluator` owns terminal task truth.

Model narration, tool-call success, disappearance of an element, or benchmark
reward cannot substitute for these owners.

## Forbidden duplicate paths

The target loop must not reintroduce:

- pre-observation task planners or exact-target compilers;
- `TaskFrontier`, `VerifiedTaskState`, or requirement-hypothesis state;
- separate set/sequence/aggregate state slots;
- an objective-operation package around `AgentDecision`;
- an Agent decision or action tool that installs execution semantics;
- one provider schema mixing LocalObjective construction with current actions;
- typed-decision to JSON to typed-decision round trips;
- task-name/benchmark-case routing in Runtime code.

Unsupported semantics return a typed, deterministic failure or remain
unresolved; they do not fall back to hidden IDs, coordinates, or prose rules.

## User-input continuation

`AskUser` creates a typed `UserInputRequest` only after its context-bound
decision has been accepted and recorded as a control root. The request binds
the question and requested fields to the task ID, current task revision,
originating context, and source transition.

The caller answers by submitting a complete `NaturalLanguageTaskRequest` with
the same task ID and exactly the next revision through
`TargetRuntime.submit_user_input`. The request is compiled again by
`ThinTaskIntake`; a prose answer or partial field patch cannot directly mutate
`TaskGoal` authority. Non-ready intake outcomes leave the paused session
unchanged.

An admitted revision updates the environment's task-relative authority without
resetting the physical GUI, consumes the AskUser root exactly once, and
invalidates the old task evaluation, context, ActionSpace,
action page, feedback epoch, and progress projection. Physical observation and
execution accounting remain monotonic. Wrong pending identity, duplicate
submission, cross-task replacement, non-consecutive revision, terminal
session, and an environment without task-revision support fail closed with a
typed rejection.

`WAITING_USER` caused by an unknown dispatched effect does not carry a
`UserInputRequest` and cannot use this clarification path.
