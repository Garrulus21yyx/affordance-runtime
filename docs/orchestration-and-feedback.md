# AgentLoop Orchestration and Live Feedback

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** target loop sequencing and externally visible wait/finish states

## 1. Main loop

```text
observe
→ evaluate current task state
→ optionally plan/replace milestones
→ select LocalObjective
→ build Internal ActionSpace and current page
→ project disposable AgentContext
→ policy returns typed AgentDecision with context_id
→ reject stale decision with zero execution
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

Before policy invocation, Runtime projects TaskGoal, bounded IntentContext,
progress, WorldObservation, current action page, bounded Turns, pending state
and budgets into a disposable AgentContext.
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
AgentLoopState, task/observation/action-space revisions and pending state remain
Runtime-owned; AgentContext never becomes a second state aggregate.

## 3. Feedback

Products may stream observation/decision/action/evaluation summaries, but a
stream event is informational. It cannot authorize an action, settle an effect,
or complete a task. Sensitive binding payloads and credentials are excluded.

## 4. Confirmation

WaitingConfirmation carries a typed `ConfirmationRequest`: confirmation ID,
semantic subject ID, ActionIntent, effects, risk, consequences, and a semantic
summary. A decision binds both IDs. On CONFIRM, `AgentRunSession` reobserves,
checks whether the task is already complete, rebuilds ActionSpace, recomputes
the subject, and only then binds the current route. The target admits reuse only
when the current subject is covered by the confirmed subject: exact semantic
action/target/destination/material parameters, effects no broader, risk and
consequences no stronger, and reversibility no worse. The current implementation
uses exact subject equality conservatively. Binding-only changes are allowed;
incomparable or expanded semantics require a new confirmation. DENY clears the
request and returns CANCELLED with zero execution.

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

P5-M0.1 is implemented on the non-default target loop. ProposeDone remains
advisory, must claim known criteria without unresolved items, and re-enters
validated TaskEvaluator control. P5-M2 adds criterion-specific production
composition without adding criterion branches to AgentLoop.

P5-M0.1.1 makes every policy invocation a new one-shot epoch, including stale
decision recovery and no-op page cycles. RequestObservation, Wait, stale/currentness
refresh, confirmation refresh and post-action observation share the same
new-acquisition-identity check. Page requests record `page_changed` or
`page_unchanged` in bounded semantic history; they never execute an action.

P5-M1 serializes each disposable context once, makes at most one injected
structured-model call, parses exactly one typed decision, then reuses these
same Runtime context/page/admission, binding, confirmation and evaluator steps.
There is no core retry and provider exceptions/raw payloads do not enter Turn
history. ProposeDone remains advisory and deterministic TaskEvaluator control is retained.
P5-M1.1 routes that single call through the existing ModelPort owner. An outer
policy deadline bounds the awaited attempt; 429, transient transport, refusal
and structured-output failures become internal `PolicyFailure` results with
zero execution and no Turn entry. Provider metadata is diagnostic only and
never enters AgentContext or changes Runtime behavior.
P5-M2 semantic evaluation is likewise one bounded zero-retry provider attempt
covering all current semantic/hybrid criteria. Failure yields UNKNOWN criterion
proposals; Runtime evidence applicability and success composition remain final.
P5-M2.1 permits a `SENT`, LOW-risk observation/local-reversible action with an
inconclusive action evaluation to continue from its fresh observation. It never
replays the request. `SENT_UNKNOWN`, elevated risk and external/irreversible
effects still wait for user direction unless task evaluation already completes.
The P5-M3 internal runner preserves the same pause semantics: `SENT_UNKNOWN`
terminates at `WAITING_USER` without replay, confirmation continuation supplies
only a typed `ConfirmationDecision`, and stale binding yields zero effectful
dispatch. Harness counters observe these outcomes but never modify them.
