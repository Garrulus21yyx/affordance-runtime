# Affordance Runtime

Affordance Runtime is a planner-neutral GUI agent execution runtime. It binds
GUI actions to versioned environment state, scoped capabilities, expected
effects, verifier evidence, trace, benchmark scoring, and regression-gated
harness evolution.

The repository implements the complete M0-M8 controlled web profile: three
reproducible Web/SaaS scenarios, trace and artifacts, independent verification,
distinct seeded layouts, baseline/ablation evaluation, executable evolution,
external parent integration, and held-out, visual, and official MiniWoB++
generalization evidence. Service-grade distributed options remain explicitly
deferred.

Planning follows two horizons: the current implementation plan is authoritative
for code and release scope, while the complete architecture blueprint preserves
future service-grade options without making them current requirements.

It is not another in-page web copilot or a thin browser automation wrapper. Its
core is:

- a unified affordance envelope for DOM, visual, accessibility, API, and device
  surfaces
- a state kernel that preserves goals, constraints, evidence, hidden-state
  hypotheses, and pending obligations across long tasks
- action contracts with environment revision, preconditions, expected effects,
  verifier plans, risk levels, capabilities, idempotency, and compensation
- preflight gates that reject stale observations before an action is executed
- trace events for debugging, replay, evaluation, and skill mining
- a harness evolution registry that quarantines proposed skills, policies,
  postconditions, and benchmark fixtures until regression replay passes
- integration surfaces for standalone reference use and subagent use by Codex,
  Claude, OpenHands, LangGraph, AutoGen, or any agent framework that can call
  tools

## Current Status

Implemented current profile:

- typed affordance, action, receipt, risk, trace, and benchmark models
- migrated DOM, Set-of-Mark, and WoT adapter code
- package-safe browser session wrapper with injectable Playwright-compatible driver
- DOM, visual-pointer, and WoT contract executors with explicit backend dispatch
- confidence/cost-aware backend selection and bounded recovery decisions
- declarative precondition evaluation and JSONL trace persistence
- single-contract execution path for debug and unit testing
- initial capability, verifier, state, benchmark, and evolution modules
- task-level `RunCoordinator` with validated state transitions and budgets
- snapshot/page/target/TTL-bound contracts with canonical hashes
- single-use approval tokens bound to run, contract, state, capability, and approver
- immediate preflight re-observation and independent post-action observation
- structural verification reports separated from executor receipts
- filesystem artifacts for observations, screenshots, receipts, verification, and JSONL trace
- resettable pricing fixture, deterministic planner, CLI gold path, and Direct Playwright baseline
- reversible settings fixture with persisted API verification
- approval-gated report export with a bound token and file-hash receipt
- DOM, visual SoM, and WoT actions through the shared Coordinator path
- opportunity-denominator benchmark metrics and JSON/Markdown/CSV report writers
- deterministic target/modal/async/transient-error/download perturbations
- executable Direct Playwright, primitive-agent, Full Runtime, and four-ablation matrix
- failure classification, SHA-bound executable evolution payloads, fresh candidate replay, persisted decisions, and rollback
- task-level submit/execute/status/approve/cancel/result/evidence/trace service and parent-agent tool adapter
- CI, package build, environment manifests, versioned reports, and one-command clean-checkout reproduction
- newline-delimited external task JSON-RPC and a real compiled LangGraph parent running against a separate runtime process
- deterministic distinct-layout seeds and held-out layouts with unseen controls and distractors
- screenshot-pixel visual grounding through the shared visual contract executor without DOM coordinates
- a pinned official MiniWoB++ curated adapter with reset, instruction, reward, diagnostics, and report aggregation
- a digest-pinned, non-root Playwright Compose profile for fixture, tests, benchmark, and mounted evidence
- an optional real node-wot conformance profile that reaches one independently observed state through DOM, screenshot/SoM, and WoT

Verified evidence:

- all 58 unit/integration tests pass with Ruff and mypy
- clean commit `e463e16` reproduces the complete M0-M8 gate via `./scripts/reproduce_local.sh`; milestone-specific historical freezes remain in `docs/evidence/`
- Full Runtime passes all three scenarios across three distinct seeded layouts with zero constraint violations, unsafe side effects, and verifier false accepts
- real Chromium parent-agent flow returns evidence/trace, blocks export before approval, and succeeds after scoped approval
- a no-verifier false accept produces a SHA-bound verifier patch; a fresh candidate passes six new Chromium replays with zero safety regression, and persisted rollback is verified
- a real LangGraph 1.2.9 parent completes pricing and approval-gated export over an external process boundary with no primitive GUI tools
- three distinct training layouts and six held-out scenario runs pass with Full Runtime task success 1.0 and unsafe side-effect rate 0.0
- five screenshot-grounded visual runs detect five distinct boxes and succeed without DOM coordinates
- 18 pinned official Farama MiniWoB++ episodes across click, type, select, dialog, sequence, and form pass with raw-reward success 1.0

Next evidence gates: finish M8.1 clean-checkout host/container agreement, then
M8.2 public benchmark expansion and M8.3 recovery-cascade evolution. M9 remains
conditional on restart/waiting evidence.

Explicitly deferred beyond the current profile:

- durable queues, browser worker pools, distributed checkpoints, and multi-tenant infrastructure
- desktop/mobile coverage and unrestricted live-site credential workflows
- automatic arbitrary source-code mutation
- Picture-in-Picture UI until a measured observer/takeover need justifies it

## Documents

- [Project Plan](docs/project-plan.md)
- [Implementation Status and Forward Gates](docs/implementation-status.md)
- [Current Implementation Plan](docs/current-implementation-plan.md)
- [Complete Architecture Blueprint](docs/complete-architecture-blueprint.md)
- [Design Freeze and Implementation Gates](docs/design-freeze.md)
- [Architecture](docs/architecture.md)
- [Agent Orchestration and Live Feedback](docs/orchestration-and-feedback.md)
- [Harness Evolution](docs/harness-evolution.md)
- [Trace and Evaluation](docs/trace-and-evaluation.md)
- [Benchmark Plan](docs/benchmark-plan.md)
- [Integrations](docs/integrations.md)
- [Open Source Landscape](docs/open-source-landscape.md)
- [Migration From A Modular Action System](docs/migration-from-modular-action-system.md)

Scenario specs:

- [Pricing Extraction](docs/scenarios/pricing-extraction.md)
- [Reversible Settings Update](docs/scenarios/settings-update.md)
- [Approval-Gated Report Export](docs/scenarios/approval-gated-report-export.md)

Container reproduction:

```bash
./scripts/reproduce_container.sh
AFFORDANCE_WOT_PROOF=1 ./scripts/reproduce_container.sh
```

## One Sentence

Affordance Runtime turns GUI environments into versioned, typed, verifiable
action spaces so agents can execute, observe, recover, replay, evaluate, and
evolve from their own interaction traces.

## What This Project Demonstrates

Affordance Runtime is designed as a GUI agent harness, not just a browser agent
demo:

- cross-surface perception: DOM, visual Set-of-Marks, accessibility tree,
  Playwright state, and WoT-style device descriptions
- unified affordance layer: Page Affordance Model, Visual Affordance Model,
  Thing Affordance Model, Accessibility Affordance Model, and shared action
  contracts
- bounded orchestration: task envelope -> state kernel -> budgeted observation
  -> versioned affordance snapshot -> planner port -> action contract ->
  capability gate -> preflight -> execute -> receipt -> post-action observation
  -> verifier ladder -> recovery or report
- live environment feedback through post-action observation first, with
  continuous watcher/event bus deferred until the gold path proves it needs one
- trace-first execution: every observation, decision, action, verification, and
  recovery step is recorded for replay and diagnosis
- evaluation loop: benchmark tasks, postcondition oracles, failure taxonomy,
  metrics aggregation, regression replay, and versioned reports
- assisted harness evolution: failed traces can propose reusable skills, policy
  patches, postcondition improvements, and regression fixtures after benchmark
  readiness gates pass
- subagent interfaces: CLI first, then MCP task API; REST and many framework
  adapters are optional later work

## Flagship Scenario

The first full-chain scenario is a Web GUI runtime that can run standalone with
a reference planner or be called as a subagent.

Example:

```text
Parent agent:
  Find the pricing page, extract plan limits, and return evidence.

Affordance Runtime:
  observe page
  build affordance model
  plan or script bounded navigation
  execute actions through Playwright
  verify page state from structural evidence
  extract structured result
  return trace, screenshots, evidence, and failure/recovery summary
```

The benchmark story should be led by realistic Web/SaaS workflows, not the
smart-room demo. The runtime should prove generalization through controlled web
environments first, then keep non-web adapters as secondary evidence:

- custom SaaS workflows for form filling, invoice download, pricing extraction,
  reversible admin settings, report export, and support-case creation
- WebArena-style mock environments for realistic multi-step tasks, state drift,
  modals, multi-tab state, and failure injection
- MiniWoB++ for atomic web actions such as click, type, select, and form fill
- VisualWebArena-style and Set-of-Mark fixtures for visual fallback and
  mark-level grounding checks
- local smart-room / WoT demo only as a non-web adapter proof, not the project
  main story

OSWorld, desktop-native apps, and mobile apps are future expansion targets after
the web harness, verifier ladder, trace replay, and evolution loop are stable.

## Positioning

PageAgent lives inside a webpage.

Browser-use and Stagehand help agents control browsers.

Affordance Runtime lives outside environments and gives agents a reliable action
layer: action contracts, postcondition checks, recovery, trace, evaluation, and
harness evolution.

## Recommended MVP

The first implementation should be intentionally narrow:

```text
v0.1 Web GUI Core
  local SaaS pricing fixture
  DOM observer
  Playwright executor
  Page Affordance Model
  State Kernel
  Affordance Lease
  ActionContract schema_version=1.0
  Capability Gate
  post-action Verifier Ladder
  Trace events and artifact writer
  CLI gold path
  direct Playwright baseline
```

Then add reliability:

```text
v0.2 Reliability
  reversible settings fixture
  approval-gated export fixture
  stale target injection
  selector drift injection
  modal recovery
  approval gate
  benchmark report
  ablations: no lease, no verifier, no capability gate, no recovery
```

Do not start with every desktop, mobile, and device surface. The architecture
should be cross-surface, but the first runnable gold path should prove the
runtime on web GUI tasks.

## Resume Summary

Implemented a planner-neutral GUI execution runtime that abstracts DOM, visual
screenshots, accessibility state, and device descriptions into a unified
affordance model. The runtime uses versioned action contracts, stale-state
preflight rejection, scoped approvals, verifier ladders, bounded recovery,
artifact-backed trace evaluation, and regression-gated evolution from failed
interaction traces.

## Code Layout

The implementation is in `src/affordance_runtime`:

- `contracts.py`: affordances, leases, action contracts, receipts, risk.
- `state_kernel.py`: long-horizon task state and evidence obligations.
- `runtime.py`: bounded contract execution loop.
- `coordinator.py`: authoritative multi-step task state machine and budgets.
- `artifacts.py`: run, observation, screenshot, receipt, download, verification, and trace persistence.
- `browser_session.py`: package-safe browser lifecycle and coherent DOM capture.
- `executors.py`: DOM, visual-pointer, and WoT contract executors.
- `routing.py`: backend confidence tracking and cost-aware routing.
- `recovery.py`: bounded, side-effect-aware recovery decisions.
- `verification.py`: declarative preflight checks and verifier ladder.
- `safety.py`: scoped capability and approval gate.
- `trace.py`: causal trace events and JSONL persistence.
- `evolution.py`: regression-gated evolution registry.
- `evolution_replay.py`: failure classification to proposal/replay/before-after decision.
- `fixtures.py`: resettable pricing, settings, and approval-gated export application.
- `planners.py`: deterministic scenario planners through `PlannerPort`.
- `integrations/`: stable task service, external task JSON-RPC, local scenario runner, and real LangGraph parent.
- `adapters/dom.py`: migrated DOM transduction.
- `adapters/som.py`: migrated Set-of-Marks grounding.
- `adapters/wot.py`: migrated Thing Description parsing.
- `benchmarks/`: local matrices, metrics, generalization aggregation, screenshot grounding, and pinned official MiniWoB++ execution.
