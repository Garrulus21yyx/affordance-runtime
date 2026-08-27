# External Interaction Shell

Standalone Web interaction and evaluation shell for the Affordance Runtime.
Everything here is independently packaged and imports no Core loop, Binder,
Executor, Monitor, private World, or internal `RunState`. Its production adapter
imports only the versioned `affordance_runtime.app.public_session` boundary.

## Layout

```text
external/interaction-shell/
├── backend/       FastAPI, Pydantic contracts, session manager, port boundary
├── frontend/      Next.js, CopilotKit, Radix primitives, Recharts, Playwright
├── diagnostics/   exported-artifact diagnosis notes
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
(capabilities are typed `Unsupported`):

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
and close. Multiple retained effects, uncertain/irreversible effects, new-task
replacement, and takeover remain typed fail-closed or unavailable.

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

For the protected read-only Steel profile, keep the provider key in the server
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
from Steel's document, and proxies only its read-only WebRTC ICE/WHEP calls.
Viewer loss remains fail-open for Runtime truth; no screenshot polling, custom
video path, input WebSocket, second browser, or takeover is added.

Live verification (2026-08-27) is complete. The initial WHEP 400 in both the
native page and proxy came from Playwright's bundled Linux Chromium lacking
H.264, which Steel's headful stream requires. An H.264-capable native control
and a separate authenticated same-origin product-path probe both completed WHEP
with 201 and rendered 1280x720 video at `readyState=4`. The product-path probe
also verified unauthorized 401, no page errors, no provider locator in delivered
HTML, and exact provider lease release. Runtime execution remains independent
of Viewer availability.
Model-call OpenTelemetry instrumentation is present, but this deployment does
not yet configure a recording `TracerProvider` or exporter; existing Runtime
JSONL/Langfuse projection remains the deployed diagnostic path.

Start the frontend in another shell:

```bash
cd external/interaction-shell/frontend
npm install
SHELL_BACKEND_URL=http://127.0.0.1:8200 npm run dev -- --port 3100
```

Open `http://127.0.0.1:3100` for the operator shell. It contains only
conversation/HITL, the read-only browser surface, and concise Runtime-projected
progress hydrated from SSE. It does not load or render token, latency,
evaluation, or attribution data.

Open `http://127.0.0.1:3100/diagnostics` for the separate engineering bad-case
workbench. Token/cost, latency, trajectory metrics, failure attribution, and
evidence references live only on that surface.

## Viewer and optional services

The local/default production profile remains typed Viewer unavailable. The
explicit Steel profile supplies a protected same-origin path through
`ViewerStateProjector`; the contract rejects provider URLs, query secrets,
writable views, and non-`/viewer/` routes. Browserbase remains an unimplemented
alternative. Langfuse is an optional fail-open diagnosis sink.

## Verification

```bash
backend/.venv/bin/pytest tests/backend tests/architecture
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

No live benchmark is part of this package's verification.
