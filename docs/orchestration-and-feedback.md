# Agent Orchestration and Live Feedback

## 1. Orchestration Model

Affordance Runtime uses a layered workflow:

```text
observe -> model -> plan -> preflight -> act -> observe_post_action -> verify -> recover -> report
```

The runtime can contain multiple expert modules, but online execution should be
coordinated by one bounded coordinator. The coordinator owns the task state,
budgets, constraints, evidence obligations, and escalation decisions.

## 2. Components

| Component | Type | Responsibility |
| --- | --- | --- |
| Coordinator | controller | Maintains task state and chooses the next phase |
| Observer | module | Reads DOM, screenshot, accessibility tree, device state |
| Affordance Builder | module | Builds available action space |
| Planner Port | interface | Receives candidate subgoals/actions from reference or parent planner |
| Contract Builder | module | Converts selected intent into an executable action contract |
| Action Router | policy module | Chooses DOM, visual, API, device, keyboard, or fallback backend |
| Executor | tool | Performs the action |
| Verifier | module | Checks postconditions against post-action evidence |
| Recovery | policy/module | Handles failure and drift within budgets |
| Evolution | offline/assisted agent | Mines skills and policy patches from traces after benchmark readiness |

## 3. Feedback Maturity Levels

Do not start with a full continuous event bus. The implementation should mature
in stages.

| Level | Mechanism | Release | Purpose |
| --- | --- | --- | --- |
| L0 | explicit observation before action | skeleton | basic action context |
| L1 | post-action observation | v0.1 | verify actual effects |
| L2 | targeted hooks for navigation, downloads, and modals | v0.2 | handle common web failures |
| L3 | continuous watcher/event bus | later | useful only if it beats L1/L2 on benchmarks |

This avoids overbuilding a watcher before the gold path shows it is necessary.

## 4. Runtime Events

Even without a continuous event bus, trace events should use consistent names:

```text
ObservationCaptured
AffordanceSnapshotBuilt
PlanProposed
ContractBuilt
PreflightPassed
PreflightBlocked
ActionStarted
ActionCompleted
PostActionObservationCaptured
PostconditionPassed
PostconditionFailed
EnvironmentDriftDetected
BlockingModalDetected
HazardDetected
RecoveryStarted
HumanApprovalRequested
TaskCompleted
TaskFailed
```

Events are recorded in the trace and routed through the coordinator.

## 5. Live Environment Feedback

GUI environments are dynamic. The first implementation should rely on
post-action observation and targeted hooks:

```text
v0.1
  observe before action
  revalidate during preflight
  execute
  observe after action
  verify expected effect

v0.2
  add navigation hooks
  add download hooks
  add modal detection
  add stale-target perturbation handling

later
  DOM mutation watcher
  screenshot diff watcher
  accessibility tree watcher
  WoT / device state watcher
  timer / animation watcher
```

A full watcher emits structured changes such as:

```json
{
  "event_type": "environment_changed",
  "change_type": "modal_appeared",
  "severity": "blocking",
  "evidence": {
    "text": "Cookie settings",
    "screenshot": "artifacts/run_001/step_003_modal.png",
    "dom_nodes": ["#cookie-banner"]
  }
}
```

## 6. Change Classification

| Change Type | Example | Runtime Reaction |
| --- | --- | --- |
| non_blocking | animation, timer, ad refresh | log and continue |
| relevant_state | button becomes enabled, result appears | refresh affordances |
| task_progress | URL changed, dashboard loaded | verify current step |
| blocking | modal, login wall, cookie banner | pause and recover |
| hazard | payment, deletion, irreversible operation | request approval or abort |
| drift | target disappeared, selector invalid | rebuild model and replan |

## 7. Coordinator Policy

```text
environment change
  -> classify impact
  -> ignore / wait / refresh / verify / recover / ask / abort
```

The parent agent should not receive raw DOM mutations. It should receive only
decision-relevant summaries:

```json
{
  "status": "needs_approval",
  "reason": "The task reached a payment confirmation page.",
  "trace_id": "run_001",
  "evidence": ["artifacts/run_001/step_012.png"],
  "options": ["approve", "abort", "continue_read_only"]
}
```

## 8. Observation as an Action

Dynamic environments sometimes require observation control. The runtime should
model observation itself as a cost-bearing action:

```text
take screenshot
record short clip
wait for network idle
inspect DOM
inspect accessibility tree
query device state
```

The runtime should track over-observation and under-observation as failure
modes. Observation budgets belong in the State Kernel.

## 9. Metrics

Live feedback should expose:

```text
observation_latency_ms
affordance_refresh_count
environment_drift_count
blocking_modal_count
postcondition_detection_time
replan_count
recovery_success_rate
false_positive_drift
false_negative_drift
hazard_block_count
```
