# Runtime-First Architecture Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** product boundary among Runtime, policy/model, adapters, parent agents, and benchmarks

## 1. Runtime product boundary

Affordance Runtime owns the unified world model, action bindings, route
selection, freshness, risk decision, execution result, observation acquisition
lifecycle, and independent evaluation. It does not own the user's high-level
reasoning policy, and it does not turn external content into user authority.

Intake is responsibility-thin but semantically strong. The execution loop is
capability-thick in perception, grounding, legal action generation, route
selection, validation, and replanning, while remaining infrastructure-thin.

## 2. Policy/model boundary

The policy sees only a disposable bounded `AgentContext`: task, context-only
intent, progress, model world, current action page, semantic history, pending
summaries, budgets and decision mode. It may select a current-page action,
request observation/action paging, ask the user, wait, abort, or propose done. It
cannot provide raw selector, coordinate, backend payload, endpoint, file path,
credential, approval, milestone satisfaction, or completion truth.
Every typed decision carries an opaque current context ID; stale context means
zero execution. Runtime alone retains Internal ActionSpace membership and
private routes.

The disposable context may carry one current, public-safe control-feedback
view sourced from typed admission/no-gain facts and existing validated
evaluation/progress facts. Runtime states what failed, whether any dispatch
occurred, and whether one new policy decision is admitted; AgentPolicy chooses
the correction. Runtime never parses exception text into advice, edits
parameters, selects a substitute action, or treats a new policy decision as
replay. M4.6-D uses the ordinary next policy call; an optional reflector is a
later evidence-gated policy implementation, not Runtime authority.

Text from pages, email, documents, screenshots, tools, or providers is observed
data. It may inform state and decisions but cannot create confirmation or widen
the requested effect.

## 3. Adapter boundary

DOM, AX, Visual, SVG, WoT, API, Device, and CLI adapters report truthful entities,
facts, coverage, conflicts, bindings, supported actions, freshness, and results.
They do not interpret task meaning or declare task completion.

Each world adapter declares operational `ObservationCapabilities`, including
whether it supports `independent_capture` and whether execution normally
provides a `post_action_observation`. These capabilities are separate from
evidence modality, source assurance, and verifier independence: recapturability
does not imply strong evidence, and strong evidence does not imply that a
backend can recapture it.

The target world boundary returns one closed `ObservationAcquisition` from
reset/capture, retaining its request, plan, correlated provider/per-need
outcomes, fusion result and typed failure stage. `ExecutionOutcome` composes
the exact `BoundActionRequest`, `ActionResult` and, after a dispatched action,
the exact post-action acquisition. Acquisition distinguishes acquired,
capability-unavailable, failed and acquired-with-unresolved-need states. A backend without independent
capture keeps the capture operation total by returning typed
`CAPABILITY_UNAVAILABLE`; it must not surface an incidental cache miss as a raw
RuntimeError. Reset must still establish the initial observation acquisition.

Credentials and signed URLs are injected at the backend boundary and do not
enter AgentWorldView, BoundActionRequest telemetry, or general trace payloads.

## 4. Action boundary

An ActionIntent expresses one semantic action. ActionBinder binds it to one
current observation and binding as a BoundActionRequest. Runtime checks support
and freshness, asks for semantic confirmation when needed, and executes at most
once. The normal path consumes the typed post-action acquisition returned by
execute. Perception and recovery paths request independent capture only when
the declared capability supports it; unavailable or failed acquisition remains
a typed control outcome. Target confirmation reuse requires the current subject
to be covered by the confirmed subject: exact action/target/destination/material
parameters, no added effects or stronger risk/consequence, and no worse
reversibility. Exact equality is the conservative current implementation;
selector/coordinate/form changes alone may fresh-rebind.

Executor success is transport/execution information only. ActionEvaluator and
TaskEvaluator use freshly admitted evidence at the required assurance. That
evidence may arrive with the execution transition or through supported
independent capture. A `SENT_UNKNOWN` dispatch is recorded before any refresh;
capture failure cannot turn it into a zero-execution failure or authorize a
duplicate attempt.

The default is one action per observation. A bounded ActionBatch is permitted
only for max-three, low-risk, same-observation/surface/session actions whose
options declare no observation barrier. It cannot contain navigation, external
effects, app/page changes, or cross-surface actions and must end with fresh observation.
That final observation must come from a typed post-action acquisition or an
explicitly supported independent capture.

## 5. State, transition and progress boundary

`AgentLoopState` is the authority for current run control state.
`ControlTransition` is a bounded, run-scoped, decision-scoped typed record of
what just happened. One accepted policy decision produces exactly one such
record, including non-action decisions and typed acquisition/admission
failures. It composes exact phase aggregates; model/telemetry summaries never
become its inputs. It is not a durable ledger, event stream, replay source, or state
reconstruction authority. AgentContext and benchmark/timeout artifacts are
disposable projections of the current authorities and bounded transition
suffix.

The bounded full-chain contract is
[Runtime authority aggregate convergence](runtime-authority-aggregate-convergence.md).
Its current implementation is reopened: generic and BrowserGym acquisition
still have duplicate composition roots, and `FreshAcquisition` plus transition
summaries narrow exact outcomes before downstream control.

The former P5-E VerifiedTaskState/TaskPlan/frontier owners are deleted. The
local ProgressController continues to contain exact `fill`/`select` repetition;
it is not a planner or general task-progress authority. Any future long-horizon
working state is benchmark-driven work after R0–R3.

M4.6-D adds a narrow ControlFeedbackPolicy with a frozen two-distinct-issue
same-scope budget for zero-dispatch public admission repair and
action-page/policy-observation no-gain; exact issue repetition stops immediately.
It envelopes rather than re-owns source facts, separates request keys from
request-echo-free results and an identity-free control epoch, stores only bounded
issue/seen-result state in AgentLoopState, and projects once through `agent/context/`.
Risk/safety/task terminal, `SENT_UNKNOWN`, component/integrity failure and an
adapter parameter mismatch after successful Runtime admission remain terminal
or paused according to their owning contracts and are never model-repair replay.
The convergence implementation is
`9e92bd2d3b55a696f06ae77fd029b4bc6db9a903`; D remains
implemented-not-verified pending held-out review, and it does not cut over the
default path.

## 6. Benchmark boundary

BrowserGym, MiniWoB++, WorkArena, WebArena, ScreenSpot, WASP, local fixtures,
and future device suites are evaluators. Production may not branch on task ID,
seed, family, expected answer, selector, coordinate, or authored shortcut.
External reward is never Runtime task completion.

## 7. Baseline and target

The transactional TaskSpec/ActionContract/StateKernel/RuntimeCommitter product
loop is physically deleted. Current production uses the target
`TargetRuntime -> AgentLoop -> AgentRunSession` path. R0–R3 converge its
remaining aggregate/projection boundaries without restoring legacy owners or
adding another framework.
