# Implementation Status and Forward Gates

This file is the durable execution ledger for the milestones defined in
`project-plan.md`. Update it in the same change that adds implementation or
verification evidence. A milestone is complete only when every exit criterion
has reproducible evidence.

Status values:

- `pending`: not started or no implementation evidence
- `in_progress`: implementation exists but exit evidence is incomplete
- `done`: exit criteria are covered by code, tests, and reproducible commands
- `blocked`: external input or state is required

## Summary

| Milestone | Status | Current evidence | Remaining gate |
| --- | --- | --- | --- |
| M0 Design Freeze | done | contracts, state machine, approvals, trace schema, scenarios, gates | none |
| M1 Web Gold Path | done | real Chromium pricing, pre/post observation, verification, artifacts, CLI, baseline | none |
| M2 Local Reliability | done | three scenarios, distinct deterministic perturbations, approval/download oracle, 3 x 7 matrix | none |
| M3 Assisted Evolution | done | classifier, typed executable proposal, fresh replay, direction-aware decision, persistence, rollback | none |
| M4 Integration Boundary | done | in-process task service, bounded adapter, external JSON-RPC, real LangGraph parent | none |
| M5 Evidence Freeze | done | CI, package build, environment manifest, versioned reports, clean-clone reproduction at `4528f25` | none |
| M6 Executable Evolution | done | SHA-bound verifier payload, fresh candidate, six new Chromium replays, persisted acceptance and rollback proof at `4cccc96` | none |
| M7 External Integration | done | separate runtime process plus real LangGraph 1.2.9 parent completes pricing and approval export at `9a9796e` | none |
| M8 Generalization Eval | done | three distinct training layouts, six held-out runs, five visual runs, and 18 pinned official MiniWoB++ episodes at `e463e16` | none |
| M8.1 Container Reproducibility | done | digest-pinned non-root profile, exact 63-run host/container agreement, and real DOM/visual/WoT conformance at `40fd93b` | none |
| M8.2A Task Intake and Generalist Planner | done | typed intake/revision, semantic proposal boundary, Mistral controlled compiler + local SaaS gates, common cross-surface planner tests, and official BrowserGym smoke at `7edaa97`/`508486b` | none; M8.2B remains separate |
| M8.2B Public Benchmark Expansion | in_progress | Generalist BrowserGym v8 PR matrix: 18/18 coverage, 15/18 official success with no 429/timeout; `press_key` executed on the remaining form tasks, whose behavioral gap remains explicit. ScreenSpot, WorkArena, WebArena-Verified, and WASP preparation gates added; committed Web/BrowserGym constraints and split BrowserGym bridge improve evidence reproducibility | documentation consolidation, official ScreenSpot assets/predictions, authorized WorkArena instance, provisioned WebArena environments/logs, current-planner/nightly/release matrices, slider behavioral coverage, and WASP end-to-end run |
| M8.3 Recovery-Cascade Evolution | done | online incident/loop detection plus quarantined, replayed, accepted, persisted, and rolled-back recovery policy at `07e406f` | none |
| M8.4 Adaptive Shallow Task Planning | in_progress | immutable TaskPlan/SubgoalSpec, PlanProgress, deterministic validator, flat RuleTaskPlanner/router, LLM candidate plus one repair, and Coordinator serial verifier-backed subgoal progress/early-finish rejection are implemented | implement task-level replanning traces, controlled long-horizon scenario, and flat/always/adaptive ablation |
| M9 Durable Single Run | pending | in-memory state only | conditional on a measured restart/waiting failure |

## M0: Design Freeze and Status Alignment

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Authoritative current plan and two-horizon rule | done | `current-implementation-plan.md`, `complete-architecture-blueprint.md` |
| Three Web/SaaS scenario specifications with oracles | done | `scenarios/pricing-extraction.md`, `scenarios/settings-update.md`, `scenarios/approval-gated-report-export.md` |
| System invariants and recovery matrix | done | `design-freeze.md` |
| One task-level state machine in code | done | `coordinator.py`, transition validation in `state_kernel.py`, coordinator tests |
| Action Contract schema v1 with snapshot and target validity | done | canonical hash and snapshot/page/target/TTL fields plus preflight tests |
| Approval binding contract | done | single-use token binds run/hash/revision/capability/approver/expiry |
| Minimum trace event schema | done | state, versions, causal parents, policy/preflight, receipts, verification, and artifact refs |
| Declarative evolution artifact schema | done | version metadata and direction-aware regression rules |
| README/status claims match implementation | done | current milestone claims are separated from deferred production-blueprint features |

## M1: Web Gold Path

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Local pricing fixture with canonical oracle | done | `/pricing`, `/api/pricing`, reset endpoint, and oracle test |
| Playwright-compatible pre/post observer | done | plan, immediate-preflight, and post-action observations |
| DOM affordance builder and executor | done | semantic page revision, target fingerprint, leases, and DOM executor |
| Scripted planner through `PlannerPort` | done | deterministic `PricingPlanner` |
| RunCoordinator and multi-step RunState | done | serial coordinator, transitions, budgets, evidence, and recovery boundaries |
| Post-action structural verifier | done | DOM verifier runs against post-action HTML |
| Artifact store and complete run layout | done | run JSON, JSONL events, observations, screenshots, receipts, verification reports, hashes |
| One-command CLI gold path | done | `affordance-runtime run --target ... --artifacts ...` |
| Direct Playwright baseline | done | `affordance-runtime baseline --target ...` |
| Repeated pricing run and stale perturbation evidence | done | three consecutive Chromium runs passed; deterministic drift test blocks stale execution |

## M2: Runtime Reliability and Cross-Surface Proof

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Settings and export fixtures | done | real settings persistence/API oracle and approved report download/file-hash/audit oracle |
| Drift/modal/delay perturbation controls | done | target replacement, selector drift, async enablement, blocking modal, transient API error, and delayed download are deterministic fixture controls |
| Scoped capabilities and approval gate | done | explicit capability plus single-use bound approval; unapproved Chromium export stops in `WAITING_APPROVAL` |
| Bounded recovery integrated into coordinator | done | execution/preflight/verification failures enter the deterministic recovery policy within budgets |
| Shared DOM/SoM/WoT contract execution path | done | all three surfaces pass the same coordinator, contract, trace, and verifier path in tests |
| Benchmark runner with independent oracles | done | executable local runner uses pricing JSON, settings API, export audit/file hash, and perturbation labels |
| JSON, Markdown, and CSV reports | done | `BenchmarkReportWriter` and format tests |
| Direct/primitive/full baselines and required ablations | done | fixed-seed 3 scenarios × 7 variants execute through the CLI and emit reports |
| Zero unsafe side effects under the suite | done | Full Runtime report: success 1.0, constraint violations 0.0, unsafe side effects 0.0; disabling capability gate produces the expected unsafe export signal |

## M3: Assisted Harness Evolution

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Failure taxonomy classifier | done | typed seven-class classifier maps benchmark/trace evidence and is tested |
| Typed declarative proposals | done | typed artifact types, proposal schema, applicability, source trace, negative examples, and validation plan |
| Quarantine/version/rollback registry | done | atomic JSON registry store, accepted-only loading, version history, runtime unload, persisted rollback proof |
| Direction-aware regression gate | done | higher/lower-is-better thresholds, allowed regression, missing-metric quarantine tests |
| Replay-category accounting | done | decision requires original, family, global-smoke, and safety-smoke evidence |
| Executable artifact applied before fresh replay | done | SHA-bound verifier payload is loaded into a fresh no-verifier candidate before six real Chromium runs |
| One real failure before/after report | done | no-verifier settings false accept is fixed; original/family/global/safety replay passes with no unsafe regression |

## M4: Optional Integrations

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Stable task-level API | done | `TaskRuntimeService` supports submit, execute, status, scoped approval, cancel, result, evidence, and trace |
| Parent agent cannot bypass runtime with public primitive actions | done | `TaskToolAdapter` exports only eight task-level operations; click/type/observe are absent |
| Local working integration | done | `LocalScenarioTaskRunner` connects the task API to real Chromium scenarios |
| Real external parent-agent integration | done | compiled LangGraph calls separate runtime process over `affordance-task-rpc/1.0`; pricing and gated export pass |
| Evidence and trace retrieval | done | adapter returns artifact paths and parsed JSONL events |
| Optional PiP decision gate | done | deferred: no measured observer/takeover need justifies another UI surface |

## M5-M9 Forward Gates

| Milestone | Required evidence |
| --- | --- |
| M5 | done: CI, package build, environment identity, clean-checkout command, and versioned benchmark/evolution summaries at `4528f25` |
| M6 | done: executable payload, fresh candidate runtime, mandatory replay, persisted decision, and rollback at `4cccc96` |
| M7 | done: real LangGraph submission/approval/result/evidence/trace over an external protocol with no primitive GUI bypass at `9a9796e` |
| M8 | done: distinct seeds, unseen layouts, repeated pinned MiniWoB++ subset, and real visual grounding at `e463e16` |
| M9 | only after a failing restart/waiting case; simple durable state/events and uncertain-effect inspection |

### M8 Generalization Evidence

The clean `e463e16` checkout upgraded the fixture to distinct seeded layouts
and passed all M8 gates:

```text
training matrix = 63/63 accepted, 3 distinct layout fingerprints
held-out local scenarios = 6/6
visual screenshot grounding = 5/5, 5 distinct boxes, no DOM coordinates
official MiniWoB++ = 18/18 raw-reward success across 6 task families
```

The official subset is pinned to Farama commit
`eb59fed60fabe8951350275ba8650633b740013b` and owns episode reset, instruction
extraction, termination/reward collection, runtime diagnostics, and report
aggregation. It is a curated compatibility/generalization subset, not a claim
of a full MiniWoB++ score.

## M8.1-M8.3 Forward Work

### M8.1 Container Reproducibility — done

The profile contains the in-memory fixture, test runner, benchmark runner,
health checks, and mounted artifacts. The optional `wot-proof` profile
selectively migrates the old node-wot fixture and a minimal dashboard; it is
not part of the default Web profile.

Clean commit `40fd93b` provides the digest-pinned non-root fixture, test, and
benchmark services. Its 63 stable host/container outcomes agree exactly. The
optional real node-wot profile reaches the same independent oracle through DOM,
real screenshot/SoM, and WoT while retaining Coordinator contracts, verifier
evidence, and traces. See `evidence/m8.1-40fd93b.md`.

### M8.2A Task Intake and Generalist Planner

Done. `UserRequest` compiles through a sourced `IntentDraft` and deterministic
policy gate into immutable versioned `TaskSpec`; `GeneralistLMPlanner` emits a
semantic `PlannerProposal`, and `ContractBuilder` is the sole executable
binding boundary. Provider-neutral local/remote profiles, fallback-safe model
manifests, compiler/planner/runtime failure attribution, clarification
revisions, and full trace lineage are implemented.

At `7edaa97`, Mistral completed controlled intent compilation plus verified
pricing read-only, settings reversible-write, and approval-gated report export
paths. The same planner class is tested across DOM/SoM/WoT affordances and
passed an official BrowserGym `click-button` smoke through typed action binding.
See `evidence/m8.2a-7edaa97.md`.

### M8.2B Public Benchmark Expansion

The isolated BrowserGym 0.14.3 adapter routes every supported action through
`RunCoordinator`, exposes a typed action whitelist, discovers 125 registered
MiniWoB tasks, checkpoints resumable episodes, and records official reward
separately from runtime diagnostics. The latest complete generalist PR matrix
has 18/18 coverage and 15/18 official success; the three form/slider cases
remain an explicit behavior gap.

Before larger or external matrices, reconcile repository claims, lock
dependencies, split the oversized BrowserGym benchmark module, freeze a
versioned stratified nightly manifest, and add a real screenshot-capable visual
grounder. WebArena-Verified is publicly provisioned rather than authorization
gated; its missing requirement is a running official environment plus agent
response/HAR artifacts. WorkArena remains the only suite in this ladder that
requires gated instance access.

### M8.3 Recovery-Cascade Evolution — done

Clean commit `07e406f` groups attempts under normalized failure signatures,
preserves root failure and symptoms, and detects repeated signatures,
no-progress, A-B oscillation, stale/verifier repetition, exhausted fallback,
and duplicate-effect risk. The benchmark schema reports cascade depth,
repetition, loop abort, effectiveness, and duplicate-effect diagnostics.

Typed `RecoveryPolicyPatch` and `RecoverySkill` payloads are digest-validated,
bounded, risk-scoped, accepted-only loaded, and unloadable. A real Coordinator
cascade was stopped online at depth two; its quarantined policy reduced fresh
original/family replays to depth one, passed global and uncertain-effect safety
smoke with no blind retry, persisted acceptance, and proved rollback. See
`evidence/m8.3-07e406f.md`.

### M8.4 Adaptive Shallow Task Planning - planned

The current `GeneralistLMPlanner` is action-level; `StateKernel.subgoals`
does not yet provide a first-class task plan, dependency validation, or
verifier-backed subgoal lifecycle. The planned M8.4 layer adds adaptive
rule/LM task planning, mandatory validation, serial outcome-oriented progress,
and Flat/Always-plan/Adaptive ablation without adding a DAG scheduler or a
second execution runtime.

## Verification Commands

Run these from the repository root:

```bash
docker compose build runtime-test
docker compose run --rm runtime-test

# A separately provisioned development environment may run the same gate:
python -m pytest -q
python -m ruff check src tests scripts
python -m mypy src
python -m build
```

M1 end-to-end commands:

```bash
affordance-runtime serve-fixture --port 3000
affordance-runtime run --target http://127.0.0.1:3000/pricing
affordance-runtime baseline --target http://127.0.0.1:3000/pricing
```

M2 and M3 evidence commands:

```bash
affordance-runtime benchmark --output benchmark-results --seeds 3
affordance-runtime evolve \
  --benchmark-report benchmark-results/benchmark-report.json \
  --output evolution-results
python scripts/generalization_smoke.py \
  --benchmark benchmark-results/benchmark-report.json \
  --output generalization-results
```

Clean-checkout M0-M8 gate:

```bash
./scripts/reproduce_local.sh
```

## Change Ledger

| Date | Milestone | Change | Files | Verification |
| --- | --- | --- | --- | --- |
| 2026-07-20 | M0-M4 | Created milestone implementation ledger from the authoritative plan and current source audit | `docs/implementation-status.md` | baseline: 27 tests, Ruff, and mypy passing before implementation changes |
| 2026-07-20 | M0 | Implemented frozen state, contract, approval, trace, and evolution semantics | core runtime modules and tests | 32+ tests, Ruff, mypy |
| 2026-07-20 | M1 | Implemented coordinator, artifacts, pricing fixture/planner, CLI, structural post-verification, immediate revalidation, screenshots, and baseline | coordinator, artifacts, fixture, planner, CLI, tests | 36 tests; Ruff/mypy; real Chromium gold path/baseline; three repeated runs |
| 2026-07-20 | M2 | Added settings and export fixtures, persisted/API and file-hash oracles, explicit CLI approval, download artifacts, cross-surface coordinator proofs, correct metric denominators, benchmark matrix, and JSON/Markdown/CSV writers | fixtures, planners, browser/executor, verification, benchmark modules, tests | 39 tests; Ruff/mypy; real Chromium settings pass, export blocked without approval, approved export and audit pass |
| 2026-07-20 | M2 | Completed deterministic perturbations and executable Direct/Primitive/Full plus four-ablation matrix | benchmark local runner, runtime feature gates, fixture perturbations | 21 real Chromium runs; Full Runtime success 1.0, stale recall 1.0, unsafe rate 0.0, false accept rate 0.0 |
| 2026-07-20 | M3 | Added failure classification, typed proposals, versioned registry/rollback, mandatory replay categories, and before/after reports | evolution and replay modules, CLI, tests | real no-verifier false accept became accepted verifier patch after 1.0/0.0/0.0 regression gate |
| 2026-07-20 | M4 | Added stable task service, bounded tool adapter, local scenario runner, scoped approval, cancellation, result/evidence/trace retrieval | integrations package and tests | real Chromium pricing task succeeded; export waited for approval then succeeded with file-hash receipt |
| 2026-07-20 | Audit | Added task-constraint policy, effect idempotency/compensation enforcement, post-approval state revalidation, async task adapter, and release thresholds | safety, coordinator, integration, benchmark validation, docs, tests | 49 tests; Ruff/mypy; 21-run local gate passed; evolution report and local async API passed |
| 2026-07-20 | M8 precursor | Ran official Farama MiniWoB++ click-button through BrowserSession, DOM Affordance, ActionContract, and DomExecutor | temporary official checkout only | historical compatibility proof later superseded by the integrated M8 suite |
| 2026-07-20 | M5 | Added CI, package build dependency, focused Chromium smoke, environment manifest, versioned report output, and one-command clean-checkout reproduction | workflow, environment module, benchmark writer, scripts, evidence summary | clean clone at `4528f25`: 49 tests, Ruff, mypy, build, smoke, 21-run matrix, and evolution gate passed |
| 2026-07-20 | M6 | Added SHA-bound executable verifier payloads, fresh candidate runtime replay, atomic registry persistence, accepted-only loading, versioned reports, and two-layer rollback proof | evolution modules, explicit benchmark runtime profiles, evidence gate, tests | clean clone at `4cccc96`: 51 tests plus 21 benchmark and 6 fresh replay runs; accepted registry and rolled-back proof verified |
| 2026-07-20 | M7 | Added external task JSON-RPC, a separate runtime server process, and a compiled LangGraph parent for pricing and approval-gated export | integration modules, parent smoke, CI/reproduction, tests, evidence | clean clone at `9a9796e`: 52 tests; pricing success; export waited then succeeded; evidence and trace retrieved; no primitive GUI tools exposed |
| 2026-07-20 | M8 | Added distinct seeded and held-out layouts, real screenshot grounding, and a pinned official MiniWoB++ curated adapter | fixture v2, benchmark/generalization modules, CI/reproduction, tests, evidence | clean clone at `e463e16`: 55 tests; 63 matrix runs, 6 held-out runs, 5 visual runs, and 18 official episodes all passed |
