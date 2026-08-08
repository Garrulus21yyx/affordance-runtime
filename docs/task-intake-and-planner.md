# Thin Semantic Intake and Agent Policy Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** semantically strong intake, risk profiles, optional planning, and model decision boundary

## 1. Boundary decision

Intake is **responsibility-thin and semantics-strong**. It owns facts that
remain stable across pages and time:

```text
goal
constraints
allowed and forbidden effects
important inputs
success criteria
requested outputs
risk boundary
material source bindings when needed
```

It does not own current buttons, tabs, scroll state, selectors, coordinates,
surface route, or action order. Those belong to the execution loop because they
depend on the current world.

## 2. TaskGoal

```python
@dataclass(frozen=True)
class TaskGoal:
    instruction: str
    constraints: tuple[Constraint, ...] = ()
    allowed_effects: tuple[AllowedEffect, ...] = ()
    forbidden_effects: tuple[ForbiddenEffect, ...] = ()
    inputs: tuple[TaskInput, ...] = ()
    success_criteria: tuple[Criterion, ...] = ()
    requested_outputs: tuple[OutputRequest, ...] = ()
    risk_profile: RiskProfile = RiskProfile.DEFAULT
    material_bindings: tuple[MaterialBinding, ...] = ()
```

`TaskGoal` contains no page structure, backend, selector/coordinate, action
sequence, or Plan. `RiskPolicy` remains an execution-time collaborator that
evaluates the current request against the task's stable risk/effect boundary.
For an effectful task, allowed effects must come from explicit instruction or
clarification; an empty set never means unrestricted effects.

RiskPolicy hashes only the canonical semantic action, semantic target,
destination, normalized semantic parameters, semantic effects, Runtime risk,
and human-readable consequence categories. Observation/option/binding IDs,
selector, coordinate, bbox, WoT form/href/method, backend, screenshot/TD digest,
and credentials are excluded. Authored low-risk metadata cannot lower the
Runtime-owned risk floor.

## 3. Risk-proportionate profiles

| Profile | Intake requirement |
|---|---|
| ordinary GUI task | lightweight TaskGoal; no mandatory source proof |
| high-risk or structured task | explicit effects/risk plus MaterialBindings for material fields |
| strict business or benchmark | TaskGoal + EvaluationSpec + exact source lineage where required |

Example: changing a local search field to “Berlin” needs a success criterion,
not a source-proof graph. Reading recipient/amount/currency from a payment notice
and paying requires material source bindings, a high-risk boundary, exact human
confirmation, and final outcome verification.

Source lineage is therefore retained but demand-gated. It is not a fixed tax on
every GUI task.

## 4. EvaluationSpec

`EvaluationSpec` is optional strict completion/output semantics. It may define
a composed success expression, required output integrity, and authoritative
checks. It does not define page navigation or grant execution authority.

## 5. TaskPlan, Milestone and LocalObjective

TaskPlan is optional, low-frequency and replaceable:

```python
@dataclass(frozen=True)
class TaskPlan:
    plan_id: str
    milestones: tuple[Milestone, ...]

@dataclass(frozen=True)
class Milestone:
    milestone_id: str
    objective: str
    depends_on: tuple[str, ...] = ()
    completion_criteria: tuple[Criterion, ...] = ()

@dataclass(frozen=True)
class LocalObjective:
    objective: str
    completion_criteria: tuple[Criterion, ...]
    action_budget: int = 5
```

TaskPlan contains high-level states to reach, never GUI actions or bindings.
TaskPlanner runs only for clearly multi-stage work, invalid plans, material
environment change, repeated no-progress, or new user information. Simple
click/read/fill/export tasks bypass it.

MilestoneEvaluator—not Planner—decides satisfaction. LocalObjective describes
the next nearby world state for one to several turns; it is not a StepPlan.

## 6. AgentPolicy

Input:

```text
AgentTaskView
AgentWorldView
AgentActionSpaceView
bounded AgentTurnView tuple
optional AgentPlanView
```

Output:

```text
Select(action_id, parameters)
ActBatch(action_ids, parameters)
AskUser(question)
Reobserve(reason)
Finish(result)
```

The policy selects only offered opaque action IDs and supplies schema-valid
semantic parameters plus an offered semantic destination ID. Runtime retains
the internal ActionSpace for membership, schema, destination, binding-group,
and current-route admission. The model views exclude binding/schema digests,
backend/surface/executor identity, request and observation lineage, adapter
evidence, selector/coordinate/bbox/href/method, credentials, and private paths.
Secret-like TaskGoal inputs are display-redacted without changing Runtime
authority. The policy cannot invent target identity, binding, backend payload,
confirmation, or completion truth.

## 7. Planning semantics

```text
TaskGoal      = what
TaskPlan      = optional current hypothesis of high-level how
LocalObjective = nearby state to reach
ActionIntent  = next semantic action
BoundActionRequest = current grounded executable request
```

TaskPlan is optional, temporary, and replaceable as a whole after fresh
observation. Simple tasks act directly from ActionSpace. Complex tasks may use
milestones, but Plan is neither intake output nor Runtime authority. Plan or
milestone exhaustion cannot complete the task.

## 8. ActionSpace, Batch and clarification

ActionSpace contains current legal, bindable semantic actions. Backend material
remains hidden in the world model. Presentation may be paged or compressed, but
the model cannot select omitted IDs or create raw bindings.

Material ambiguity yields `AskUser`. A strict profile may validate source
fields and output bindings before the loop, but it cannot create a second
default control path or copy proof/lineage graphs into every BoundActionRequest.

ActionBatch is a later optional optimization. Policy can request it only from
options explicitly marked batchable with no observation barrier. The Runtime
validator enforces max-three, low-risk, same-surface/session, no navigation,
external effect, app/page change, or cross-surface dependency.

## 9. Current migration note

Current code still requires admitted TaskSpec, mandatory planning flows, and
ActionChoiceCatalog authority objects. Those remain baseline behavior until
P5-A/P5-E/P5-H cutover and are not target contracts.

P5-M0 model-boundary contracts are integrated only on the non-default target
loop. No provider SDK, model-backed AgentPolicy, or model evaluator is present.
