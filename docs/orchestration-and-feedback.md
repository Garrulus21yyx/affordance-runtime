# Agent Orchestration and Live Feedback

## 1. Orchestration Model

Affordance Runtime uses a layered workflow:

```text
observe -> model -> plan -> act -> verify -> recover -> learn
```

The runtime can contain multiple expert modules, but the online execution should
be coordinated by one bounded coordinator.

## 2. Components

| Component | Type | Responsibility |
| --- | --- | --- |
| Coordinator | main agent / controller | Maintains task state and chooses the next phase |
| Observer | module | Reads DOM, screenshot, accessibility tree, device state |
| Affordance Builder | module | Builds available action space |
| Planner | agent/module | Selects next subgoal and action contract |
| Action Router | policy module | Chooses DOM, visual, API, device, keyboard, or fallback backend |
| Executor | tool | Performs the action |
| Verifier | module | Checks postconditions |
| Recovery | agent/module | Handles failure and drift |
| Evolution | offline agent | Mines skills and policy patches from traces |

## 3. Event-Driven Runtime

The runtime is driven by events:

```text
ObservationEvent
AffordanceUpdated
PlanProposed
ActionStarted
ActionCompleted
PostconditionPassed
PostconditionFailed
EnvironmentChanged
EnvironmentDriftDetected
BlockingModalDetected
HazardDetected
RecoveryStarted
HumanApprovalRequested
TaskCompleted
```

Events are recorded in the trace and routed through the coordinator.

## 4. Live Environment Feedback

GUI environments are dynamic. The system should include an Environment Watcher:

```text
Environment Watcher
  DOM mutation watcher
  screenshot diff watcher
  URL / navigation watcher
  network idle watcher
  accessibility tree watcher
  WoT / device state watcher
  timer / animation watcher
```

The watcher emits structured changes:

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

## 5. Change Classification

| Change Type | Example | Runtime Reaction |
| --- | --- | --- |
| non_blocking | animation, timer, ad refresh | log and continue |
| relevant_state | button becomes enabled, result appears | refresh affordances |
| task_progress | URL changed, dashboard loaded | verify current step |
| blocking | modal, login wall, cookie banner | pause and recover |
| hazard | payment, deletion, irreversible operation | request approval or abort |
| drift | target disappeared, selector invalid | rebuild model and replan |

## 6. Coordinator Policy

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

## 7. Observation as an Action

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

This is especially relevant for living-screen environments where the interface
changes continuously. The runtime should track over-observation and
under-observation as failure modes.

## 8. Metrics

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

