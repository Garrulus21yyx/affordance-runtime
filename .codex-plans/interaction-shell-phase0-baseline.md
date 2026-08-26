# Interaction Shell Phase 0 baseline

Date: 2026-08-26

Worktree: `/home/yang/projects/affordance-runtime-interaction-shell`

Branch: `codex/external-interaction-shell`

Baseline parent: `5fe837f296a2b2e37344e80aaf3a2137aaf4840d`

Scope: verification and evidence only. No Phase 1/2 production code was changed
while establishing this record.

## Public contract freeze

The existing public boundary remains exactly these four contracts:

- `RuntimeSessionPort`
- `ShellCommand`
- `RuntimeSessionSnapshot`
- `ShellEvent`

Contract-owner fingerprints before Phase 1/2:

```text
99c79322ce68c070ef106789e7e051a5a3028bc6ea8c706358cc343d6be03adb  backend/interaction_shell/port.py
4a8a5ea67c24501890f689c6978fadce84d52d9067518e83e74f3437f9a95da6  backend/interaction_shell/contracts.py
```

The default `interaction_shell.api:app` was exercised without
`INTERACTION_SHELL_DEMO`. `StartTask` returned:

```text
Unsupported unsupported capability_not_advertised_by_runtime_port
advertised capabilities: [close_session]
```

The Demo remains explicitly non-authoritative and synthetic:

- `demo_port.py` identifies itself as a contract demo for local UI/E2E only;
- README startup labels it contract-only;
- `docs/contracts.md` labels the flow contract-only;
- `docs/interaction-shell.md` states that it performs no real browser or GUI action.

## Passing gates

Backend and public Runtime boundary:

```text
backend/.venv/bin/pytest tests/backend tests/architecture
35 passed

backend/.venv/bin/ruff check backend/interaction_shell tests
all checks passed

(from backend/) .venv/bin/pyright interaction_shell
0 errors, 0 warnings

PYTHONPATH=../../src:../../tests backend/.venv/bin/pytest \
  ../../tests/unit/app/test_public_session.py -q
2 passed

PYTHONPATH=src /home/yang/.venvs/affordance-browsergym-py312/bin/mypy \
  src/affordance_runtime/app/public_session.py
success

/home/yang/.venvs/affordance-browsergym-py312/bin/ruff check \
  src/affordance_runtime/app/public_session.py \
  src/affordance_runtime/app/__init__.py \
  src/affordance_runtime/agent/observability.py \
  tests/unit/app/test_public_session.py
all checks passed
```

Frontend and synthetic Demo:

```text
npm test
1 file / 2 tests passed

npm run lint
passed

npm run typecheck
passed

npm run build
Next.js production build passed; / and /diagnostics generated

npm run test:e2e
1 Chromium Demo E2E passed
```

Tool versions observed:

```text
backend Python 3.13.13
Node v25.8.2
npm 11.11.1
Next.js 16.3.3
```

`git diff --check` passed.

## Non-product invocation corrections

Two initial verification invocations were invalid and were corrected without a
code change:

- Pyright was first launched from the parent directory, so it did not load the
  backend package configuration and reported two false missing imports. Running
  it from `backend/` passed with zero findings.
- The main worktree `.venv` lacked pytest/mypy, and the BrowserGym environment
  lacked `pytest-asyncio`. Core async tests were therefore run with the external
  backend test environment plus the target worktree `PYTHONPATH`; both passed.

These environment/invocation failures are not counted as product test failures.

## Phase 0 conclusion

The contract/demo baseline is green and remains distinct from real deployment.
This record does not claim that the real execution profile is available; that
claim requires Phase 1 session isolation and the Phase 2 real deployment smoke.
