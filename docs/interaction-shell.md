# External Web Interaction and Evaluation Shell

Status: **Proposed external product shell**  
Date: 2026-08-26  
Scope: standalone Web product and evaluation proposal outside the core Runtime

## 1. Decision

Build one external Web shell. It is neither a second GUI Agent nor an internal Core module. It owns user-facing session
lifecycle, command serialization, bounded conversational revision input, event delivery, evaluation projection, and
browser viewing. It consumes only versioned typed Runtime commands, events, snapshots, trace exports, and benchmark
artifacts. It does not import, mutate, or drive `CoreAgentLoop` internals.

The initial implementation uses:

- Next.js for the product UI;
- CopilotKit V2 components for chat and human-in-the-loop presentation;
- shadcn/ui dashboard blocks and primitives for layout and status panels;
- AG-UI events over Server-Sent Events for run, step, tool, message, and UI-projection updates;
- ordinary typed HTTP commands for user answers and confirmation, plus capability-gated cancellation and revision;
- Steel Live View for the first embedded browser viewer, with Browserbase as the managed alternative;
- a Python HTTP service around a `RunSessionManager` and a thin `RuntimeSessionPort` adapter.

Android and desktop are deferred and are not part of this proposal's implementation or acceptance scope.

### 1.1 Reuse-first implementation rule

Infrastructure, protocol, UI primitives, browser transport, model transport, tracing, and test automation should use
mature existing components. Custom code is limited to the domain-specific adapters and projections that no general
framework can own without duplicating Runtime authority.

| Need | Reuse | Do not build |
|---|---|---|
| Web application | Next.js | custom router, SSR, or build system |
| Chat and human input | CopilotKit `CopilotChat` and human-in-the-loop components | chat scrolling, streaming, or approval state UI |
| UI layout and controls | shadcn/ui | modal, tabs, panels, timeline, and dashboard primitives |
| Run event protocol | AG-UI SDK over SSE | a proprietary event protocol or client event runtime |
| HTTP and schemas | FastAPI and Pydantic | request parsing, validation, or hand-written schema machinery |
| Frontend API types | generated from the FastAPI OpenAPI document | separately maintained TypeScript DTOs |
| Browser automation | existing Playwright/BrowserGym Runtime | browser actions, currentness, or selectors |
| Browser media/input | Steel Live View or Browserbase | screenshot polling, video encoding, or mouse/keyboard transport |
| Structured model calls | existing PydanticAI/provider boundary | another LLM or Agent framework |
| Trace, usage, and cost | existing local trace plus Langfuse | another observability platform |
| Charts | shadcn chart components/Recharts | custom SVG charting |
| Web end-to-end tests | Playwright | a custom browser test harness |

Only the following proposal-specific code is expected:

1. `RuntimeSessionPort`: one thin translation boundary over supported public Runtime capabilities;
2. `RunSessionManager`: session lifetime, serialized/idempotent commands, event cursor, viewer handle, and cleanup;
3. `TaskRevisionCompiler`: bounded input and closed structured-output contract using the existing model provider;
4. `CaseDiagnosisProjector`: deterministic interpretation of exported benchmark/trace evidence;
5. Web composition and small domain renderers over the reused UI components.

The proposal does not introduce Temporal, Celery, a custom workflow engine, a custom event store, or multiple tracing
platforms for the initial scope. It also does not embed Agent TARS, Qwen-Agent, LangGraph, AutoGen, CrewAI, or another
top-level Agent kernel: those would duplicate the existing goal, policy, state, or execution authority. A dependency is
admitted when it supplies a mature boundary capability without becoming a second GUI Agent, task authority, state
machine, or Runtime loop.

### 1.2 Simplicity contract

The external shell is organized around four public concepts:

```text
RuntimeSessionPort
ShellCommand
RuntimeSessionSnapshot
ShellEvent
```

`RuntimeSessionPort` exposes coarse product operations rather than internal Core transitions. `ShellCommand` is one
closed command union with command identity and expected public revision/status. Every command returns one small typed
admission result: `Accepted | Conflict | Unsupported | Rejected`. The port does not expose Binder, Monitor, provider,
step-commit, selector, or private World APIs.

There is one current public `RuntimeSessionSnapshot` per session and one ordered `ShellEvent` stream. Runtime facts are
converted to their public shell representation once at the adapter boundary, then reused unchanged by SSE, snapshot
hydration, UI rendering, and optional persistence. The frontend and Langfuse adapters must not independently rebuild
run status, pending input, task completion, or execution outcomes. Benchmark diagnosis separately consumes the
versioned benchmark/trace export and never round-trips through UI events.

`RunSessionManager` keeps only external resource state: session identity, Runtime/viewer handles, command lock or
queue, event cursor, expiry, and whether the external session is open or closed. Runtime status remains in the public
snapshot. Conversation revision keeps one bounded context. No mirrored Runtime state machine, workflow graph, mutable
plan progress, event-sourced reconstruction, or collection of partially overlapping session projections is added.

Safety is proportional to this boundary. The shell performs ordinary authentication/session isolation, typed input
validation, stale-command rejection, secret/private-field exclusion, and viewer-URL protection. Task permission,
confirmation, binding, currentness, and effect enforcement remain Runtime responsibilities. The proposal adds no
security classifier, taint engine, policy DSL, generalized capability system, speculative threat workflow, or
security-specific retry/state machine.

New abstraction is justified only by a demonstrated second consumer or a contract that cannot be expressed through
the four public concepts above. Prefer one direct adapter and a small explicit union over registries, plugin systems,
generic orchestration layers, nested projections, and extensibility designed for hypothetical future surfaces.

## 2. Why this is an external proposal

The repository already has a one-shot product CLI, a persistent benchmark console, typed `RunState`, and Runtime
entrypoints for initialization, continuation, user-answer resume, and confirmation resume. It does not yet have a
product owner for keeping a surface environment and run alive across independent HTTP requests.

The proposal establishes one product boundary for:

- starting, observing, pausing, resuming, cancelling, and replacing runs;
- displaying `AskUser` and RiskPolicy confirmation without inventing new control semantics;
- showing the current surface while keeping private bindings out of the UI event stream;
- recording and diagnosing Web runs without changing Runtime behavior;
- adding later task-revision and user-takeover flows once their Runtime contracts are explicit.

The shell must remain deliberately thinner than a workflow engine. It must not accumulate plan progress, reconstruct
Runtime state from traces, interpret the current GUI, or add a control path beside the Runtime's public entrypoints.

## 3. Architecture and ownership

```text
┌──────────────────────────── Next.js UI ────────────────────────────┐
│ CopilotChat │ SurfaceViewer │ Run status / tool timeline / outputs │
└───────┬───────────────┬───────────────────────────────┬────────────┘
        │ typed HTTP     │ viewer-native media/input    │ AG-UI SSE
        │ commands       │ channel                      │ events
        ▼               ▼                               ▲
┌──────────────────── Python interaction service ───────────────────┐
│ RunSessionManager                                                 │
│   command serialization │ surface lifecycle │ event cursor         │
│   bounded conversation  │ control lease     │ UI event projection  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ RuntimeSessionPort only
                               ▼
                       existing Runtime public API
                               │
                               ▼
                     existing Web environment

benchmark artifacts / exported trace
              │
              ▼
     CaseDiagnosisProjector ──> Langfuse / evaluation UI
```

`RuntimeSessionPort` is the anti-coupling boundary. The external service may request only supported operations such as
start, continue, answer, confirm, snapshot, subscribe, and close. Optional cancel, revise, pause, and takeover methods
are exposed only when the Runtime independently publishes those typed capabilities. The shell never calls
`CoreAgentLoop.step()`, edits `RunState`, or reconstructs a transition from trace data.

### 3.1 Authoritative owners

| Fact or transition | Owner |
|---|---|
| Current user goal and revision | `TaskGoal` produced through TaskIntake |
| Current environment | fresh `WorldObservation` |
| GUI action selection | the single `ActionPolicy` |
| Binding, legality, currentness, risk | existing Runtime owners |
| Run control state and step commit | `CoreAgentLoop` and `RunState` |
| Task completion | `TaskEvaluator` or native verifier |
| Web browser/session lifetime | `RunSessionManager` |
| User/agent control lease | interaction control boundary |
| UI-visible event projection | AG-UI projection adapter |
| Conversation window used for revision interpretation | bounded conversation context |

The manager stores owner values or references to owner values; it does not keep independently mutable copies of the
current goal, run status, pending question, or pending confirmation.

### 3.2 Session value

Illustrative shape:

```python
@dataclass
class RunSession:
    session_id: str
    runtime_handle: RuntimeSessionHandle
    browser_view: BrowserViewHandle
    public_snapshot: RuntimeSessionSnapshot
    control_state: SessionControlState
    conversation: BoundedConversationContext
    event_cursor: int
```

Derived UI facts come only from the latest versioned public snapshot/event:

- active task and revision;
- public run status;
- pending question identity;
- pending confirmation identity;
- owner-produced completion outcome.

`SessionControlState` is not a second task status. It only identifies who currently owns input and whether the
interaction service has requested a boundary pause, cancellation, or teardown.

## 4. Reused Runtime behavior and current gaps

The current implementation can be wrapped behind `RuntimeSessionPort` using:

- `TargetRuntime.initialize_task(...)`;
- `TargetRuntime.continue_task(...)`;
- `TargetRuntime.resume_user(...)`;
- `TargetRuntime.resume_confirmation(...)`;
- `RunStatus.WAITING_USER` and `RunStatus.WAITING_CONFIRMATION`;
- consecutive task revision on `resume_user`;
- typed `StepResult`, execution receipts, task evaluation, and trace events.

The adapter may use supported Runtime entrypoints internally, but the external shell depends only on the port contract.

The following are not currently general supported transitions and must not be simulated in the manager:

- interrupting a running policy or executor in the middle of an atomic action;
- cancelling a running task through an external product command;
- revising a task while `RunState` is still `RUNNING`;
- returning control after arbitrary manual page mutation;
- treating a new unrelated instruction as a revision of the current run.

Cancellation, running-task pause, revision, and takeover remain disabled until the Runtime exposes corresponding typed
public capabilities. The external proposal does not prescribe an internal CoreLoop change and does not simulate these
transitions. Closing a Web session may release external viewer resources, but it cannot be reported as a Runtime task
cancellation unless the Runtime returns that typed outcome.

## 5. Frontend composition without hand-built primitives

### 5.1 Recommended component stack

Use CopilotKit rather than combining CopilotKit and assistant-ui. CopilotKit speaks AG-UI directly and provides chat,
sidebar, and human-in-the-loop hooks. assistant-ui is a viable alternative when richer standalone chat/tool rendering
is more important than native AG-UI integration, but using both would introduce two frontend runtimes and duplicated
message/tool state.

| UI need | Existing component |
|---|---|
| Chat thread and composer | CopilotKit `CopilotChat` |
| Optional collapsible chat | CopilotKit `CopilotSidebar` |
| Human approval/input rendering | CopilotKit `useHumanInTheLoop` |
| Application frame | shadcn/ui dashboard/sidebar block |
| Three resizable columns | shadcn/ui `ResizablePanelGroup` |
| Run and connection state | `Card`, `Badge`, `Progress`, `Alert` |
| Step/tool history | `ScrollArea`, `Accordion`, `Collapsible` |
| Confirmation | `AlertDialog` |
| Task or session switcher | `Command`, `Dialog` |
| Outputs and evidence | `Tabs`, `Table`, `Sheet` |
| Narrow-screen presentation | `Drawer`, `Sheet` |

The project still needs composition and a small number of domain renderers. It should not hand-build chat scrolling,
message streaming, tool lifecycle chrome, modal primitives, split panes, or browser video transport.

### 5.2 Three-column layout

```text
┌──────────────────┬──────────────────────────┬─────────────────────┐
│ Conversation     │ SurfaceViewer            │ Run inspector       │
│                  │                          │                     │
│ task/revision    │ read-only while agent    │ task + revision     │
│ AskUser          │ interactive on takeover  │ current step        │
│ confirmation     │ connection state         │ tool/execution      │
│ final response   │ Web browser              │ evaluation/outputs  │
└──────────────────┴──────────────────────────┴─────────────────────┘
```

The inspector displays owner-emitted projections. It does not infer plan progress, success, or execution state from
text messages.

## 6. Transport decision

No single transport should carry commands, structured run events, and high-frequency pixels/input.

| Traffic | Transport | Reason |
|---|---|---|
| Run lifecycle, steps, tools, messages, UI snapshots | AG-UI over SSE | ordered server-to-browser stream; official AG-UI default |
| Answer and confirm; capability-gated revise/cancel/takeover | typed HTTP `POST` | explicit command identity, validation, idempotency, and response |
| Browser video and manual mouse/keyboard | Live View iframe using WebRTC/screencast | avoids base64 screenshot streaming and custom input protocol |
| Reload and lost-event recovery | snapshot plus event cursor | deterministic resynchronization |
| External provider callback | webhook only when required | server-to-server completion notification, not UI streaming |
| Health/status fallback | bounded polling | fallback only, never primary step delivery |

### 6.1 Why SSE for Runtime events

AG-UI defines lifecycle, step, text, tool-call, tool-result, state snapshot/delta, activity, and custom events. Its
official Python package provides typed Pydantic models and SSE encoding. The interaction service should project current
Runtime events into this wire vocabulary rather than replacing Runtime contracts with AG-UI state.

Commands travel on separate HTTP requests while the SSE stream remains open. Reconnection uses an event cursor or
`Last-Event-ID`; durable owner events are replayed, while transient streaming deltas may be dropped or reconstructed
from the final durable event.

### 6.2 Why not webhook or primary polling

A browser UI is not a reliable public callback target, so webhook is the wrong direction for live agent output.
Polling increases latency and creates ambiguous duplicate delivery unless every response is cursor-based. It remains
useful only for initial session hydration, health checks, and recovery when SSE cannot reconnect.

### 6.3 When WebSocket is justified

WebSocket is appropriate for a viewer or sandbox channel carrying high-frequency bidirectional input. It is not
required for ordinary run events and user commands. Steel/Browserbase already own the browser media/input channel.
No mobile or desktop viewer protocol is selected in this proposal.

## 7. AG-UI projection

Suggested mapping:

| Runtime fact | AG-UI projection |
|---|---|
| run start | `RunStarted` |
| step start/commit | `StepStarted` / `StepFinished` |
| model-selected tool call | `ToolCallStart`, arguments, `ToolCallEnd` |
| local tool result or execution receipt | `ToolCallResult` |
| final user-facing text | text message start/content/end |
| bounded UI state | `StateSnapshot` or `StateDelta` |
| user information required | custom `user_input.required` |
| RiskPolicy confirmation | custom `confirmation.required` |
| task revised | custom `task.revised` |
| run completion | `RunFinished` |
| Runtime failure | `RunError` |

The projection must exclude:

- raw model prompts or hidden reasoning;
- selector, coordinate, backend handle, accessibility node ID, and private binding;
- credentials and provider environment values;
- full `WorldObservation` payloads;
- a second mutable copy of GoalPlan item status;
- claims of completion not produced by the completion owner.

The UI may show a public semantic tool target such as `E7`, its label, a typed execution status, and bounded public
effect evidence.

## 8. Typed command API

Initial endpoints:

```http
POST /sessions
POST /sessions/{session_id}/tasks
GET  /sessions/{session_id}
GET  /sessions/{session_id}/events

POST /sessions/{session_id}/commands/answer
POST /sessions/{session_id}/commands/confirm
POST /sessions/{session_id}/commands/close
```

Later endpoints after their Runtime contracts exist:

```http
POST /sessions/{session_id}/commands/cancel
POST /sessions/{session_id}/commands/revise
POST /sessions/{session_id}/commands/takeover
POST /sessions/{session_id}/commands/return-control
POST /sessions/{session_id}/commands/start-new-task
```

Every command carries:

```text
command_id
session_id
expected_task_revision
expected_run_status or pending request identity where applicable
typed payload
```

The manager serializes commands per session and rejects stale or duplicate commands deterministically. An HTTP success
means the command was admitted, not that the GUI task succeeded. Task outcome continues to arrive through owner events.

## 9. User interaction flows

### 9.1 Start task

```text
StartTask
→ TaskIntake
→ admitted task / typed intake outcome
→ RunSessionManager asks RuntimeSessionPort.start
→ SSE until waiting or terminal status
```

### 9.2 Answer `AskUser`

```text
Runtime → public user-input-required event
→ user_input.required event
→ AnswerQuestion command with pending request identity
→ TaskIntake produces consecutive TaskGoal revision
→ RuntimeSessionPort.answer
→ owner-produced revised snapshot/event
```

### 9.3 Confirmation

```text
RiskPolicy → WAITING_CONFIRMATION
→ confirmation.required event
→ Confirm command
→ RuntimeSessionPort.confirm(approved=True|False)
```

No revision compiler participates in a boolean confirmation decision.

### 9.4 Running-task revision

This feature is absent until `RuntimeSessionPort` advertises a typed running-revision capability:

```text
ReviseTask command
→ TaskRevisionCompiler
→ proposed revision command
→ RuntimeSessionPort.revise
→ owner-produced accepted / needs-input / unsupported outcome
```

The shell does not implement pause, invalidation, fresh acquisition, or resume itself. A completely unrelated
instruction yields `NewTaskSuggested`; after explicit user confirmation, the shell requests a new Runtime session
rather than forcing it into the old task identity.

### 9.5 Takeover and return

This is also capability-gated. The viewer becomes interactive only after `RuntimeSessionPort` returns a typed
user-control lease. The shell does not infer that the Agent stopped from viewer state. Returning control is complete
only when the Runtime returns a new public snapshot/event after handling any required invalidation and observation.

## 10. Bounded conversation and revision compiler

Conversation history is used only to interpret user-owned task revision language such as “change it to tomorrow” or
“use the second one.” It is not Runtime memory or a second goal authority.

```python
@dataclass(frozen=True)
class BoundedConversationContext:
    current_task_id: str
    current_task_revision: int
    recent_turns: tuple[ConversationTurn, ...]  # normally 3–6
    pending_question: AskUser | None
    pending_confirmation: ConfirmationRequest | None
    latest_user_message: str
```

The later `TaskRevisionCompiler` receives the current `TaskGoal`, pending question if any, bounded recent turns, latest
message, and the fields the user is permitted to modify. Its closed outcomes are:

```text
RevisionReady
NeedsInput
NoChange
NewTaskSuggested
Unsupported
Failed
```

It cannot produce GUI actions, selectors, coordinates, plan progress, task completion, or expanded permissions. Its
output must pass through TaskIntake before becoming a new `TaskGoal` revision.

## 11. Evaluation and bad-case diagnosis

Evaluation is an external consumer of exported evidence. It does not add an evaluator, monitor, state machine, or
trace-dependent control path to the Runtime.

```text
versioned BenchmarkCaseResult + public trace export
                    │
                    ▼
          CaseDiagnosisProjector
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
   Langfuse projection    Web evaluation view
```

`CaseDiagnosisProjector` emits:

```text
terminal_stage
terminal_code
first_abnormal_step
last_progress_step
likely_upstream_stage
context_health
trajectory_metrics
evidence_refs
```

Canonical outcome and failure fields are copied from exported owner facts. `likely_upstream_stage` is a bounded,
non-authoritative classification with confidence and evidence references; `unknown` is valid. Monitor no-progress or
oscillation is a control-stage terminal fact, not automatic proof that Monitor caused the run to fail. A supported
upstream classification may identify perception, policy, grounding/binding, execution, or evaluation only when the
preceding exported evidence establishes it.

A hard context-capacity diagnosis requires an exported capacity rejection or `complete_request_tokens` exceeding the
exported `effective_input_limit`. High history share, compaction, and long trajectories are context pressure only.
Claims of context pollution or summary information loss require controlled replay/ablation and are not inferred from
one trace.

The projection exposes success, failure stage, first abnormal step, token usage by request section, model/runtime
latency, steps, retries, recoveries, no-progress/cycles, context fill ratio, and capacity rejection. Langfuse remains a
viewer for these projections. The shell neither changes benchmark status nor treats Langfuse availability as evidence
of task success.

## 12. Surface viewing

### 12.1 Web v0

Steel returns a session `debugUrl` that can be embedded in an iframe. The default Agent view is read-only. A later
takeover flow enables interaction only while the user holds the control lease.

```tsx
<iframe
  src={`${debugUrl}?interactive=false&showControls=true`}
  className="h-full w-full border-0"
/>
```

Steel's headful Live View uses WebRTC/H.264. Its debug URLs are unauthenticated by design, so a public deployment must
protect access and must never expose a reusable URL outside the authorized session. Browserbase provides a managed
Live View and session inspector and is the alternative when operational speed is more important than local ownership.

## 13. Core-isolation contract

The proposal lives outside the core package and depends on versioned ports/artifacts only:

- `RuntimeSessionPort` for supported commands and public snapshots/events;
- a browser-view provider handle for pixels and optional leased input;
- versioned benchmark result and trace-export schemas for diagnosis;
- Langfuse APIs as an optional projection sink.

It does not import `CoreAgentLoop`, Binder, Executor, Monitor, internal `RunState`, private World objects, or provider
history. It cannot add a Runtime transition, infer one from trace, or make a projection authoritative. If a desired
operation is absent from the public port, the UI reports it as unavailable and the proposal remains blocked on that
capability instead of implementing a workaround.

The intended implementation is a separately deployable service and frontend, or a separate top-level package with
its own dependency manifest. Core-domain classes must not become frontend DTOs. The adapter translates public Runtime
outcomes into versioned shell contracts at one boundary; neither UI nor diagnosis code depends on the adapter's
internal Runtime imports.

Prompt injection is only a design constraint here. The shell treats page/DOM/OCR/tool text as untrusted display data
and never converts it into a revision, permission, or confirmation. It relies on the Runtime's existing deterministic
task, risk, binding, and execution boundaries. No security Agent, injection detector, security benchmark, or security
dashboard is proposed.

## 14. Implementation sequence

### Phase A — external diagnosis projection

1. Freeze the versioned benchmark-result and public trace-export inputs consumed by the proposal.
2. Implement `CaseDiagnosisProjector` without Runtime imports.
3. Project token, latency, trajectory, context-health, terminal-stage, and evidence-linked diagnosis to Langfuse.
4. Add the Web bad-case list and case-detail timeline.

### Phase B — Web shell v0

1. Define `RuntimeSessionPort` and implement a thin adapter over currently supported `TargetRuntime` entrypoints.
2. Add `RunSessionManager` with one serialized command queue, event cursor, browser-view handle, and expiry per session.
3. Add cursor-based SSE/AG-UI projection and StartTask, AnswerQuestion, Confirm, Close, snapshot, and event endpoints.
4. Scaffold Next.js, CopilotKit, and shadcn/ui.
5. Embed one read-only Steel or Browserbase live view.
6. Render public task, step, execution, evaluation, output, token, and diagnosis projections.
7. Record one end-to-end Web demo without any core modification.

### Phase C — bounded user revision

1. Add bounded conversation storage in the external service.
2. Implement the typed `TaskRevisionCompiler` as a one-shot proposal compiler.
3. Support explicit/pending-question revision only through currently available port capabilities.
4. Enable running-task revision and new-task replacement only if later public Runtime capabilities advertise them.

### Phase D — optional takeover

Enable interactive viewer control only after the public port exposes an exclusive control lease and typed return
outcome. No CoreLoop or binding behavior is implemented in this proposal.

Android and desktop are deferred indefinitely from this sequence. No Android/ADB/UIAutomator, desktop/AT-SPI/VNC,
cross-surface abstraction, dependency, or acceptance gate belongs to the current proposal.

## 15. Acceptance criteria

The Web v0 is acceptable when:

- the external API consists of one `RuntimeSessionPort`, one closed command union, one public snapshot schema, and one
  ordered event envelope rather than parallel per-feature protocols;
- a session survives multiple HTTP requests without reconstructing Runtime state from events;
- one task runs through `RuntimeSessionPort` without the shell importing or driving `CoreAgentLoop`;
- event order is stable, cursor-resumable, and duplicate commands are rejected;
- `AskUser` and confirmation pause and resume through existing typed Runtime entrypoints;
- unsupported cancel, revision, or takeover capabilities are disabled rather than simulated;
- the viewer is read-only while the Agent controls the surface;
- public events contain no selector, coordinate, private binding, credential, or full World payload;
- completion shown in the UI exactly matches `TaskEvaluator` or native-verifier output;
- external browser/session cleanup happens once on close, terminal completion, or expiry;
- a reload hydrates from snapshot plus event cursor without creating a second run;
- no frontend component directly invokes an executor or silently revises `TaskGoal`;
- diagnosis consumes exports only and cannot change task, failure, Monitor, or benchmark truth;
- Langfuse failure cannot change or erase the local exported result;
- each Runtime fact is publicly projected once and reused by snapshot/event consumers without a second status,
  completion, pending-input, or execution-outcome derivation;
- shell-owned state remains limited to external resource lifetime, serialization, cursor, expiry, and bounded
  conversation context;
- safety code remains limited to ordinary product-boundary checks and reuses Runtime enforcement for task effects.

Running-task revision and takeover are acceptable only when the public Runtime port returns their typed outcomes; the
external shell is tested only for correct command admission, stale-command rejection, and event projection.

## 16. Alternatives considered

### assistant-ui instead of CopilotKit

assistant-ui provides strong prebuilt `Thread`, `ToolFallback`, tool grouping, and approval rendering. It remains a
reasonable alternative, but the current proposal favors CopilotKit because AG-UI is its native protocol and official
Pydantic AI examples exist. Do not combine both in v0.

### OpenHands frontend fork

OpenHands demonstrates a mature separation between conversation management, runtime management, sandbox execution,
and an event-driven frontend. Its UI and event store are closely coupled to coding actions, terminal, file system,
sandbox, and conversation schemas. Reuse the responsibility split and event-handling lessons, not the full frontend.

### Custom screenshot SSE

Rejected for Web v0. It duplicates media transport, increases bandwidth, produces low frame rates, and still requires
a separate input protocol for takeover. Use an existing Live View.

### WebSocket for everything

Rejected. Run events are mostly ordered server-to-client traffic, while user commands benefit from explicit HTTP
admission and idempotency. High-frequency viewer input remains on its own existing channel.

### Polling as the main event mechanism

Rejected. Polling remains a bounded recovery path only.

## 17. References

- [AG-UI event concepts](https://docs.copilotkit.ai/ag-ui/concepts/events)
- [AG-UI protocol repository and Python SDK](https://github.com/ag-ui-protocol/ag-ui)
- [CopilotKit repository and official examples](https://github.com/CopilotKit/CopilotKit)
- [assistant-ui Tool UI](https://www.assistant-ui.com/docs/tools/tool-ui)
- [assistant-ui Thread component](https://www.assistant-ui.com/docs/ui/thread)
- [Steel Live Sessions](https://docs.steel.dev/overview/sessions-api/embed-sessions/live-sessions)
- [Steel human-in-the-loop sessions](https://docs.steel.dev/overview/sessions-api/human-in-the-loop)
- [Browserbase Session Live View](https://docs.browserbase.com/platform/browser/observability/session-live-view)
- [OpenHands system architecture](https://github.com/OpenHands/OpenHands/blob/main/openhands/architecture/system-architecture.md)
