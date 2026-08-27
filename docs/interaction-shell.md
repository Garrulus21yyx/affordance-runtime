# External Web Interaction and Evaluation Shell

Status: **Local real execution, durable control, bounded task revision, and single-effect compensation implemented; Viewer unavailable**

Date: 2026-08-27

Scope: standalone Web product, deployment composition, resumable control, and evaluation design outside the core Runtime

Status authority: this document owns only the external interaction-shell/deployment capability status. Core GUI-agent
architecture and benchmark closure remain governed by the main Runtime architecture and benchmark documents.

## 1. Decision

Build one external Web shell. It is neither a second GUI Agent nor an internal Core module. It owns user-facing session
lifecycle, command serialization, bounded conversational revision input, event delivery, evaluation projection, and
browser viewing. It consumes only versioned typed Runtime commands, events, snapshots, trace exports, and benchmark
artifacts. It does not import, mutate, or drive `CoreAgentLoop` internals.

The shell contract, synthetic demo, frontend, diagnosis projection, provider-free tests, and local real-execution
profile are implemented. The production-safe default deliberately uses an unavailable Runtime port, while
`interaction_shell.deployment_app:app` composes one real Runtime, policy/history, BrowserGym environment, browser
context, trace sink, and idempotent resource cleanup owner per Web session. The local profile has passed real API/UI
execution and two-session isolation witnesses. Cooperative `CancelRun` is now a distinct public terminal capability;
durable `PauseRun`/`ResumeRun` and bounded `ReviseTask` are also public Runtime capabilities. A single retained known
effect can be kept when fresh evaluation proves the revised goal complete or compensated through the same
ActionPolicy/Binder/Risk/Executor chain. Viewer, local BrowserGym process-restart reconnection, multi-effect
reconciliation, and takeover remain visible as typed unavailable/unsupported states rather than being hidden by the
UI or simulated by the shell.

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
| Model-history persistence | PydanticAI Harness `StepPersistence(SqliteStepStore)`, `ModelMessagesTypeAdapter`, and deferred-tool results | a parallel transcript schema or prose reconstruction |
| Initial durable session storage | SQLite transaction/WAL, with Postgres only when multi-process deployment requires it | a custom event store or event-sourcing platform |
| Trace, usage, and cost | PydanticAI/custom-provider OpenTelemetry instrumentation plus the existing Runtime trace/Langfuse projection; deployment exporter wiring remains pending | another observability platform |
| Charts | shadcn chart components/Recharts | custom SVG charting |
| Web end-to-end tests | Playwright | a custom browser test harness |

The only public shell-specific concepts remain the four values in Section 1.3. The following are private
implementation details behind those boundaries, not additional cross-layer APIs:

1. `RuntimeSessionPort`: one thin translation boundary over supported public Runtime capabilities;
2. `RunSessionManager`: external session authentication/TTL, serialized commands, in-process duplicate protection,
   bounded conversation, and exactly-once invocation of port cleanup; for restart recovery its Shell-private SQLite
   registry stores a salted session-key verifier, original TTL, and a versioned projection of at most six recent
   turns plus 64 immutable revision contexts, never Runtime state, command results, or a reusable key; it
   streams port-owned events without retaining or renumbering a second event log;
3. deployment-private session construction: per-session Runtime, environment/browser lease, optional viewer reference,
   Runtime-owned checkpoint persistence, and idempotent cleanup, returned only as one opaque public handle;
4. Runtime-private checkpoint storage: persistence of Runtime-owner state and execution truth, never exposed to the
   Shell as a DTO and never a second evaluator or workflow state machine;
5. `TaskRevisionCompiler`: a one-shot conversion dependency invoked inside `RuntimeSessionPort.revise`, with bounded
   user input and a closed structured-output contract using the existing PydanticAI/provider boundary;
6. `CaseDiagnosisProjector`: deterministic interpretation of exported benchmark/trace evidence;
7. Web composition and small domain renderers over the reused UI components.

The proposal does not introduce Temporal, Celery, a custom workflow engine, a custom event store, or multiple tracing
platforms for the initial scope. Process restart between committed safe points is handled by explicit typed snapshots,
PydanticAI message serialization, and a reconnectable browser lease. If a later declared requirement demands durable
recovery while arbitrary external activities are in flight, evaluate an existing PydanticAI durable-execution
integration before introducing custom orchestration. The proposal also does not embed Agent TARS, Qwen-Agent,
LangGraph, AutoGen, CrewAI, or another
top-level Agent kernel: those would duplicate the existing goal, policy, state, or execution authority. A dependency is
admitted when it supplies a mature boundary capability without becoming a second GUI Agent, task authority, state
machine, or Runtime loop.

### 1.2 Delivery-state truth

The following states must not be collapsed into one label such as "implemented":

| Layer | Current state | Meaning |
|---|---|---|
| Shell contracts, API, frontend, demo, and provider-free tests | Implemented | The public interaction shape and synthetic flow exist. |
| Default `interaction_shell.api:app` | Intentionally unavailable | Real task commands return typed `Unsupported`; this is fail-closed behavior, not a deadlock. |
| `INTERACTION_SHELL_DEMO=true` | Synthetic only | It demonstrates the UI/contract but never controls a real page. |
| Core public session adapter | Implemented with durable pause/recovery/revision | It wraps start, answer, confirmation, cooperative pause/cancel, exact checkpoint recovery/resume, bounded task revision/effect reconciliation, snapshot/event, and close; SQLite remains private to Runtime. |
| Local real Runtime/environment composition | Implemented and verified | `interaction_shell.deployment_app:app` creates one isolated Runtime, policy/history, trace sink, BrowserGym environment, browser context, and unified cleanup owner per session. |
| Live View deployment | Unavailable | The default viewer is typed unavailable; no protected same-origin provider route is configured. |
| Cooperative running cancel | Implemented and verified | `CancelRun` is admitted while active, closes dispatch truth, projects terminal `CANCELLED`, and remains distinct from CloseSession teardown. |
| Durable pause | Implemented and verified | Public `PAUSED` is projected only after one SQLite WAL transaction commits the Runtime checkpoint and pause-command outcome. |
| Restart resume | Implemented for reconnectable leases; unavailable in local BrowserGym | Checkpoint validation/hydration, exact environment reconnection, fresh World, new event epoch, same-session auth, and one-shot `ResumeRun` are implemented. The local BrowserGym profile cannot reconnect its Playwright context and returns typed `environment_not_reconnectable`. |
| Running-task revision | Implemented with bounded single-effect reconciliation | One `RuntimeSessionPort.revise` call reuses cooperative pause, compiles and validates a complete consecutive goal, revises the same environment, captures fresh World, compiles one new GoalPlan, atomically commits the new checkpoint/outcome, and remains `PAUSED`. Shell recovery restores the exact bounded command context, so lost-response retries retain the Runtime digest across Shell restart. One retained known effect is either kept by fresh complete evaluation or attached to revision `n+1` as pending compensation; uncertain, irreversible, missing, or multiple effect truth fails closed without replacing revision `n`. |
| Model OTel deployment export | Unavailable, non-blocking | Native/custom instrumentation exists, but this deployment has no recording `TracerProvider + exporter`; Runtime JSONL/Langfuse projection remains available. |
| Effect reconciliation/compensation | Implemented for one retained known effect | Runtime preserves the original receipt, classifies typed reversibility, and exposes only semantic lineage. A reversible/compensatable conflict remains `PAUSED`; separate Resume uses the same ActionPolicy and ordinary current action pipeline on the same resource. Risk/confirmation stays authoritative, fresh local postcondition closes the compensation receipt, and another Resume continues the revised goal. `SENT_UNKNOWN`, irreversible, missing, multiple, unavailable, mismatched, or unverified cases stay typed and paused; no rollback is claimed. |
| Real end-to-end deployment witness | Verified | A real API/UI task reached native success through dispatch, fresh World, snapshot/SSE/UI, explicit close, and cleanup. |
| Delivery hygiene | Phase 7 provider-free implementation verified | Phase 0–6.5 plus typed effect conservation, single-effect reconciliation, checkpoint v2/v3 compatibility, Runtime-owned result codes, Shell v2 projection, and provider-free tests agree. No live compensation/browser witness or benchmark was run for this change. |

An unavailable viewer does not make the Runtime unavailable, and an unavailable checkpoint does not make a live
single-process run unavailable. The UI and deployment health response must report these three capabilities separately:

```text
runtime_execution
viewer
durable_pause
durable_resume
```

### 1.3 Simplicity contract

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

There is one current public `RuntimeSessionSnapshot` per session and one ordered `ShellEvent` stream, including one
port-owned event epoch/cursor. Runtime facts are
converted to their public shell representation once at the adapter boundary, then reused unchanged by SSE, snapshot
hydration, UI rendering, and optional persistence. The frontend and Langfuse adapters must not independently rebuild
run status, pending input, task completion, or execution outcomes. Benchmark diagnosis separately consumes the
versioned benchmark/trace export and never round-trips through UI events.

`RunSessionManager` keeps only external resource state: session identity, opaque Runtime handle, command lock or
queue, expiry, and whether the external session is open or closed. Runtime status and event position remain in the public
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

### 1.4 Coupling and projection budget

The control/resume design must remain shallower than the Agent loop it exposes:

- each authoritative fact is produced once and publicly projected once at `RuntimeSessionPort`; snapshot, SSE, and UI
  reuse that projection instead of deriving parallel status/effect/completion values;
- one product command makes one Shell-to-`RuntimeSessionPort` call. Deployment factories run only when opening or
  restoring a session; checkpoint stores, browser providers, GoalCompiler, and Executor are not separate Shell calls;
- the Shell sees `checkpoint_id`, `resume_eligible`, bounded status/effect summaries, and capability flags only. It never
  receives `RunState`, PydanticAI messages, full World, execution receipt internals, provider reconnect locator, or
  checkpoint payload;
- Runtime owns effectful command idempotency because it alone knows whether dispatch/control commit occurred. The Shell
  may reject concurrent/duplicate requests in process, but durable replay truth is not duplicated in a Shell store;
- Viewer and diagnosis remain side projections. Neither participates in the command success path, checkpoint commit,
  Runtime resume, or task completion;
- no distributed transaction spans Shell, Runtime, browser provider, Viewer, and trace. Runtime commits its own resume
  boundary, then emits an owner snapshot/event; other projections recover from that value;
- persistence is not inserted into every Agent step. A resume checkpoint is written only at an explicit durable pause,
  an existing `WAITING_USER`/`WAITING_CONFIRMATION` interruption selected for durable support, and the atomic revision
  commit. Ordinary running steps keep the existing execution/trace path; a crash outside a committed boundary is not
  advertised as resumable;
- Trace/Langfuse and Viewer updates remain fail-open/asynchronous projections. Only the Runtime checkpoint write is on
  the acknowledgement path for `PAUSED`/durable revision;
- capability-specific fields are optional and bounded. Adding Pause does not require Viewer, adding Viewer does not
  require checkpoint, and adding diagnosis does not enlarge the control command or Runtime snapshot payload.

The dependency direction is one-way:

```text
UI → Shell command/manager → RuntimeSessionPort → opaque Runtime session handle
                                      │
                                      ├→ owner-produced public snapshot/event → UI
                                      └→ deployment-private Runtime/environment/checkpoint internals

Viewer proxy ← opaque viewer reference (independent side channel)
Diagnosis    ← exported trace/benchmark artifacts (independent side channel)
```

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
│   command serialization │ auth/expiry       │ event passthrough    │
│   bounded conversation  │ capability view  │ UI event projection  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ RuntimeSessionPort only
                               ▼
                  opaque public Runtime session handle
                               │
                               ▼
                       existing Core Runtime

session open/restore only:
deployment-private factory ──> isolated Runtime + environment/browser + checkpoint

independent side channel:
viewer proxy ──> opaque viewer reference from the same browser lease

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
| Per-session Runtime/provider-history lifetime | deployment-private session constructor |
| Web browser/environment lifetime and cleanup | deployment-private environment lease |
| Pause/cancel/revision admission and safe-point transition | public Runtime session/Core control boundary |
| Resume checkpoint facts | existing Runtime owners, persisted by `RunResumeCheckpointStore` |
| External session identity, authentication, TTL, in-process serialization | `RunSessionManager` |
| Durable effectful/control command idempotency | public Runtime session boundary |
| Ordered public event epoch/cursor/envelopes | public Runtime session/`RuntimeSessionPort` projection |
| Viewer URL protection and provider session lookup | deployment viewer projector/proxy |
| User/agent surface-control lease | Runtime control boundary plus deployment viewer lease |
| UI-visible event projection | AG-UI projection adapter |
| Conversation window used for revision interpretation | bounded conversation context |

The manager stores owner values or references to owner values; it does not keep independently mutable copies of the
current goal, run status, pending question, or pending confirmation.

### 3.2 Session value

The manager-facing value stays small:

```python
@dataclass
class RunSession:
    session_id: str
    runtime_handle: RuntimeSessionHandle
    conversation: BoundedConversationContext
    expires_at: datetime
```

Web v0 uses one Shell session for exactly one Runtime task/run identity. `StartTask` is legal only from `IDLE`; waiting,
paused, and terminal states remain part of that same run; a terminal/closed session cannot be reused for another task.
An unrelated instruction or explicit replacement creates a new Shell session and therefore new private
Runtime/environment resources. Within this bounded algebra, `session_id` is also the public run identity, while
`task_id` and consecutive `task_revision` address the goal. Commands need no additional `run_id`; expanding one session
to multiple runs would be
a new schema/lifecycle migration rather than an implicit behavior of the plural `/tasks` route.

The deployment owner constructs private resources behind `runtime_handle`, but exposes only one small callable to the
Shell composition root:

```python
async def open_runtime_session(
    session_id: str,
    expires_at: datetime,
) -> RuntimeSessionHandle: ...
```

Its closure privately creates one Runtime, environment/browser lease, optional viewer reference, optional Runtime
checkpoint store, and idempotent cleanup. No general `Bundle` DTO crosses a module boundary. If any required resource
fails to initialize, the constructor returns one typed deployment error and cleans up already-created resources once.
Closing, expiry, terminal completion, and failed creation share the same cleanup owner.

Derived UI facts come only from the latest versioned public snapshot/event:

- active task and revision;
- public run status;
- pending question identity;
- pending confirmation identity;
- owner-produced completion outcome.

An optional shell `SessionControlState` is not a second task status. It may expose only transient ownership such as
`agent | user` and a submitted boundary request such as `pause_requested`; the durable `PAUSED`, `CANCELLED`, waiting,
and terminal facts come from the Runtime snapshot.

### 3.3 Per-session Runtime isolation

The public session factory now accepts `runtime_factory(session_id)` and creates one Runtime/provider-policy instance
per opened session. This is required because the configured PydanticAI provider bridge retains `message_history`,
active task identity, compaction state, recovery-event consumption, and last-invocation diagnostics on the policy
instance. The factory also creates one environment lease per session and returns only the existing opaque handle.

Provider clients,
immutable model configuration, HTTP connection pools proven concurrency-safe, schemas, and stateless builders may be
shared; task identity, model history, mutable diagnostics, Runtime trace fanout, World environment, browser context,
and cleanup state may not be shared.

This is the smallest coherent deployment repair. A later refactor may move all provider conversation state into the
serializable Runtime checkpoint and make `TargetRuntime` genuinely stateless and reusable, but the deployment must not
assume that property before the policy boundary exposes and verifies it.

## 4. Reused Runtime behavior and current gaps

The implemented public Core session boundary already wraps:

- initial task intake and `TargetRuntime.run_request(...)`;
- consecutive task revision while answering an open `AskUser` through `TargetRuntime.resume_request(...)`;
- confirmation approval/rejection through `TargetRuntime.resume_confirmation(...)`;
- `RunStatus.WAITING_USER` and `RunStatus.WAITING_CONFIRMATION`;
- typed `StepResult`, execution receipts, task evaluation, and trace events.

`CoreRuntimeSessionPort` translates those owner values into shell contracts. The external shell depends only on that
port and must not import the private `RunState` held behind its opaque handle.

### 4.1 Default startup is deliberately non-operational

Running:

```bash
uvicorn interaction_shell.api:app
```

constructs `UnavailableRuntimeSessionPort`; real task commands therefore return typed `Unsupported`. Setting
`INTERACTION_SHELL_DEMO=true` selects `ContractDemoPort`, which owns a synthetic contract flow and performs no browser
or GUI action. These modes are valuable fail-closed and UI-test paths, but neither is a real deployment.

`interaction_shell.runtime_app.create_runtime_app(factory)` is only a composition hook. There is no concrete ASGI
module that loads product configuration and creates a per-session Runtime, environment/browser lease, protected viewer
reference, persistence handle, and cleanup. A real deployment must start that explicit module rather than
`interaction_shell.api:app`.

### 4.2 Current state is process-local

The public Core session currently retains request, admitted task, private `RunState`, progress, events, active asyncio
task, locks, and cleanup flags in memory. It owns the event epoch, cursor, timestamp, and retained envelope source;
`RunSessionManager` forwards `events(after)` without retaining or renumbering a second list. The Manager still retains
session-key material, opaque Runtime handles, in-process command IDs, bounded conversation, and expiry. A service
restart loses both layers.

This is acceptable for the implemented contract/demo scope and is not a deadlock. It is insufficient for a claim of
durable pause/resume or multi-process deployment. Trace and Langfuse must not be used to reconstruct this state because
they are observation projections, not control authority.

### 4.3 Close is not cancel

The current `close()` marks the external session closed and, if a run is active, waits for it to finish before calling
cleanup. It does not interrupt the Runtime or establish whether an action was dispatched. The UI must therefore not
label Close as Stop/Cancel and must not report a running task cancelled when only viewer/session teardown was requested.

The following are not currently general supported transitions and must not be simulated in the manager:

- interrupting a running policy or executor in the middle of an atomic action;
- cancelling a running task through an external product command;
- revising a task while `RunState` is still `RUNNING`;
- resuming a task after a service process restart;
- returning control after arbitrary manual page mutation;
- treating a new unrelated instruction as a revision of the current run.

The existing public status also has no `PAUSED` value and currently projects Runtime `CANCELLED` as public `FAILED`.
Pause and cancellation therefore require an end-to-end public algebra migration; adding only HTTP endpoints or buttons
would be a false implementation.

### 4.4 Capability-separated operational status

A deployed session snapshot or health projection should distinguish:

| Capability | Ready condition | Typed unavailable examples |
|---|---|---|
| Runtime execution | per-session Runtime and environment reset/capture succeed | `runtime_factory_unavailable`, `environment_unavailable` |
| Viewer | protected provider route resolves an active viewer lease | `viewer_provider_not_configured`, `viewer_session_lost` |
| Durable resume | latest committed checkpoint and reconnectable environment lease exist | `checkpoint_store_unavailable`, `environment_not_reconnectable` |

Viewer failure must not stop an otherwise valid Agent run. Checkpoint failure must prevent a durable-pause
acknowledgement but need not retroactively turn a live single-process task into a GUI failure. Deployment/reporting
failures remain distinct from provider, environment, execution, and evaluator outcomes.

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
| Reload and lost-event recovery | snapshot plus event epoch/cursor | deterministic resynchronization |
| External provider callback | webhook only when required | server-to-server completion notification, not UI streaming |
| Health/status fallback | bounded polling | fallback only, never primary step delivery |

### 6.1 Why SSE for Runtime events

AG-UI defines lifecycle, step, text, tool-call, tool-result, state snapshot/delta, activity, and custom events. Its
official Python package provides typed Pydantic models and SSE encoding. The interaction service should project current
Runtime events into this wire vocabulary rather than replacing Runtime contracts with AG-UI state.

Commands travel on separate HTTP requests while the SSE stream remains open. Within one process epoch, reconnection
uses `event_epoch + cursor` or an epoch-qualified `Last-Event-ID` and replays the port owner's bounded retained public
events. `RunSessionManager` forwards `events(after)` without copying, renumbering, or rebuilding envelopes. The initial
scope does not persist an event journal. After process restart, the restored Runtime projects one
fresh snapshot baseline under a new event epoch; a client presenting an old epoch receives `resync_required` and
hydrates that baseline rather than requesting unavailable historical envelopes. Transient streaming deltas may be
dropped because the current owner snapshot remains sufficient for UI hydration.

Persisting a cursor without its event envelopes is never described as replay. If a later product requirement needs
cross-restart event history, store bounded public event envelopes or use a mature log; do not reconstruct them from
Trace, checkpoint internals, or UI conversation.

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
POST /sessions/{session_id}/commands/approve
POST /sessions/{session_id}/commands/reject
POST /sessions/{session_id}/commands/close
```

Capability-gated endpoints are added only after their Runtime contracts exist:

```http
POST /sessions/{session_id}/commands/pause
POST /sessions/{session_id}/commands/resume
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
expected_checkpoint_id where a paused/recovered state is addressed
typed payload
```

The manager serializes commands per session. It rejects stale non-revision commands from the current Runtime snapshot;
for `ReviseTask` it forwards the complete command and lets Runtime validate expected revision/status/checkpoint so the
same owner also decides durable replay. An HTTP success means the command was admitted, not that the GUI task
succeeded. Task outcome continues to arrive through owner events.
`command_id` and expected values provide optimistic concurrency across reconnects; a stale revision or checkpoint
returns `Conflict` with the current owner-produced snapshot. The current in-memory implementation treats every reused
command ID as `duplicate_command`. The durable target algebra is stricter and genuinely idempotent:

```text
same command_id + same canonical payload digest
→ return the originally committed admission/result summary without re-executing

same command_id + different canonical payload digest
→ Conflict(command_identity_reused)
```

For effectful/control commands, the public Runtime session boundary persists command ID, canonical payload digest, and
bounded owner-produced result reference/summary alongside its control commit. The Shell forwards the identity and may
cache the response, but durable replay truth is not duplicated there. It may not infer that a submitted pause request
has reached a Runtime safe point.

## 9. User interaction flows

### 9.1 Start task

```text
StartTask
→ RunSessionManager calls RuntimeSessionPort.start once
→ public Runtime session runs TaskIntake internally
→ admitted task / typed intake outcome
→ SSE until waiting or terminal status
```

### 9.2 Answer `AskUser`

```text
Runtime → public user-input-required event
→ user_input.required event
→ AnswerQuestion command with pending request identity
→ RunSessionManager calls RuntimeSessionPort.answer once
→ public Runtime session runs TaskIntake and consecutive TaskGoal revision internally
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

### 9.4 Pause, resume, cancel, and close

The UI must expose separate intentions:

| Command | Runtime meaning | Resumable |
|---|---|---|
| `PauseRun` | request a cooperative boundary pause and commit a resume checkpoint | yes |
| `ResumeRun` | restore/revalidate the paused session and continue the same task revision | yes |
| `CancelRun` | terminally stop the task after closing execution truth | no |
| `CloseSession` | release the external session/viewer according to lifecycle policy | no; it is not task cancellation |

A pause request is acknowledged in two stages:

```text
PauseRun admitted
→ pause_requested event (the Agent may still be closing one atomic step)
→ Core reaches a safe boundary and closes dispatch truth
→ RunResumeCheckpoint durably commits
→ owner snapshot/event reports PAUSED + checkpoint_id
```

The frontend shows "Stopping…" or "Pause requested" until the last event. It must not render `PAUSED` from the HTTP
admission response alone. A pure pause preserves the task revision. Resume obtains a fresh World and revalidates
currentness before another action can dispatch.

`CancelRun` is also cooperative around the execution boundary: cancelling an LLM policy request cannot undo a GUI
effect, and cancelling during dispatch must close as `NOT_SENT`, `SENT`, or `SENT_UNKNOWN` before terminal projection.
Cancel persists final audit/receipt truth but produces no resumable checkpoint. Close remains resource teardown.

### 9.5 Running-task revision

`RuntimeSessionPort` now advertises running revision only when the Runtime owns durable pause/checkpoint support. The
user message is not injected directly into ActionPolicy and does not mutate an existing `GoalPlan`:

```text
ReviseTask(command_id, expected_task_revision=n, bounded_conversation)
→ cooperative pause at a Runtime safe boundary
→ commit checkpoint for the last closed step
→ validate bounded dispatch-crossing effect lineage; missing/multiple truth fails closed on revision n
→ TaskRevisionCompiler interprets bounded user-owned language
→ TaskIntake validates a proposed complete TaskGoal(revision=n+1)
→ public Runtime revision boundary stages environment.revise_task
→ acquire fresh WorldObservation
→ GoalCompiler runs exactly once with TASK_REVISION
→ classify the retained effect against fresh revised-goal evaluation and typed reversibility
→ no effect / fresh COMPLETE: commit TaskGoal(n+1) with no pending compensation
→ one reversible/compensatable conflict: commit TaskGoal(n+1) with pending reconciliation
→ SENT_UNKNOWN / irreversible / unknown: restore revision n and return the exact typed result
→ atomically commit the accepted TaskGoal(n+1), invalidation, GoalPlan outcome, fresh World lineage, and checkpoint
→ owner snapshot reports PAUSED with revised + checkpoint_id
→ a later ResumeRun lets the same ActionPolicy continue from the committed revision
```

These arrows describe one internal Runtime transition, not a Shell-orchestrated chain of services. Externally the Shell
makes one `RuntimeSessionPort.revise(command)` call and receives one typed admission/current snapshot; it never calls
TaskIntake, environment revision, GoalCompiler, checkpoint storage, or ActionPolicy separately.

Structured Pause/Resume/Cancel commands need no LLM. `TaskRevisionCompiler` is a one-shot model-backed conversion
boundary only when free-form language must be interpreted. It cannot perform GUI actions, decide completion, expand
permissions, or own control state. `GoalCompiler` produces new bounded static guidance; it does not compute old-plan
progress or rollback. On a later `ResumeRun`, the same ActionPolicy decides subsequent semantic action selection from
the revised authoritative goal and current World.

The proposed task is not authoritative merely because the compiler or TaskIntake returned it. The public Runtime
revision boundary owns one serialized commit, and `environment.revise_task` must not perform an unrelated GUI effect.
If environment revision, fresh acquisition, history rebinding, or checkpoint construction fails, Runtime restores
revision `n`, its model history, the environment task, and a fresh paused World before returning typed
`revision_failed`. `GoalCompiler` `Unsupported|Failed` commits revision `n+1` with plan guidance unavailable and
retains the ordinary loop behavior. Failure to commit the revised checkpoint restores the same revision-`n` paused
authority and returns `revision_persistence_failed`; it never auto-resumes either revision.

Any pending action, binding, action page, or confirmation created under revision `n` is stale under revision `n+1`.
An accepted-but-not-dispatched PydanticAI deferred tool proposal must receive a Runtime-projected `not_dispatched /
task_revised` result so tool-call history remains structurally paired; it must not be silently dropped or represented
by invented assistant prose.

Compiler/conversion outcomes have closed control semantics:

| Outcome | Goal authority | Run/control result |
|---|---|---|
| No retained dispatch-crossing effect | becomes `n+1` | remain `PAUSED` with `revised`; separate `ResumeRun` is legal |
| One retained effect + fresh revised TaskEvaluator `COMPLETE` | becomes `n+1` | preserve effect, remain `PAUSED`, and require no compensation dispatch |
| One retained known reversible/compensatable conflict | becomes `n+1` | remain `PAUSED` with pending `effect_reconciliation`; separate `ResumeRun` enters the ordinary compensation pipeline |
| `SENT_UNKNOWN`, irreversible, unknown, missing, or multiple effect truth | remains `n` | remain `PAUSED` with exact typed `effect_reconciliation_required` result; no blind retry or invented rollback |
| `NeedsInput` | remains `n` | remain `PAUSED` with typed `revision_needs_input`; no GUI dispatch occurs |
| `NoChange` | remains `n` | remain `PAUSED`; user may resume, revise again, cancel, or close |
| `Unsupported` / `Failed` / TaskIntake rejection | remains `n` | remain `PAUSED` with typed conversion failure; original task may resume |
| `NewTaskSuggested` | remains `n` | remain `PAUSED` with a typed suggestion; creating a new session requires a separate future command |

Accepting `NewTaskSuggested` creates a new Shell/Runtime session and then cancels or closes the old paused session only
according to the user's explicit choice. Rejecting it leaves the old session paused. The shell never forces unrelated
language into the old task identity.

### 9.6 Already-applied effects and compensation

A revised instruction does not imply that every earlier action should be undone. Runtime first preserves immutable
execution truth, while the policy evaluates the new desired state against fresh World evidence:

| Execution/effect fact | Required handling |
|---|---|
| No dispatch or `NOT_SENT` | invalidate the old proposal and plan forward from the revised goal |
| `SENT` and still compatible with the revised goal | preserve it; no compensating action is needed |
| `SENT` and conflicting, with a current reversible/compensatable capability | select and execute that capability as a new action |
| `SENT_UNKNOWN` | reacquire/verify before retry or compensation; unresolved truth yields typed unknown/needs-input |
| Irreversible or unsupported compensation | disclose the retained effect and return typed unsupported/needs-input |

Undo is not checkpoint rewind. A checkbox can be toggled back, a cart item can be removed, and an order can be
cancelled only when the fresh action space exposes those operations. A sent email or external transaction cannot be
made nonexistent by restoring model history. Compensation follows the unchanged product path:

```text
ResumeRun + fresh World + revised TaskGoal + retained execution receipt
→ ActionPolicy selects one currently available compensation
→ Binder → RiskPolicy/confirmation → Executor
→ new ExecutionReceipt → TaskEvaluator/native verifier
```

The original receipt remains immutable; compensation produces another receipt. Runtime owns dispatch facts,
currentness, risk, and typed reversibility. The same ActionPolicy owns the semantic choice of whether a prior effect
conflicts with the new goal and which offered compensation to select. No rollback Agent, mutable achievement record,
second Binder, or second Runtime loop is introduced.

The first supported scope guarantees forward revision and compensation only when the relevant effect is visible in
fresh World or represented by retained typed execution evidence. If the product later promises compensation for old
external effects across process restarts, persist only the minimum Executor-owned resource/effect references needed to
address those provider capabilities; do not turn Trace/Langfuse into an effect ledger.

### 9.7 Takeover and return

This is also capability-gated. The viewer becomes interactive only after `RuntimeSessionPort` returns a typed
user-control lease. The shell does not infer that the Agent stopped from viewer state. Returning control is complete
only when the Runtime returns a new public snapshot/event after handling any required invalidation and observation.

### 9.8 User feedback for unfinished states

The shell does not need a conversational supervisor Agent to explain control state. It renders deterministic copy and
available next actions from the typed Runtime snapshot; optional natural-language polish cannot alter the facts.
"Not finished" must not collapse waiting, pausing, blocked, failed, cancelled, unknown effect, and unsupported into one
message:

| Owner state | Required user feedback | Allowed next actions |
|---|---|---|
| `RUNNING` | current bounded progress; no completion claim | request pause/cancel/revision only when advertised |
| `pause_requested` | Agent is closing the current safe boundary; an action may still be in flight | wait for owner event |
| `PAUSED` | checkpoint ID/time and whether environment reconnect is healthy | resume, revise, cancel, close |
| `WAITING_USER` | exact Runtime question and requested fields | answer, cancel, close |
| `WAITING_CONFIRMATION` | exact effect/risk subject; approval is scoped to this request identity | approve, reject, revise/cancel when advertised |
| `BLOCKED` | owner-produced reason/code and retained effects; not presented as success | revise/new session/close as supported |
| `FAILED` | failing owner/stage and safe error code; distinguish deployment/reporting from GUI failure | retry only when contract says no unknown side effect |
| `CANCELLED` | terminal cancellation plus the last closed execution truth | close or start a new session |
| `SENT_UNKNOWN` | explicitly state that the effect may have happened | reconcile/ask user; never show a blind Retry button |
| `Unsupported` | unavailable capability and dependency, e.g. Viewer versus Runtime versus durable resume | show only supported alternatives |

Every non-terminal view must answer: what is known, what may already have happened, who currently owns input/control,
and which typed command is legal next. The UI must not invent success, failure, rollback, or progress from assistant
text, elapsed time, viewer connectivity, or an accepted HTTP status.

## 10. Bounded conversation and revision compiler

Conversation history is used only to interpret user-owned task revision language such as “change it to tomorrow” or
“use the second one.” It is not Runtime memory or a second goal authority.

```python
@dataclass(frozen=True)
class RevisionConversationContext:
    turns: tuple[ConversationTurn, ...]  # at most 6, total UTF-8 text <= 16 KiB
    latest_turn_id: str                  # identifies the final user turn exactly once
```

The Shell includes only this bounded user-owned conversation value in one `ReviseTask` command. Inside the single
`RuntimeSessionPort.revise(...)` call, the public Runtime revision boundary reads current `TaskGoal`, revision, pending
question/confirmation, and modifiable fields from its owner state, then invokes `TaskRevisionCompiler`. Runtime facts
are invocation inputs, not copied into Shell conversation storage or exposed back through the command. The compiler's
closed outcomes are:

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

### 10.1 Transcript separation

Three records serve different owners and must not be merged:

| Record | Purpose | Persistence/visibility |
|---|---|---|
| Shell bounded conversation | interpret user-owned follow-up/revision language and render chat | bounded shell/session projection; no GUI execution authority |
| PydanticAI model messages/steps | preserve exact ActionPolicy tool-call/result conversation and model-step lifecycle | Harness `StepPersistence`/`SqliteStepStore`; Runtime checkpoint stores only a settled snapshot reference and digest |
| Trace/Langfuse transcript | observe provider calls, repairs, latency, and lineage | PydanticAI/native provider OpenTelemetry plus append-only Runtime diagnosis projection; never resume/control authority |

The shell conversation is necessary for user experience and revision interpretation, but it is not sufficient to
resume the Agent. The PydanticAI transcript is necessary for model continuity, but it is not sufficient to restore the
Runtime or browser. Trace is necessary for diagnosis, but must never reconstruct either one. Each provider initial and
repair attempt remains captured at the provider boundary even when the enclosing policy call is cancelled.
PydanticAI ActionPolicy calls have native instrumentation with binary content
disabled; GoalCompiler/TaskRevisionCompiler calls made through the custom
structured `ModelPort` have compatible `gen_ai.*` instrumentation at that
provider boundary. The current deployment does not configure a recording
`TracerProvider` or exporter, so no deployed model-span recording is claimed.
A later deployment may choose Langfuse or another OTLP exporter without adding
a Runtime-specific transcript database. Ephemeral `last_invocation_result` and
Runtime JSONL/Langfuse projections remain diagnostics, not persistence or
recovery inputs.

## 11. Resume checkpoint and persistence contract

### 11.1 A checkpoint is a committed owner snapshot, not a frozen coroutine

`RunResumeCheckpoint` captures the last stable Runtime boundary. It does not serialize an active Python coroutine,
rewind a browser, or prove that an in-flight network request was not sent. A submitted pause command remains pending
until the current phase reaches one of the following closures:

| Current phase | Pause behavior | Checkpoint boundary |
|---|---|---|
| ActionPolicy/provider call | cooperatively cancel or let the bounded call return; no GUI effect is inferred | last committed step, plus typed aborted provider attempt |
| Selected/bound action before dispatch | invalidate it and commit a paired non-dispatched tool result | after `NOT_SENT` closure |
| Dispatch in progress | do not claim immediate pause; Executor determines `SENT`, `NOT_SENT`, or `SENT_UNKNOWN` | only after dispatch truth is recorded |
| Post-action capture or evaluation | finish capture/evaluation or record its typed cancellation phase | after the atomic `StepResult` commits |
| Between steps / waiting for user / waiting confirmation | already stable; persist current owner state | current stable boundary |

No action selected under a stale World, task revision, binding, or confirmation may survive resume/revision without the
existing currentness and risk checks.

### 11.2 Persisted value

The private checkpoint contains only owner facts and deterministic resume metadata:

```text
checkpoint_id and schema_version
session_id and TaskGoal (including task_id/revision)
authoritative RunStatus and pause reason
accepted GoalPlan resolution/version
RunState counters, budgets, bounded AgentWorkspace, Runtime World-delivery index
last committed StepResult, including its typed ExecutionReceiptBatch
pending AskUser or confirmation identity when applicable
PydanticAI settled-snapshot run reference, conversation ID, message digest, and task identity
opaque environment_lease_ref and lease expiry
bounded Runtime command-id → payload-digest + committed-outcome references
integrity digest and committed_at
```

Shell-owned recovery facts are a separate value, linked but never copied into the Runtime checkpoint:

```text
ShellSessionRecord
  session_id, hashed session credential, expires_at, closed
  current opaque runtime_session_ref
```

These records do not form a distributed transaction. Runtime first commits its resume snapshot and command outcome,
then exposes `PAUSED + checkpoint_id + resume_eligible` through the existing public handle. The Shell persists only its
directory/projection facts and can recover them from the public Runtime snapshot if its own write fails. Each fact has
one owner: the private resume snapshot does not copy Shell authentication state; the public Runtime session owns and
projects event epoch/cursor/envelopes; and the Shell record never copies event position, command effect truth,
checkpoint ID as authority, private RunState, TaskGoal, PydanticAI history, World, or execution receipts.

The checkpoint is a serialization of existing authorities, not a second status or evaluator. `TaskGoal` remains goal
authority, fresh `WorldObservation` remains environment authority, execution receipts remain effect authority, and
`TaskEvaluator`/native verifier remains completion authority. Public snapshots and AG-UI events are projections of the
restored Runtime value; they are not inputs used to rebuild it.

PydanticAI owns model-step and message persistence through Harness
`StepPersistence(SqliteStepStore)`. Each ActionPolicy invocation has an
explicit run ID and the Runtime session ID as its conversation ID. Deployment
maps that session ID to a deterministic private SQLite file, keeping concurrent
session schema initialization and model records isolated while allowing the
same file to be reopened after restart. At a Runtime
safe point, after any deferred GUI tool call has been paired with its official
result, the model boundary writes one immutable `complete` Harness snapshot and
returns only its run reference plus the `ModelMessagesTypeAdapter` digest. A
new process restores that exact snapshot before fresh-World revalidation.
Legacy checkpoints that embed an official `ModelMessagesTypeAdapter` payload
remain readable for migration. Deferred external tool calls continue through
the existing `DeferredToolResults`/`ToolReturn`/`ToolFailed` pairing. Harness
step/tool-effect lifecycle is never interpreted as `NOT_SENT | SENT |
SENT_UNKNOWN`, and it does not own Runtime status, checkpoint eligibility, or
browser effects. The deployment must not define a parallel transcript JSON
shape, summarize an unresolved tool call into prose, or use the UI conversation
as ActionPolicy model history. Existing bounded history compaction remains the
model-boundary owner.

### 11.3 Storage and commit ordering

SQLite is sufficient for the first single-process deployment. Use an explicit transaction, WAL, foreign keys, schema
versioning, unique `(session_id, checkpoint_id)`, and a monotonic session version. Persist the checkpoint before
emitting `PAUSED`. While persistence is pending, Runtime is quiescent at the safe boundary and the public snapshot
remains its prior run status with shell control projection `pause_requested`; there is no public half-paused state.
This transaction is not on the ordinary per-step hot path and does not wait for Viewer, SSE delivery, Langfuse, or
Shell projection persistence.

If the commit fails, emit typed `pause_persistence_failed`, clear the pause request, reacquire fresh World, and continue
the same task revision from that boundary. There is no automatic persistence retry and no `PAUSED` claim. If fresh
World/currentness cannot be re-established, transition through the existing typed environment/currentness failure
contract rather than dispatching or pretending the pause succeeded. The user may submit a new pause command with a new
command ID after observing the failure.

The external session directory stores hashed session credentials, TTL, and one opaque Runtime-session reference.
Runtime owns durable command payload/result idempotency and the public event epoch/cursor/envelopes. Provider reconnect
locators and credentials stay in the deployment lease registry; Runtime-private checkpoint payloads stay behind the
Core public session boundary. If multi-process replicas become a declared requirement, move the relevant owner
repositories to Postgres and use database-backed optimistic concurrency; do not create a cross-layer transaction or
add a workflow engine merely to replace an in-memory dictionary.

`ResumeRun` consumes no checkpoint; it advances the same checkpoint version to a running snapshot after environment
revalidation. `CancelRun`, `CloseSession`, and TTL expiry revoke `resume_eligible` before releasing the browser lease.
The checkpoint may remain under bounded audit retention, but it can no longer reopen the session. Cleanup failure cannot
restore resume eligibility or change the last Runtime task outcome.

### 11.4 Environment resume

Logical state is only half of GUI recovery. The deployment must reconnect the browser provider session/context, then
capture a fresh World before ActionPolicy continues:

```text
load checkpoint
→ reconnect browser/environment lease
→ capture fresh WorldObservation
→ validate task revision, session identity, and currentness
→ restore PydanticAI history and bounded Runtime state
→ publish restored snapshot as a new event-epoch baseline
→ continue only after an explicit ResumeRun or accepted ReviseTask
```

If the browser session is lost or cannot be proven to represent the same task environment, return typed
`environment_not_reconnectable`/`currentness_unavailable`. Do not reset a new page and replay old GUI actions. Viewer
reconnection is separately projected and may fail without changing a valid Runtime resume.

## 12. Evaluation and bad-case diagnosis

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

## 13. Surface viewing

### 13.1 Web v0

Steel or Browserbase supplies an existing Live View for the browser session. The default Agent view is read-only. A
later takeover flow enables interaction only while the user holds the typed control lease. The provider URL is stored
only in the deployment viewer registry; the browser receives a protected same-origin shell path:

```tsx
<iframe
  src={`/viewer/${sessionId}`}
  className="h-full w-full border-0"
/>
```

Steel's headful Live View uses WebRTC/H.264. Its debug URLs are unauthenticated by design, so a public deployment must
protect access and must never expose a reusable URL outside the authorized session. Browserbase provides a managed
Live View and session inspector and is the alternative when operational speed is more important than local ownership.

`ViewerStateProjector` publishes only readiness and a secret-free `/viewer/...` path. The deployment proxy
authenticates the shell session, resolves the opaque provider viewer reference, enforces read-only mode unless a valid
control lease exists, and applies expiry/cleanup. The shell does not implement screenshot polling, video encoding, or
mouse/keyboard forwarding.

### 13.2 Concrete deployment entry

The production module must be explicit and separate from the fail-closed `interaction_shell.api:app`:

```text
interaction_shell.deployment_app
├── validate provider/model/browser/checkpoint configuration
├── create private open_runtime_session(session_id, expires_at)
│   ├── compose one TargetRuntime/provider-policy instance per session
│   ├── create BrowserSession + WorldEnvironment lease
│   ├── register protected viewer reference when configured
│   ├── inject Runtime-private checkpoint repository when configured
│   └── provide idempotent cleanup
├── create public TargetRuntime session factory/port
├── create RunSessionManager
└── app = create_runtime_app(...)
```

The exact provider-specific constructors stay in deployment code, not in the public Shell package or Core loop. The
deployment loads credentials from its environment/configuration without logging them. Startup validates configuration
needed to create sessions, while per-session browser/provider failures return typed session-creation errors and clean
up partial resources.

The initial real vertical slice may use the existing local Playwright/BrowserGym environment with Viewer reported
unavailable. That proves real GUI execution independently. A later Steel/Browserbase profile supplies both a
reconnectable remote browser lease and Live View. These are separate acceptance gates so viewer work cannot mask a
Runtime composition failure.

## 14. Core-isolation contract

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

## 15. Implementation sequence

The order below follows authority and dependency, not UI visibility. A later phase cannot be declared complete using a
demo or adapter fake when its prerequisite owner capability is absent.

```text
Phase 0 → Phase 1 → Phase 2 ───────────────→ Phase 3 (read-only Viewer)
                       │                         │
                       └→ Phase 4 → Phase 5 → Phase 6 → Phase 7
                                      │                    │
                                      └────────────────────┴→ Phase 8 (optional takeover; also requires Phase 3)

Phase 9 reviews whichever release profile is declared below.
```

Release profiles keep optional work from blocking an already honest capability:

| Profile | Required phases | Claim permitted |
|---|---|---|
| Contract/demo | 0 | synthetic UI and public-contract behavior only |
| Real execution | 0–2 | one-session real GUI execution; Viewer and durable resume may remain unavailable |
| Observed real execution | 0–3 | real GUI execution plus protected read-only Live View |
| Resumable revision | 0–2 and 4–7 | durable pause/resume, running revision, and bounded compensation; Viewer optional |
| Full Web control | 0–8 | adds protected user takeover/return |

Phase 5 additionally requires a reconnectable environment lease. That may be supplied by a local browser context with
proven reattachment or by the remote browser-session portion of Phase 3; Live View itself is not the dependency. Phase
9 runs all fixed gates for the selected profile and cannot require or waive an optional phase implicitly.

Across all phases, the public interface delta is capped at new closed command/status/capability variants,
`checkpoint_id | resume_eligible | bounded effect uncertainty`, and `event_epoch`. No phase may expose a deployment
bundle, store interface, provider session, GoalPlan progress, PydanticAI history, World, binding, raw receipt, or trace
payload through Shell contracts. If implementation appears to require another cross-layer coordinator or projection,
first prove why the existing `RuntimeSessionPort` command/snapshot/event algebra cannot express it.

### Phase 0 — preserve and attest the implemented foundation

Status: implemented, provider-free gates attested, and committed before Phase 1.

1. Keep `RuntimeSessionPort`, the closed command union, snapshot/event schemas, cursor-based SSE, duplicate/stale
   command handling, bounded conversation, diagnosis projection, frontend, and contract demo unchanged except for
   migrations required by later public capabilities.
2. Run existing backend, architecture, frontend unit, lint, typecheck, build, and demo E2E gates.
3. Commit/review the worktree before calling this foundation delivered.

Exit evidence: provider-free gates pass; default startup remains typed unavailable; demo remains explicitly synthetic;
the public shell imports no private Core loop, Binder, Executor, World, or provider history.

### Phase 1 — correct session-scoped composition ownership

Owner: Core public-session boundary plus deployment composition.

Status: implemented and provider-free verified after the Phase 0 baseline.

1. Replace the singleton `TargetRuntime` assumption with one private session constructor using
   `runtime_factory(session_id)`; keep the Shell-facing result as the existing opaque handle.
2. Define typed session-creation/cleanup outcomes and ensure partial initialization cleanup is exactly once; do not add
   a general bundle registry or DTO.
3. Create one PydanticAI ActionPolicy/provider-history owner, trace fanout, Runtime handle, World environment, and
   browser context per session; share only explicitly stateless/concurrency-safe dependencies.
4. Move event epoch/cursor/envelope ownership to the public Runtime session/port; make `RunSessionManager` stream
   `events(after)` without retaining, renumbering, or reprojecting a second event list.
5. Add two-session concurrency tests proving task identity, PydanticAI history, events, World observations, viewer
   references, and cleanup cannot cross sessions.
6. Add creation-failure tests at each private resource-construction stage.

Exit evidence: simultaneous sessions produce disjoint model histories and browser contexts; closing or failing one
session cannot alter the other; no global mutable Runtime/provider-policy instance is shared.

### Phase 2 — real deployment entry and execution vertical slice

Owner: deployment package.

Status: implemented and real-deployment verified on 2026-08-26 for the local
BrowserGym/Playwright profile. This status does not include Viewer, durable
resume, revision, takeover, or benchmark acceptance.

1. Add `interaction_shell.deployment_app` that loads the existing model/provider configuration and constructs the Phase
   1 private session constructor.
2. First profile: reuse the existing Playwright/BrowserGym `WorldEnvironment`; expose Viewer as typed unavailable.
3. Start FastAPI through the deployment module, not `interaction_shell.api:app`.
4. Run one real task through session creation → TaskIntake → ActionPolicy → Binder/Risk → Executor → fresh World →
   TaskEvaluator → public event/UI projection.
5. Verify cleanup on normal close, terminal outcome, expiry, session-creation failure, and application shutdown.
6. Add deployment health that reports Runtime, Viewer, and durable-resume readiness separately without secrets.

Exit evidence: at least one real browser task moves the actual page and reaches an owner-produced waiting or terminal
status through the deployed API. `Viewer unavailable` does not prevent it. No live benchmark is implied; any benchmark
run still requires separate user authorization.

Recorded evidence: a held-out Web/UI run opened one session, admitted the exact
BrowserGym goal, selected and dispatched one real `activate` action, captured a
second fresh World, received native `verified_success`, streamed
`STEP_FINISHED/RUN_FINISHED` through the Next.js same-origin route, rendered
`done` in the Shell, accepted explicit close, and completed application
shutdown. A separate real two-session witness proved distinct environments and
owner threads and showed the second browser remained alive after closing the
first. The reusable native task-state classifier now belongs to the BrowserGym
surface; the benchmark policy is only a compatibility projection.

Two deployment-boundary defects were closed by that evidence. BrowserGym
0.14.3's process-global synchronous Playwright cache is migrated at all cached
import sites to owner-thread-local driver state before reset, so per-session
owner threads cannot share greenlets or stop each other's drivers. SSE responses
declare `no-cache, no-transform`, identity encoding, and buffering disabled, so
the Next.js proxy cannot gzip-buffer Runtime events until disconnect. Neither
repair adds Shell Runtime state or a second event stream.

The deployment factory also owns one private idempotent cleanup closure per
session. It closes the BrowserGym surface and flushes/closes the optional trace
viewer worker on normal close, TTL, terminal cleanup, application shutdown, and
partial session creation. Trace cleanup failures are logged and cannot skip
surface cleanup or change task truth. Focused tests cover normal exactly-once
cleanup, environment-open failure, later composition failure, cancellation,
trace failure, and two-session resource independence.

### Phase 3 — read-only Live View deployment

Owner: deployment viewer registry/proxy and browser lease.

This phase depends on Phase 2 but does not block Phases 4–7; it can be scheduled later if Runtime control and resume are
the nearer product priority.

1. Select Steel as the first profile or Browserbase as the managed alternative; use its existing session and Live View
   APIs rather than custom pixels/input transport.
2. Bind the provider session to the same environment lease used by Runtime execution.
3. Implement authenticated, expiring, same-origin `/viewer/{session_id}` resolution without exposing provider URLs or
   credentials.
4. Enforce read-only viewer mode while the Agent owns control.
5. Test unauthorized access, wrong-session access, expiry, provider disconnect, terminal cleanup, and the invariant that
   viewer loss does not change Runtime outcome.

Exit evidence: an authorized user can observe the same browser session controlled by Runtime; no reusable provider URL
appears in public snapshots, events, HTML, logs, or browser storage.

### Phase 4 — Runtime-owned pause and cancellation safe points

Owner: `CoreAgentLoop`, `RunState`, Executor cancellation algebra, and public Runtime session; Shell only projects.

This phase builds and verifies the control substrate. `CancelRun` may be advertised after its terminal semantics pass;
durable `PauseRun` remains unadvertised until Phase 5 commits a real checkpoint before `PAUSED`.

1. Add distinct `CANCELLED` status/capability and stop mapping cancelled to failed. Define an internal typed
   `pause_boundary_reached` result, but do not yet add or emit public `PAUSED`.
2. Add cooperative `PauseRun`, `ResumeRun`, and `CancelRun` control requests that can be admitted while the background
   run is active without allowing arbitrary concurrent mutation.
3. Check the control request at defined policy/pre-dispatch/post-dispatch/post-capture/evaluation boundaries.
4. Reuse `DispatchStatus`, `ExecutionCompletion`, and `ExecutionCancellationPhase` to close each atomic action; never
   infer dispatch truth from task cancellation.
5. Invalidate or structurally close accepted-but-not-dispatched PydanticAI deferred calls.
6. Verify `pause_requested → pause_boundary_reached` internally while the public pause capability remains disabled;
   keep CloseSession as separate teardown.
7. Add state-machine/property tests for command races, confirmation races, exact receipt closure, no dispatch after an
   acknowledged pause boundary, and cleanup idempotency.

Exit evidence: every exercised control request has one typed outcome; every dispatch-crossing attempt has one closed
execution truth; no stale action/binding/confirmation dispatches after an internal pause/resume boundary. Durable pause
is not yet advertised.

Implementation status (2026-08-26): complete for this bounded phase. Core owns a per-session cooperative request and
commits the reached boundary into the sole `RunState`; accepted-but-undispatched PydanticAI calls receive a terminal
ToolReturn; held policy and dispatch races cover `NOT_SENT`, `SENT`, and `SENT_UNKNOWN`; the public Runtime/Shell/API/UI
project a distinct terminal `CANCELLED`. `PauseRun` is now advertised only by sessions with a checkpoint store; the
safe-boundary substrate itself remains independent of persistence.

### Phase 5 — durable checkpoint and process-boundary resume

Owner: Runtime snapshot boundary, `RunResumeCheckpointStore`, and deployment browser lease.

1. Define a versioned checkpoint DTO from the Section 11 owner facts; do not serialize asyncio tasks, locks, clients,
   trace projections, or frontend conversation as Runtime truth.
2. Serialize PydanticAI history with `ModelMessagesTypeAdapter` and validate deferred-call pairing on write/read.
3. Implement a transactional SQLite repository plus schema migration, integrity digest, monotonic version, and atomic
   checkpoint-before-`PAUSED` ordering.
4. Persist Runtime-owned command-result idempotency with the private control commit and let the public Runtime session
   own the new event-epoch baseline. Keep only Shell auth/TTL and opaque Runtime-session reference in the Shell record;
   do not add a cross-layer transaction or duplicate event/checkpoint/effect truth.
5. Add browser/environment reconnect locator support; restore only after same-session validation and fresh World
   acquisition.
6. Add restart tests at every supported safe point, corrupted/stale checkpoint tests, missing/lost browser tests, and
   injected persistence failures.
7. Keep in-flight crash recovery outside the supported scope: unknown dispatch stays unknown and is never replayed.
8. Add public `PAUSED` and advertise `PauseRun` after checkpoint commit ordering passes. Advertise `ResumeRun` only
   after restart recovery gates pass.

Exit evidence: stop service after a committed pause, restart it, authenticate the same session, reconnect the same
environment, hydrate an equivalent public snapshot under a new event epoch, and resume without replaying a committed
GUI effect. An old epoch deterministically yields `resync_required` rather than fabricated event replay.

Implementation status (2026-08-26): implemented and verified for the bounded reconnectable-lease contract. The Runtime checkpoint contains the task revision,
paused-from status, validated GoalPlan disposition, bounded counters/budgets/workspace, last closed step/receipt and
pending interrupt identity, a settled PydanticAI Harness snapshot reference and message digest, environment reconnect
reference, pause command outcome, schema version, digest, and timestamp. It excludes complete World payloads, live tasks/locks/clients, Shell
conversation/events, and Viewer/trace projections. SQLite uses WAL and commits the checkpoint and command outcome in
one transaction. Injected command-outcome failure rolls both rows back, emits typed `pause_persistence_failed`, clears
the internal pause, acquires a fresh current World when the run was active, and continues the original revision.
Only after a successful commit does `RunState` enter authoritative `PAUSED` and the Shell receive `checkpoint_id` and
`resume_eligible`. Restart recovery validates the exact session/schema/digest and one-shot resume outcome, loads and
validates the referenced provider-valid Harness snapshot (or a legacy official message payload), restores bounded
Runtime facts, reconnects only the checkpoint's exact environment reference,
captures and evaluates a fresh World, then publishes one new-epoch `SESSION_RECOVERED` baseline while remaining
`PAUSED`. `ResumeRun` consumes the checkpoint before any new policy/dispatch; duplicate or competing resume commands
cannot replay it. Fresh terminal truth finishes directly after explicit resume, and a fresh confirmation action ID is
rebased only when its canonical confirmation subject has exactly one current semantic match. Shell restart auth stores
a salted key verifier, original TTL, and only the bounded language projection needed to reproduce revision input;
old epochs return snapshot resync required. Restart tests cover
RUNNING, waiting-user, waiting-confirmation, a committed `SENT` receipt with zero replay, corrupt checkpoints,
already-consumed checkpoints, auth isolation, and missing environments. Local BrowserGym cannot reconnect the same
Playwright context after process death, so its health remains durable-resume unavailable and recovery returns typed
`environment_not_reconnectable` without opening a replacement browser. An already-open Web client makes one bounded
same-session recovery attempt only when its current owner snapshot is `PAUSED + resume_eligible + checkpoint_id`, then
resubscribes from the recovered epoch/cursor; other stream failures remain offline and never open a new session.
Concurrent recovery requests are serialized at the Shell handle-install boundary, so exactly one opaque Runtime handle
owns a recovered session; SQLite also rejects any row whose indexed session/checkpoint scope disagrees with its signed
checkpoint payload.

### Phase 6 — bounded running-task revision

Owner: Shell bounded user-conversation input plus the public Runtime revision boundary, TaskIntake/TaskGoal,
GoalCompiler, and existing ActionPolicy.

1. Add `ReviseTask` with `command_id`, expected task revision/status/checkpoint, bounded text, and one immutable
   at-most-six-turn/16-KiB conversation snapshot whose latest user turn is identified exactly once.
2. Implement one-shot PydanticAI-backed `TaskRevisionCompiler` outcomes:
   `RevisionReady | NeedsInput | NoChange | NewTaskSuggested | Unsupported | Failed`.
3. Require a cooperative safe-point checkpoint before accepting the authoritative revision.
4. Pass the complete proposed goal through TaskIntake; only an accepted consecutive `TaskGoal` becomes authority.
5. Invalidate old GoalPlan/action-page/binding/confirmation values, acquire fresh World, and invoke GoalCompiler exactly
   once with `TASK_REVISION`.
6. Commit every accepted revision back to `PAUSED`; a separate `ResumeRun` later continues the same ActionPolicy. Do not
   add a revision Agent, per-step compiler, mutable task plan, or second loop.
7. Test revision during policy, before dispatch, during confirmation, after known dispatch, and after unknown dispatch;
   test stale and duplicate revision commands.
8. Commit `revised` directly when no dispatched receipt exists. The Phase 7 extension may also accept one known effect
   as fresh-compatible or commit one reversible/compensatable conflict with pending reconciliation. Unknown,
   irreversible, missing, or multiple effect truth keeps the old goal/checkpoint authoritative and returns the exact
   typed `effect_reconciliation_required` result.

Exit evidence: every revision command ends in one table-defined paused/waiting outcome; all subsequent resumed actions
use revision `n+1`; no revision-`n` selection or approval can dispatch; old
effects are preserved as immutable receipts; GoalCompiler is called exactly once for an accepted candidate revision;
and every prior-effect branch has one typed paused result without replaying the old action.

Implementation status (2026-08-27): complete for the bounded Phase 6/6.5 scope. `ReviseTask` is a dedicated Shell command
and endpoint that makes one `RuntimeSessionPort.revise` call. Runtime reuses the Phase 5 cooperative pause and source
checkpoint, durably closes every compiler non-ready outcome, admits only a complete consecutive `TaskGoal`, revises
the same environment, captures fresh World, invokes the existing GoalCompiler once, rebinds official PydanticAI
history, and atomically commits the new checkpoint plus command outcome before publishing revision `n+1`. Successful
revision remains `PAUSED`, clears stale action/confirmation state, and never auto-resumes. Duplicate commands replay
the Runtime-owned stored result. The Shell now attaches one immutable bounded conversation snapshot; Runtime adds
only its authoritative current goal and pending question/confirmation before calling the existing compiler once.
The latest user message appears once in the compiler payload, conversation never enters ActionPolicy Harness history,
and the unused external Shell compiler has been removed. The stored row contains a canonical digest of the complete
command including conversation plus a bounded outcome/message summary: an exact retry replays without compilation or
environment mutation, while reuse of the same identity for different expected values, text, or context returns typed
`command_identity_reused`. The Shell recovery registry persists at most six recent turns and 64 immutable command
contexts in the same credential row. It commits a newly constructed context before forwarding the revision, restores
the projection before recovering the Runtime handle, and deletes the projection with TTL/revoke; a projection write
failure prevents the Runtime call. This projection owns neither Runtime outcome nor TaskGoal/GUI state. The Shell
always forwards revision attempts under its per-session lock and does not decide revision idempotency or staleness. Task admission
also binds model-history identity before initialization, so a pre-policy pause can persist and recover an empty settled
Harness snapshot. Phase 7 now extends the prior-dispatch boundary without changing Phase 6 compiler ownership:
single known compatible/compensatable truth can reach a revised checkpoint, while uncertain, irreversible, missing,
or multiple effect truth fails closed and keeps revision `n`. Viewer and takeover remain unavailable. OTel exporter
wiring remains a non-blocking deployment task and is not part of this closure.

### Phase 7 — bounded compensation for already-applied effects

Owner: existing effect authority, ActionPolicy, Binder/Risk/Executor, and TaskEvaluator.

1. Ensure action/effect contracts expose typed `REVERSIBLE | COMPENSATABLE | IRREVERSIBLE | UNKNOWN` and the minimum
   current resource reference needed by offered provider actions.
2. Make fresh World plus retained execution evidence visible to the existing ActionPolicy after revision.
3. Represent undo/cancel/refund/remove only as normal currently offered actions; keep all currentness, risk,
   confirmation, execution, and evaluation gates.
4. Preserve original receipts and append compensation receipts; never rewrite history or infer success from intent.
5. Return typed unknown/needs-input/unsupported for `SENT_UNKNOWN`, unavailable compensation, or irreversible effects.
6. Use generic reversible/compensatable fixtures and real surface witnesses; do not add site-, label-, task-, or
   benchmark-specific undo branches.
7. On `ResumeRun` from `effect_reconciliation_required`, produce one closed outcome: preserve a compatible effect and
   continue; dispatch a normal offered compensation; or remain paused/ask user for unknown, irreversible, or
   unsupported cases. Only then advertise resume for revised sessions with prior effects.

Exit evidence: reversible and compensatable cases converge through the ordinary action pipeline; irreversible and
unknown cases fail closed; no test requires a production branch keyed to a fixture or page string.

Implementation status (2026-08-27): provider-free implementation and public projection are verified for one retained
dispatch-crossing effect. ActionBinding, ActionOption, admitted selection, bound request, receipt, checkpoint, and
public snapshot conserve one typed `resource_ref` plus
`REVERSIBLE | COMPENSATABLE | IRREVERSIBLE | UNKNOWN`; semantic conflicts fail closed and BrowserGym remains
conservatively `UNKNOWN` unless its surface contract supplies stronger metadata. Revision `n+1` is accepted directly
when its fresh TaskEvaluator already reports `COMPLETE`. Otherwise one known reversible/compensatable `SENT` effect
becomes a Runtime-owned pending reconciliation and remains `PAUSED`. A separate Resume gives the existing ActionPolicy
only currently offered actions for the same resource plus the bounded original-effect summary. The selected action
still passes the existing Binder, currentness, Risk, Confirmation, Executor, fresh World, ActionOutcome, and
TaskEvaluator boundaries. A fresh satisfied local postcondition appends a new compensation effect and atomically
checkpoints `compensated`; the task remains paused until another separate Resume. `SENT_UNKNOWN`, irreversible,
missing lineage, more than one retained dispatch-crossing receipt, no current same-resource action, mismatched
resource, multiple compensation receipts, or unverified compensation produce a typed paused/needs-input/unsupported
result without retrying or rewriting the original receipt. Runtime checkpoints are v3 and continue reading v2;
revision command digests remain frozen to their existing command-payload version, independent of the additive public
session/Shell v2 snapshot. The Shell projects the bounded reconciliation value and exact conflict codes but owns no
effect state or compensation logic. This is intentionally not a general effect ledger, task rollback, multi-effect
Saga, or proof that an incomplete revised goal is semantically compatible with a retained effect. No live browser
compensation witness or benchmark was run for this implementation milestone.

Post-push verification recorded `1830 passed / 25 skipped` across the whole provider-free repository. The only two
failures are unchanged external baselines: documentation governance permits five maintained Markdown files and rejects
this user-required sixth document, while one semantic-delivery test cannot open an absent historical live trace. The
synthetic Demo Playwright E2E passed one Chromium test. Existing deployment tests may load the project `.env` through
established startup behavior, but Phase 7 did not inspect, print, or use the Viewer credential and did not start
Viewer, a live model/provider, a real compensation browser profile, or a benchmark.

### Phase 8 — optional user takeover and return

Owner: Runtime control lease plus deployment viewer lease.

1. Enable interactive viewer control only after the public port returns an exclusive user-control lease.
2. Prevent Agent dispatch while the user holds the lease.
3. On return, invalidate stale action material, acquire fresh World, and resume only from an owner-produced snapshot.
4. Do not infer takeover/return from iframe focus, viewer connectivity, or mouse activity.

Exit evidence: control has one exclusive owner, stale Agent actions cannot dispatch across the lease transition, and
return-control produces fresh World lineage.

### Phase 9 — release and closure review

1. Declare one release profile and freeze its supported status × command × execution-phase matrix before running gates.
2. Produce the applicable fixed evidence artifacts: provider-free/architecture report; frontend unit/lint/typecheck/
   build/demo E2E report; two-session isolation report; real deployment smoke record; control state-machine/property
   report; checkpoint fault-injection/restart record; and revision/compensation matrix.
3. Test held-out command orderings and two-session concurrency from a fresh process.
4. Verify implementation, this document, external README/start commands, OpenAPI-generated frontend types, and public
   capability advertisement agree.
5. Record separately which gates are contract/demo, real Runtime, Viewer, durable resume, revision, compensation, and
   optional takeover; do not use one green UI test as closure for all layers.
6. Commit/review all changes and publish the real deployment entry/configuration instructions.

Android and desktop remain outside this sequence. No Android/ADB/UIAutomator, desktop/AT-SPI/VNC, cross-surface
abstraction, dependency, or acceptance gate belongs to the current scope.

## 16. Acceptance criteria

Closure is reported per layer. A layer may be complete while a later capability remains unavailable, but no layer may
borrow evidence from a demo or projection that does not exercise its owner.

### 16.1 Contract/demo foundation

- the external API consists of one `RuntimeSessionPort`, one closed command union, one public snapshot schema, and one
  ordered event envelope rather than parallel per-feature protocols;
- a session survives multiple HTTP requests without reconstructing Runtime state from events;
- event order is stable and cursor-resumable within one event epoch; the current in-memory duplicate-command conflict
  behavior is explicit rather than described as durable idempotent replay;
- `AskUser` and confirmation pause and resume through existing typed Runtime entrypoints;
- unsupported execution, viewer, durable pause/resume, revision, and takeover capabilities are independently disabled
  rather than simulated;
- waiting, pause-requested, paused, blocked, failed, cancelled, `SENT_UNKNOWN`, and unsupported states render distinct
  owner-backed feedback and legal next actions;
- public events contain no selector, coordinate, private binding, credential, or full World payload;
- completion shown in the UI exactly matches `TaskEvaluator` or native-verifier output;
- a reload hydrates from snapshot plus event epoch/cursor without creating a second run;
- no frontend component directly invokes an executor or silently revises `TaskGoal`;
- diagnosis consumes exports only and cannot change task, failure, Monitor, or benchmark truth;
- Langfuse failure cannot change or erase the local exported result;
- each Runtime fact is publicly projected once and reused by snapshot/event consumers without a second status,
  completion, pending-input, or execution-outcome derivation;
- each product command makes one `RuntimeSessionPort` call; deployment construction, checkpoint storage, Viewer, trace,
  TaskIntake, GoalCompiler, and Executor are not independently orchestrated by Shell;
- shell-owned state remains limited to external resource lifetime, in-process command serialization, expiry, and
  bounded conversation context; any browser-held delivery cursor is only a non-authoritative request position against
  the Runtime-owned event epoch and is never persisted by the Shell as event truth;
- safety code remains limited to ordinary product-boundary checks and reuses Runtime enforcement for task effects.

### 16.2 Real deployment

- the actual ASGI deployment entry constructs isolated per-session Runtime/environment resources behind one opaque
  handle;
- two concurrent sessions cannot observe or mutate each other's task, model history, World, events, browser, viewer,
  checkpoint, or cleanup state;
- the public Runtime session/port owns the only event epoch/cursor/envelopes; the manager only forwards
  `events(after)` and creates no second event log;
- one real GUI task runs through `RuntimeSessionPort` without the shell importing or driving `CoreAgentLoop`;
- external browser/session cleanup happens exactly once on close, terminal completion, expiry, failed creation, and
  shutdown;
- default unavailable and demo startup remain visibly distinct from the real deployment command;
- Runtime, Viewer, and durable-resume readiness are reported separately.

### 16.3 Viewer

- the viewer displays the exact browser session leased to Runtime and is read-only while the Agent owns control;
- only an authenticated same-origin `/viewer/...` path is public;
- provider URL/token/session secrets do not appear in snapshots, events, HTML, logs, or client storage;
- viewer loss cannot change Runtime task status, execution receipts, or completion.

### 16.4 Pause, cancel, and durable resume

- HTTP admission and durable `PAUSED` acknowledgement are distinct events;
- no dispatch begins after the acknowledged pause boundary until a valid resume/revision;
- every in-flight attempt closes deterministically as `NOT_SENT`, `SENT`, or `SENT_UNKNOWN` with the existing typed
  completion/cancellation phase;
- CloseSession never masquerades as CancelRun, and CancelRun never masquerades as failure;
- `PAUSED` is emitted only after its checkpoint commits;
- checkpoint commit failure emits `pause_persistence_failed`, never exposes a half-paused status, and resumes only after
  fresh World/currentness is re-established;
- service restart restores the same task revision, PydanticAI history, bounded Runtime state, equivalent public
  snapshot, and reconnectable browser session under a new event epoch without replaying a committed GUI effect;
- an old event epoch yields `resync_required`; no cross-restart event replay is claimed without stored envelopes;
- same command ID plus the same payload returns the committed result without re-execution, while a different payload
  under that ID returns `command_identity_reused`;
- missing, stale, corrupt, or incompatible checkpoints and lost environments fail in typed deterministic ways.

### 16.5 Running revision and compensation

- one accepted revision creates exactly one consecutive authoritative `TaskGoal` revision and one GoalCompiler call;
- every revision command ends paused or waiting according to the closed outcome table; only a later `ResumeRun` may
  enter ActionPolicy, and prior dispatched effects must first pass the Phase 7 gate;
- compiler/TaskIntake/environment/commit outcomes each leave either revision `n` or `n+1` unambiguous and the run in a
  documented paused/waiting/running state; no half-committed public goal is visible;
- all old GoalPlan, action-page, binding, and confirmation material is invalid before another dispatch;
- accepted PydanticAI tool calls remain structurally paired across pause/revision;
- fresh World, not old plan progress or chat text, determines the current environment;
- existing compatible effects are preserved; reversible/compensatable conflicts use a new ordinary action and receipt;
- original receipts are immutable; `SENT_UNKNOWN`, irreversible, and unsupported compensation fail closed without blind
  retry or invented rollback;
- the implementation contains no site-, selector-, label-, task-, fixture-, or benchmark-specific undo behavior.

### 16.6 Takeover

Takeover is acceptable only when the public Runtime port returns an exclusive typed control lease, Agent dispatch is
disabled for the lease duration, and return-control reacquires fresh World before resuming. The shell is tested for
admission, lease projection, stale-command rejection, and viewer protection; it does not implement a second executor.

## 17. Alternatives considered

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

### One global `TargetRuntime` for every Web session

Rejected while the configured policy/provider boundary retains mutable task history and invocation state. Reuse the
composition recipe and concurrency-safe clients, but instantiate session-scoped Runtime/provider-history owners. A
singleton becomes valid only after the Runtime is proven stateless and all session state is passed explicitly.

### Cancelling the background asyncio task as Pause

Rejected. Task cancellation does not establish dispatch truth, can turn a cooperative user request into a generic
failure, and cannot persist a resumable boundary. Core-owned safe points and execution receipts are required.

### Persisting only chat or PydanticAI messages

Rejected as a resume design. Model history cannot restore RunState, task revision, execution receipts, current browser
session, World lineage, pending confirmation, or event/idempotency state. Reuse PydanticAI serialization as one field of
the Runtime checkpoint, not as the checkpoint authority.

### Automatic rollback after every task revision

Rejected. A prior effect may remain compatible, may be compensatable rather than reversible, may be irreversible, or
may have unknown dispatch status. Preserve receipts and let the existing policy/action pipeline select a currently
offered compensation only when required by the revised goal.

### Workflow engine or event sourcing in the initial deployment

Deferred. Explicit safe-point snapshots, SQLite, reconnectable browser leases, and PydanticAI history are sufficient for
the declared single-process/restart boundary. If durable in-flight activities or multi-service orchestration becomes a
measured requirement, evaluate mature PydanticAI durable-execution integrations and Postgres before custom machinery.

## 18. References

- [AG-UI event concepts](https://docs.copilotkit.ai/ag-ui/concepts/events)
- [AG-UI protocol repository and Python SDK](https://github.com/ag-ui-protocol/ag-ui)
- [CopilotKit repository and official examples](https://github.com/CopilotKit/CopilotKit)
- [assistant-ui Tool UI](https://www.assistant-ui.com/docs/tools/tool-ui)
- [assistant-ui Thread component](https://www.assistant-ui.com/docs/ui/thread)
- [Steel Live Sessions](https://docs.steel.dev/overview/sessions-api/embed-sessions/live-sessions)
- [Steel human-in-the-loop sessions](https://docs.steel.dev/overview/sessions-api/human-in-the-loop)
- [Browserbase Session Live View](https://docs.browserbase.com/platform/browser/observability/session-live-view)
- [PydanticAI message history](https://ai.pydantic.dev/message-history/)
- [PydanticAI deferred tools](https://ai.pydantic.dev/deferred-tools/)
- [PydanticAI step persistence](https://ai.pydantic.dev/harness/step-persistence/)
- [PydanticAI observability](https://ai.pydantic.dev/logfire/)
- [PydanticAI durable execution](https://ai.pydantic.dev/durable_execution/overview/)
- [OpenHands system architecture](https://github.com/OpenHands/OpenHands/blob/main/openhands/architecture/system-architecture.md)
