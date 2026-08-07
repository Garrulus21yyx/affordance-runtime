# AgentLoop Orchestration and Live Feedback

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** target loop sequencing and externally visible wait/finish states

## 1. Main loop

```text
observe
→ evaluate current task state
→ optionally plan/replace milestones
→ select LocalObjective
→ build ActionSpace
→ policy selects ActionIntent or admitted ActionBatch
→ risk decision / human confirmation
→ bind current request
→ execute one action or admitted batch once
→ fresh observe
→ action evaluation
→ task evaluation
→ continue / reobserve / replan / ask / wait-confirmation / done / failed
```

AgentLoop sequences collaborators; it does not parse surfaces, choose policy
internals, evaluate effects, or persist telemetry.

## 2. Loop state

The serial MVP state contains current observation ref, bounded recent turns,
optional TaskPlan/milestone summary, pending semantic confirmation, pending
uncertain request, budget, and final result.
Externally meaningful states are RUNNING, WAITING_USER,
WAITING_CONFIRMATION, DONE, and FAILED.

Preflight, acting, verifying, and recovering are local call steps, not a global
durable state machine.

## 3. Feedback

Products may stream observation/decision/action/evaluation summaries, but a
stream event is informational. It cannot authorize an action, settle an effect,
or complete a task. Sensitive binding payloads and credentials are excluded.

## 4. Confirmation

WaitingConfirmation carries ActionIntent, consequences and a semantic
confirmation-subject identity. On confirmation, Runtime reobserves and rebinds.
Binding-only changes are allowed; target/destination/parameters/effect/risk
changes invalidate confirmation.

## 5. Serial execution

The core executes one primitive request at a time by default. It has no
parallel surface fallback or hidden retry. Later, a max-three low-risk
same-surface batch may run only when all intermediate observation barriers are
false; failure stops the batch and final fresh observation is mandatory.

## 6. Interruption

General checkpoint/resume and crash restoration are non-goals for the current
target. A waiting user/confirmation result may be resumed by the product using
fresh observation; it does not restore stale bindings or replay an old action.

## 7. Current migration note

The current Coordinator/stage/delta/committer sequence remains baseline code.
It is not the target sequencing contract and receives no new platform features
during migration.
