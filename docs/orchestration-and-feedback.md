# AgentLoop Orchestration and Live Feedback

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** target loop sequencing and externally visible wait/finish states

## 1. Main loop

```text
reset → initial ObservationAcquisition
→ evaluate current task state
→ optionally plan/replace milestones
→ select LocalObjective
→ build Internal ActionSpace and current page
→ project disposable AgentContext
→ policy returns typed AgentDecision with context_id
→ reject stale decision with zero execution
→ risk decision / human confirmation
→ bind current request
→ execute one action or admitted batch once → ExecutionOutcome
→ use returned post observation; capture independently only when needed/supported
→ action evaluation
→ task evaluation
→ append exactly one bounded root ControlTransition for the accepted decision
→ continue / reobserve / replan / ask / wait-confirmation / done / failed
```

AgentLoop sequences collaborators; it does not parse surfaces, choose policy
internals, evaluate effects, or persist telemetry.

Before policy invocation, Runtime projects TaskGoal, bounded IntentContext,
progress, WorldObservation, current action page, bounded ControlTransition
summaries, pending state
and budgets into a disposable AgentContext.
The policy never receives the internal ActionSpace or ControlTransition objects. Its opaque
action ID is resolved and admitted only against the still-current internal
ActionSpace.

## 2. Loop state

The serial target state contains current observation ref, an exact transition
total plus bounded recent ControlTransition suffix, optional TaskPlan and
VerifiedTaskState/frontier, pending semantic confirmation, pending
uncertain request, budget, and final result.
Externally meaningful states are RUNNING, WAITING_USER,
WAITING_CONFIRMATION, CANCELLED, DONE, BLOCKED, and FAILED.

Preflight, acting, verifying, and recovering are local call steps, not a global
durable state machine.
AgentLoopState, task/observation/action-space revisions and pending state remain
Runtime-owned; AgentContext never becomes a second state aggregate.

## 2.1 Control-transition accounting

Every policy decision that passes the current context/schema boundary and is
accepted for Runtime handling produces exactly one immutable root
`ControlTransition`, including SelectAction, RequestObservation,
RequestActionPage, AskUser, ProposeDone, Wait and Abort. Admission rejection,
capability-unavailable, evaluation failure, pending/waiting and terminal
consequences remain typed fields of that same decision record; they are not
recovered later from exception text or several state owners.

A confirmation/user continuation that changes state may carry a typed
continuation source referencing the root transition, but cannot masquerade as
another policy decision. A provider failure before a valid decision, initial
pre-policy completion and harness watchdog have no accepted decision and do not
fabricate one. ControlTransition is run-scoped and bounded, not a durable event
log, replay source, global bus, commit record or state-reconstruction authority.

## 3. Feedback

Products may stream observation/decision/action/evaluation summaries, but a
stream event is informational. It cannot authorize an action, settle an effect,
or complete a task. Sensitive binding payloads and credentials are excluded.
The stream and optional TurnRecorder project ControlTransition/current state;
they are not a second execution truth and recorder failure is behavior-neutral.

Model-facing control feedback is not telemetry, but it keeps the same one-way
authority direction. The owning admission/evaluation/no-gain boundary first
produces a typed fact; a small control-feedback policy may envelope it on that
accepted decision's root `ControlTransition` and decide whether the small frozen
policy-repair budget remains. A dedicated model-boundary projector copies
only the public-safe category/code/subject/field refs, next-decision disposition and
`strategy_transition_required` into the next disposable AgentContext.
ContextBuilder only assembles that view.

The policy consumes this as an outcome observation, not as a Runtime-authored
correction. It may reflect inside its ordinary inference, but any correction is
a new AgentDecision. `next_decision_disposition` means only that a new policy decision
is admitted; it never authorizes replay of the rejected request.

AgentPolicy—not Runtime—uses the next normal `decide()` call to correct public
parameters or change strategy. Runtime never parses exception text into advice,
rewrites parameters, selects a replacement action, or automatically replays a
request. M4.6-D does not add a separate reflector call; a reflector remains an
evidence-gated policy extension if later benchmark results show that explicit
feedback is delivered but ignored.

For repairable zero-dispatch public admission mismatch and policy-origin
no-gain, M4.6-D freezes one shared budget of two distinct issue fingerprints per
unchanged identity-free public semantic scope. An identical issue terminates on
its second occurrence; a third distinct issue terminates with zero
bind/probe/execute/capture. Issue identity excludes invalid parameter values and
fresh Runtime IDs, preventing both value enumeration and alternating invalid
action/page/observation loops. Only effectful `SENT` or relevant public semantic,
task-progress or action-page gain resets the budget; a merely valid no-gain
control decision does not. Runtime binding/currentness/confirmation/post-action
refresh,
risk/safety/task/session terminal, budget/cancel, `SENT_UNKNOWN`, component/
integrity failure and post-admission adapter-contract mismatch are not model
repair paths. No fresh identity alone resets a semantic streak.

The declared bounded feedback path is implemented at
`ccb682a8ef4acb00973e5c6a14c7c69c91d073fc` and verified by the fixed run
`miniwob-control-feedback-25:ca6cfffdf3334844958b38210a5043bd`; correction
measurements remain distinct from task success.

## 4. Confirmation

WaitingConfirmation carries a typed `ConfirmationRequest`: confirmation ID,
semantic subject ID, ActionIntent, effects, risk, consequences, and a semantic
summary. A decision binds both IDs. On CONFIRM, `AgentRunSession` requests a
capability-admitted independent capture,
checks whether the task is already complete, rebuilds ActionSpace, recomputes
the subject, and only then binds the current route. The target admits reuse only
when the current subject is covered by the confirmed subject: exact semantic
action/target/destination/material parameters, effects no broader, risk and
consequences no stronger, and reversibility no worse. The current implementation
uses exact subject equality conservatively. Binding-only changes are allowed;
incomparable or expanded semantics require a new confirmation. DENY clears the
request and returns CANCELLED with zero execution.

If capture is unavailable/failed, the continuation returns a typed control
result and does not bind or send the old request. If the confirmed subject is
absent after the fresh observation, Runtime clears
that approval and returns the already-fresh ActionSpace to the ordinary policy
turn. It does not choose the first or a similar candidate. A terminal session
is immutable: repeated run or resolve calls return its original DONE,
CANCELLED, FAILED, or BLOCKED result without observing or executing again.

## 5. Serial execution

The core executes one primitive request at a time by default. It has no
parallel surface fallback or hidden retry. Later, a max-three low-risk
same-surface batch may run only when all intermediate observation barriers are
false; failure stops the batch and final fresh acquisition is mandatory.

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
new-acquisition-identity check, but the current port does not distinguish their
acquisition mechanisms. Page requests record `page_changed` or
`page_unchanged` in bounded semantic history; they never execute an action.

P5-M1 serializes each disposable context once, makes at most one injected
structured-model call, parses exactly one typed decision, then reuses these
same Runtime context/page/admission, binding, confirmation and evaluator steps.
There is no core retry and provider exceptions/raw payloads do not enter bounded
history.
ProposeDone remains advisory and deterministic TaskEvaluator control is retained.
P5-M1.1 routes that single call through the existing ModelPort owner. An outer
policy deadline bounds the awaited attempt; 429, transient transport, refusal
and structured-output failures become internal `PolicyFailure` results with
zero execution and no fabricated accepted-decision transition. Provider metadata is diagnostic only and
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
M3.1 counts confirmation exactly where the typed decision is submitted and
counts provider/judge attempts at their call ports. Stale zero-call compares a
stale opportunity with actual effectful dispatch, while canonical unknown-attempt
identity excludes bindings/routes and includes semantic parameters, effects and
effective risk.
External-smoke preflight is outside orchestration. Even an admitted manifest
requires both `RUN_EXTERNAL_SMOKE=1` and explicit `--execute`; absent any gate,
no external environment or provider is constructed. Environment-native reward
or completion is consumed only by the benchmark-only mechanical TaskEvaluator
and post-run acceptance, never by policy routing.
Model conformance is also outside orchestration. Levels 0–3 stop before
execution; Level 4 enters the unchanged AgentEpisodeRunner and Runtime
admission. A diagnostic failure cannot trigger retry/fallback, repair output,
change a Runtime turn, or enter AgentContext/Turn history. Compact grounding is
explicit per diagnostic call; the ordinary policy composition stays format-only.
P5-M3.4 makes format-only and compact-contract explicit production composition
choices. Selection occurs once at factory construction; it is not a runtime
router. Grounding construction failure returns typed internal failure before a
provider attempt and never falls back. Matrix/cutover evidence is offline
feedback only and cannot alter active policy or evaluation.

P5-M3.5 adds `compact-contract-v2` to the same one-time factory composition.
The ordinary factory admits it only behind the explicit
`LLM_ENABLE_EXPERIMENTAL_GROUNDING=1` conformance gate; the flag does not make
the profile production-supported or default.
The recurrent benchmark passes exact parsed decisions into production
decision-control owners, but its oracle and qualification status remain
post-hoc evidence. No case ID, expected decision, retry, fallback or provider
name can affect production orchestration.

P5-M3.6 retains the same boundary while making two diagnostic provider calls
with distinct responsibilities: one route proposal and, only after a valid
route, one complete canonical payload. The second call is not a retry. A route
failure causes zero payload and Runtime calls; a payload failure causes zero
effectful Runtime calls. Fixed pacing is recorded but never failure-adaptive,
and progress is observational rather than resumable. No two-stage branch is
present in AgentLoop or production factory composition.

At the P5-M4 baseline, BrowserGym added no branch to orchestration: the loop
performed observe, context construction, policy, admission, bind, execute once,
one-use cache consumption and TaskEvaluation. That baseline supplied normal
post-step freshness but raised RuntimeError when RequestObservation, Wait,
stale/currentness or confirmation refresh reached an empty cache; rerun-v3
observed seven such failures.

M4.5-A has replaced that lifecycle without adding a BrowserGym branch to
AgentLoop. Logical reset returns the prepared initial acquisition, execute
returns the step-derived post acquisition, and capability-admitted refresh uses
owner-thread read-only `capture()`. Before dispatch the adapter still performs
exactly one currentness probe; stale/unavailable is `NOT_SENT` with zero action
calls, and a thrown step remains `SENT_UNKNOWN` with no replay. Official
mechanical status remains Runtime-private evaluator input. Fixed pacing remains
benchmark-only and cannot alter decisions or recover failures.

## Verified-progress selection containment

P5-M4.2 inserts one run-scoped check only after normal selection admission and
before binding. It compares fill/select requested values with current complete
structural public state. An already-satisfied selection records a bounded
route-free progress event plus the accepted decision's root ControlTransition,
then starts a fresh policy context without fabricating ActionResult, transport
status, observation, or execution. One identical
repeat under the same task/criterion/output/relevant-target fingerprint returns
typed `NO_PROGRESS_REPETITION`. Different values, relevant progress, or a
confirmed effect reset the streak. Runtime never chooses Submit or another
replacement action.

At the pre-M4.5-B baseline this branch had no Turn and was an accounting gap.
The M4.5-B candidate records the accepted selection and its suppression/progress
consequence as one ControlTransition while still fabricating no execution or
observation; reducer properties must verify this invariant. The controller remains a fill/select local liveness guard; future
TaskProgressAuditor and planner remain separate P5-E owners.

M4.6-D makes this existing ActionEvaluation/ProgressEvent strategy-transition
feedback explicit in the model-facing channel, but does not turn
ProgressController into a universal effectful-action retry controller. A
different action remains the AgentPolicy's choice.

The reopened convergence contract requires ordered dispatch attempts and physical
acquisition/probe totals to be recorded at their
actual boundaries, before evaluator completion. RuntimeError or cancellation
therefore closes and rethrows from the same accepted-decision root. Confirmation
refresh, binding/currentness refresh and final post acquisition append once in
physical order; terminal, denied or externally completed continuations clear
confirmation state and never create another root. ALREADY_SATISFIED closes the
root before a new policy decision, confirmation may finish after the last policy
turn, and pre-execution evaluation never masquerades as post-action evaluation.
An accepted-decision exception or cancellation also latches a privacy-safe terminal
AgentResult in AgentRunSession before propagating; later session APIs return that
same result without another policy, capture or dispatch. A fresh risk BLOCK takes
precedence over an older approval, and invalid confirmation/risk enum values fail closed.

## Breadth campaign orchestration

The MiniWoB-60 runner creates cases in frozen manifest order, shares one fixed
pacing state across case boundaries, and delegates every episode to the normal
AgentEpisodeRunner/AgentLoop. A case outcome is classified only after the loop
or harness terminates. Failure advances to the next case without retry;
process interruption leaves `complete=false` and a later run must start all 60
cases under a new run ID. Capability labels and aggregate feedback remain
offline measurement and cannot route production decisions.

Future breadth reports retain bounded failure authority: component origin,
stable code, exception class only, last decision type, action/task evaluation
status, ActionSpace/target counts, coverage, and pending kind. They never retain
exception text or traceback. Waiting-user effect uncertainty, task uncertainty,
AskUser, Abort, provider failure, Runtime rejection, evaluator failure,
watchdog, and cleanup are separate outcomes; legacy reports lacking these
fields remain unresolved rather than inferred from prose.

The historical clean `b3b64a2` run (6/60) and clean `83dc4fa` rerun-v3
(4/60) are separate immutable exact-run records. Rerun-v3's seven
post-observation failures motivate M4.5-A; its remaining nine unclassified
typed failures motivate M4.5-B. Neither outcome is online orchestration input.
