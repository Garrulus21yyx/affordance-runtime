# Affordance Runtime

Affordance Runtime is a harness-first GUI agent runtime for reliable action
execution across web pages, visual interfaces, and device-like environments.

It is not another in-page web copilot or a thin browser automation wrapper. Its
core is:

- a unified affordance model for DOM, visual, accessibility, and device surfaces
- an event-driven runtime that observes, plans, acts, verifies, and recovers
- action contracts with preconditions, expected effects, risk levels, and
  fallbacks
- full-fidelity traces for debugging, replay, evaluation, and skill mining
- a harness evolution loop that turns failures into reusable skills, policy
  patches, postconditions, and regression cases
- integration surfaces for standalone use and subagent use by Codex, Claude,
  OpenHands, LangGraph, AutoGen, or any agent framework that can call tools

## Documents

- [Project Plan](docs/project-plan.md)
- [Architecture](docs/architecture.md)
- [Agent Orchestration and Live Feedback](docs/orchestration-and-feedback.md)
- [Harness Evolution](docs/harness-evolution.md)
- [Trace and Evaluation](docs/trace-and-evaluation.md)
- [Integrations](docs/integrations.md)
- [Open Source Landscape](docs/open-source-landscape.md)

## One Sentence

Affordance Runtime turns GUI environments into typed, verifiable action spaces
so agents can execute, observe, recover, replay, evaluate, and evolve from
their own interaction traces.

## What This Project Demonstrates

Affordance Runtime is designed as a complete GUI agent harness, not just a
browser agent demo:

- cross-surface perception: DOM, visual Set-of-Marks, accessibility tree,
  Playwright state, and WoT-style device descriptions
- unified affordance layer: Page Affordance Model, Visual Affordance Model,
  Thing Affordance Model, and a shared action contract
- bounded orchestration: observe -> model -> plan -> act -> verify -> recover
  -> learn
- live environment feedback: DOM mutation, screenshot diff, URL navigation,
  modal detection, device state changes, and hazard detection
- trace-first execution: every observation, decision, action, verification, and
  recovery step is recorded for replay and diagnosis
- complete evaluation loop: benchmark tasks, postcondition oracles, failure
  taxonomy, metrics aggregation, regression replay, and versioned reports
- Hermes-style harness evolution: failed traces can generate reusable skills,
  policy patches, postcondition improvements, and regression fixtures
- subagent interfaces: CLI, REST, MCP server, LangGraph node, Codex/Claude tool
  adapter, and OpenHands-style browser/GUI operator

## Flagship Scenario

The first full-chain scenario is a Web GUI runtime that can run standalone or be
called as a subagent.

Example:

```text
Parent agent:
  Find the pricing page, extract plan limits, and return evidence.

Affordance Runtime:
  observe page
  build affordance model
  plan navigation
  execute actions through Playwright or visual fallback
  verify page state
  extract structured result
  return trace, screenshots, evidence, and failure/recovery summary
```

The runtime should also support controlled benchmark environments:

- MiniWoB++ for atomic web actions
- WebArena-style mock environments for realistic multi-step tasks
- VisualWebArena-style tasks for visual grounding
- local smart-room / WoT demo for non-web affordances
- custom SaaS workflows for form filling, invoice download, pricing extraction,
  and admin-panel operations

## Positioning

PageAgent lives inside a webpage.

Browser-use and Stagehand help agents control browsers.

Affordance Runtime lives outside environments and gives agents a reliable action
layer: action contracts, postcondition checks, recovery, trace, evaluation, and
harness evolution.

## Recommended MVP

The first implementation should be intentionally narrow:

```text
Web GUI Runtime
  DOM adapter
  screenshot / SoM adapter
  Playwright executor
  Page Affordance Model
  action contracts
  postcondition checker
  event bus
  trace logger
  recovery policy
  evaluation runner
  MCP server
  3 benchmark demos
```

Do not start with every desktop, mobile, and device surface. The architecture
should be cross-surface, but the first runnable gold path should prove the
runtime on web GUI tasks.

## Resume Summary

Designed and implemented a harness-first GUI Agent Runtime that abstracts DOM,
visual screenshots, accessibility state, and device descriptions into a unified
Affordance Model. The system supports action routing, postcondition
verification, live environment feedback, failure recovery, full trace replay,
benchmark evaluation, and Hermes-style harness evolution from failed
interaction traces.

