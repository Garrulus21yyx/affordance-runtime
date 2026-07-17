# Affordance Runtime

Affordance Runtime is a planner-neutral GUI agent execution runtime. It binds
GUI actions to versioned environment state, scoped capabilities, expected
effects, verifier evidence, trace, benchmark scoring, and regression-gated
harness evolution.

The repository is currently an executable skeleton plus implementation plan, not
yet a complete Web GUI runtime. The immediate goal is to turn the skeleton into
a reproducible Web/SaaS gold path with trace, verification, baseline, and
benchmark evidence.

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

Implemented skeleton:

- typed affordance, action, receipt, risk, trace, and benchmark models
- migrated DOM, Set-of-Mark, and WoT adapter code
- single-contract execution path for debug and unit testing
- initial capability, preflight, verifier, state, trace, and evolution modules

Partial:

- long-task State Kernel lifecycle
- lease/preflight semantics beyond revision equality
- task constraints and approval token binding
- benchmark metric protocol

Planned before claiming a complete runtime:

- Playwright observer and executor
- task-level run context and explicit state machine
- post-action observation and verification reports
- artifact-backed trace writer
- local SaaS fixture and benchmark runner
- CLI gold path
- bounded recovery policy
- baseline and ablation reports
- task-level MCP interface
- assisted harness evolution after benchmark freeze

## Documents

- [Project Plan](docs/project-plan.md)
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

Designed and prototyped a planner-neutral GUI execution runtime skeleton that
abstracts DOM, visual screenshots, accessibility state, and device descriptions
into a unified affordance model. The planned system uses versioned action
contracts, stale-state preflight rejection, capability gating, verifier ladders,
live environment feedback, failure recovery, trace evaluation, and assisted
harness evolution from failed interaction traces.

## Code Skeleton

The initial skeleton is in `src/affordance_runtime`:

- `contracts.py`: affordances, leases, action contracts, receipts, risk.
- `state_kernel.py`: long-horizon task state and evidence obligations.
- `runtime.py`: bounded contract execution loop.
- `verification.py`: preflight checks and verifier ladder.
- `safety.py`: scoped capability and approval gate.
- `trace.py`: causal trace events.
- `evolution.py`: regression-gated evolution registry.
- `adapters/dom.py`: migrated DOM transduction.
- `adapters/som.py`: migrated Set-of-Marks grounding.
- `adapters/wot.py`: migrated Thing Description parsing.
- `benchmarks/`: benchmark tasks, suites, and runtime-specific metrics.
