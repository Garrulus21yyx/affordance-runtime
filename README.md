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
  -> compile the current per-turn Tool Registry
  -> project task, current observation, verified progress, and recent steps
  -> model chooses exactly one offered tool
  -> Runtime validates and resolves one local result, or binds and executes one GUI action
  -> after GUI dispatch, acquire a fresh observation and evaluate the action and task
  -> continue or finish
```

The model sees one current public world, verified task progress, and up to eight mechanically paired recent
action/result summaries. Tool schemas are compiled for the current turn. Runtime keeps backend routes, selectors,
coordinates, handles, credentials, and all budget counters private; it validates, executes, refreshes observation,
evaluates outcomes, and terminates the loop.

When required task information is unavailable, the model may pause with `ask_user`. That decision contains a concrete
question that the caller can show verbatim plus the input fields expected from the reply. Runtime preserves and resumes
that request; confirmations for risky actions use the separate Runtime-owned confirmation path.

Ordinary GUI-effect tasks end as soon as `TaskEvaluator` verifies completion. If a task explicitly requests a textual
result, the PydanticAI path permits one native final response only after the requested outputs are verified; the model
does not call a separate completion tool.

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
  model/       PydanticAI provider/tool bridge, current tool catalog, and model context
  benchmarks/  benchmark integration; never product semantics
```

The target boundaries are described in [Architecture](docs/architecture.md).
Benchmark profiles and current evidence are in [Benchmark](docs/benchmark.md).
Extension rules are in [Extending](docs/extending.md).

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev,browsergym,visual,pydantic-ai]'
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
Use `LLM_MODEL_ADAPTER=pydantic-ai` for models that return standard native tool calls. Use
`LLM_MODEL_ADAPTER=compact-json` for `glm-4.1v-thinking-flashx`: the model is retained for visual operation, but its
non-standard response envelope requires the bounded compact compatibility path. Both adapters feed the same catalog,
context, typed decisions, and `CoreAgentLoop`.

## Current simplification boundary

The R2 checkpoint remains available in Git history. The current branch keeps the existing world, adapter,
semantic-action, tool, execution, and evaluation boundaries and uses one `CoreAgentLoop`, one `RunState`, one
`StepResult` per turn, one stable GUI-agent prompt, and one compact model projection. The public Runtime, CLI, and
target benchmark harness all use this core. The former control reducer, transition, feedback, session, and legacy-loop
modules have been removed. PydanticAI owns standard native tool transport, while 4.1V keeps one bounded compact wire
adapter. Superseded structured-package, native-tool, automatic-fallback, and model-conformance paths are deleted;
running paired live benchmarks is the next gate.
