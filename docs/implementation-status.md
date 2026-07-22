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
| M8.2B Public Benchmark Expansion | in_progress | clean `7e1c7db` passes smoke 6/6, PR 18/18, diagnostic 30/30, and frozen nightly 300/300; its complete residual release observes 625/625 at 402/625 success and retains 223 cross-layer failure envelopes. R9 clean `b4e596e` closes the label/form cluster through family 20/20 and PR 18/18; its new diagnostic is 29/30 with one typed-constraint planning residual | distinguish exact field values from prefix/suggestion constraints generically; then repeat the bounded ladder; improve trace-derived family taxonomy; provisioned ScreenSpot/WebArena/WASP/WorkArena remain separate gates |
| M8.3 Recovery-Cascade Evolution | done | online incident/loop detection plus quarantined, replayed, accepted, persisted, and rolled-back recovery policy at `07e406f` | none |
| M8.4 Adaptive Shallow Task Planning | done | criteria-bound progress, bounded TaskPlanningContext, evidence-aware replanning, monotonic lineage, verified-progress preservation, controlled ablation, and real Chromium reference entrypoint | none |
| M8.5 Unified Adaptive Routing and Skill Internalization | done | Runtime-first R1-R6 cover criteria-bound progress, task-aware perception, target-specific routing, Core gesture binding, safe fallback, R5 de-specialization, canonical cross-run TaskSkill mining, digest-bound replay, accepted TaskSkill/RecoverySkill loading, fallthrough, and rollback | none; public benchmark promotion remains M8.2B/R7 evidence |
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
separately from runtime diagnostics. The latest GPU-local v101 PR matrix has
18/18 coverage and official success; v102 covers all 30 nightly-manifest tasks
at seed 0 with 0.9667 mean reward and no provider/runtime/429/retry failure.
Structured SVG point families and sortable drag families pass 10/10, while
v103 enforces clean source identity for the pending frozen nightly/release.

Before larger or external matrices, repository claims, dependency constraints,
the BrowserGym module split, and the `miniwob-action-family-v1` 30-task nightly
manifest are complete. A real screenshot-capable visual grounder is implemented,
but official ScreenSpot assets are still required before a result claim.
WebArena-Verified is publicly provisioned rather than authorization
gated; its missing requirement is a running official environment plus agent
response/HAR artifacts. WorkArena remains the only suite in this ladder that
requires gated instance access.

The earlier task-specific `benchmarks.miniwob` compatibility runner remains
available only to reproduce historical M8 evidence. Its generated reports are
explicitly ineligible for M8.2B scoring; current MiniWoB claims must use the
BrowserGym Generalist full-Coordinator track.

Current local external-suite preflight (2026-07-22) remains intentionally
non-runnable where provisioned inputs are absent: the ordinary project Python lacks BrowserGym,
but the existing isolated Python 3.12 runtime has pinned MiniWoB 0.14.3 and
Playwright 1.44, and the launcher-confirmed current-code local smoke passes
6/6 with 18 calls and no runtime/provider failure. This dirty-tree run remains
a runtime confirmation rather than a promoted score. Runtime discovery is now
guarded by dedicated BrowserGym and WorkArena preflight boundaries. WorkArena
v104 selects only its dedicated interpreter and probes it without credentials;
the environment, L1 registration, and authorized ServiceNow instance are still
absent. ScreenSpot assets, a running WebArena-Verified
environment plus upstream agent artifacts, and an isolated WASP VisualWebArena
evaluator are likewise absent from this worktree. These are deployment/asset
gates, not zero-score results; no dependency install, credential lookup, or
remote benchmark request was made.

The v109 clean immutable 30x10 nightly completed 300/300 and exposed one
acceptance error plus two execution failures. Trace-derived generic repairs and
the hierarchy-scope follow-up passed their family, PR, and breadth ladders. The
replacement clean v112 nightly then passed 300/300 at official success/reward
1.0 with `official_score_claimed=true` and no error/failure cluster. The local
frozen nightly gate is closed; release and provisioned external suites remain.

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

### M8.4 Adaptive Shallow Task Planning - done

`TaskPlan`/`SubgoalSpec`, `PlanProgress`, deterministic validation, the
rule/LLM planner router, Coordinator sequencing, and controlled
Flat/Always-plan/Adaptive ablation exist.

The shared matcher advances Subgoals and SkillSteps only from fresh, strong,
explicitly linked evidence covering every mandatory criterion and evidence
requirement. `TaskPlanningContext` now carries bounded environment, affordance,
evidence, failure, recovery, assumption, and remaining-budget summaries;
replacement plans form a monotonic supersession chain and preserve verified
subgoals. The optional normal pricing CLI path completes two stages in real
Chromium. See `evidence/runtime-r2-task-planning-context-20260722.md`,
`evidence/runtime-r1-criteria-evidence-20260722.md`,
`evidence/m8.4-task-planning-ablation.md`, and
`current-architecture-audit-20260722.md` for the remaining completion gates.

### M8.5 Unified Adaptive Routing and Skill Internalization - done

Typed candidates, unified routes, Core dual-target gesture contracts, fresh
fallback contracts, inspect-before-repeat, visual/DOM/WoT component proofs,
source-conflict extension points, and TaskSkill/RecoverySkill models exist.

Runtime-first R3 and R4 now cover generic TaskSpec/SubgoalSpec-to-perception
wiring, ordinary BrowserSession visual candidates and sourced assertions,
target-specific evidence gates, verifier-backed scoped route calibration, and
geometry-aware conservative fusion. Milestone completion still requires
canonical trace-to-TaskSkill extraction, explicit accepted-profile loading,
and removal of benchmark-family semantics from shared modules.

R4 evidence: `evidence/runtime-r4-verifier-calibrated-routing-20260722.md`.

Follow M8.5R in `current-implementation-plan.md` and the normative
`runtime-first-boundary.md`. The prior completion audit is component evidence,
not milestone closure.

## Verification Commands

Run these from the repository root:

```bash
docker compose build runtime-test
docker compose run --rm runtime-test

# A separately provisioned development environment may run:
python -m pytest -q
python -m ruff check src tests scripts
python -m build

# Repository-wide mypy is an open R7 gate until optional integration
# environments and ignore policies are aligned:
python -m mypy src
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
| 2026-07-22 | Runtime-first R8 / module containment closure | Audited extracted Core collaborators, typed boundaries, authoritative state/trace ownership, benchmark-vocabulary isolation, and BrowserGym facade compatibility; documented the legacy one-contract conformance harness as non-authoritative | executable R8 architecture boundary test, plans/audit/evidence | 522 tests; Ruff; mypy with optional imports across 89 source files; no Core benchmark vocabulary/adapter import; no collaborator `StateKernel` construction; observer/encoder/runner/protocol/report facade identity checks; `runtime-r8-closure-20260722.md` |
| 2026-07-23 | M8.2B R9 / native labels and explicit form obligations | Kept descriptive native labels out of the action inventory, associated explicit/nested/adjacent labels with controls, and compiled multi-field exact-value obligations with verified-target progress and ambiguity fallthrough | generic DOM observation, semantic compiler/planner, non-BrowserGym controls, clean bounded BrowserGym ladder | clean `b4e596e`: original failures 2/2, form family 20/20, PR 18/18; complete diagnostic 29/30 with one retained planning-budget envelope caused by exact-value versus prefix/suggestion semantics; 528 tests, Ruff, mypy 89 source files; `m8.2b-r9-form-obligations-20260723.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym report and protocol containment | Separated versioned profile metadata and seed-major protocol from FailureEnvelope construction/clustering and aggregate report publication; matrix retains scheduling, circuit state, and atomic checkpoints; unknown release tasks use observed action capability evidence or an explicit unresolved evidence gap without task-name dispatch | `browsergym_protocol.py`, `browsergym_report.py`, matrix compatibility wiring, direct taxonomy/report tests, plans/evidence | 519 tests; Ruff; mypy with optional imports across 89 source files; 66 focused tests; compatibility, declared-family precedence, observed-capability fallback, and no-action evidence-gap controls; `runtime-r8-browsergym-report-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym episode runner containment | Extracted one-episode setup, Coordinator traversal, backend execution, external-policy lifecycle, model/context trace projection, local source serving, and killable process timeout/exit/cleanup while suite scheduling, frozen identity, checkpoints, circuit breaking, and reports remain outside | `browsergym_episode_runner.py`, bridge facade wiring, direct lifecycle/isolation tests, plans/evidence | 515 tests; Ruff; mypy with optional imports across 87 source files; 69 focused tests; facade identity, forced timeout termination/cleanup, and empty-worker-result exit-code controls; `runtime-r8-browsergym-episode-runner-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym encoder containment | Extracted external-policy contract attachment, semantic-action translation, validated gesture and point encoding, native value conversion, and action-specific verifier mapping while Core retains dual-target binding, currentness, route, policy, capability, and preflight authority | `browsergym_encoder.py`, bridge facade wiring, direct encoder/adapter/Core tests, plans/evidence | 512 tests; Ruff; mypy with optional imports across 86 source files; 88 focused tests; invalid geometry/missing binding/value/verifier negative controls; facade compatibility and Core gesture invariants; `runtime-r8-browsergym-encoder-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym observer containment | Extracted coherent capture, observation metadata normalization, bounded epoch-drift retry, drag geometry/fingerprint enrichment, DOM grounding refresh, screenshot fallback, visual candidate fusion, and JSON-safe adapter metadata while preserving bridge facade imports and Runtime ownership | `browsergym_observer.py`, shared BrowserGym backend constant, bridge facade wiring, direct observer/adapter tests, plans/evidence | 498 tests; Ruff; mypy with optional imports across 85 source files; 76 focused BrowserGym/observer/boundary tests; retry-cap, unrelated-error, serialization, geometry, visual, and facade compatibility controls; `runtime-r8-browsergym-observer-20260722.md` |
| 2026-07-22 | Runtime-first R8 / planner model orchestration containment | Extracted provider-neutral candidate data/dynamic schemas, structured model invocation, bounded same-context repair, redacted exhaustion, and call-budget reservation hooks while Generalist retains Prompt/configuration, semantic validation/binding, fallback order, and trace assembly | `planner_model_orchestrator.py`, Generalist policy wiring and compatibility wrappers, direct provider-neutral tests, plans/evidence | 494 tests; Ruff; mypy with optional imports across 84 source files; 88 focused tests; first-pass/repair/schema-failure/budget/exhaustion negative controls; public candidate JSON Schema field equivalence; `runtime-r8-planner-model-orchestrator-20260722.md` |
| 2026-07-22 | Runtime-first R8 / default SemanticCompiler registry containment | Moved ordered rule/constraint assembly, applicability declarations, evidence metadata, operation scopes, output kinds, and negative examples behind a typed factory while Generalist retains unchanged semantic algorithms and a compatible public entrypoint | `default_semantic_compilers.py`, Generalist callback wiring, direct generic factory tests, plans/evidence | 488 tests; Ruff; mypy with optional imports across 83 source files; exact precedence/evidence assertions, empty/unsupported-context negative controls, existing non-BrowserGym DOM integration, and benchmark-vocabulary boundary; `runtime-r8-default-semantic-registry-20260722.md` |
| 2026-07-22 | Runtime-first R8 / PlannerContextBuilder containment | Extracted bounded task/state/observation context models, semantic inventory projection, action exposure, relevance bounds, current progress, and one-failure summary while preserving Generalist LM Prompt/schema/compiler behavior and compatible imports | `planner_context.py`, Generalist planner wiring, generic context tests, plans/evidence | 485 tests; Ruff; mypy with optional imports across 82 source files; bounded/no-handle/legacy-envelope negative controls; `runtime-r8-planner-context-builder-20260722.md` |
| 2026-07-22 | Runtime-first R8 / RecoveryHandler containment | Separated immutable failure/cascade/context/policy evaluation from Coordinator-owned incident, reroute, budget, diagnostic, and state-transition application | `recovery_handler.py`, Coordinator wiring, generic recovery tests, plans/evidence | 482 tests; Ruff; mypy with optional imports across 81 source files; stale, uncertain-effect, repeated-loop, and no-incident-mutation controls; `runtime-r8-recovery-handler-20260722.md` |
| 2026-07-22 | Runtime-first R8 / ContractExecutionLoop containment | Extracted run/snapshot binding, scoped gate construction, policy/capability/preflight checks, fresh-observation revalidation, one-shot executor delegation, and structural verification while retaining state/trace/budget/approval/recovery authority in Coordinator | `contract_execution_loop.py`, Coordinator wiring, generic contract-stage tests, plans/evidence | 479 tests; Ruff; mypy with optional imports across 80 source files; policy/capability/staleness negative controls; approval/uncertain-effect/fallback integration; `runtime-r8-contract-execution-loop-20260722.md` |
| 2026-07-22 | Runtime-first R8 / PerceptionSession containment | Extracted task/subgoal requirement derivation, failed-route escalation, coherent BrowserSession capture profiles, screenshot artifact handling, and sync/async targeted observation port resolution while retaining observation recording, counters, budgets, and trace transitions in Coordinator/StateKernel | `perception_session.py`, Coordinator wiring, generic perception tests, plans/evidence | 476 tests; Ruff; mypy with optional imports across 79 source files; plain-source/no-mutation, missing-port, invalid-source negative controls; visual-primary/fallback/conflict integration; `runtime-r8-perception-session-20260722.md` |
| 2026-07-22 | Runtime-first R8 / TaskPlanLifecycle containment | Extracted immutable task-plan transition preparation, bounded planning context, async planner resolution, validation, replan eligibility, completion, and active-subgoal lookup from Coordinator while retaining all mutation in Coordinator/StateKernel | `task_plan_lifecycle.py`, Coordinator wiring, generic lifecycle tests, plans/evidence | 473 tests; Ruff; mypy with optional imports across 78 source files; generic invalid-plan negative control; benchmark-vocabulary boundary; `runtime-r8-task-plan-lifecycle-20260722.md` |
| 2026-07-22 | Runtime-first R7 / clean public evaluation | Froze one source/model/Prompt/schema/context/budget identity, ran the three-layer breadth-first protocol through complete nightly and all-supported-task residual release, and retained cross-layer failures without in-run repair | fixed Python 3.12 launcher, BrowserGym matrix/checkpoint/report artifacts, plans/evidence | clean `7e1c7db`: smoke 6/6, PR 18/18, diagnostic 30/30, nightly 300/300 reward 1.0; release 625/625 observed, 402 successes, zero provider/retry/missing/drift/circuit failures, 223 retained envelopes; `runtime-r7-clean-public-evaluation-20260722.md` |
| 2026-07-22 | R7 diagnostic / target-scoped perception and bounded incremental control | Preserved task-level coherent observation acquisition while projecting route hard gates onto the current semantic action/target; after a complete frozen nightly, unified typed incremental-control compilation and constraint selection around verified Page/Arrow steps without task-family dispatch | perception, unified target resolution/grounding, semantic compiler, non-BrowserGym routing controls, tests, plans/evidence | clean `f8001d9`: smoke 6/6, PR 18/18, diagnostic 30/30, frozen nightly 298/300 with only two >50-step control failures; dirty generic repair reproduction 7/7 and family 10/10; 471 tests, Ruff, mypy 77 source files, diff/boundary checks pass; replacement clean ladder is recorded in the R7 row above |
| 2026-07-22 | Runtime-first R6 / complete harness learning | Added causal canonical JSONL validation, backend-neutral semantic extraction, cross-run clustering and parameter/negative/applicability mining, schema 1.1 source/report provenance, digest-bound replay evidence, accepted TaskSkill/RecoverySkill profile loading, and explicit System 1 selection provenance | harness learning, TaskSkill/evolution/profile loader, Coordinator trace, normal CLI, tests, plans/evidence | fixed Python 3.12: 463 tests pass; Ruff passes; mypy passes all 77 source files; three real non-BrowserGym System 2 traces across three layouts auto-quarantine one skill; five-category fresh replay accepts it and a fresh persisted profile completes held-out with zero System 2 calls; rollback and digest-tamper controls pass |
| 2026-07-22 | Runtime-first R5 / planner and observation de-specialization | Moved BrowserGym authored DOM/SVG profiles and backend encoding into its adapter; normalized shared observation to opaque handles; added typed semantic compiler/constraint registry, generic incremental-control compilation, terminal-evidence separation, boundary scans, non-BrowserGym controls, and disabled-profile ablation | DOM/SVG adapters, BrowserSession, grounding, planner/compiler registry, verification, BrowserGym adapter, tests, plans/evidence | fixed Python 3.12: 452 tests pass; Ruff passes; mypy passes all 76 source files; dirty-tree diagnostic family 10/10 and seed-major PR 18/18 with no provider/retry failures; not an official benchmark score |
| 2026-07-22 | Runtime-first R2 / M8.4 | Added bounded TaskPlanningContext, evidence-aware replanning, monotonic plan lineage, verified-progress preservation, forbidden plan-content validation, and optional real Chromium pricing entrypoint | task planning, StateKernel, Coordinator, reference planners/CLI, tests, plans/status | fixed Python 3.12: 423 tests pass; Ruff passes; mypy with optional imports ignored passes all 73 source files; Flat/Always-plan/Adaptive semantic ablation acceptance passes |
| 2026-07-22 | Runtime-first R3 / generic perception | Wired TaskSpec/SubgoalSpec requirements through Coordinator and BrowserSession; added coherent DOM/A11Y/SVG/screenshot/visual candidates, ordinary source assertions, fresh targeted perception, trusted visual binding, and evidence-driven DOM-to-visual escalation | perception, BrowserSession, Coordinator, ContractBuilder, recovery, BrowserGym point-region reuse, tests, plans/status | fixed Python 3.12: 433 tests pass; Ruff passes; mypy with optional imports ignored passes all 73 source files; 59 BrowserGym adapter regressions pass; public BrowserSession.launch Chromium 125 visual route passes an independent DOM-state verifier |
| 2026-07-22 | Runtime-first R4 / verifier-calibrated routing | Made candidate evidence gates target-specific, added geometry-aware conservative sibling fusion, typed post-verification RouteOutcome, strong-evidence-only scoped calibration, origin-level browser environment family, and removed receipt learning from the static backend selector | grounding, unified routing, Coordinator, BrowserSession, routing, tests, plans/status | fixed Python 3.12: 442 tests pass; Ruff passes; mypy passes all 74 source files; shifted-layout candidate ids switch to the verified source without cross-environment leakage; six-profile ablation has zero unsafe effects, false accepts, and duplicate risk |
| 2026-07-22 | Runtime-first R1 | Added shared criteria/evidence matching, explicit verifier evidence identity and obligation links, fresh strong-evidence gates for Subgoal and TaskSkill checkpoints, and structured trace reports | criteria, contracts, verifier, task planning/skills, Coordinator, controlled benchmark fixtures, tests, plans/status | fixed Python 3.12: 412 tests pass; Ruff passes; mypy with optional imports ignored passes all 73 source files; unrelated, partial, stale-revision, stale-snapshot, weak/self-declared receipt, state-delta weakness, mandatory-coverage, multi-criterion, and unbound SkillStep cases covered |
| 2026-07-22 | Architecture audit | Adopted Runtime-first boundary, prohibited benchmark specialization in shared architecture, corrected M8.4/M8.5 status, and added ordered remediation gates | boundary, audit, README, project/current plans, status ledger | reviewed `0272765`; 401 tests pass, Ruff passes, full mypy has four optional-integration errors |
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
| 2026-07-22 | M8.2B v132 | Added bounded authored item/type/current-quantity observation and fresh-epoch semantic increment selection without admitting every unmarked `bid` | DOM adapter, browser session, generalist planner, tests, evidence | `order-food` 10/10 with zero model calls; same-source PR 18/18 and breadth 60/60; 388 tests, Ruff, focused mypy, diff check |
| 2026-07-22 | M8.2B v148 | Preserved action-family diversity in the bounded planner inventory so a 96-endpoint calendar cannot hide its newly rendered name/create controls | generalist planner, DOM/BrowserGym calendar path, tests, evidence | same-source `daily-calendar` 10/10, PR 18/18, and seed-major breadth 60/60; 395 tests, Ruff, focused mypy, diff check; no provider, 429, retry, runtime, acceptance, or failure cluster |
| 2026-07-22 | M8.2B v149 | Restored local Ollama GPU residency without replacing its model volume, added fail-closed provider preflight to the sole launcher, and restored documented smoke/PR defaults | launcher, provider preflight, fixed-budget evidence | same-source fixed 165/10/15/15 PR 18/18; RTX 3080 and 4.75 GB model residency recorded; no provider, 429, retry, runtime, acceptance, or failure cluster |
| 2026-07-22 | M8.2B v155 | Added bounded owner/position/action/toggle semantics for authored collection controls and a BrowserGym current-bid scroll/DOM-click route without exposing bids to Planner proposals | DOM adapter, generalist compiler, BrowserGym binder/executor, tests, evidence | same-source social families 30/30, PR 18/18, and seed-major breadth 60/60; 401 tests; no provider, 429, retry, runtime, acceptance, or failure cluster |
