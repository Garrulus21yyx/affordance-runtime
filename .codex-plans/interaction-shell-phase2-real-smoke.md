# Interaction Shell Phase 2 real-deployment smoke

Date: 2026-08-26

Worktree: `/home/yang/projects/affordance-runtime-interaction-shell`

Branch: `codex/external-interaction-shell`

Scope: the local BrowserGym/Playwright real-execution profile. This was a
deployment smoke, not a benchmark run.

## Profile

- Entrypoint: `interaction_shell.deployment_app:app`
- Runtime task: `browsergym/miniwob.click-test`, seed 7
- BrowserGym: 0.14.3
- Playwright: 1.44.0
- Model profile used for the successful runs: existing `deepseek` project
  configuration, with profile fallback disabled
- MiniWoB URL: `http://127.0.0.1:18888/miniwob/`
- Viewer: typed `viewer_provider_not_configured`
- Durable resume: typed `checkpoint_store_not_configured`

No credential values were printed or written to this record.

## Provider-free gates before the live smoke

```text
PYTHONPATH=src:tests:external/interaction-shell/backend \
  /home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest \
  external/interaction-shell/tests/backend \
  external/interaction-shell/tests/architecture \
  tests/unit/app/test_public_session.py \
  tests/unit/surfaces/browsergym/test_browsergym_task_evaluator.py -q

50 passed
```

Ruff, MyPy, and Pyright passed for the touched deployment and evaluator slice.
The final full-gate result is recorded in the implementation plan.

## Real execution evidence

The first Zhipu attempt acquired a real World and exposed the current
`Click Me!` action candidate, but both ActionPolicy requests received HTTP 429.
It terminated as typed provider unavailable with no dispatch. That run is an
environment/provider failure witness and is not counted as execution success.

The clean run using the existing DeepSeek profile completed this owner sequence:

```text
POST /sessions (201)
→ StartTask accepted / running
→ fresh BrowserGym World observation 1
→ GoalCompiler not_required
→ ActionPolicy select_action
→ Binder admits activate(E1)
→ low-risk dispatch
→ BrowserGym receipt dispatch_status=sent, effectful_dispatch_count=1
→ fresh BrowserGym World observation 2
→ native evaluator verified_success
→ STEP_FINISHED + RUN_FINISHED
→ snapshot done / completion verified_success
```

Trace facts: one step, one execution, two observations; the before and after
observation IDs differ; the receipt backend is `browsergym`; and terminal proof
references the fresh observation's `browsergym-task-state` artifact.

## Concurrent session isolation witness

A real two-environment smoke initially reproduced a shared BrowserGym defect:
BrowserGym 0.14.3 stores its synchronous Playwright driver at process scope.
The second per-session owner thread therefore failed with `greenlet.error:
cannot switch to a different thread`, and closing either owner could stop the
other driver's global instance.

The BrowserGym integration owner now replaces all three cached driver access
sites (`core`, `core.env`, and `core.chat`) with owner-thread-local state before
reset. The held-out real witness then reported:

```text
distinct_surfaces True
distinct_backends True
distinct_owner_threads True
second_after_first_close alive
cleanup_complete True
```

## SSE and UI witness

The first real UI run showed that the direct backend SSE stream contained all
three events while the Next.js rewrite exposed `content-encoding: gzip` and
buffered the short stream. The SSE owner now declares `no-cache, no-transform`,
identity encoding, and buffering disabled. Through the same Next.js route, the
browser then observed those headers and received incremental Runtime events.

Playwright CLI drove the operator Shell against the real deployment. One run
proved the asynchronous interrupt path by moving from `running` to a
provider-produced `waiting_user` through SSE, accepting an answer through the
same opaque Runtime session, and then reaching verified success through SSE.

After the StrictMode acquisition repair, a fresh held-out UI run:

1. opened one session and showed connection `live`;
2. admitted `Click the button.` without treating admission as success;
3. moved through real BrowserGym dispatch to `done` through SSE;
4. rendered `verified_success` and `Completed an interaction`;
5. retained typed Viewer unavailable throughout;
6. accepted explicit `CloseSession` at task revision 1; and
7. shut down the application with cleanup complete.

React StrictMode had also replayed the session-opening effect and created two
real browser sessions during development. The hook now retains one in-flight
session promise across that replay; its component test asserts exactly one
backend create call.

## Cleanup and failure evidence

- terminal snapshot/event reads trigger idempotent handle cleanup;
- explicit close after terminal remains accepted;
- closing one real browser owner leaves the other alive;
- a composition failure after environment creation closes that environment;
- cancellation during synchronous BrowserGym open waits for the late result and
  closes it instead of losing the newly created browser;
- application lifespan shutdown calls idempotent `RunSessionManager.close_all`;
- environment-open errors remain typed HTTP 503 responses and log their private
  server-side exception without exposing it to the client.

## Conclusion

The local real-execution profile is runnable through API and UI. This evidence
does not claim Viewer, checkpoint, pause/resume, revision, takeover, release
fault injection, or benchmark completion.
