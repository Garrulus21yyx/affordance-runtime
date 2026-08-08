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

## 6. IntentContext and AgentContext

Raw user language may be retained only as bounded, source-labelled
`IntentContextView(authority="context_only")`. Current TaskGoal revision outranks
admitted clarification, which outranks IntentContext, which outranks page/tool
content. A clarification that changes semantics must first create a new
TaskGoal revision and therefore a new context ID.

The unified policy input is a disposable `AgentContext`: opaque current
`context_id`, task, intent, progress, bounded world, current action page,
bounded semantic history, pending summaries, budgets and decision mode. It is
a one-way projection, never Runtime state. Every bounded section reports total
count and truncation; private route/binding/credential data is excluded.

## 7. AgentPolicy

Input: `AgentContext` only.

Output:

```text
SelectAction | RequestObservation | RequestActionPage | AskUser
| ProposeDone | Wait | Abort
```

Every decision carries the current `context_id`. The policy selects only an
offered ID from the current action page and supplies schema-valid
semantic parameters plus an offered semantic destination ID. Runtime retains
the internal ActionSpace for membership, schema, destination, binding-group,
and current-route admission. The model views exclude binding/schema digests,
backend/surface/executor identity, request and observation lineage, adapter
evidence, selector/coordinate/bbox/href/method, credentials, and private paths.
Secret-like TaskGoal inputs are display-redacted without changing Runtime
authority. The policy cannot invent target identity, binding, backend payload,
confirmation, or completion truth.

P5-M0.1 adds ContextIdentity over task/observation/action-space/page/progress/
pending revisions. A stale decision is discarded with zero execution. Source
assurance describes observation quality but never grants write authorization.

## 8. Planning semantics

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

LocalObjective assigns DIRECT/ENABLING/INFORMATION/OTHER relevance to actions
already legal under TaskGoal. It cannot expand effects, lower risk, create a
capability or prove completion.

## 9. ActionSpace, paging, Batch and clarification

ActionSpace contains current legal, bindable semantic actions. Backend material
remains hidden in the world model. Presentation may be paged or compressed, but
the model cannot select omitted IDs or create raw bindings.
RequestActionPage creates a new action-page ID and therefore a new context ID;
decisions over the prior page are stale.

Material ambiguity yields `AskUser`. A strict profile may validate source
fields and output bindings before the loop, but it cannot create a second
default control path or copy proof/lineage graphs into every BoundActionRequest.

ActionBatch is a later optional optimization. Policy can request it only from
options explicitly marked batchable with no observation barrier. The Runtime
validator enforces max-three, low-risk, same-surface/session, no navigation,
external effect, app/page change, or cross-surface dependency.

## 10. Current migration note

Current code still requires admitted TaskSpec, mandatory planning flows, and
ActionChoiceCatalog authority objects. Those remain baseline behavior until
P5-A/P5-E/P5-H cutover and are not target contracts.

P5-M0 and P5-M0.1 model-boundary contracts are integrated only on the
non-default target loop. P5-M1 adds a model-backed AgentPolicy only through an
injected provider-neutral structured port; no real provider profile, provider
SDK, or model evaluator is present. AgentContext/ContextIdentity/current-page admission and
explicit-hint relevance are implemented; clarification continuation and
targeted observation provider selection remain deferred.
