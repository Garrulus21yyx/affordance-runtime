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
| M8.1 clean-checkout container reproduction | completed | clean `40fd93b`; 63 stable runs agree; versioned evidence summary |
| M8.2A task intake and GeneralistLMPlanner | completed | typed compiler/revision, semantic contracts, Mistral SaaS gates, common surface planner, and official BrowserGym smoke at `7edaa97`/`508486b` |
| M8.2 BrowserGym full-path adapter and expanded MiniWoB ladder | in progress | full-path adapter done; external-planner PR/nightly/release suites remain |
| M8.2 public suites in planned order | pending | ScreenSpot, WorkArena L1, WebArena-Verified, WASP gates |
| M8.3 incident/signature/loop detection | completed | repeated/no-progress/A-B/stale/verifier/fallback/duplicate-effect detection at `07e406f` |
| M8.3 executable recovery artifacts | completed | quarantined policy, four fresh replays, acceptance persistence, rollback and uncertainty safety proof |
| Final documentation and CI audit | pending | plans/status/evidence/README aligned; remote checks green |

## Change Record

| Date | Step | Result | Files |
| --- | --- | --- | --- |
| 2026-07-20 | Forward-plan initialization | M8.1 selected first per authoritative ordering | this file |
| 2026-07-20 | M8.1 implementation | Default non-root profile and optional real WoT conformance passed from the working tree | Docker/Compose, conformance runner, tests, CI |
| 2026-07-20 | M8.1 clean evidence | Host/container agreement and all three conformance surfaces passed at clean `40fd93b` | `evidence/m8.1-40fd93b.md` |
| 2026-07-20 | M8.2 bridge slice | Added isolated BrowserGym 0.14.3 adapter, typed action whitelist, external-policy boundary, profile coverage reporting, and real one-task bridge smoke | BrowserGym benchmark module, CLI, tests, CI |
| 2026-07-20 | M8.3 implementation | Added causal incidents, normalized signatures, online loop detection, recovery metrics, typed executable policy/skill payloads, and explicit uncertain-effect inspection | recovery, coordinator, evolution, benchmark metrics, tests |
| 2026-07-20 | M8.3 clean evidence | Clean `07e406f`: 69 tests, static checks, build, 63/63 local runs, four mandatory fresh replays, persisted acceptance, and rollback | `evidence/m8.3-07e406f.md` |
| 2026-07-21 | M8.2A evidence | Controlled Mistral compiler suite, local verified read/write/approval runs, cross-surface common planner tests, and official BrowserGym GeneralistLMPlanner smoke | `evidence/m8.2a-7edaa97.md` |
