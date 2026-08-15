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
  -> build AgentContext and semantic ActionSpace
  -> model chooses a semantic decision
  -> Runtime validates, binds, and executes
  -> acquire a fresh post-action observation
  -> evaluate the action and task
  -> continue or finish
```

The model sees public semantics such as roles, labels, state, relations, and call-local entity references. The target
context also carries recent semantic actions and their verified outcomes. The Runtime keeps backend routes, selectors,
coordinates, handles, credentials, and all remaining-budget counters private; it terminates the loop and filters the
currently available tools.

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

The R2 checkpoint remains available in Git history. This branch introduces the replacement target: one `RunState`,
one `StepResult` per policy outcome, and a readable core loop. Existing world, adapter, action, evaluation, and model
boundaries are reused. The default CLI still uses the legacy loop until its decision paths are migrated one at a time;
the simplified path is currently explicit through `TargetRuntime.run_core_task`. Legacy control modules are migration
sources, not extension points.
