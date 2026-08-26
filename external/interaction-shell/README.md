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
and close. Cancel, revise, new task, and takeover remain typed unavailable.

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
`durable_resume` independently. The first real profile uses local
BrowserGym/Playwright. Runtime-private SQLite WAL checkpoints make cooperative
pause durable and provide the reconnectable-lease restart/resume contract.
Viewer and the local BrowserGym profile's process-restart resume intentionally
remain typed unavailable until an environment reconnect contract exists.

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

The current production default is typed `viewer_not_configured`. A deployment
adapter may supply a protected same-origin Steel or Browserbase
path through `ViewerStateProjector`; the contract rejects provider URLs,
query secrets, writable views, and non-`/viewer/` routes. This shell never
creates screenshot polling, video encoding, or remote
mouse/keyboard transport. Langfuse is an optional fail-open diagnosis sink.

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
