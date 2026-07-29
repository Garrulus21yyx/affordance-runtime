# Step Planner Standard Input Read-Set Audit

> Baseline: `8445747f0d734b3998b88edb204e099edf58d259`
> Slice: `TPA-1`
> Status: current read-only inventory

## Current standard boundary

```python
PlannerPort.propose(
    envelope: TaskEnvelope,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlannerDecision | Awaitable[PlannerDecision]
```

The target of TPA-2/3 is `StepPlannerPort.propose(request: PlanningRequest)`.
Only `PlanningRequestBuilder` may read all three legacy objects together.

## Standard triple-signature implementation inventory

| Module | Class | Role | TPA migration |
|---|---|---|---|
| `planning_contracts.py` | `PlannerPort` | standard protocol | rename/cut over in TPA-3 |
| `generalist_planner.py` | `GeneralistLMPlanner` | standard model Step Planner | TPA-3 |
| `planner_adapters.py` | `ParentAgentPlannerAdapter` | parent-agent adapter | TPA-3 |
| `planners.py` | `PricingPlanner` | reference Step Planner | TPA-3 |
| `planners.py` | `SettingsPlanner` | reference Step Planner | TPA-3 |
| `planners.py` | `ExportPlanner` | reference Step Planner | TPA-3 |
| `conformance.py` | `ConformancePlanner` | conformance compatibility planner | TPA-3 compatibility |
| `recovery_evolution.py` | `RecoveryFixturePlanner` | recovery fixture planner | TPA-3 compatibility |
| `benchmarks/adaptive_routing.py` | `_CountingSystem2Planner` | benchmark wrapper | TPA-3/8 |
| `benchmarks/browsergym_episode_runner.py` | `BrowserGymPlanner` | external policy adapter | TPA-3/8 |
| `benchmarks/browsergym_episode_runner.py` | `BrowserGymGeneralistPlanner` | generalist BrowserGym wrapper | TPA-3/8 |
| `benchmarks/generalization_rollout.py` | `_SurfacePlanner` | rollout fixture | TPA-3/8 |
| `benchmarks/generalization_rollout.py` | `_DoneAfterDisclosurePlanner` | rollout fixture | TPA-3/8 |
| `benchmarks/generalization_rollout.py` | `_ProviderFailOncePlanner` | rollout fixture | TPA-3/8 |
| `benchmarks/task_planning.py` | `_StageActionPlanner` | task-planning benchmark Step Planner | TPA-3/8 |

Tests also contain scripted sync and async triple-signature planners. They are
compatibility fixtures and must move with the protocol cutover; they are not part
of the production allowlist above.

## PlannerContextBuilder read set

Each row is a required target projection unless a later behavior-equivalence
test proves it unused.

| Field | Current source | Why needed | Target view | Mutable reference required |
|---|---|---|---|---:|
| Task identity/revision/objective/constraints/targets/success | `envelope.task_spec` | bind task authority and provider context | `PlannerTaskView` | false |
| Granted capabilities | `envelope.capabilities` | distinguish requested from currently granted authority | `PlannerTaskView.granted_capabilities` | false |
| Active step objective | `state.active_subgoal()` plus TaskSpec fallback | focus next action | `PlannerStepView.active_step` | false |
| Active action family | `state.task_plan` + `state.plan_progress.active_subgoal_id` | restrict current action family | `PlannerStepView.active_step` | false |
| Latest receipt status/backend/error | `state.receipts[-1]` | avoid blind repetition and report outcome | `PlannerOutcomeSummary` | false |
| Latest verification status/reason/evidence | `state.latest_verification` | evidence-aware progress and finish control | `PlannerOutcomeSummary` | false |
| Recent proposal | `state.planner_history[-1:]` | bounded repair/history context | immutable recent proposal summary | false |
| Verified effects | latest proposal plus passed verification | exclude verified work | `PlannerOutcomeSummary.verified_criterion_ids/effects` | false |
| Pending evidence obligations | `state.pending_obligations[-5:]` | compatibility evidence prompt context | compatibility request field | false |
| Satisfied action targets | `state.action_progress[-40:]` plus current page/environment revision | exclude repeated satisfied effects | frozen target/action tuples | false |
| Relevant failure | progress guard, failed receipt, verification, recovery diagnostics, current failure | bounded recovery guidance | `PlannerRecoverySummary` | false |
| Remaining budgets | state counters plus `PlannerLimits` | bound actions and observations | `RuntimeBudgetView` | false |
| State version | `state.version` | stale proposal binding | `PlanningRequestIdentity` | false |
| Visible text | `snapshot.observation.metadata.visible_text` | bounded page evidence | `PlannerObservationView.observed_text` | false |
| Affordance inventory | unified affordances plus source affordances | semantic target/action selection | tuple of `PlannerAffordanceView` | false |
| Permitted actions | current inventory plus finish policy | provider schema restriction | `PlanningRequest.permitted_action_kinds` | false |
| Artifact references | `snapshot.observation.artifact_refs` | opaque correlation only | immutable opaque refs | false |
| Snapshot/page/environment identity | `snapshot.observation` | stale binding | `PlanningRequestIdentity` | false |

Literal audit marker required by governance:

```yaml
mutable_reference_required: false
```

## Additional direct readers outside PlannerContextBuilder

### GeneralistLMPlanner

`GeneralistLMPlanner.propose` uses the raw triplet only to:

1. require a TaskSpec;
2. build `PlannerContext`;
3. call terminal narrowing with StateKernel and BrowserSnapshot.

After those steps the model orchestration uses `PlannerContext`. TPA-3 therefore
migrates terminal narrowing before removing the raw signature.

### StrictDecisionConstraintBuilder

`narrow_terminal_candidates` directly reads:

- `state.task_plan`;
- `state.plan_progress`;
- `snapshot.unified_affordances`;
- `snapshot.observation` and target fingerprints.

Target: immutable TaskPlanView/StepProgressView/PlannerObservationView adapter.

### ParentAgentPlannerAdapter

It uses the raw triplet solely through `build_planner_context`, then sends the
bounded JSON context to the parent source. Target: build from PlanningRequest.

### Reference planners

| Planner | Direct reads | Target projection |
|---|---|---|
| `PricingPlanner` | HTML metadata, affordances, URL, active plan criterion/requirement IDs | observation plus active-step criterion policy |
| `SettingsPlanner` | receipts, latest verification, affordances, URL | recent outcomes plus observation |
| `ExportPlanner` | latest verification, receipt evidence, affordances, URL | recent outcomes plus observation |

These planners currently produce compatibility `ActionContract` values directly.
TPA-3 changes input only; contract-output retirement is a separate boundary.

### Benchmark and compatibility wrappers

BrowserGym and generalization wrappers either delegate the full triplet or
construct compatibility decisions from snapshot/state. They migrate after core
context equivalence is established, but before the standard old signature is
deleted.

## Sole future projection owner

`PlanningRequestBuilder` may read `TaskEnvelope`, `StateKernel`, and
`BrowserSnapshot` together. It may not:

- mutate StateKernel or activate a step;
- write trace;
- invoke a planner;
- admit or replace a TaskPlan;
- decide finish or recovery;
- retain any source list/dict/object by reference.

## Provider-facing equivalence gate

Before TPA-3 cuts over the standard port, identical legacy inputs must produce
equivalent PlannerContext JSON, terminal narrowing, permitted actions, target
sets, budget summaries, recent outcome summaries, and proposal identity. Any
intentional provider payload change requires a policy-version update and clean
6x2 PR breadth; otherwise PR breadth remains held.
