# External Interaction Shell implementation plan

Status: complete through Phase 2 (Phase 3+ not started)
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
13. **done — Phase 2: add the real deployment entrypoint.**
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

## Phase 2 final verification

- Affected Core/deployment/benchmark compatibility slice: 107 passed.
- External backend and architecture suite: 44 passed.
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
