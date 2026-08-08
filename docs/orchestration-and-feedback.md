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

Before policy invocation, Runtime projects TaskGoal, AgentWorldView, internal
ActionSpace, bounded Turns, and optional TaskPlan into model-safe typed views.
The policy never receives the internal ActionSpace or Turn objects. Its opaque
action ID is resolved and admitted only against the still-current internal
ActionSpace.

## 2. Loop state

The serial MVP state contains current observation ref, bounded recent turns,
optional TaskPlan/milestone summary, pending semantic confirmation, pending
uncertain request, budget, and final result.
Externally meaningful states are RUNNING, WAITING_USER,
WAITING_CONFIRMATION, CANCELLED, DONE, BLOCKED, and FAILED.

Preflight, acting, verifying, and recovering are local call steps, not a global
durable state machine.

## 3. Feedback

Products may stream observation/decision/action/evaluation summaries, but a
stream event is informational. It cannot authorize an action, settle an effect,
or complete a task. Sensitive binding payloads and credentials are excluded.

## 4. Confirmation

WaitingConfirmation carries a typed `ConfirmationRequest`: confirmation ID,
semantic subject ID, ActionIntent, effects, risk, consequences, and a semantic
summary. A decision binds both IDs. On CONFIRM, `AgentRunSession` reobserves,
checks whether the task is already complete, rebuilds ActionSpace, recomputes
the subject, and only then binds the current route. Binding-only changes are
allowed; action/target/destination/parameters/effects/risk/consequences changes
require a new confirmation. DENY clears the request and returns CANCELLED with
zero execution.

If the confirmed subject is absent after the fresh observation, Runtime clears
that approval and returns the already-fresh ActionSpace to the ordinary policy
turn. It does not choose the first or a similar candidate. A terminal session
is immutable: repeated run or resolve calls return its original DONE,
CANCELLED, FAILED, or BLOCKED result without observing or executing again.

## 5. Serial execution

The core executes one primitive request at a time by default. It has no
parallel surface fallback or hidden retry. Later, a max-three low-risk
same-surface batch may run only when all intermediate observation barriers are
false; failure stops the batch and final fresh observation is mandatory.

## 6. Interruption

General checkpoint/resume and crash restoration are non-goals. `AgentRunSession`
is in-memory and process-local with no registry, token, database, or serialized
checkpoint. `NOT_SENT` retains same-subject confirmation for another bounded
fresh rebind; `SENT` and `SENT_UNKNOWN` consume it. No old bound request is
restored or replayed.

## 7. Current migration note

The current Coordinator/stage/delta/committer sequence remains baseline code.
It is not the target sequencing contract and receives no new platform features
during migration.

Task evaluation has explicit control semantics at initial observation,
pre-policy, confirmation reobservation, and post-action evaluation:
`COMPLETE` returns DONE, `INCOMPLETE` permits a policy turn, `UNKNOWN` returns
WAITING_USER with the evaluator reason, and `BLOCKED` returns BLOCKED. UNKNOWN
is not automatically reobserved in this profile.

Every evaluator response is a proposal. Action evaluation must resolve every
evidence ref in the fresh after observation. Task evaluation must match the
task/current observation and pass criterion, evidence, requested-output, and
declared integrity validation before its status controls the loop. Invalid
proposals fail the run and are not recorded as trusted evaluations.
