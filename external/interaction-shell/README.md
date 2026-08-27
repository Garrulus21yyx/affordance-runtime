# External Interaction Shell

Standalone Web interaction and evaluation shell for the Affordance Runtime.
Everything here is independently packaged and imports no Core loop, Binder,
Executor, Monitor, private World, or internal `RunState`. Its production adapter
imports only the versioned `affordance_runtime.app.public_session` boundary.

## Layout

```text
external/interaction-shell/
├── backend/       FastAPI, Pydantic contracts, session manager, port boundary
├── frontend/      Next.js, CopilotKit, Radix primitives, Playwright
├── diagnostics/   completed-run resolver notes
├── langfuse/      reproducible analysis-view configuration
├── tests/         backend contracts/properties and architecture guards
├── docs/          standalone public contract documentation
└── README.md
```

## Start

Create the isolated backend environment:

```bash
cd external/interaction-shell/backend
python -m venv .venv
.venv/bin/pip install -e '.[test,model]'
```

Production-safe backend without a configured Runtime/environment factory
(commands are typed `Unsupported`):

```bash
.venv/bin/uvicorn interaction_shell.api:app --host 127.0.0.1 --port 8100
```

For the synthetic, contract-only UI Demo and E2E flow:

```bash
INTERACTION_SHELL_DEMO=true .venv/bin/uvicorn interaction_shell.api:app --host 127.0.0.1 --port 8100
```

For a real session, the deployment composition supplies a per-session
Runtime, ActionPolicy/history, BrowserGym environment, browser context,
`RuntimeEnvironmentLease`, and opaque public handle. This is deliberately
explicit: browser/provider credentials and the product's stable task boundary
stay with the deployment, while the returned handle keeps `RunState` private.
The Runtime/public port owns one event epoch and cursor; the Shell manager only
forwards `events(after)` and never keeps a second event log.
The configured port supports start, AskUser answer, confirmation approve/reject,
cooperative cancel, durable pause/resume, bounded task revision, one retained
known reversible/compensatable effect through the ordinary compensation pipeline,
exclusive Steel user takeover/return, and close. Multiple retained effects,
uncertain/irreversible effects, and new-task replacement remain typed fail-closed
or unavailable.

For revision, the manager attaches an immutable language-only snapshot of at
most six turns and 16 KiB to the single Runtime command. Runtime adds its own
current goal and pending question/confirmation before invoking the sole
TaskRevisionCompiler. The snapshot participates in Runtime command identity but
never enters ActionPolicy history or grants GUI-effect authority. The existing
Shell recovery SQLite row stores only the last six turns and last 64 immutable
revision contexts alongside its salted verifier and TTL. A new revision context
is persisted before the Runtime call and restored before the opaque Runtime
handle, so an exact lost-response retry survives Shell restart. This bounded
projection stores no Runtime outcome, TaskGoal, GUI state, receipt, or model
history, and is deleted with session revoke/expiry.

Install the deployment profile alongside the Runtime worktree, then start its
dedicated app (the example interpreter is the repository's pinned BrowserGym
environment):

```bash
cd /path/to/affordance-runtime
DEPLOYMENT_PYTHON=/path/to/browsergym-python
uv pip install --python "$DEPLOYMENT_PYTHON" -e . \
  -e 'external/interaction-shell/backend[deployment]'

set -a
source .env
set +a
export PYTHONPATH="$PWD/src:$PWD/external/interaction-shell/backend"
export MINIWOB_URL=http://127.0.0.1:18888/miniwob/
export INTERACTION_SHELL_BROWSERGYM_TASK_ID=browsergym/miniwob.click-test
export INTERACTION_SHELL_CHECKPOINT_DB="$PWD/.runtime/interaction-shell-checkpoints.sqlite3"
"$DEPLOYMENT_PYTHON" -m uvicorn interaction_shell.deployment_app:app \
  --host 127.0.0.1 --port 8200
```

`/health` reports `runtime_execution`, `viewer`, `durable_pause`, and
`durable_resume` independently. The safe default real profile uses local
BrowserGym/Playwright and keeps Viewer typed unavailable. Runtime-private SQLite
WAL checkpoints make cooperative pause durable and provide the reconnectable-
lease restart/resume contract; the local profile still cannot reconnect its
Playwright context after process restart.

For the protected Steel profile, keep the provider key in the server
environment and point BrowserGym at a task host reachable from the cloud browser
(a loopback/private URL is rejected):

```bash
export INTERACTION_SHELL_BROWSER_PROVIDER=steel
export Viewer_API_KEY='<server-only Steel key>'  # STEEL_API_KEY is also accepted
export MINIWOB_URL=https://tasks.example.test/miniwob/
export INTERACTION_SHELL_SECURE_COOKIES=true      # when served over HTTPS
```

BrowserGym executes through Playwright CDP in the exact Steel session whose Live
View is exposed at the secret-free `/viewer/{session_id}` path. The backend uses
HttpOnly same-session auth, removes provider locators and reusable credentials
from Steel's document, and proxies its native WebRTC ICE/WHEP calls. The view is
read-only while Runtime projects Agent ownership. `TakeOver` consumes the exact
durable paused checkpoint and grants one process-local user lease; only then does
the same protected document use an authenticated same-origin proxy for Steel's
native input WebSocket. `ReturnControl` requires that exact lease, disables later
input by revoking it before capture, captures/evaluates fresh World, invalidates
stale Agent material, and only then continues the existing loop. Every input
frame is checked against both current user ownership and the exact lease captured
when its WebSocket connected, under the same per-session lock as ReturnControl.
Capture failure grants a new user lease, so an old socket cannot revive. Viewer loss remains fail-open for Runtime truth;
no screenshot polling, custom media/input protocol, second browser, or second
executor is added.

Live verification (2026-08-27) is complete. The initial WHEP 400 in both the
native page and proxy came from Playwright's bundled Linux Chromium lacking
H.264, which Steel's headful stream requires. An H.264-capable native control
and a separate authenticated same-origin product-path probe both completed WHEP
with 201 and rendered 1280x720 video at `readyState=4`. The product-path probe
also verified unauthorized 401, no page errors, no provider locator in delivered
HTML, and exact provider lease release. Runtime execution remains independent
of Viewer availability.

The no-model takeover witness additionally reached `waiting_user`, committed a
durable pause, granted user ownership, changed the same CDP-owned page through
the protected native input proxy, and returned control. Runtime captured one
fresh World and finished before a second ActionPolicy call. The strengthened
witness blocked that capture, sent another click on the revoked socket, observed
no second page effect, and then observed WebSocket close 4409. The exact checkpoint
was consumed, cleanup ran once, and the exact Steel lease was released. This is
a deployment/control witness, not a benchmark result.

Benchmark runs that load the repository `.env` currently persist Runtime JSONL
under their run evidence directory and publish the asynchronous Langfuse
projection. Native/custom model-call OpenTelemetry instrumentation is present,
but the standalone Shell deployment still lacks a fully verified recording
`TracerProvider + exporter`, and its Langfuse generation mapping still needs
standard model/cost/latency verification. These are fail-open analysis gaps,
not Runtime or benchmark-result gaps.

Start the frontend in another shell:

```bash
cd external/interaction-shell/frontend
npm install
SHELL_BACKEND_URL=http://127.0.0.1:8200 npm run dev -- --port 3100
```

Open `http://127.0.0.1:3100` for the operator shell. It contains only
conversation/HITL, the live surface, Runtime-offered takeover/return controls,
and concise Runtime-projected progress hydrated from SSE. The surface is
read-only unless Runtime projects the current user-control lease. The UI does not
load or render token, latency, evaluation, or attribution data.

`http://127.0.0.1:3100/diagnostics` is a read-only completed-run index. It has no
POST ingestion, process-local diagnosis store, transcript reader, chart engine,
or evaluator. Configure exact run directories and the authenticated Langfuse UI:

```bash
export INTERACTION_SHELL_EVIDENCE_RUNS=/absolute/evidence/run-a:/absolute/evidence/run-b
export LANGFUSE_BASE_URL=https://langfuse.example.test
```

The route shows only benchmark status, turns, provider input/output usage,
recovery/stall counts, `suspected_detour | not_assessed`, and independent links.
`INTERACTION_SHELL_LOCAL_EVIDENCE_ENABLED=true` plus a nonblank
`INTERACTION_SHELL_EVIDENCE_ACCESS_KEY` enables the opaque fixed-result route.
The engineering reverse proxy must inject the matching `X-Engineering-Key`;
unauthorized and unknown locators both return 404.
It never accepts or exposes filesystem paths. Full token, cost, latency, trace,
dashboard, and annotation analysis stays in Langfuse. An ordinary product task
without `BenchmarkCaseResult` explicitly displays benchmark result
`not_applicable`. See `docs/interaction-shell.md`, Section 12 and Phase 10.

## Viewer and optional services

The local/default production profile remains typed Surface unavailable. The
explicit Steel profile produces an ephemeral provider-neutral
`SurfaceAvailability`; `CoreRuntimeSessionPort` alone projects the protected
same-origin `SurfaceView`. The contract rejects provider URLs and query secrets.
Interactive projection is valid only while Runtime owns an exact user-control
lease; all other projections remain read-only. Browserbase
remains an unimplemented alternative. Langfuse is the fail-open primary
engineering-analysis surface when configured; benchmark evidence remains the
evaluation authority and durable local fallback.

## Verification

```bash
backend/.venv/bin/pytest tests/backend tests/architecture
cd frontend
npm run check:generated
npm test
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

The opt-in no-model Steel control witness runs only after loading a server-side
Steel key and does not launch a benchmark:

```bash
cd /path/to/affordance-runtime
set -a && source .env && set +a
PYTHONPATH=src:external/interaction-shell/backend \
  /home/yang/.venvs/affordance-browsergym-py312/bin/python \
  scripts/phase8_steel_takeover_witness.py
```

No live benchmark is part of this package's verification.
