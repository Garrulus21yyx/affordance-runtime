# External Interaction Shell implementation plan

Status: Full Web control release profile reverified through Phase 9 after lease-fencing repair; no live benchmark run
Worktree: `/home/yang/projects/affordance-runtime-interaction-shell`
Branch: `codex/external-interaction-shell`
Scope owner: standalone product plus the subsequently authorized Core public session boundary

## Invariants

- Core changes stay within the authorized public session boundary, trace
  fanout, and BrowserGym surface-owned execution/evaluation boundaries;
  authoritative architecture and benchmark docs record their current status.
- The shell consumes one versioned `RuntimeSessionPort`, closed `ShellCommand`, one current `RuntimeSessionSnapshot`, and one ordered `ShellEvent` stream.
- Runtime facts are projected exactly once at the adapter boundary; HTTP/SSE/UI reuse that representation.
- Unsupported Runtime capabilities remain typed `Unsupported`; no simulated cancellation, revision, takeover, completion, or Runtime state machine.
- No live benchmark is run.

## Visual direction

- Subject/audience/job: a focused GUI-task cockpit for users, plus a separate engineering flight recorder for exported bad cases.
- Palette: `flight-deck #E8EDF1`, `ink #15232B`, `panel #F7F9FA`, `signal #E9893A`, `verified #1B8A78`, `muted #72818A`.
- Type: condensed system display stack for panel titles, Inter/system sans for prose, IBM Plex Mono/system mono for cursors, timing, and evidence IDs.
- Operator layout: conversation and HITL / read-only live surface / concise owner-projected progress; no token, latency, evaluation, or attribution fields.
- Diagnostic layout: exported-case index / deterministic attribution / trajectory, token, latency, and evidence detail at `/diagnostics`.
- Signature: a restrained amber signal rail connects conversation, live view, and progress without exposing raw event plumbing.

## Steps

1. **done — Inspect public schemas and current exported artifacts.**
   - Identify public Runtime entrypoints, snapshot/event/outcome exports, benchmark result, and trace artifact shapes without importing internal owners into shell contracts.
   - Files: this plan only.
2. **done — Freeze standalone backend contracts and Phase A diagnosis.**
   - Add package/build isolation, Pydantic public contracts, deterministic projector, optional fail-open Langfuse sink, fixtures, and tests.
   - Files: `external/interaction-shell/backend/**`, `diagnostics/**`, `tests/backend/**`.
3. **done — Implement Phase B manager, port boundary, FastAPI, SSE, and cleanup.**
   - Add one port protocol, in-memory public demo adapter, command admission/idempotency/staleness, snapshot/event consistency, expiry, exactly-once viewer cleanup, and OpenAPI export.
   - Files: `backend/**`, `tests/backend/**`.
4. **done — Implement Phase C bounded conversation and revision compiler.**
   - Add bounded 3–6 turn context and one-call closed compiler boundary; submit only through advertised revise capability.
   - Files: `backend/**`, `tests/backend/**`.
5. **done — Build the standalone Next.js UI.**
   - Use generated API types, CopilotKit, shadcn/Radix primitives, Recharts, resumable SSE, read-only provider Live View or typed unavailable state, and a separately routed bad-case workbench.
   - Files: `frontend/**`, `tests/frontend/**`.
   - Frontend-design critique pass: strengthen the flight-recorder identity, remove generic CopilotKit visual residue, improve unavailable-view and diagnosis information hierarchy, then verify from a fresh browser screenshot.
6. **done — Add architecture guards and Web E2E.**
   - Negative import/path/media/platform checks and Playwright task/AskUser/confirmation/reconnect/diagnosis flows.
   - Files: `tests/architecture/**`, `frontend/e2e/**`.
7. **done — Run full verification and document operation.**
   - Backend tests, frontend tests, Playwright E2E, lint, typecheck, build, diff checks, forbidden search, and README/docs.
   - Files: `README.md`, `docs/**`, this plan.

## Produced files

- `.codex-plans/interaction-shell-implementation.md` — durable plan and progress ledger.
- `external/interaction-shell/backend/**` — isolated Pydantic/FastAPI package and public port boundary.
- `external/interaction-shell/tests/**` — backend contract/property tests and negative architecture guards.
- `external/interaction-shell/frontend/**` — operator Shell, separate diagnostics workbench, component tests, and Playwright E2E.

## Standalone baseline before the later port authorization

- Backend and architecture: 32 passed; Ruff and Pyright clean.
- Frontend: 2 component tests passed; TypeScript, ESLint, production build clean.
- Browser E2E: 1 passed, including zero diagnostic reads from the operator route.
- Production npm audit: 0 vulnerabilities.
- Core-path diff and forbidden-import searches were clean at that checkpoint.
- The missing public Runtime session port recorded at that checkpoint triggered
  the subsequently authorized extension below. Steel/Browserbase still requires
  deployment credentials and remains typed unavailable when unconfigured.

## Authorized SOTA-aligned Runtime port extension

The user subsequently authorized a minimal Core-owned public session port. The
new bounded contract follows AG-UI's thread/run/interrupt model: opaque session
identity, owner-projected snapshots before an interrupt, stable interrupt IDs,
resume on the same session, and internal checkpoint/`RunState` ownership hidden
behind the handle.

8. **done — Add the Core-owned versioned public session boundary.**
   - Public snapshot/events/capabilities, opaque handle, async run lifecycle,
     exact AskUser/confirmation resume identities, and fail-closed commands.
9. **done — Connect the external adapter and streaming drain.**
   - One projection at the adapter boundary; background Runtime events feed the
     existing cursor-resumable Shell SSE without exposing internal state.
10. **done — Verify owner invariants and update capability documentation.**
   - Core port tests, adapter tests, stale/interrupt identity tests, cleanup,
     frontend E2E, full lint/type/build/diff checks, no live benchmark.

## Final verification after public port authorization

- Core boundary and adjacent regression slice: 35 passed; Ruff clean; public
  session module MyPy clean.
- External backend and architecture: 35 passed; Ruff and Pyright clean.
- Frontend: 2 component tests passed; ESLint, TypeScript, generated OpenAPI
  types, production build, and production npm audit clean.
- Browser E2E: 1 passed, including zero diagnostic reads from the operator
  route.
- `git diff --check`, protected docs/root-build diff, forbidden internal-import
  search, and custom media transport search: clean.
- No live benchmark was run.

## Real deployment implementation sequence (current work)

Constraints:

- Complete and record Phase 0 before changing Phase 1/2 architecture.
- Preserve the four public contracts: `RuntimeSessionPort`, `ShellCommand`,
  `RuntimeSessionSnapshot`, and `ShellEvent`.
- Keep `interaction_shell.api:app` fail-closed with typed Runtime unavailable and
  keep the Demo explicitly synthetic.
- Implement only Phase 1 session isolation/event ownership and Phase 2 real
  deployment composition. Do not start Viewer, checkpoint, pause/resume, or task
  revision work.
- Commit and push each coherent milestone.

11. **done — Phase 0: lock the existing baseline.**
    - Run backend tests/lint/typecheck, frontend tests/lint/typecheck/build, and
      Demo Playwright E2E using the repository-owned commands.
    - Verify the four public contract exports, default typed unavailable behavior,
      and explicit synthetic Demo labeling.
    - Record exact commands and outcomes without architecture changes.
    - Files: this plan and a baseline evidence record only.
12. **done — Phase 1: isolate Runtime sessions and move event ownership.**
    - Establish the current shared-state mechanism and owners before editing.
    - Open one independent Runtime, model policy/history, environment/browser,
      public port, and event epoch/cursor per session behind an opaque handle.
    - Keep only the opaque handle, TTL, command lock, and bounded conversation in
      `RunSessionManager`; make cleanup idempotent and partial-open safe.
    - Verify concurrent isolation and independent close behavior.
    - Root cause: `TargetRuntimeSessionFactory.runtime` currently reuses one
      `TargetRuntime`, whose `ModelBackedAgentPolicy` and
      `PydanticAIGroundedDecisionPort.message_history` are mutable; the Shell
      manager separately retains and renumbers a second copy of port events.
    - Positive contract: each `open(session_id)` creates a distinct Runtime and
      environment lease; the opaque handle alone owns task/run/World/event state;
      snapshot and event epoch/cursor originate at that handle/port; Manager event
      reads are direct passthrough; close and failed open clean known resources once.
    - Evidence: 40 combined Core/backend/architecture tests passed; the concurrent
      two-session witness observed distinct policy histories, environments, task
      identities, event epochs, and cleanup counters; concurrent readers received
      identical owner timestamps/envelopes. Ruff, MyPy, Pyright, frontend unit,
      lint, typecheck, production build, and Demo E2E passed.
13. **done — Phase 2: add and fully close the real deployment entrypoint.**
    - Add thin `interaction_shell.deployment_app` composition over existing
      provider/runtime configuration and per-session BrowserGym/Playwright.
    - Keep Viewer typed unavailable.
    - Verify one real deployed chain from Web session through page mutation,
      fresh World/evaluation, snapshot/SSE/UI, and cleanup.
    - Owner finding: the existing MiniWoB native outcome interpreter lives under
      the benchmark package. The deployment must consume a reusable BrowserGym
      surface-owned native TaskEvaluator rather than import benchmark policy or
      branch on a smoke case/task label.
    - Root-cause repairs from the real witness: BrowserGym 0.14.3's process-global
      synchronous Playwright cache is now owner-thread-local at every cached
      import site; the Next.js SSE path uses identity/no-transform/no-buffer
      headers; StrictMode shares one in-flight session open; trace directories
      are per session; cancelled late browser opens are recovered and closed.
    - Evidence: the held-out UI run issued one session create, one real dispatch,
      two observations, native `verified_success`, incremental SSE/UI `done`,
      explicit close, and clean application shutdown. A separate real concurrent
      witness opened distinct BrowserGym owners and kept the second alive after
      closing the first. No benchmark was run.
    - Cleanup closure: one deployment-private idempotent owner now closes the
      BrowserGym surface and flushes/closes the optional trace viewer worker.
      Environment-open failure, later composition failure, cancellation,
      normal/session/TTL/terminal/application close, and concurrent sessions all
      converge on that owner. Trace cleanup failure is logged and fail-open for
      task truth and surface cleanup. The delivery-state truth table now agrees
      with the verified Phase 2 status.
14. **done — Phase 3: cooperative control and dispatch closure.**
    - Add Runtime-owned `PauseRun` and `CancelRun` requests without SQLite,
      durable `PAUSED`, revision, or a second execution loop.
    - Define one closed dispatch truth algebra: `NOT_SENT | SENT |
      SENT_UNKNOWN`. Never derive it from asyncio task cancellation.
    - Check cooperative control at owner boundaries before/after policy,
      before binding/dispatch, after dispatch closure, after fresh World capture,
      after evaluation, and in waiting-user/confirmation states.
    - Pause terminates the active loop only at an internally reported
      `pause_boundary_reached`; Cancel commits terminal `CANCELLED`; close remains
      resource destruction.
    - Preserve complete policy/tool history: a selected-but-undispatched action
      receives a typed non-dispatch closure before the loop yields.
    - Verify the state/transition algebra and held dispatch races with owner-level
      and public-session integration tests. Do not add a checkpoint store.
    - Core substrate complete: one per-Runtime bounded cooperative-control owner,
      `RunState`-owned reached boundary, terminal user cancellation, exact
      receipt propagation, and PydanticAI terminal ToolReturn closure are in
      place. Held policy/dispatch races cover `NOT_SENT`, `SENT`, and
      `SENT_UNKNOWN`; 211 focused Core/model/architecture tests pass.
    - Public closure complete: `CancelRun` is advertised through the public
      Runtime session, Shell port, optional command API, generated frontend
      types, and capability-gated UI control. It projects terminal `CANCELLED`
      with a cancellation completion and remains separate from Close teardown.
      Pause/Resume stay private and unadvertised until durable checkpoint
      ordering exists.
    - Final evidence: 263 focused Core/model/public-session/backend/architecture
      tests passed with 3 optional-dependency skips; Ruff passed. Frontend 4
      unit tests, ESLint, TypeScript, OpenAPI equality/generation, and production
      build passed. No benchmark was run and no SQLite/checkpoint code was added.
      The full provider-free suite passed 1770 tests with 19 skips after
      deselecting the two pre-existing non-Phase-3 witnesses: documentation
      governance rejects this required implementation document, and one
      semantic-delivery test depends on a historical live trace absent here.
15. **done — Phase 4: SQLite checkpoint and durable pause.**
    - Persist only Runtime-owned state reached through the Phase 3 cooperative
      pause boundary; do not use SQLite as an interruption or dispatch owner.
    - Atomically commit checkpoint plus pause command outcome before projecting
      public `PAUSED`, `checkpoint_id`, or `resume_eligible`.
    - Store the bounded recovery contract: task goal/revision, authoritative run
      state, validated GoalPlan, required counters/budgets, last closed step and
      receipt, pending interrupt identity, model history, reconnect reference,
      Runtime command idempotency outcome, schema version, digest, and timestamp.
    - Exclude live tasks/locks/clients, complete World payloads, Shell transcript,
      trace/view projections, and duplicate Shell events.
    - Fail typed as `pause_persistence_failed` without publishing durable
      `PAUSED`; acquire fresh World and continue the original revision when
      currentness can be recovered.
    - Keep ReviseTask, reconciliation/compensation, Viewer, and takeover out of
      this phase. Commit and push each coherent milestone.
    - Implemented one immutable versioned Runtime checkpoint, official
      PydanticAI message serialization with unclosed-tool-call rejection, and a
      SQLite WAL store that commits checkpoint plus pause-command outcome in one
      transaction. `RunState` enters authoritative `PAUSED` only after commit.
    - Public Runtime/Shell/OpenAPI/UI advertise `PauseRun` only for sessions with
      a store and project `checkpoint_id`, `resume_eligible`, and the typed
      command outcome. Local BrowserGym honestly reports durable pause available
      and restart resume unavailable.
    - Verification so far: 152 focused Core/model/public/backend/architecture
      tests passed with 3 optional skips and 2 live-name deselections; the wider
      agent/app/architecture slice passed 303 tests with 3 optional skips.
      External backend/architecture passed 50 tests; frontend 5 unit tests,
      ESLint, TypeScript, OpenAPI generation, and production build passed;
      backend Pyright and touched-owner MyPy passed. No benchmark was run.
16. **done — Phase 5: process restart recovery and explicit ResumeRun.**
    - On restart validate session/schema/digest, reconnect the same environment,
      restore model history, capture a fresh World, create a new event epoch and
      baseline snapshot, then wait for explicit `ResumeRun` without replaying an
      old action.
    - Fail typed as `environment_not_reconnectable` rather than opening and
      replaying against a replacement browser.
    - Add authenticated same-session recovery, old-epoch resync behavior,
      corrupted/stale checkpoint rejection, and restart fault-injection tests.
    - Implemented exact checkpoint load/digest/schema validation, official
      PydanticAI history restore, bounded RunState hydration against a fresh
      World, semantic confirmation rebasing, a new Runtime-owned event epoch,
      and explicit ResumeRun with SQLite one-shot checkpoint consumption before
      any new policy/dispatch.
    - Shell restart authentication persists only a salted key verifier and the
      original TTL. Old epochs require snapshot resync; checkpoint/session/key
      mismatches and consumed checkpoints fail typed. RUNNING, waiting-user,
      waiting-confirmation, committed-SENT/no-replay, corruption, lost browser,
      and auth-isolation witnesses pass.
    - Local BrowserGym cannot reconnect the exact Playwright context after
      process death. Its deployment health remains durable-resume unavailable
      and recovery returns `environment_not_reconnectable` without opening a
      replacement browser; reconnectable deployment leases can use the now
      complete factory/port contract.
    - Verification: the focused Core/model/public-session/architecture slice
      passed 204 tests with 3 optional skips; external backend/architecture
      passed 54 tests; frontend passed 7 unit tests, ESLint, TypeScript,
      generated-OpenAPI equality, production build, and 1 Demo Playwright E2E.
      Backend Pyright, Ruff, compileall, diff checks, and the five touched
      Runtime-owner MyPy files passed. The full provider-free suite passed 1778
      tests with 25 skips and retained only the two known non-Phase-5 failures:
      documentation governance rejects the user-required interaction-shell
      implementation document, and one semantic-delivery witness requires a
      historical live trace absent from this worktree. Two added owner-boundary
      regressions also pass: concurrent same-session recovery installs one
      Runtime handle, and SQLite rejects row/payload scope mismatch. No benchmark
      was run.
17. **done — Phase 6: ReviseTask compiler and paused revision commit.**
    - Baseline is clean `0a7b0ddc`; Phase 5 checkpoint/recovery infrastructure
      is fixed and will not be redesigned for this phase.
    - First map the existing TaskIntake, GoalCompiler, environment task-revision,
      checkpoint transaction, public session, Shell port, OpenAPI, and UI owners.
    - Add one bounded `TaskRevisionCompiler` call with the closed outcomes
      `Ready | NeedsInput | NoChange | NewTaskSuggested | Unsupported | Failed`.
      It is a typed compiler, not an Agent, manager, or execution loop.
    - `ReviseTask` must reuse the cooperative pause boundary, commit the old
      revision checkpoint, compile and validate a complete consecutive
      `TaskGoal`, revise the same environment, capture fresh World, invoke the
      existing GoalCompiler exactly once, atomically commit the new revision
      checkpoint, and remain `PAUSED` until a separate `ResumeRun`.
    - Invalidate the old GoalPlan/action/binding/confirmation. If the committed
      old boundary contains `SENT` or `SENT_UNKNOWN`, return typed
      `effect_reconciliation_required`; compensation remains Phase 7.
    - Migrate Runtime/private checkpoint/public session/Shell/OpenAPI/UI and
      documentation together. Verify every compiler outcome, stale/idempotent
      command behavior, pause/commit ordering, rollback/failure currentness,
      zero auto-resume, one GoalCompiler call, and no second state authority.
    - Internal compiler milestone implemented: a non-agent
      `TaskRevisionCompiler` algebra, complete TaskGoal proposal schema, one
      bounded model call with schema/provider retry evidence, production role
      composition, and disabled fallback. Its 31 contract/model/factory tests,
      22 Runtime composition regressions, Ruff, MyPy, and diff check pass.
    - Runtime owner milestone implemented: one revision command can request the
      existing cooperative pause, commit its source checkpoint, reject any
      prior dispatched effect for Phase 7, compile/re-admit a consecutive goal,
      revise the environment, capture fresh World, invoke GoalCompiler once,
      rebind one closed official model history, and atomically commit the new
      checkpoint plus revision outcome without auto-resume. Persistence failure
      restores old history/environment/fresh paused state. The 82 checkpoint and
      PydanticAI tests plus 51 public Runtime/composition/architecture tests,
      Ruff, compileall, and the five typed Runtime-owner MyPy files pass.
    - Shell/API/UI milestone implemented: `ReviseTask` is a dedicated command
      and HTTP route; Manager makes exactly one `RuntimeSessionPort.revise`
      call per request and lets duplicate retries replay the Runtime-owned
      durable outcome. Generated OpenAPI/TypeScript contracts and the
      capability-gated conversation input carry the exact expected checkpoint;
      success remains paused and never invokes Resume automatically. Synthetic
      Demo and the default unavailable port remain typed unavailable.
    - Final owner evidence includes revision arriving during a held policy
      call, waiting-confirmation invalidation with zero dispatch, stale Shell
      rejection before the port, duplicate result replay, every compiler
      non-ready outcome, prior-effect rejection, persistence rollback, and
      exact single GoalCompiler/environment revision on success.
    - Final verification: the Phase 6/Core/Shell focused slice passed 174 tests;
      external backend/architecture passed 56 tests; frontend passed 8 unit
      tests, ESLint, TypeScript, generated OpenAPI, and production build;
      backend Pyright/Ruff and touched Core Ruff passed; Demo Playwright E2E
      passed 1 test. The full provider-free suite passed 1805 tests with 19
      skips after deselecting the same two known non-Phase-6 witnesses: the
      documentation-governance count rejects this user-required document, and
      one semantic-delivery test requires a historical live trace absent from
      the worktree. An initial unfiltered run recorded only those two failures.
      No live benchmark was run; Viewer and Phase 7 were not started.
18. **done — Phase 6.5: reuse model persistence/trace and close command identity.**
    - Preserve Runtime ownership of `TaskGoal`, `RunState`, cooperative safe
      points, GUI dispatch receipts, fresh-World currentness, checkpoint/resume
      eligibility, and browser reconnect references.
    - Verify the installed `pydantic-ai-harness==0.25.0` APIs and migrate model
      message/step continuity to `StepPersistence(SqliteStepStore)` only where
      it can replace the current parallel transcript/history persistence
      without becoming GUI-effect or Runtime-checkpoint authority.
    - Use PydanticAI/OpenTelemetry instrumentation for model/provider spans and
      connect the custom structured-provider boundary to the same trace path;
      remove only transcript state made redundant by that positive owner flow.
    - Extend the existing Runtime revision-outcome transaction with a canonical
      `ReviseTask` payload digest and bounded original result. Same command ID +
      same digest replays the original outcome; a different digest returns
      typed `command_identity_reused` before compilation/environment mutation.
    - Remove Shell-side duplicate authority for `ReviseTask`; the Shell keeps
      its command lock and bounded conversation but forwards every revision
      request once to Runtime. Do not add a service, ledger, workflow engine,
      Temporal/DBOS/LangGraph, or Phase 7 compensation behavior.
    - Migrate schema/versioning, recovery/duplicate/fault paths, public
      contracts, OpenAPI/UI tests, documentation, and verification together.
      Commit and push each coherent milestone; do not run live benchmark.
    - API finding: Harness 0.25.0 `StepPersistence` persists complete snapshots
      only at PydanticAI-owned settled boundaries. This Runtime intentionally
      returns deferred external tool calls and later appends their GUI
      `ToolReturn` synchronously from a closed `StepResult`; no Harness hook
      owns that later boundary. Until an adapter durably saves that owner-closed
      official history before Runtime checkpoint commit, replacing the embedded
      message snapshot would expose only `interrupted` history and is unsafe.
      Keep the current `ModelMessagesTypeAdapter` snapshot while building and
      testing that adapter; do not claim StepPersistence migration complete.
    - Command-identity milestone implemented: the public Runtime receives the
      complete revision command, hashes its canonical payload, and atomically
      stores the digest plus bounded outcome/message in the existing revision
      row. Exact retries replay before stale-state checks; changed payload under
      the same ID fails typed as `command_identity_reused` before compiler or
      environment work. Legacy rows migrate in place with an unverifiable
      sentinel and therefore fail closed against new payloads. Shell forwards
      every revision attempt and retains the ID only as a bounded-conversation
      cache. Focused evidence: 23 Runtime checkpoint tests and 13 Shell
      manager/port tests passed; touched Ruff, MyPy, and Pyright checks passed.
    - Model-continuity milestone implemented: every PydanticAI ActionPolicy call
      uses official Harness `StepPersistence` with explicit run/conversation
      identity, while a Runtime safe checkpoint saves one immutable,
      provider-valid official Harness snapshot through `SqliteStepStore` and stores only its run reference,
      message digest, and task identity. A new `SqliteStepStore` instance can
      restore the exact settled messages; legacy embedded
      `ModelMessagesTypeAdapter` checkpoints remain readable. Deployment maps
      each session to a deterministic private step-store SQLite file, avoiding
      the proven concurrent first-schema-initialization lock while preserving
      restart lookup and complete session isolation.
    - Trace milestone implemented: PydanticAI native instrumentation emits
      ActionPolicy model/tool spans with binary content excluded, and the
      custom OpenAI-compatible/Ollama structured-provider boundary emits
      compatible `gen_ai.*` spans through the same global or injected
      OpenTelemetry provider. No trace value participates in checkpoint,
      receipt, revision, or task authority.
    - Final focused evidence: 132 Runtime checkpoint/public-session/PydanticAI/
      provider tests, 91 root architecture tests, and 58 external backend/
      architecture tests passed. Deployment Pyright, six touched-owner MyPy
      files, touched Ruff, compileall, and diff checks passed. Failure injection
      proves model-step persistence failure never publishes `PAUSED`; concurrent
      session stores initialize without locking; SQLite reopen/digest tampering,
      official step events, and native/custom OTel spans are covered. No live
      benchmark was run; Phase 7, Viewer, and takeover were not started.
19. **done — Reclose pre-policy checkpoint identity and revision conversation.**
    - Keep the single `CoreAgentLoop`, existing Runtime checkpoint/receipt
      authorities, existing Runtime `TaskRevisionCompiler`, and current SQLite
      stores. Do not add an Agent, database, workflow engine, or Phase 7
      compensation behavior.
    - Diagnose and repair model-history identity at its owner: bind admitted
      `TaskGoal(task_id, revision)` before environment reset/GoalCompiler/first
      ActionPolicy, allow a provider-valid empty settled Harness snapshot, and
      prove pause/restart/resume before the first policy call.
    - Define one immutable bounded revision-conversation value (at most six
      turns and one total byte bound), include it in the complete Runtime
      command digest, and pass it only to the existing one-shot Runtime
      `TaskRevisionCompiler`. Runtime alone adds authoritative TaskGoal and
      pending question/confirmation facts; conversation cannot authorize GUI
      actions and never enters ActionPolicy Harness history.
    - Make Shell construct and forward the bounded snapshot with the latest
      revision message exactly once. Remove the unused external Shell revision
      compiler and migrate public contracts/OpenAPI/generated frontend types,
      duplicate/stale behavior, tests, and docs together.
    - Correct observability status: native/custom OTel instrumentation exists,
      but deployment has no configured recording `TracerProvider + exporter`;
      this remains a non-blocking deployment follow-up and does not count as
      Phase 6 closure evidence.
    - Acceptance matrix: pre-policy pause with zero policy calls and restart
      recovery; ordinary post-step pause; contextual and self-contained
      revisions; pending-question reference; exact duplicate replay; changed
      text/context identity conflict; stale command with zero compiler calls;
      old action/binding/confirmation invalidation; revised state remains
      paused until explicit Resume.
    - Commit and push the checkpoint-identity repair first, then the bounded
      conversation/removal/doc closure. Do not run live benchmark.
    - Checkpoint-identity milestone implemented: synchronous task admission now
      binds model continuity before the public start task is scheduled, and
      every direct Runtime initialize/run entry binds idempotently before
      environment reset or GoalCompiler. Empty official PydanticAI history is a
      provider-valid settled Harness snapshot. The pre-policy restart witness
      pauses while reset is held with zero policy calls, restores under a new
      epoch, and calls policy only after explicit Resume. Focused evidence: 102
      public-session/checkpoint/Runtime/PydanticAI tests, touched Ruff/MyPy,
      compileall, and diff checks passed.
    - Revision-conversation milestone implemented: the Shell manager constructs
      one immutable snapshot of at most six turns and 16 KiB, identifies the
      latest user turn exactly once, caches the exact command snapshot for
      replay, and forwards it through the existing dedicated revision port.
      Runtime alone adds current `TaskGoal` plus pending question/confirmation
      facts from `RunState`, calls the existing compiler once, and includes the
      complete conversation in its canonical command digest. Same identity with
      changed text or context fails typed before a second compiler call;
      conversation never enters ActionPolicy Harness history. The unused
      external Shell compiler module and its parallel schema/provider tests were
      removed; OpenAPI and generated TypeScript now reflect the typed value.
    - Closure evidence: the acceptance-focused Runtime/model/Shell slice passed
      45 tests; the broader Runtime app/model/external-isolation slice passed
      117; external backend plus architecture passed 57; backend Pyright and
      touched-owner MyPy/Ruff/compileall/diff checks passed. Frontend passed 8
      unit tests, ESLint, TypeScript, generated OpenAPI, production build, and 1
      Demo Playwright E2E. Root architecture/governance passed 93 tests; its
      only failure remains the pre-existing five-document count rejecting this
      user-required implementation document. No live benchmark ran. Phase 7,
      Viewer, takeover, and deployment OTel exporter wiring remain unstarted.
    - Post-push full provider-free regression: 1816 passed, 19 skipped, and one
      governance test was explicitly deselected for the same required-document
      conflict. The only executed failure was the known semantic-delivery replay
      whose historical `evidence/live/.../trace.jsonl` is absent from this
      worktree; it failed at file open before exercising production code. No
      `.env` or live provider/benchmark profile was loaded.
20. **complete — Persist bounded Shell revision recovery projection.**
    - Repair only the existing Shell recovery-registry owner. Persist the latest
      at-most-six/16-KiB conversation turns and at-most-64 immutable revision
      command contexts in its current SQLite database; do not add a database,
      Agent, Runtime checkpoint field, command-result authority, GUI state, model
      history, receipt, Viewer, OTel exporter, or Phase 7 behavior.
    - For StartTask/AnswerQuestion, persist the resulting bounded turn after the
      port admission path closes. For ReviseTask, construct the immutable
      context, persist it before `RuntimeSessionPort.revise`, then call Runtime;
      a projection-write failure must prevent Runtime admission.
    - Recover and validate the bounded projection after Shell authentication and
      before installing/using the recovered Runtime handle. Session revoke/TTL
      cleanup must delete the projection with the existing recovery credential.
    - Verify three held-out properties: a new revision after Shell restart sees
      pre-restart turns; a committed revision with lost HTTP response replays
      after restart without a second compiler call; changed text/context under
      that command ID remains typed `command_identity_reused`.
    - Update architecture/benchmark/interaction-shell status only after owner,
      failure-ordering, restart, TTL/revoke, and existing gates agree. Commit and
      push this coherent repair before Phase 7; do not run live benchmark.
    - Implemented in the existing `shell_session_recovery` row with an in-place
      migration and versioned canonical JSON. The projection validates and
      retains at most six/16-KiB turns and 64 immutable command contexts. New
      revision context plus latest turn commits before the Runtime port call;
      restore validates it before Runtime recovery; explicit/terminal/TTL revoke
      deletes the row and projection together. Projection failures are typed,
      and the pre-dispatch failure witness records zero Runtime revise calls.
    - Closure evidence: held-out Shell-restart tests prove pre-restart context in
      the first new revision, exact lost-response replay with compiler count one,
      and same-ID changed text/context conflict. Bounds, legacy-table migration,
      and revoke deletion are also covered. External backend/architecture passed
      63 tests, Runtime/checkpoint/model revision passed 112, root architecture
      passed 91, backend Pyright plus touched Ruff/compileall/diff checks passed.
      Documentation now identifies this as a Shell language projection rather
      than a Runtime checkpoint or command-result authority. No live benchmark,
      Viewer, OTel exporter, Phase 7, or compensation work ran.
21. **done for the bounded provider-free contract — Phase 7 effect reconciliation and compensation.**
    - Owner model: `Reversibility` and operation semantics classify the original
      effect; the immutable execution receipt owns dispatch truth; fresh World
      owns currentness; `RunState` owns one bounded reconciliation requirement;
      the existing ActionPolicy chooses any ordinary compensation action; the
      existing Binder/Risk/Confirmation/Executor/ActionOutcome chain executes
      and verifies it. Shell and Viewer remain projections only.
    - Positive supported contract: a revision with no sent receipt follows the
      existing Phase 6 path; one uniquely retained latest `SENT` effect is
      classified as compatible, reversible/compensatable, irreversible, or
      unknown. Compatible effects are preserved. Reversible/compensatable
      effects commit revision `n+1` paused with one bounded reconciliation fact
      and may dispatch only a current ordinary action against the same resource
      before normal goal execution continues. `SENT_UNKNOWN`, missing or
      ambiguous receipt lineage, multiple unrepresented effects, irreversible
      effects, unavailable compensation, and unverifiable compensation close
      as typed paused/needs-input/unsupported outcomes without retrying the old
      action.
    - Preserve the original receipt and append a new compensation receipt. Do
      not mutate receipt history, roll back checkpoints, add a compensation or
      manager Agent, add a second Binder/loop/checkpoint/database, infer undo
      from page strings, or grant authority from the Viewer/API key.
    - First migrate the owner contracts end to end: carry typed reversibility
      and stable public resource identity through binding → ActionOption →
      admitted selection → execution receipt; persist/restore the bounded
      reconciliation fact in Runtime checkpoint; expose only its public summary
      to the same ActionPolicy against fresh World.
    - Then replace the coarse `execution_count > 0` revision rejection with the
      closed reconciliation algebra, wire ordinary compensation through current
      ActionSpace and existing risk/confirmation/dispatch verification, and
      keep successful revision/compensation paused until the existing explicit
      Resume boundary permits continuation.
    - Acceptance properties: compatible effect retained without a dispatch;
      reversible and compensatable effects use the ordinary pipeline and append
      receipts; confirmation remains mandatory where Risk requires it;
      irreversible and `SENT_UNKNOWN` stay paused and typed; restart preserves
      reconciliation without replay; stale action/binding/confirmation cannot
      dispatch; no production branch keys on fixture/page/task text. Run
      provider-free owner/Runtime/external/architecture gates, update docs,
      commit and push coherent milestones promptly. Do not run live benchmark
      or implement Viewer/takeover in this phase.
    - Owner-contract milestone implemented: dependency-free typed
      `Reversibility` and canonical `resource_ref` now survive binding,
      ActionSpace grouping/admission, model projection, bound-request identity,
      execution receipt, and one deterministic `CommittedEffect` projection.
      Ambiguous route semantics fail closed; page-authored metadata cannot
      downgrade registered irreversibility; ordinary BrowserGym effects remain
      `UNKNOWN`. WorldFusion rewrites only default source-local resource IDs to
      canonical target identity while preserving explicit stable resource IDs.
      Focused evidence passed 122 existing owner tests, then 81 new/affected
      tests and 39 fusion/conservation witnesses; root architecture passed 91.
      The wide provider-free run passed 1324 with 12 skips after the new fusion
      regression was repaired; its only remaining failures are the same two
      documented baseline witnesses (absent historical live trace and the
      user-required sixth maintained Markdown document). Ruff and diff checks
      pass. Repository-wide MyPy still reports 46 pre-existing inference errors
      outside changed lines, so it is not claimed as a passing gate.
    - Runtime/checkpoint milestone implemented: one dispatch-crossing
      `CommittedEffect` and one optional compensation effect are conserved in
      `RunState` and checkpoint v3; v2 remains readable. Fresh revised-goal
      `COMPLETE` preserves the effect. Otherwise one known
      reversible/compensatable effect commits revision `n+1` with a pending
      reconciliation and remains paused. A separate Resume gives the same
      ActionPolicy only current same-resource actions; the existing Binder,
      currentness, Risk, Confirmation, Executor, fresh World, ActionOutcome,
      and TaskEvaluator boundaries remain unchanged. Verified compensation
      appends its receipt, atomically checkpoints, and pauses again until a
      second Resume. Unknown dispatch/semantics, irreversible, missing or
      multiple effects, unavailable/mismatched actions, multi-receipt
      compensation, and unverified postconditions close typed and fail closed.
    - Public milestone implemented: Runtime public session and Shell snapshot
      v2 expose one bounded semantic reconciliation projection and exact result
      codes; no private binding or GUI state crosses the port. Historical
      revision command identity stays on its unchanged durable payload version,
      so the additive snapshot upgrade cannot invalidate stored retries. Shell
      OpenAPI/generated TypeScript and the operator UI show the owner-produced
      state but own no effect logic. Viewer remains typed unavailable; the
      Phase 7 path neither inspects nor consumes its configured key.
    - Provider-free evidence: 42 focused checkpoint/reconciliation tests, 216
      owner/Runtime/architecture tests with 3 optional skips, and 64 external
      backend/architecture tests passed. Frontend unit/lint/typecheck/build,
      backend Pyright, repository Ruff, compileall, and diff checks passed.
      Compatibility witnesses cover checkpoint v2, revision digest stability,
      restart without replay, confirmation, resource scoping, exact typed
      rejections, unavailable/unverified compensation, and public/private
      projection. No live browser compensation witness or benchmark was run;
      this does not claim a multi-effect ledger, rollback, or general Saga.
    - Post-push full provider-free regression: 1830 passed and 25 skipped in
      79.17 seconds. The only two failures are the unchanged baselines: the
      five-document governance assertion rejects the user-required
      `docs/interaction-shell.md`, and one semantic-delivery test fails while
      opening an absent historical live trace before production code runs.
      Synthetic Demo Playwright E2E also passed 1 Chromium test. Existing
      deployment tests may load the project `.env` through the deployment
      module's established startup behavior, but Phase 7 did not inspect,
      print, or use the Viewer credential and did not start Viewer, a live
      model/provider, a browser compensation profile, or a benchmark.
22. **complete — protected read-only Viewer deployment.**
    - Owner model: the deployment browser/environment lease owns the provider
      session locator and cleanup; a deployment-private viewer registry/proxy
      owns authenticated short-lived resolution; the Runtime public session
      projects only readiness and a secret-free same-origin `/viewer/{session}`
      path; Shell/UI remain read-only consumers.
    - First establish the configured provider from environment variable names
      only and inspect the existing BrowserGym lease/viewer extension points.
      Never print, serialize, log, or send `VIEWER_API_KEY` or an upstream viewer
      URL to the frontend.
    - Positive contract: Viewer and Runtime refer to the same browser session;
      session authentication, expiry, wrong-session access, and cleanup are
      enforced at the same-origin backend boundary; Viewer loss is fail-open for
      Runtime task truth; unavailable provider/session state stays typed.
    - Keep takeover out of scope. Do not add screenshot polling, custom media
      transport, remote input, a second browser, Runtime state, checkpoint
      fields, or provider credentials to Shell recovery.
    - Provider finding: the configured key is explicitly labelled Steel.
      Steel returns one session-scoped CDP endpoint and one unauthenticated
      debug document. The pinned BrowserGym owner currently launches Chromium
      locally, so the coherent profile must replace that surface-owned launch
      with `connect_over_cdp` to the same Steel lease; key-only iframe wiring
      against the local browser would be a false second-session projection.
    - Read-only proxy finding: Steel `interactive=false` does not open its input
      WebSocket. Its headful viewer uses only the provider document plus the
      `ice-servers` and `whep` WebRTC endpoints. The deployment can therefore
      authenticate a same-origin `/viewer/{session}` route, rewrite the
      provider document to that origin, and proxy only those two bounded media
      calls. The reusable API key, provider debug/CDP URLs, provider session ID,
      and RTC bearer remain server-private; native short-lived ICE credentials
      remain the provider media transport rather than a Shell media protocol.
    - Profile boundary: remote Steel execution is explicit because a cloud
      browser cannot reach a loopback MiniWoB source. The existing local
      BrowserGym profile remains the safe default and keeps Viewer typed
      unavailable; the Steel profile requires a remotely reachable task source
      and never silently opens a second browser as a fallback.
    - First live CDP/reset probe exposed one pinned-provider lifecycle rule:
      Steel's single initial page keeps the remote context alive, so closing it
      before `new_page()` terminates the provider session. The surface-owned
      conversion now claims that exact initial page and applies BrowserGym's
      viewport to it. The failed probe released its provider lease; a repeated
      no-model/no-action probe was then repeated against an in-process
      BrowserGym smoke task: reset and initial World acquisition succeeded with
      the Steel browser connected and page open, followed by successful release.
      A separate live provider-document probe confirmed server-side locator
      removal and a 200 ICE proxy response. The public raw-githack MiniWoB URL
      returned its CDN notice to the cloud browser and is explicitly not counted
      as a product/task-chain witness; no model, GUI action, or benchmark ran.
    - Verify authorized/unauthorized/wrong-session/expired access, provider
      disconnect, exactly-once cleanup, two-session isolation, no-secret public
      projection, Viewer-failure independence, frontend rendering, OpenAPI, and
      existing Runtime/Phase 7 regression gates. Commit and push each coherent
      milestone; no live benchmark without separate authorization.
    - Implemented result: one explicit `steel_browsergym` profile creates a
      provider session, replaces only BrowserGym's environment Chromium launch
      with the provider CDP connection, claims its single existing context/page,
      and registers one opaque handle-to-viewer projection. The local profile is
      unchanged and Viewer-unavailable. HttpOnly same-session auth plus the
      Next.js same-origin rewrite protect the iframe; the provider document is
      validated and stripped of reusable locators/credentials, and only native
      read-only ICE/WHEP calls are proxied. Cleanup releases surface, provider,
      and trace owners independently and idempotently.
    - Verification: 73 external backend/architecture tests passed, including
      session auth, wrong nested identity, provider disconnect, two-session
      isolation, partial/composition cleanup, no-secret document projection,
      exact provider lease reuse, and Viewer/Runtime failure independence. Seven
      focused BrowserGym owner tests, Ruff, Pyright, diff/OpenAPI checks, and 10
      frontend tests plus lint/typecheck/build passed. A no-model/no-action live
      Steel BrowserGym reset observed a connected open page and released the
      session; a separate real document/ICE probe returned 200 after confirming
      provider locator removal. No benchmark, model call, GUI task action,
      compensation action, input WebSocket, or takeover ran.
      The post-feature full provider-free repository suite reached 1837 passed
      and 19 skipped; only the two unchanged baseline failures remained (the
      five-document governance assertion and an absent historical live trace).
      Demo Playwright E2E passed one Chromium test.
    - Live media convergence: Steel's current document appends its session
      region to the WHEP request. The proxy admits only the documented current
      Steel region algebra and forwards that value to the fixed provider host;
      missing/unknown values fail typed. The earlier WHEP 400 witness was not a
      provider outage: the bundled Playwright Chromium used by that probe
      advertised VP8/VP9/AV1 but no H.264, while Steel's documented headful
      stream requires H.264 baseline. A held-out native control using an
      H.264-capable Steel browser completed WHEP with 201 and rendered 1280x720
      video at `readyState=4`. The protected same-origin product route was then
      verified with a temporary official Chrome-for-Testing client: unauthenticated
      access returned 401, the authenticated document returned 200, the proxied
      WHEP returned 201, video reached `readyState=4` at 1280x720, no page error
      occurred, provider locators remained absent, and cleanup released the
      exact provider lease. The first protected-path polling attempt also
      exposed an acceptance-harness constraint: the production CSP correctly
      rejects Playwright string `wait_for_function` because it requires
      `unsafe-eval`; the final witness used Python-side polling without weakening
      CSP. No alternate media path, second Runtime browser, model call, GUI
      action, compensation action, input WebSocket, takeover, or benchmark ran.
23. **done — Phase 8 exclusive user takeover and return.**
    - Authority: `TargetRuntimeSession` owns one ephemeral control owner and
      opaque lease identity. The deployment Viewer consumes that public
      projection but never infers ownership from iframe focus, socket state, or
      input traffic. Shell serializes and forwards typed commands only.
    - Positive command contract: `TakeOver` is admitted only against the exact
      durable PAUSED checkpoint while the Agent owns control and an interactive
      Viewer lease is available. It atomically consumes that checkpoint for
      recovery, creates one process-local user-control lease, disables ordinary
      Resume/Revise, and leaves the single Core loop stopped. `ReturnControl`
      requires the exact lease, disables Viewer input, captures fresh World,
      evaluates it, invalidates stale action/binding/confirmation material, and
      returns the existing Agent loop only from that owner-produced fresh
      snapshot. A terminal fresh evaluation ends the run instead of dispatching.
    - Provider boundary: create the same Steel browser lease with provider-side
      interactive capability available, but keep the delivered document
      read-only while the Agent owns control. Only a valid Runtime user-control
      projection may rewrite the current player to the same-origin native Steel
      input WebSocket proxy. Provider URL, token, session identity, and reusable
      key remain server-private. No custom mouse/keyboard protocol or second
      browser is introduced.
    - Failure contract: stale checkpoint, stale lease, unavailable Viewer,
      active/non-paused run, duplicate/reused identity, provider input loss, and
      fresh-World failure are typed. Return capture failure retains user
      ownership and cannot unblock Agent dispatch. Process restart revokes the
      ephemeral user lease; the consumed pre-takeover checkpoint cannot be
      replayed as if manual effects had not happened.
    - Verification: cover command/state properties, stale orderings, two-session
      isolation, crash/recovery fail-closed behavior, Viewer read-only/interactive
      rewrite and WebSocket auth, provider loss independence, return fresh-World
      lineage, stale pending-material invalidation, frontend projection, OpenAPI
      generation, existing Phase 0-7 gates, and one no-model
      live Steel takeover/return witness. Do not run a benchmark without separate
      authorization.
    - Runtime authority milestone implemented: one public `agent|user` owner and
      opaque process-local lease now gate the existing session handle. Takeover
      consumes the exact durable pause through the existing one-shot checkpoint
      outcome before exposing user ownership. Return clears the pause, captures
      and evaluates a fresh World through the existing Core loop owners, commits
      a non-budget-consuming `RequestObservation`, invalidates stale pending
      action material, and only then restarts the ActionPolicy. Failed currentness
      retains user ownership under a newly issued lease, permanently fencing
      the old input epoch, while Agent dispatch stays disabled; recovery of the
      consumed pre-takeover checkpoint fails closed. The focused Runtime/session
      slice passes 47 tests; Shell/Steel/UI wiring remains in progress.
    - Shell/Steel/UI milestone implemented: dedicated typed TakeOver and
      ReturnControl endpoints carry the exact checkpoint/lease identities; the
      adapter advertises takeover only when the same-session Viewer is available
      and preserves ReturnControl even after provider loss. Steel sessions are
      created input-capable, but the protected document remains read-only until
      Runtime projects user ownership. Interactive documents replace the private
      provider locator with one authenticated same-origin WebSocket; every input
      frame matches the lease captured at WebSocket connection against the
      current Runtime lease. Check-plus-forward and ReturnControl use the same
      session command lock; Runtime revokes the lease before fresh capture, and
      capture failure grants a new lease. Old sockets close with 4409. The UI exposes only capability-gated
      Take control / Return to Agent controls and reloads the same protected
      iframe mode. Evidence: 64 external backend/architecture tests, 14
      deployment tests, 135 Core/architecture tests, 12 frontend tests plus
      lint/typecheck/build, touched backend Pyright, Ruff, OpenAPI generation,
      and diff checks pass. Final authoritative documentation closure remains.
    - Live witness passed through the protected product API and native Steel
      input channel without a model or benchmark: the Runtime reached
      `waiting_user`, committed one durable pause, granted the exact user lease,
      and forwarded one click only after Steel's input-ready status. That input
      changed the same CDP-owned page. The strengthened witness blocked return
      capture, proved a second old-lease click had no page effect, and observed
      socket close 4409. `ReturnControl` then captured exactly one
      fresh World, evaluated the task `DONE` before a second policy call, and
      restored Agent ownership. The ActionPolicy call count remained one, the
      paused checkpoint was consumed by takeover, cleanup ran once, the exact
      provider lease was released, and no provider locator entered the public
      document. Authoritative architecture/benchmark/interaction-shell docs,
      standalone contracts, and the external README now agree with that bounded
      release profile.
24. **done — Phase 9 release-profile closure review.**
    - Begin only after Step 23 passes its owner/property/integration gates.
      Reconcile implementation, generated contracts, UI, documentation, and the
      declared profile evidence without treating Viewer/takeover evidence as a
      benchmark result.
    - Release result: Full Web control is closed for the declared single-process
      Steel profile. After the fencing repair, the whole provider-free repository
      reached 1842 passed and 19 skipped; only the absent historical live trace
      evidence-environment baseline failed. The stale fixed-document governance
      gate now declares the maintained set explicitly and passes.
      External backend/architecture passed 79 tests. Frontend passed 12 unit
      tests, ESLint, TypeScript, generated OpenAPI equality, production build,
      and one synthetic Demo Playwright E2E. External Pyright and Ruff passed;
      touched Core MyPy reports only the two unchanged nullable-task baseline
      findings in `core_loop.py`. The opt-in no-model Steel takeover witness
      passed and released its exact lease. No model call, compensation action,
      live benchmark, or benchmark artifact was produced by Phase 8/9.

25. **done — Phase 10 merged metrics and Bad-case causal projection.**
    - Restore the missing producer side of the Phase 10 contract on the current
      simplify-descended branch: immutable `run_attempt_id`, typed Runtime
      stall/oscillation measurements, provider-usage versus request-admission
      separation, bounded trajectory analysis, and Langfuse attempt lineage.
    - Add one benchmark-owned, closed Bad-case presentation projection derived
      only from `BenchmarkCaseResult`, `CaseFacts`, `RuntimeFailure`, terminal
      reason, and native evaluator outcome. It exposes a stable category,
      failure stage/origin/code, termination source, and a bounded plain-language
      summary without parsing display text or making Shell authoritative.
    - Supported presentation categories include structured model output failure,
      control stall/oscillation, harness timeout/interruption, provider failure,
      Runtime execution/acquisition/evaluation failure, native task failure,
      user/confirmation wait, cancellation, and bounded unknown typed failure.
      Monitor is a source only when Runtime-owned typed control termination proves
      it; invalid JSON is represented by the existing policy
      `invalid_response|schema_error` algebra rather than substring matching.
    - Project these persisted fields through the existing completed-run summary
      endpoint and existing Bad cases list. Preserve the current page, visual
      system, tabs, and evidence navigation; add only the hierarchy needed to
      read cause, owner, and code at a glance.
    - Add a cross-boundary acceptance gate using an actual runner-produced result
      shape, so Shell consumer tests cannot remain green against fabricated fields
      that the runner does not produce. Re-run affected Core, external backend,
      generated OpenAPI/client, frontend unit/lint/type/build, and diff gates.
    - Do not modify Runtime control decisions, benchmark truth, or introduce a
      Langfuse-to-Runtime loop. No live benchmark/provider call without separate
      authorization.
    - Verification: benchmark Runtime suite passed 335 tests; the affected
      observability/Core/Shell backend slice passed 156 tests with 3 skips;
      frontend passed 28 unit tests, ESLint, TypeScript, deterministic generated
      client equality, and production build; Ruff, Pyright, compileall, and diff
      checks passed. After advancing to the current Shell head, full
      provider-free root verification reached 2003 passed and 19 skipped with
      no failures; frontend verification reached 40 unit tests plus ESLint,
      TypeScript, deterministic generated contracts, and production build. No
      model/provider call or live benchmark was performed. A separately
      authorized provider-free Langfuse audit then exposed and repaired an IPC
      privacy-projection gap that had removed public `model_id`, `provider_id`,
      suite/profile, and attempt identity and had over-truncated standard message
      content. The held-out trace `e5c14028025e940fba1b351805764dd5`
      (`attempt:2a144e2a235849099253d9b90e8630fc`) was read back through the v2
      Observations and Scores APIs with the expected agent/generation hierarchy,
      readable messages, model `gpt-4o`, usage 100/20/120, calculated cost
      0.00045 USD, 125 ms generation duration, immutable identity tags,
      `structured_output_invalid`, and billing=false request-admission scores.
      Post-repair full verification remained 2003 passed and 19 skipped.

## Current-work produced files

- `.codex-plans/interaction-shell-implementation.md` — Phase 0-2 progress ledger.
- `.codex-plans/interaction-shell-phase0-baseline.md` — exact Phase 0 commands,
  outcomes, contract fingerprints, and corrected invocation notes.
- `src/affordance_runtime/app/public_session.py` — per-session Runtime factory,
  typed open stages, epoch/cursor/timestamp ownership, and partial-open cleanup.
- `external/interaction-shell/backend/interaction_shell/manager.py` — direct
  owner-event passthrough with no Shell event list or cursor override.
- `.codex-plans/interaction-shell-phase2-real-smoke.md` — real deployment,
  concurrent isolation, SSE/UI, and cleanup evidence.
- `external/interaction-shell/backend/interaction_shell/deployment_app.py` —
  thin local BrowserGym deployment composition.
- `src/affordance_runtime/surfaces/browsergym/task_evaluator.py` — reusable
  native task-state interpretation and fresh-World TaskEvaluator.
- `src/affordance_runtime/app/checkpoint.py` — Runtime-owned immutable
  checkpoint contract and atomic SQLite WAL store.
- `tests/unit/app/test_runtime_checkpoint.py` — safe-boundary ordering,
  transaction rollback, currentness recovery, idempotency, all supported
  restart boundaries, sent-receipt no-replay, corruption, and cancel witnesses.
- `external/interaction-shell/backend/interaction_shell/session_registry.py` —
  salted same-session restart authentication and original TTL, without Runtime
  state or reusable key persistence.
- `scripts/phase8_steel_takeover_witness.py` — opt-in no-model live Steel
  takeover/return witness; it emits only bounded status/boolean evidence and
  releases its one short-lived provider lease.

## Phase 2 final verification

- Affected Core/deployment/benchmark compatibility slice: 110 passed.
- External backend and architecture suite: 47 passed.
- Frontend: 3 unit tests passed; ESLint, TypeScript, generated OpenAPI, and
  production build passed.
- Synthetic Demo Playwright E2E: 1 passed.
- Ruff, touched-file Ruff format, Pyright, touched typed-owner MyPy, compileall,
  and `git diff --check`: passed.
- Default `interaction_shell.api:app`: `StartTask` still returned typed
  `unsupported`; advertised capabilities remained close-only.
- Full root provider-free suite: 1758 passed / 19 skipped, with two known
  non-Phase-2 failures retained honestly: documentation governance rejects the
  branch's pre-existing `docs/interaction-shell.md`, which the user explicitly
  required as the implementation-sequence source; one semantic-delivery replay
  requires a historical live trace absent from this worktree. No production
  workaround or benchmark run was added for either.
- Held-out real deployment: one Web session, one BrowserGym dispatch, two fresh
  observations, native `verified_success`, incremental SSE/UI `done`, explicit
  close, and clean lifespan shutdown. The independent real two-session witness
  kept the second browser alive after closing the first.
