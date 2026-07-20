# M8 Forward Execution Log

This file tracks implementation of the authoritative M8.1-M8.3 increments in
`current-implementation-plan.md`. The milestone status ledger remains
`implementation-status.md`.

## Constraints

- Keep the runtime a modular monolith; do not add queues, worker pools, brokers,
  multi-tenancy, or a fictional fixture database.
- Preserve the full Coordinator, policy, verification, trace, evaluator, and
  independent-oracle path for scored and cross-surface work.
- Keep official benchmark scores separate from injected harness diagnostics.
- Commit reproducible evidence summaries, not mutable runtime output.

## Execution Steps

| Step | Status | Evidence / files |
| --- | --- | --- |
| Audit current Docker, fixture, cross-surface, benchmark, recovery, and CI state | completed | repository, predecessor fixture, host Docker, and current gates inspected |
| M8.1 pinned non-root container profile | completed | digest-pinned Dockerfile; fixture health/reset; 58 tests, Ruff, mypy, build; 63-run benchmark |
| M8.1 Coordinator-level DOM/visual/WoT conformance | completed | real node-wot 0.9.2 shared oracle; three Coordinator traces; visual pixel detection and four screenshots |
| M8.1 clean-checkout container reproduction | pending | host/container agreement and evidence summary |
| M8.2 BrowserGym full-path adapter and expanded MiniWoB ladder | pending | PR/nightly/release suites, coverage and unsupported-action reports |
| M8.2 public suites in planned order | pending | ScreenSpot, WorkArena L1, WebArena-Verified, WASP gates |
| M8.3 incident/signature/loop detection | pending | repeated/no-progress/A-B cascade evidence |
| M8.3 executable recovery artifacts | pending | fresh replay, persistence, rollback, safety proof |
| Final documentation and CI audit | pending | plans/status/evidence/README aligned; remote checks green |

## Change Record

| Date | Step | Result | Files |
| --- | --- | --- | --- |
| 2026-07-20 | Forward-plan initialization | M8.1 selected first per authoritative ordering | this file |
| 2026-07-20 | M8.1 implementation | Default non-root profile and optional real WoT conformance passed from the working tree | Docker/Compose, conformance runner, tests, CI |
