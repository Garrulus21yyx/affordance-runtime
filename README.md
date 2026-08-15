# Affordance Runtime

Affordance Runtime is a research-oriented GUI agent runtime for **adaptive multi-source observation**.
It combines structured and visual evidence into one semantic world, lets a model choose semantic actions,
keeps selectors and coordinates private, and requests a fresh observation after each dispatch.

The project is built to answer one question:

> Can a GUI agent retain task success while observing only the sources that are useful for the current decision?

## Core loop

```text
TaskGoal
  -> choose observation sources
  -> acquire DOM / AX / visual / WoT evidence
  -> fuse one current WorldObservation
  -> compile the current semantic ToolCatalog
  -> project task, current observation, verified progress, and recent steps
  -> model chooses exactly one offered tool
  -> Runtime validates, binds, and executes
  -> acquire a fresh post-action observation
  -> evaluate the action and task
  -> continue or finish
```

The model sees one current public world, verified task progress, and up to eight mechanically paired recent
action/result summaries. Tool schemas are compiled for the current turn. Runtime keeps backend routes, selectors,
coordinates, handles, credentials, and all budget counters private; it validates, executes, refreshes observation,
evaluates outcomes, and terminates the loop.

## What belongs in the project

- source adapters with one shared observation contract;
- cost- and need-aware observation selection;
- provenance-preserving world fusion;
- semantic actions with current private bindings;
- one compact model context;
- post-action effect and task evaluation;
- BrowserGym benchmarks that measure success, observation cost, model cost, and recovery.

This project does not implement a durable event ledger, predictive world model, multi-agent platform,
general workflow engine, or production-grade replay system.

## Repository map

```text
src/affordance_runtime/
  world/       observation contracts, source selection, fusion, environment port
  surfaces/    DOM, BrowserGym, visual, WoT, and HTTP adapters
  actions/     semantic action space, admission, grounding, private binding
  agent/       compact context, policy boundary, run state, and core loop
  evaluation/  action-effect and task-completion evaluation
  model/       provider-neutral model ports and provider adapters
  benchmarks/  benchmark integration; never product semantics
```

The target boundaries are described in [Architecture](docs/architecture.md).
Benchmark profiles and current evidence are in [Benchmark](docs/benchmark.md).
Extension rules are in [Extending](docs/extending.md).

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev,browsergym,visual]'
```

Run the focused test suite:

```bash
.venv/bin/pytest tests/unit tests/integration
```

Run the command-line agent against a browser target:

```bash
affordance-runtime run \
  --target https://example.com \
  --instruction "Complete the requested task" \
  --boundary task-boundary.json
```

`task-boundary.json` supplies stable success criteria, allowed effects, requested outputs, and budgets.
Provider configuration is read from environment variables; secrets never enter the public world or benchmark reports.

## Current simplification boundary

The R2 checkpoint remains available in Git history. The current branch keeps the existing world, adapter,
semantic-action, tool, execution, and evaluation boundaries and uses one `CoreAgentLoop`, one `RunState`, one
`StepResult` per turn, one stable GUI-agent prompt, and one compact model projection. The public Runtime, CLI, and
target benchmark harness all use this core. The former control reducer, transition, feedback, session, and legacy-loop
modules have been removed; paired live benchmark evidence is the next gate, not another control architecture.
