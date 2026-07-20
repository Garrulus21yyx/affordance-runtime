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
| M8.2 BrowserGym full-path adapter and expanded MiniWoB ladder | in progress | Generalist PR matrix now runs through the full path (15/18 official success); nightly/release suites and public ladder remain |
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
| 2026-07-21 | M8.2B PR checkpoint | GeneralistLMPlanner ran the 18-episode official MiniWoB PR matrix with complete episode coverage; slider adjustment is an explicit remaining semantic gap | `evidence/m8.2b-pr-generalist-0a7ff46.md` |
| 2026-07-21 | ScreenSpot harness | Added strict offline ScreenSpot point-in-box scoring with complete-coverage diagnostics; no official assets or score are claimed | `benchmarks/screenspot.py`, `benchmark-plan.md` |
| 2026-07-21 | WorkArena preflight | Added credential-safe isolated deployment gate for official L1 registration and instance-source readiness; no oracle or WorkArena score is claimed | `benchmarks/workarena.py`, `benchmark-plan.md` |
| 2026-07-21 | Native select checkpoint | Bound native option activations to their owning select and increased the official Generalist PR result to 15/18; slider adjustment remains an explicit gap | `evidence/m8.2b-pr-native-select-0b2c542.md` |
| 2026-07-21 | WASP security baseline | Marked page-derived planner context as untrusted, with authority remaining in TaskSpec/capability/approval gates; no WASP score is claimed | `generalist_planner.py`, `benchmark-plan.md` |
| 2026-07-21 | WebArena-Verified manifest | Added a digest-bound, primary-site-stratified 30--50 task selection manifest; official evaluator traces remain required | `benchmarks/webarena_verified.py`, `benchmark-plan.md` |
| 2026-07-21 | WebArena-Verified dataset check | Validated the 30-task manifest against all 812 official tasks and six-site balance; no environment run or score is claimed | `evidence/m8.2b-webarena-manifest-9cb727c.md` |
| 2026-07-21 | WebArena-Verified evaluator bridge | Added shell-free delegation to upstream deterministic `eval-tasks` and fail-closed result coverage; real agent traces remain required | `benchmarks/webarena_verified.py` |
| 2026-07-21 | WASP configuration check | Selected a digest-bound 12-case official security subset without copying malicious instructions; upstream isolated execution remains required | `evidence/m8.2b-wasp-manifest.md` |
| 2026-07-21 | Generalist v6 regression | Re-ran the official PR matrix after marking page-derived context untrusted; result remained 15/18 with slider gap explicit | `evidence/m8.2b-pr-generalist-v6.md` |
| 2026-07-21 | Resumable matrix check | Added atomic per-episode checkpointing and verified a zero-new/18-reused PR resume, preserving official diagnostics | `evidence/m8.2b-browsergym-checkpoint-5837984.md` |
