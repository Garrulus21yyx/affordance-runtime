# Target AgentLoop Intake and Local Objective Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Updated:** 2026-08-13
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

The repository's workflow `TaskSpecAuthority`, `TaskPlanAuthority`, and
`TaskPlan<StepSpec>` remain owned by the separate Coordinator runtime. They are
not a hidden preparer, ingress, or planning layer for `AgentLoop`.

## Observation-grounded execution semantics

After an observation and current ActionSpace exist, the explicit
`LocalObjectiveProposalPort` may return one authority-free bounded semantic
proposal:

- sequence: future-resolvable semantic selectors and action templates;
- set: scope, predicate, quantifier, and member action template;
- aggregate: source scope/predicate/extractor/operator and destination selector.

All variants share one `local_objective_state` owner. Runtime validates the
proposal against the exact post-observation context, assigns objective/scope/
step identities, and resolves current entities from current evidence. A
LocalObjective narrows relevance and tracks obligations; it never expands
TaskGoal legality, risk permission, or ActionSpace authority.

This proposal phase is not part of `AgentPolicy` and is not projected as an
action tool. The recurrent Agent interface contains only current action/control
decisions. Predicate, scope, quantifier, aggregate, and future-resolvable
selector schemas stop at the proposal adapter and cannot couple to E-ref action
tools.

Every fresh observation invalidates prior entity/action/binding resolution.
The LocalObjective semantic value may persist, but its reducer must re-enumerate
the scope, re-evaluate evidence, and re-authorize current ActionSpace members.

## Evidence

DOM/AX facts, derived layout facts, and visual assessments enter the same typed
evidence obligation/reducer lifecycle. Their source and assurance differ; their
identity, scope, action-admission, effect, and completion owners do not.

Visual providers may discover candidates or assess open-vocabulary predicate
leaves. They cannot declare scope completeness, bind actions, execute points
when a DOM identity exists, or certify task completion.

## Completion

Action dispatch, action effect, LocalObjective completion, and TaskGoal
completion are separate outcomes:

- the executor owns dispatch truth;
- `ActionEvaluator` owns item/effect confirmation;
- the LocalObjective reducer owns sequence/set/aggregate obligation state;
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
