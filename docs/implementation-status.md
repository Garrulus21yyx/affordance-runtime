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

Live state is represented on separate axes; compound labels such as `done
locally` or `component done` are explanatory headings only and are not valid
milestone status values.

| Axis | Values | Purpose |
| --- | --- | --- |
| Milestone status | `pending`, `in_progress`, `done`, `blocked` | progress against the milestone's declared exit criteria |
| Completed scope | concise factual scope | what is actually implemented or verified |
| Evidence maturity | `none`, `protocol`, `injectable`, `normal_entrypoint`, `local_reproducible`, `ci_reproduced`, `immutable_empirical` | strongest current evidence level |
| Promotion status | `held`, `eligible`, `promoted`, `not_applicable` | whether broader claims or runs are authorized |
| Architecture admission | `pass`, `fail`, `waived`, `not_evaluated` | result of the horizontal gate for the change |
| Remote CI | `pass`, `fail`, `pending`, `not_run` | state of CI for the exact committed revision |

### Current Evidence Identity

| Field | Current value |
| --- | --- |
| Committed source revision | `3d44a9d222decd1de272d7a4d3eb14b025a8738a` |
| Committed baseline local gate | pass for targeted SG7 repair set: 429 focused planner/intake/perception/grounding/governance tests, Ruff, mypy over 116 source files, and diff check before commit |
| Current worktree identity | SG7 clean-evidence ledger/archive diff based on committed `3d44a9d`; no production-code change |
| Current worktree local gate | pass for documentation/evidence archive diff: file digests rechecked and `git diff --check` passed |
| Architecture admission | pass for the committed targeted repair; SG7 targeted protected-family confirmation passed cleanly, while PR breadth/nightly/release promotion remains held |
| Remote CI | fail: [push run 30271191621](https://github.com/Garrulus21yyx/affordance-runtime/actions/runs/30271191621) and [PR run 30271194148](https://github.com/Garrulus21yyx/affordance-runtime/actions/runs/30271194148) |
| Promotion status | held |

The remote failures are not one undifferentiated environment failure. Verified
logs show a Python 3.12 collection/package-path failure (`scripts` not
importable), matching Chromium/container benchmark failures caused by coherent
observation epoch drift, and a BrowserGym Playwright dependency-provisioning
failure (`libasound2` unavailable on Ubuntu Noble); Python 3.11 was cancelled
after another matrix failure. The current local diff repairs the core pytest
invocation (`python -m pytest -q`) and the BrowserGym runner/profile
provisioning (`ubuntu-22.04` plus `requirements/constraints-browsergym.txt`).
The coherent observation epoch drift crash is repaired by bounded semantic
stabilization in `BrowserSession.capture`; true semantic DOM drift is still
rejected. The local benchmark now completes and writes all 63 run records under
the explicit diagnostic flag, while its release acceptance remains failed
because settings/recovery effectiveness is still below the promotion threshold.
Local success must not be described as remote-CI or immutable promotion
evidence.

## Horizontal Architecture Governance

This is an independent, always-active track rather than an `M*` milestone. Its
normative execution semantics are in
[Horizontal Architecture Governance Track](architecture-governance-track.md).
A failed gate blocks the violating change, not unrelated milestone work or the
repository until a unified rewrite is complete.

| Track state | Snapshot | Admission baseline | Active waiver | Next remediation |
| --- | --- | --- | --- | --- |
| `active` | committed `3d44a9d` targeted SG7 confirmation passing locally / prior remote CI pending rerun | Coordinator 3473 lines / 26 methods; `run_sync` 2039 lines; planning/intake/control ratchets plus dependency and execution-commit gates | none | protected cross-family / PR breadth is the next vertical lane; immutable Planner input is the next horizontal lane and should not be mixed into the same evidence identity |

Change admission uses `pass | fail | waived | not_evaluated`; remediation items
use `pending | in_progress | done | blocked`. These states do not replace the
milestone maturity labels below.

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
| M8.2A Task Intake and Planner Contracts | in_progress | SG1-SG6 complete locally: code-owned schemas, bounded SourceLedger lineage, canonical flat/multi-stage graph reconstruction with typed evidence, deterministic source-to-terminal coverage, proposal normalization, veto-only audit, bounded repair, and held-out non-BrowserGym conformance. SG7 targeted protected-family confirmation passed cleanly at `3d44a9d`: `enter-date` and `text-transform`, seeds 0 and 1, 4/4 observed and passed, no provider/runtime failure, `official_score_claimed=false`. | continue to protected cross-family / PR breadth under the same architecture gates; promotion held |
| M8.2B Public Benchmark Audit | in_progress | clean `df5b820` 30 x 2 diagnostic completed 60/60 at 24/60 success with zero provider failure/retry and 36 attributed residuals; later protected recheck isolates a shared local-provider obligation-graph intake failure | hold PR/nightly/release; establish provider-neutral obligation-complete intake before breadth promotion |
| M8.3 Recovery-Cascade Components | in_progress | incident/loop detection, lower-half online recovery, typed dispatch, configured provider-switch owner, planner-context compaction owner, and target-bound planner-schema repair owner wired in BrowserGym and `GeneralistTaskPipeline` normal entrypoints | level-4 empirical effectiveness remains open; do not claim full-phase recovery |
| M8.4 Adaptive Shallow Task Planning | in_progress | TaskPlan contracts, criteria-bound progress, obligation outcomes/evidence, deterministic cross-scenario controls, and stateless decision admission | prove held-out behavior |
| M8.5 Unified Adaptive Routing and Skill Internalization | in_progress | unified candidates, routes, gestures, safe fallback, active perception, trace mining, accepted profile loading, fallthrough, and rollback | preserve generic main path while planner/recovery operational gaps close |
| M8.6 Planner, Active Perception, and Recovery Governance | in_progress | `c939051` closes the scoped internal gate/rollout; concrete context/schema recovery owners plus neutral Planner/approval contracts remain green in the current dedicated 939-test governance-sync worktree | level-4 recovery effectiveness, planner generalization, and Coordinator responsibility reduction remain open |
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

Contract and local canonical-intake boundaries are done; empirical open-world
behavior remains open. UserRequest, IntentDraft,
immutable TaskSpec, semantic PlannerProposal, ContractBuilder, provider-neutral
ports, clarification revisions, and trace lineage exist. The 2026-07-23 audit
below is historical diagnosis; later SG1-SG6 slices replace provider-authored
authority with Runtime canonical compilation and deterministic coverage. Those
local gates still do not prove open-world planner generality.

At `7edaa97`, Mistral completed controlled intent compilation plus verified
pricing read-only, settings reversible-write, and approval-gated report export
paths. The same planner class is tested across DOM/SoM/WoT affordances and
passed an official BrowserGym `click-button` smoke through typed action binding.
See `evidence/m8.2a-7edaa97.md`.
Clean `bba582c` closes the local correctness defects around bounded intake
repair: malformed provider obligation nodes become typed repair input, graph
fields survive repair, model-call reservations are counted, repair has an
immutable Prompt/checkpoint identity, selected provider profile is preserved,
and failed repair emits a redacted trace event.

The historical `bba582c` snapshot still lacked Runtime-owned canonical graph
construction. That statement is superseded by locally completed SG2-SG6:
`CanonicalObligationCompiler` now reconstructs flat and bounded multi-stage
graphs, typed evidence and deterministic source-to-terminal coverage gate
admission, and the model audit has veto-only authority. Protected-family,
breadth, diagnostic, nightly, and release promotion remain separately gated.

### M8.2B Public Benchmark Audit - diagnostic complete, repair required

The latest clean strict diagnostic at `df5b820` completed all 60 episodes at
24/60 success (`0.4`) with zero provider failure, retry, missing episode,
invalidation, or batch stop. Its 36 envelopes are 12 intent/planning, 11
contract/field binding, 8 verification, 3 execution, and 2 observation/context.
The result is diagnostic and non-promotable. It also contains protected-family
regressions, including `text-transform` 2/2 to 0/2 and `enter-date` 2/2 to 1/2.
The immutable report must be published before any release claim.

The earlier strict-generalist evaluation at implementation SHA `351dbdf` completed
all 60 scheduled cases in seed-major order after fresh smoke and PR breadth
gates. It recorded 19 successes and 41 failures, mean official reward
`0.3166666667`, 251 model calls, and zero provider failures, rate-limit retries,
transient retries, missing cases, invalidations, or batch stops. Seven tasks are
2/2, five are 1/2, and eighteen are 0/2. `official_score_claimed` remains false.

Formal envelopes contain 4 contract/field-binding, 4 execution, 7
intent/planning, and 26 generic recovery results. Because the recovery bucket
mixes unlike precondition, approval, routing-target, and terminal-action facts
across eight families, frozen nightly is held. The next implementation slice is
generic attribution fidelity followed by cross-family contract, context,
subgoal-routing, and execution/verification owners—not task-specific repair.
Evidence: `evidence/runs/m8.2b-diagnostic-351dbdf/`.

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
acceptance error plus two execution failures. The replacement v112 nightly
passed 300/300 for its exact revision and active compiler profile. These are
historical compatibility and diagnostic results, not proof of a
strict-generalist planner. The scoped M8.6 internal gate is closed, and the new strict diagnostic
remains non-promotable while its cross-family residual owners are open;
release and provisioned external suites remain later audit gates.

### M8.3 Recovery-Cascade Components - partial

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

### M8.4 Adaptive Shallow Task Planning - component done

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

### M8.5 Unified Adaptive Routing and Skill Internalization - component done

Typed candidates, unified routes, Core dual-target gesture contracts, fresh
fallback contracts, inspect-before-repeat, visual/DOM/WoT component proofs,
source-conflict extension points, and TaskSkill/RecoverySkill models exist.

Runtime-first R3 and R4 now cover generic TaskSpec/SubgoalSpec-to-perception
wiring, ordinary BrowserSession visual candidates and sourced assertions,
target-specific evidence gates, verifier-backed scoped route calibration, and
geometry-aware conservative fusion. Canonical trace mining and accepted-profile
loading exist as components. Milestone completion still requires empirical
main-path evidence and removal of the remaining allowlisted benchmark-package
dependencies from shared modules.

R4 evidence: `evidence/runtime-r4-verifier-calibrated-routing-20260722.md`.

Follow M8.5R in `current-implementation-plan.md` and the normative
`runtime-first-boundary.md`. The prior completion audit is component evidence,
not milestone closure.

### M8.6 Planner, Active Perception, and Full-Phase Recovery Governance - internal gate done

The [M8.6 Closure Audit](current-closure-audit-20260724.md) reopened behavioral
and responsibility-containment exit criteria. The scoped repairs and fresh G5
internal rollout pass for immutable implementation revision `c939051`. M8.2B
has since completed a separately identified strict diagnostic at 24/60; it is
not promotion evidence.

The governing documents are:

- [Runtime-First Architecture Boundary](runtime-first-boundary.md);
- [Responsibility Containment Boundary](responsibility-containment-boundary.md);
- [Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md);
- [Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md);
- [M8.6 Closure Audit](current-closure-audit-20260724.md).

| Gate | Status | Evidence and remaining work |
| --- | --- | --- |
| G0 Freeze and classify | complete | score-bearing and legacy summaries are classified; current identities are explicit |
| G1 Strict-generalist profile | complete | strict default, physical compatibility isolation, typed provenance, shared proposal validation, and anti-specialization controls |
| G2 Intent and TaskPlan integration | obligation chain and decision owner complete | TaskSpec obligations compile to same-id outcomes, every plan source is checked, verified evidence reaches TerminalReadiness, cross-scenario controls pass, and `DecisionConstraintSet` owns typed text, ordinal, terminal, and current-state admission |
| G2.5 Active perception and evidence repair | repaired / locally verified | strict authority intersection, no adapter escalation, current relevant semantic-candidate evidence, typed flow owner, and negative controls pass |
| G3 Full-phase Recovery Coordinator | component owners integrated / empirical gate open | BrowserGym generalist and `GeneralistTaskPipeline` configure concrete context-compaction and planner-schema repair owners; a provider-switch owner is added only for a real multi-profile fallback. Level-4 effectiveness and every-entrypoint coverage remain unproven. |
| G4 Complete-run audit | complete | immutable run identity, ordinary-failure continuation, exact resume, allowlisted batch stops, and post-collection clustering |
| G5 Internal conformance evidence | complete for internal scope | fresh 11-case profile-separated Runtime rollout at `docs/evidence/runs/m8.6-g5-c939051`; expected/safe outcomes 100%, hash index revalidated, external/open-world suites unprovisioned |
| Responsibility containment | Planner/approval contracts extracted / feature freeze remains | ActivePerceptionFlow, RecoveryCommandDispatcher, Runtime evidence projections, stateless TaskPlanFlow, TaskPlanCommitPreparation, RecoveryTraceProjection, TaskObligationCoverage, TaskObligationOutcomeCompiler, immutable PlannerModelRequest, neutral PlannerDecision/PlannerPort contracts, and explicit approval-source contracts have typed ownership; strict `propose()` remains separately bounded and Coordinator owns task-execution commit sequencing at 3473 lines / 26 methods. Legacy harness, skill/progress mutation, and scoped non-execution trace debt remain explicitly tracked; the reduction target remains open. |

Current verified facts:

- the default planner is strict-generalist and historical task grammar is
  physically isolated;
- proposal provenance and validation are shared across model, deterministic,
  parent, skill, and recovery sources;
- raw requests enter typed intent and TaskPlan routing;
- active perception and lower-half recovery run through normal Coordinator
  paths; BrowserGym generalist and `GeneralistTaskPipeline` configure concrete
  context/schema owners, while configured multi-profile paths can also switch a
  fallback provider through a real owner;
- complete-run accounting continues after ordinary failures;
- immutable historical evidence remains bound to its recorded revisions; the
  committed revision `627b5f7` passes 938 tests, including 18 focused
  horizontal/existing architecture gates, plus Ruff and mypy over 116 source
  files in the dedicated Python 3.12 environment. Its associated remote CI
  fails, so this is locally reproducible committed evidence, not remote-green
  or immutable promotion evidence.

Current blockers for the scoped `c939051` internal gate: none. This does not
close the broader product work. Entrypoints still explicitly own dispatcher
composition, level-4 recovery effectiveness remains unproven, the Coordinator
remains above its reduction target, and strict planner behavior is still
diagnostic. External-suite provisioning is a separate confirmation gap.

Current vertical next action (the horizontal architecture track applies in
parallel and is not an arrow in this sequence):

~~~text
SG1-SG6 canonical intake and local conformance complete
  -> context/schema normal-entrypoint owners complete at component level
  -> targeted SG7 protected-family confirmation
  -> cross-family and fresh diagnostic confirmation
~~~

The broader product claim may be promoted only when enabled recovery actions
have concrete normal-entry owners and real evidence-backed changes, authority
budgets only narrow downstream, semantic requirements use target-relevant
evidence, Coordinator and Planner pass their reduction gates, and comparisons
come from immutable Runtime runs without protected-family regression. External
suites remain independently provisioned and historical scores remain
unpromoted.

## Verification Commands

Run these from the repository root:

```bash
docker compose build runtime-test
docker compose run --rm runtime-test

# A separately provisioned development environment may run:
python -m pytest -q
python -m ruff check src tests scripts
python -m build

# Current repository-governed static gate:
python -m mypy --ignore-missing-imports src
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

| Date | Workstream / milestone | Change | Files | Verification |
| --- | --- | --- | --- | --- |
| 2026-07-27 | M8.2A SG7 clean targeted protected-family confirmation | Reran the exact SG7 matrix after committing the generic repair as `3d44a9d222decd1de272d7a4d3eb14b025a8738a`. This clean run preserves the selected scope (`enter-date`, `text-transform`, seeds 0 and 1), strict-generalist planner profile, local Ollama `qwen2.5:7b`, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0, existing 15-call episode budget, and `official_score_claimed=false`. | `docs/evidence/runs/m8.2a-sg7-3d44a9d/`, `/tmp/affordance-sg7-3d44a9d-20260727-184535` | Clean-tree result: expected 4, observed 4, passed 4, failed 0, missing 0, invalidated 0, unrun 0, runtime failures 0, provider failures 0, rate-limit retries 0, transient retries 0, official success rate 1.0, mean official reward 1.0. Run identity digest `sha256:d09d403f6976b246ff614f5f288e8bc7a7bca6719529e934919973ade608309d`; source tree digest `sha256:cb4dd50f8cf2376fce30673d813e1ca895f44b67a2c46860022902c163fa8403`; report sha256 `cea708f3971a85bf231448b5f5cdab182629d54c2449694c8c69cb9f0ff84eed`; matrix metadata sha256 `0ad2bb171b6d8d41aa2c827057e07ba2a8c185fcc6c45cfba10d0ce0936171a1`. This closes SG7 targeted confirmation only; it is not PR breadth, nightly/release, M8.2B promotion, or a formal benchmark score. |
| 2026-07-27 | M8.2A SG7 generic repair candidate | Repaired the clean `fa288af` SG7 protected-family failure without adding task-name, URL, selector, Prompt-only, budget, Coordinator, StateKernel, or PlannerStateView changes. The repair remains generic: unresolved dependency drafts can be boundedly repaired and rechecked before reviewer admission; explicit imperative field entry is canonicalized as reversible write with exact literal value only when the raw request provides that value; page-sourced "text below" is not literalized; reversible generic `HAS_CHANGED` obligations no longer infer text entry unless the subject is a value-entry field; strict planner fallback handles exact value entry, single page-observed text entry, and verifier-backed terminal submit; targeted active perception can preserve requested probes while adding required evidence gaps; the BrowserGym observer exposes targeted capture; opaque DOM/accessibility locators can satisfy executor-local spatial binding without raw coordinates. | intent compiler, canonical compiler, task planning, strict generalist planner, active perception flow, BrowserGym observer, unified grounding, focused regressions, status/goal records | Dirty-tree SG7 diagnostic `/tmp/affordance-sg7-fa288af-submit-fallback-dirty-20260727-182502/browsergym-report.json` passed 4/4 for `enter-date` and `text-transform`, seeds 0 and 1: expected 4, observed 4, failed 0, missing 0, invalidated 0, unrun 0, runtime failures 0, provider failures 0, official success rate 1.0, mean official reward 1.0, `official_score_claimed=false`; report sha256 `0b2313a2356c2411ce5a77db9bd1469227a6d404af5f3be97657cbeec94fc953`, matrix metadata sha256 `26006f8f025e645c3e109615aafa27f127c60bcad20df3f24defc5efd47c63d6`, source tree digest `sha256:cb4dd50f8cf2376fce30673d813e1ca895f44b67a2c46860022902c163fa8403`, `working_tree_clean=false`. The result is a validated repair candidate, not clean SG7 evidence, not PR breadth, not nightly/release, and not a promoted score. Focused repair/gate verification passed: 429 planner/intake/perception/grounding/governance tests, Ruff, mypy over 116 source files, and diff check. |
| 2026-07-27 | M8.2A SG7 targeted protected-family diagnostic | Ran the requested strict-generalist targeted confirmation for `enter-date` and `text-transform`, seeds 0 and 1, after repairing the local Ollama GPU environment by restarting the existing container. The run is bound to clean committed revision `fa288afa7ba047dd3d0ae186f74e948058928436`, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0, local Ollama `qwen2.5:7b`, profile `diagnostic`, and `official_score_claimed=false`. All four scheduled episodes were observed with no missing/unrun/invalidated cases, no provider failures, and no rate-limit/transient retries. Result: SG7 did not pass. Three episodes failed before TaskSpec creation with `unresolved_task_dependency`; `enter-date` seed 0 produced a canonical compiler TaskSpec and accepted TaskPlan, then the strict planner returned `ask_user` / `waiting_clarification`. | `/tmp/affordance-sg7-fa288af-20260727-173720`, preflight artifacts, BrowserGym traces, status/goal records | preflight after restart passed: BrowserGym runtime ready and Ollama model resident on 100% GPU. Pre-run gates passed: 21 horizontal architecture/responsibility tests, 40 SG1-SG6 deterministic intake tests, Ruff, mypy over 116 source files, and diff check. Decision-tree classification: case B for three episodes and case C for one episode; root owner remains INTENT / PLANNING. No production code change, no PlannerStateView migration, no PR breadth/nightly/release, no score or promotion claim. |
| 2026-07-27 | Active-subgoal read/activation boundary | Split the formerly hidden `StateKernel.active_subgoal()` progress mutation into a read-only `active_subgoal()` query and an explicit `activate_next_subgoal()` command. Production activation is Coordinator-owned; planner context construction now remains read-only and no longer advances plan progress while building untrusted planner context. The old planner-context hidden-mutation exception was removed from the architecture gate instead of being kept as an allowlist waiver. | `state_kernel.py`, `coordinator.py`, planner context/task-plan/planning/browsergym tests, horizontal governance test, governance/current/status/goal records | new planner-context no-mutation test and architecture debt-closure test failed before the implementation and pass after it; 189 focused active-subgoal/planner/context/governance tests pass; full dedicated Python 3.12 suite 944 passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. No benchmark/provider/remote CI/promotion claim. |
| 2026-07-27 | Benchmark epoch stabilization and diagnostic CI split | Added bounded BrowserSession recapture for transient affordance-state stabilization during multi-source observation epochs. The retry is allowed only when URL is unchanged and the semantic affordance inventory is unchanged; semantic DOM drift still raises. Split local benchmark CLI semantics so default `benchmark` remains a release acceptance gate, while CI smoke jobs use explicit `--allow-acceptance-fail` to prove the benchmark runs and writes reports without claiming promotion. Container benchmark uses the same explicit diagnostic flag. | `browser_session.py`, CLI benchmark command, CI workflow, compose benchmark command, browser/session/CLI/governance tests, status/goal records | new transient-state-drift test failed before the BrowserSession change and passes after it; semantic DOM drift rejection still passes; CLI diagnostic flag test passes; workflow/compose governance test passes; `affordance-runtime benchmark --seeds 3 --allow-acceptance-fail` completes 63 runs and exits 0 while reporting release acceptance failed; full dedicated Python 3.12 suite 942 passed; 13 focused CLI/browser/governance gates passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. No new remote CI run yet. |
| 2026-07-27 | CI failure classification and harness repair | Converted two classified CI failures into narrow harness repairs: core CI now invokes pytest through the active interpreter so repo-root script imports remain available, and the BrowserGym bridge job uses the documented isolated BrowserGym dependency profile on an Ubuntu runner compatible with Playwright 1.44 dependency names. Added an executable governance test that failed against the old workflow and passes with the repaired workflow. The Chromium/container `coherent observation epoch drifted during multi-source capture` failure is intentionally left open as a benchmark/runtime diagnostic rather than relabeled as environment. | `.github/workflows/ci.yml`, horizontal architecture governance test, status/goal records | focused CI workflow contract test passed; `tests/test_generalization_evidence.py` passed under `python -m pytest`; `scripts/chromium_smoke.py` passed; focused epoch-drift behavior tests passed; full dedicated Python 3.12 suite 940 passed; 10 focused horizontal governance gates passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. The dedicated local interpreter lacks `pip`, so BrowserGym pip dry-run could not be executed there; no new remote CI run yet. |
| 2026-07-27 | Governance baseline self-calibration | Removed duplicated live milestone state from the stable project plan; established the vertical/horizontal `1 + 1` WIP and single-production-writer policy; separated milestone, completed-scope, evidence-maturity, promotion, architecture-admission, and remote-CI axes; bound the current evidence to committed revision `627b5f7`; classified the associated failed push/PR jobs from verified logs; scoped INV-11 to authoritative task-execution commit sequencing with non-expanding compatibility/skill/progress exceptions; and added an executable document-drift gate. | project/current plans, architecture governance/status/intent documents, architecture test, active goal plan | new drift test observed failing before documentation changes and then passed; 19 focused architecture gates; full dedicated Python 3.12 suite 939 passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. The dedicated interpreter cannot run isolated `python -m build` because its host Python lacks `ensurepip/python3.12-venv`; no production code, benchmark/provider episode, promotion, push, or new remote CI run. |
| 2026-07-27 | Horizontal architecture governance activation | Established an independent always-active change-admission track rather than a new serial milestone. Froze current control-module and long-method growth, classified every public StateKernel method as read/mutation, prohibited neutral/extracted collaborator reverse dependencies and authority reacquisition, recorded the existing hidden mutation debt, normalized absolute/relative import scanning, froze existing non-adapter benchmark import debt, documented prior-waiver/anti-circumvention semantics, and synchronized the current plan, architecture, responsibility boundary, and status axes. Existing debt is baselined but not declared healthy; gate failure blocks the violating change rather than requiring a unified rewrite first. | horizontal governance normative document, four governed documents, executable architecture tests, active goal plan | 18 focused horizontal/existing architecture gates; full dedicated Python 3.12 suite 938 passed; Ruff, mypy over 116 source files, and diff check pass. Local snapshot only; no benchmark/provider/remote CI/score claim. |
| 2026-07-27 | M8.6 neutral approval-source boundary | Moved `ApprovalProvider` and `ConfiguredApprovalProvider` out of Coordinator into a neutral approval-contract module. CLI and local benchmark entrypoints now depend directly on neutral approval and planning contracts; Coordinator consumes the approval protocol and preserves compatibility re-exports. Added executable neutral-ownership/direct-import/compatibility gates plus provider token-binding, TTL, no-match, and first-allowed-capability regressions; lowered the Coordinator line ratchet from 3499 to 3473 without moving state, trace, policy, or capability-gate authority. | approval contracts, Coordinator/entrypoint imports, architecture/behavior/containment tests | 20 focused approval/boundary tests; full dedicated Python 3.12 suite 930 passed; Ruff, mypy over 116 source files, and diff check pass. No benchmark/provider/CI run or score claim. |
| 2026-07-27 | M8.6 neutral Planner contract boundary | Moved `PlannerDecision` and `PlannerPort` definitions out of Coordinator into a neutral planning-contract module. Generalist, parent adapter, and deterministic planners now depend on that module; Coordinator consumes the same contracts and retains compatibility re-exports. Added an AST import-boundary gate and lowered the Coordinator line ratchet from 3520 to 3499 without moving state/trace authority. | planning contracts, Coordinator/planner imports, architecture and containment tests | 106 focused architecture/Coordinator/planner tests; full dedicated Python 3.12 suite 924 passed; Ruff, mypy over 115 source files, and diff check pass. No benchmark/provider/CI run or score claim. |
| 2026-07-27 | M8.3 normal-entrypoint schema recovery owner | Added a one-way `REPAIR_MODEL_SCHEMA` owner at the Generalist planner's provider-neutral model-orchestration boundary. It changes subsequent candidate decoding from the action-bound initial schema to the existing current-target/value-bound repair schema, with before/after schema identity and evidence. Ordinary task-pipeline and BrowserGym paths expose it only for planners implementing the real transition. | planner schema recovery owner, Generalist planner, model recovery dispatcher, normal entrypoints, regressions | 160 focused recovery/planner/pipeline/BrowserGym tests; full dedicated Python 3.12 suite 923 passed; Ruff, mypy over 114 source files, and diff check pass. No provider/benchmark/CI run or score claim. |
| 2026-07-26 | M8.3 normal-entrypoint context recovery owner | Added an owner for `COMPACT_CONTEXT` that changes only Generalist planner optional context windows, emits a validated before/after receipt, and is installed only when the ordinary task pipeline or BrowserGym planner exposes that concrete compaction surface. Provider-switch wiring remains conditional. | planner context recovery owner, model recovery dispatcher, normal entrypoints, regressions | 89 focused recovery/pipeline/BrowserGym tests; full dedicated Python 3.12 suite 922 passed; Ruff, mypy over 113 source files, and diff check pass. No provider/benchmark/CI run or score claim. |
| 2026-07-26 | M8.2A provisioned local quality gate | Re-ran the full repository gate with the dedicated project BrowserGym interpreter rather than the unrelated agent-reach environment. | local quality-gate record | `/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest -q`: 921 passed; Ruff, mypy over 112 source files, and `git diff --check` pass. No benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG6 local held-out intake conformance | Added a non-BrowserGym held-out sequential value-flow request using unrelated agreement/records vocabulary and verified it passes the ordinary model intake, canonical multi-stage compiler, deterministic coverage, and independent audit path. Existing source-clause omission, independent-audit veto, ambiguity, stale-lineage, and unknown-source controls provide adversarial omission boundaries. | non-BrowserGym conformance and coverage/compiler regressions | 16 focused SG6 tests; Ruff; repository-governed mypy over 112 source files; no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG5 canonical graph migration | Extended `CanonicalObligationCompiler` to construct a generic flat graph from source-bound requested effects and to reconstruct bounded multi-stage semantic proposals. Runtime owns all graph node instances, identifiers, dependency/value-flow references, provenance, and typed evidence; model/parent proposals may contribute only validated semantic relations and edges. Both normal entrypoints therefore have no direct candidate graph copy into `TaskSpec`. The independent auditor's `COMPLETE` is advisory-only; typed non-complete findings retain bounded veto authority. | canonical compiler, model/parent intake, coverage boundary, and regressions | 116 focused compiler/intake/multi-stage-planning tests; Ruff; repository-governed mypy over 112 source files; `git diff --check`; full suite 916 passed with four unchanged environment-only failures (two missing Playwright; two subprocess interpreter importability); no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG4 deterministic coverage and veto-only audit | Added a code-owned SourceLedger-to-claim-to-obligation-to-terminal structural coverage validator. It runs before the model audit, rejects missing/unknown/uncovered source-unit lineage, and repeats graph/terminal reachability validation. A coverage `COMPLETE` cannot make an invalid graph READY; optional audit unavailability also cannot reject a deterministically admitted task, while clarification/unsupported responses retain downgrade authority. | obligation coverage and intent compiler; intake/coverage regressions | 126 focused tests; full suite 913/917 in this environment. Four unrelated environment prerequisites remain: missing Playwright (two Chromium tests) and uninstalled editable project in the active interpreter's subprocess (two architecture tests). Ruff and mypy pass 112 source files; no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG3 parent proposal normalization | Added a model-free `ParentSemanticProposalCompiler` for untrusted parent semantic proposals. It requires the same bounded SourceLedger, source binding, Runtime-derived graph identities, deterministic validation, policy, and immutable TaskSpec admission as the model route. A complete typed TaskSpec remains a separate API. | intent compiler and intake regressions | 69 focused intake/pipeline tests; Ruff; repository-governed mypy over 112 source files; no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG3 provider proposal-identity slice | Provider claim/obligation IDs are now proposal-local references only. Runtime validates source-unit membership, derives bounded semantic IDs for the accepted graph, rewrites edges/value dependencies deterministically, and gives coverage review the normalized graph. A narrow review-reference bridge preserves pre-SG3 replay fixtures without allowing a provider handle into `TaskSpec`. Deterministic source coverage and removal of proposal-shape compatibility remain open. | intent compiler; intake, pipeline, and BrowserGym-adapter regressions | 120 focused tests pass; mypy passes 112 source files; full suite is 909/913 in this environment. The four failures are pre-existing environment prerequisites: Playwright is absent for two Chromium tests and the active interpreter's subprocess cannot import the editable project for two architecture tests. No benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG2 canonical graph foundation | Added generic Runtime-owned canonical effect-to-claim/obligation construction, stable ids/provenance, typed evidence contracts, and source-ledger membership rejection. The model-draft normal path remains explicitly un-migrated. | canonical compiler, task-intake contracts, tests, current plan | 913 tests; Ruff; repository-governed mypy over 112 source files; `git diff --check`; no benchmark/provider/GitHub Actions/`.env`/push or score claim |
| 2026-07-26 | M8.2A SG1 source-ledger lineage | Added a deterministic, bounded SourceLedgerBuilder before model intake. It owns whole-request/clause ids, exact request spans, hashes, metadata-only external references, redacted trace projection, and canonicalization of the legacy raw-text alias; over-bound input rejects before a model call. | source ledger, intent compiler, intake/coordinator/BrowserGym identity tests, current plans | 911 tests; Ruff; repository-governed mypy over 111 source files; `git diff --check`; no benchmark/provider/GitHub Actions/`.env`/push or score claim |
| 2026-07-25 | M8.2A repair-failure observability | Added a typed, redacted `IntentDraftRepairFailed` trace event when the bounded repair call cannot decode; it records only the immutable repair Prompt version and error type, while the reservation-based compiler count still accounts for the attempted call. | intent compiler, intake tests, current plan | targeted repair trace test; 907 tests; Ruff; repository-governed mypy over 110 source files; `git diff --check`; no benchmark/provider/GitHub Actions/`.env`/push or score claim |
| 2026-07-26 | M8.2A schema/graph authority audit | Audited clean source revision `bba582c`; froze code-owned SourceLedger, CanonicalObligationCompiler, deterministic coverage, veto-only model audit, and SG1-SG7 ordering without changing Runtime behavior | schema-authority governance, architecture/boundary, task-intake, project/current plans | 907 tests; Ruff; repository-governed mypy over 110 source files; no benchmark/provider/GitHub Actions/.env/push or score claim |
| 2026-07-25 | M8.2B provider-profile launcher boundary | Removed the launcher's unconditional local-profile override. The sole launcher now accepts explicit local/mistral/gemini/zhipu selection, retains Ollama preflight only for local, and leaves the selected provider in immutable run identity. | BrowserGym launcher, current plan | Gemini-profile runtime preflight passed without a remote call; succeeding full local gate passed |
| 2026-07-25 | M8.2B protected intake recheck | Ran only `enter-date` and `text-transform` after fixed Python/BrowserGym/Ollama preflight. The first `f2f689a` wave invalidated on schema incompatibility; `05bd94c` then completed all four 2-task x 2-seed episodes and `58f01ff` reproduced both seed-0 failures. Every observed case failed before action at typed sourced-obligation intake; zero provider/retry failure. | immutable `/tmp/affordance-m8.2b-protected-*` run reports/traces; current plan | negative evidence only; no PR breadth, diagnostic, nightly, release, remote provider, GitHub Actions, `.env`, push, or score claim |
| 2026-07-25 | M8.2A immutable repair identity | Factored the compiler-stage checkpoint identity into one pure construction and directly tested that the initial compiler and repair Prompt versions are distinct and both participate in immutable resume identity | BrowserGym checkpoint identity, adapter test | targeted identity test, full local gate pending this revision; no benchmark or provider run |
| 2026-07-25 | M8.6 containment ratchet | Re-audited active-perception ownership: `ActivePerceptionFlow` already owns gap/probe/capture/resolution while Coordinator commits state and canonical trace; lowered the feature-freeze line ceiling to the measured 3520-line surface | containment test, boundary, implementation status | containment test, full local gate pending this revision; no benchmark or provider run |
| 2026-07-25 | M8.3 normal-entrypoint provider recovery | Attached the existing evidence-backed fallback-provider owner to `GeneralistTaskPipeline` only when its compiler has a real configured multi-profile model; explicit handlers remain authoritative and single-provider/context/schema paths remain unavailable | task pipeline, model recovery, pipeline test | focused recovery/pipeline tests; Ruff; repository-governed mypy over 110 source files; no provider call, browser benchmark, GitHub Actions, `.env`, push, or score claim |
| 2026-07-25 | M8.2A intake repair audit | Replaced inferred BrowserGym intake-call accounting with the compiler's bounded reservation count; bound the repair call to its own Prompt identity in trace/checkpoint metadata; corrected `missing_source_claims`; retained fail-closed policy, ambiguity, stale, and unsafe-repair behavior | intent compiler, BrowserGym runner/checkpoint metadata, intake and runner tests, current plan | 902 tests; Ruff; repository-governed mypy over 110 source files; `git diff --check`; no BrowserGym matrix, remote provider, GitHub Actions, `.env`, push, or score claim |
| 2026-07-24 | M8.6 reclosure | Enforced strict probe authority and semantic evidence, extracted typed active-perception flow, invoked real recovery owning ports, rejected no-op progress, reduced the Coordinator ratchet, and published real four-profile Runtime evidence | active perception/session, recovery dispatcher, Runtime evidence projection, G5 rollout, Coordinator, tests, synchronized plans/status | implementation `c939051`; 680 tests; Ruff; mypy over 100 source files; immutable 11-case rollout passed with 82-file hash index; no remote model, BrowserGym benchmark, GitHub Actions, score claim, `.env`, or push |
| 2026-07-24 | M8.6 closure audit / responsibility containment | Reopened G2.5, G3, and G5 empirical closure; froze Coordinator feature growth; added normative ownership, typed-result, no-op-success, budget-narrowing, and evidence-level gates | closure audit, responsibility boundary, README, plans, status | audited clean `f4c3308`; 666 tests after adding the containment ratchet; Ruff; mypy over 96 source files; no remote model/browser/score run |
| 2026-07-23 | M8.6 G1 / behavioral governance and proposal provenance | Added runtime-authored source identity for model, rule, parent, skill, recovery, external-policy, and runtime-terminal proposals; rejected missing provenance before binding; persisted provenance in trace/state; added generic target-scope and unrequested-effect gates with camelCase/hyphen/morphology normalization and a non-BrowserGym anti-specialization matrix | proposal contracts/validator, Coordinator, all production proposal sources, governance matrix, plans/evidence | 567 tests; Ruff; mypy with optional imports across 90 source files; paraphrase positive control and distractor/extra-control/ambiguity/unrelated-interface/unrequested-terminal/destructive-effect/scope-expansion negatives; G1 complete; `m8.6-g1-behavior-provenance-20260723.md` |
| 2026-07-23 | M8.6 G1 / physical compatibility containment | Moved historical objective parsers, terminal exposure, repair recipes, semantic rewrites, and compiler callback assembly out of the strict Planner module; retained only a lazy explicit replay entrypoint and reverse dependency on shared proposal contracts | `compatibility_planner_algorithms.py`, strict Planner lazy boundary, architecture controls, plans/evidence | 557 tests; 95 focused tests; Ruff; mypy with optional imports across 90 source files; subprocess proof that strict import/construction does not load compatibility while the historical profile does; `m8.6-g1-physical-containment-20260723.md`; G1 remains open for broader behavioral controls and proposal provenance |
| 2026-07-22 | Runtime-first R8 / module containment closure | Audited extracted Core collaborators, typed boundaries, authoritative state/trace ownership, benchmark-vocabulary isolation, and BrowserGym facade compatibility; documented the legacy one-contract conformance harness as non-authoritative | executable R8 architecture boundary test, plans/audit/evidence | 522 tests; Ruff; mypy with optional imports across 89 source files; no Core benchmark vocabulary/adapter import; no collaborator `StateKernel` construction; observer/encoder/runner/protocol/report facade identity checks; `runtime-r8-closure-20260722.md` |
| 2026-07-23 | M8.2B R9 / native labels and explicit form obligations | Kept descriptive native labels out of the action inventory, associated explicit/nested/adjacent labels with controls, and compiled multi-field exact-value obligations with verified-target progress and ambiguity fallthrough | generic DOM observation, semantic compiler/planner, non-BrowserGym controls, clean bounded BrowserGym ladder | clean `b4e596e`: original failures 2/2, form family 20/20, PR 18/18; complete diagnostic 29/30 with one retained planning-budget envelope caused by exact-value versus prefix/suggestion semantics; 528 tests, Ruff, mypy 89 source files; `m8.2b-r9-form-obligations-20260723.md` |
| 2026-07-23 | M8.2B R9 / typed suggestion selection | Separated exact form literals from prefix/suffix suggestion relations; compiled prefix entry, uniquely observed option activation, matching-current progress, and unique terminal exposure with ambiguity fallthrough | default semantic registry, Generalist typed obligations, generic DOM controls, clean immutable BrowserGym ladder | clean `7d0ada0`: original failure 1/1, task family 10/10, PR 18/18, diagnostic 30/30, frozen nightly 300/300 reward 1.0; zero missing/runtime/envelope/provider/retry/circuit failures; 532 tests, Ruff, mypy 89 source files; `m8.2b-r9-suggestion-selection-20260723.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym report and protocol containment | Separated versioned profile metadata and seed-major protocol from FailureEnvelope construction/clustering and aggregate report publication; matrix retains scheduling, circuit state, and atomic checkpoints; unknown release tasks use observed action capability evidence or an explicit unresolved evidence gap without task-name dispatch | `browsergym_protocol.py`, `browsergym_report.py`, matrix compatibility wiring, direct taxonomy/report tests, plans/evidence | 519 tests; Ruff; mypy with optional imports across 89 source files; 66 focused tests; compatibility, declared-family precedence, observed-capability fallback, and no-action evidence-gap controls; `runtime-r8-browsergym-report-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym episode runner containment | Extracted one-episode setup, Coordinator traversal, backend execution, external-policy lifecycle, model/context trace projection, local source serving, and killable process timeout/exit/cleanup while suite scheduling, frozen identity, checkpoints, circuit breaking, and reports remain outside | `browsergym_episode_runner.py`, bridge facade wiring, direct lifecycle/isolation tests, plans/evidence | 515 tests; Ruff; mypy with optional imports across 87 source files; 69 focused tests; facade identity, forced timeout termination/cleanup, and empty-worker-result exit-code controls; `runtime-r8-browsergym-episode-runner-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym encoder containment | Extracted external-policy contract attachment, semantic-action translation, validated gesture and point encoding, native value conversion, and action-specific verifier mapping while Core retains dual-target binding, currentness, route, policy, capability, and preflight authority | `browsergym_encoder.py`, bridge facade wiring, direct encoder/adapter/Core tests, plans/evidence | 512 tests; Ruff; mypy with optional imports across 86 source files; 88 focused tests; invalid geometry/missing binding/value/verifier negative controls; facade compatibility and Core gesture invariants; `runtime-r8-browsergym-encoder-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym observer containment | Extracted coherent capture, observation metadata normalization, bounded epoch-drift retry, drag geometry/fingerprint enrichment, DOM grounding refresh, screenshot fallback, visual candidate fusion, and JSON-safe adapter metadata while preserving bridge facade imports and Runtime ownership | `browsergym_observer.py`, shared BrowserGym backend constant, bridge facade wiring, direct observer/adapter tests, plans/evidence | 498 tests; Ruff; mypy with optional imports across 85 source files; 76 focused BrowserGym/observer/boundary tests; retry-cap, unrelated-error, serialization, geometry, visual, and facade compatibility controls; `runtime-r8-browsergym-observer-20260722.md` |
| 2026-07-22 | Runtime-first R8 / planner model orchestration containment | Extracted provider-neutral candidate data/dynamic schemas, structured model invocation, bounded same-context repair, redacted exhaustion, and call-budget reservation hooks while Generalist retains Prompt/configuration, semantic validation/binding, fallback order, and trace assembly | `planner_model_orchestrator.py`, Generalist policy wiring and compatibility wrappers, direct provider-neutral tests, plans/evidence | 494 tests; Ruff; mypy with optional imports across 84 source files; 88 focused tests; first-pass/repair/schema-failure/budget/exhaustion negative controls; public candidate JSON Schema field equivalence; `runtime-r8-planner-model-orchestrator-20260722.md` |
| 2026-07-22 | Runtime-first R8 / default SemanticCompiler registry containment | Moved ordered rule/constraint assembly, applicability declarations, evidence metadata, operation scopes, output kinds, and negative examples behind a typed factory while Generalist retains unchanged semantic algorithms and a compatible public entrypoint | `default_semantic_compilers.py`, Generalist callback wiring, direct generic factory tests, plans/evidence | 488 tests; Ruff; mypy with optional imports across 83 source files; exact precedence/evidence assertions, empty/unsupported-context negative controls, existing non-BrowserGym DOM integration, and benchmark-vocabulary boundary; `runtime-r8-default-semantic-registry-20260722.md` |
| 2026-07-23 | M8.6 G1 / proposal validation and compatibility containment | Added one Coordinator-owned PlannerProposalValidator before completion/binding/approval/execution; preserved clarification in strict mode; renamed the historical registry as compatibility-only; added form/suggestion/disclosure task-shape controls and strict DOM/visual/WoT conformance | `planning.py`, Coordinator trace, `compatibility_semantic_compilers.py`, strict planner, generic behavior and cross-surface tests, plan/evidence | 554 tests; Ruff; mypy across 89 source files; `m8.6-g1-proposal-validation-20260723.md`; G1 remains open for broader controls and physical algorithm extraction |
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
