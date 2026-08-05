# Agent Orchestration and Live Feedback

The normative contracts, ownership boundary, safety rules, and implementation
sequence for this layer are defined in
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md).

## 1. Orchestration Model

Affordance Runtime uses one evidence-driven control loop:

```text
task / active subgoal
  -> derive PerceptionRequirements
  -> capture one coherent observation epoch
  -> arbitrate sourced assertions
  -> if evidence is insufficient:
       EvidenceGap -> ActivePerceptionController -> bounded read-only probe
       -> new observation epoch -> re-arbitrate
  -> plan -> semantic PlannerProposal -> PlannerProposalValidator
  -> bind -> ActionContract
  -> policy / preflight -> act
  -> observe post-state -> verify
  -> continue / complete

failure from any phase
  -> FailureEnvelope
  -> RecoveryCoordinator
  -> validated RecoveryCommand
  -> owning Runtime port
  -> RecoveryReceipt + non-empty RecoveryDelta
  -> re-enter the normal loop / ask / abort
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
| Assertion Arbiter | deterministic module | Accepts, conflicts, or rejects sourced state claims |
| Active Perception Controller | bounded policy module | Selects the cheapest permitted read-only probe for a typed evidence gap |
| Planner Port | interface | Receives candidate subgoals/actions from reference or parent planner |
| Plan Validator | deterministic module | Validates every deterministic, LM, parent, skill, and recovery proposal |
| Contract Builder | module | Converts selected intent into an executable action contract |
| Action Router | policy module | Chooses DOM, visual, API, device, keyboard, or fallback backend |
| Executor | tool | Performs the action |
| Verifier | module | Checks postconditions against post-action evidence |
| Recovery Coordinator | bounded policy module | Converts phase-general failures into one changed-strategy recovery command |
| Recovery command owner | existing Runtime port | Executes reobserve, replan, reroute, stronger verification, ask, or abort under Coordinator authority |
| Evolution | offline/assisted agent | Mines skills and policy patches from traces after benchmark readiness |

ActivePerceptionController and RecoveryCoordinator do not own a browser, a
second RunState, or a second event log. They return immutable decisions. Only
RunCoordinator applies those decisions and advances authoritative state.

## 3. Unified Execution Order

The implementation order is facts first, effects second:

1. freeze strict-generalist and benchmark-governance boundaries;
2. freeze EvidenceGap, ProbePlan, ProbeReceipt, FailureEnvelope,
   RecoveryCommand, RecoveryReceipt, and RecoveryDelta contracts;
3. complete ActivePerceptionController over the existing
   PerceptionSession/source-arbitration foundation;
4. integrate active perception into normal observation, high-risk preflight,
   and inconclusive verification;
5. normalize failures from intake through verification;
6. add the phase-general RecoveryCoordinator;
7. execute recovery commands through existing owning ports;
8. require a non-empty changed strategy before another attempt;
9. trace and evaluate the complete loop;
10. only then promote replay-gated perception or recovery policy patches.

This order matters. Recovery must first determine whether it lacks facts. When
facts are missing, it invokes active perception; it does not guess a new action.
When an external effect may have occurred, it inspects post-state before any
retry or route switch.

Normal-path active perception is not considered recovery. For example, a
visual-vibe task may request screenshot evidence immediately, while a standard
form task starts with DOM/accessibility and escalates only when structural
evidence is insufficient.

## 4. Feedback Maturity Levels

Do not start with a full continuous event bus. The implementation should mature
in stages.

| Level | Mechanism | Release | Purpose |
| --- | --- | --- | --- |
| L0 | explicit observation before action | skeleton | basic action context |
| L1 | post-action observation | v0.1 | verify actual effects |
| L2 | targeted hooks for navigation, downloads, and modals | v0.2 | handle common web failures |
| L3 | continuous watcher/event bus | later | useful only if it beats L1/L2 on benchmarks |

This avoids overbuilding a watcher before the gold path shows it is necessary.

## 5. Runtime Events

Even without a continuous event bus, trace events should use consistent names:

```text
ObservationCaptured
AffordanceSnapshotBuilt
AssertionArbitrated
EvidenceGapRaised
PerceptionProbePlanned
PerceptionProbeCompleted
PlanProposed
PlanValidated
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
FailureNormalized
RecoveryStarted
RecoveryCommandSelected
RecoveryCommandValidated
RecoveryCommandCompleted
RecoveryDeltaApplied
HumanApprovalRequested
TaskCompleted
TaskFailed
```

Events are recorded in the trace and routed through the coordinator.

## 6. Live Environment Feedback

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

## 7. Change Classification

| Change Type | Example | Runtime Reaction |
| --- | --- | --- |
| non_blocking | animation, timer, ad refresh | log and continue |
| relevant_state | button becomes enabled, result appears | refresh affordances |
| task_progress | URL changed, dashboard loaded | verify current step |
| blocking | modal, login wall, cookie banner | pause and recover |
| hazard | payment, deletion, irreversible operation | request approval or abort |
| drift | target disappeared, selector invalid | rebuild model and replan |

## 8. Coordinator Policy

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

Any phase can emit a FailureEnvelope. Recovery selection follows this order:

```text
effect status
  -> authority and duplicate-effect risk
  -> missing evidence
  -> intent/context/task-plan repair
  -> reground/reroute
  -> idempotent retry or explicit compensation
  -> ask/abort
```

The Coordinator rejects a recovery attempt when its RecoveryDelta does not
change evidence coverage, an assumption, task/step plan, grounding candidate,
route, verifier, provider/context policy, accepted skill use, authority, or user
input.

## 9. Observation as an Action

Dynamic environments sometimes require observation control. The runtime should
model observation itself as a cost-bearing action:

```text
EvidenceGap
  -> permitted probe capabilities
  -> select minimum-cost sufficient ProbePlan
  -> inspect DOM / accessibility / SVG / screenshot / OCR / SoM / WoT / API
  -> produce ProbeReceipt
  -> build a new coherent observation epoch
  -> re-run arbitration
```

Every probe is read-only, budgeted, provenance-preserving, and task-relevant.
Probe results never mutate the old snapshot in place. A surviving
safety-relevant conflict produces an explicit inconclusive result and blocks
effectful execution.

The runtime should track over-observation and under-observation as failure
modes. Observation budgets belong in the State Kernel.

## 10. Metrics

Live feedback should expose:

```text
observation_latency_ms
affordance_refresh_count
evidence_gap_count
probe_count
probe_budget_exhaustion_rate
evidence_resolution_rate
irreducible_conflict_rate
environment_drift_count
blocking_modal_count
postcondition_detection_time
replan_count
recovery_success_rate
recovery_changed_strategy_rate
recovery_loop_stop_rate
uncertain_effect_inspection_rate
duplicate_effect_count
false_positive_drift
false_negative_drift
hazard_block_count
```
