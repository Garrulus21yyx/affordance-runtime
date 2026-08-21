# Affordance Runtime

Affordance Runtime is a research-oriented runtime for **evidence-grounded, task-aware GUI control**.
It combines structured and visual evidence into one semantic world, lets a model choose semantic actions,
keeps selectors and coordinates private, and derives task-relative progress from each fresh observation.

The project is built to answer one question:

> Can a GUI agent combine adaptive observation with explicit task semantics, without turning the Runtime into a
> workflow engine or hiding progress inside model prose?

## Core loop

```text
TaskGoal
  -> acquire and fuse one current WorldObservation
  -> at task start/revision, model proposes an optional five-field Simple GoalPlan
       Ready                -> project the static plan directly into context
       NotRequired          -> continue without plan guidance
       Failed/Unsupported   -> trace unavailable guidance and continue normally
       NeedsInput           -> ask only for a missing user-owned goal fact
  -> project Task + fresh World + GoalPlan + bounded recent steps + current tools
  -> the single ActionPolicy reassesses plan items and chooses exactly one action/evidence request
  -> Runtime strictly validates, binds, executes, refreshes World, and evaluates effect/task completion
  -> continue or finish only through TaskEvaluator/native verifier
```

`GoalPlan` contains one to eight immutable items with only `id`, `objective`, `done_when`, `depends_on`, and `final`.
It is a semantic skeleton, not a recursive world-query program, workflow, mutable todo list, or progress authority.
Runtime validates only bounded structure and DAG integrity, then projects it directly. The ActionPolicy interprets
current progress from the fresh public World and recent action/effect pairs on every turn.

The stable policy requires fresh reassessment, preservation of already satisfied state, no repeated activation of an
already active toggle unless undo is requested, dependency-first work, and deferral of a final item until every
prerequisite is visibly satisfied. Runtime does not store item status, frontier, per-subject progress, or a goal
snapshot. Only `TaskEvaluator` or the environment's native verifier may declare completion.

Compiler failure remains advisory. Initial, schema-repair, and contract-repair provider attempts are captured
immediately with raw transcript, usage, latency, response ID, status, and violations; repairs cannot overwrite earlier
calls. Compiler attempts remain separate from ActionPolicy attempts in traces and benchmark metrics.

There is one decision-input chain and one `CoreAgentLoop`. Runtime keeps selectors, coordinates, bindings, credentials,
routes, safety decisions, confirmation facts, and budgets private. Adaptive visual evidence enters the same
`WorldObservation`; repetition or generic no-progress does not start a parallel visual or planning loop.

## What belongs in the project

- source adapters with one shared observation contract;
- cost- and need-aware observation selection;
- provenance-preserving world fusion;
- semantic actions with current private bindings, including finite two-endpoint `drag_to` where an adapter can
  honestly publish both endpoints;
- one compact model context;
- sparse model-backed goal compilation and deterministic task-relative goal evaluation;
- post-action effect and task evaluation;
- BrowserGym benchmarks that measure success, observation cost, model cost, and recovery.

This project does not implement an authoritative control/event ledger, predictive world model, mutable progress
store, nested Manager/Worker runtime, general workflow engine, or production-grade replay system.

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

Durable implementation constraints are in [Project agent policy](AGENTS.md). These five files are the maintained
project documentation set; implementation evidence stays in reports and traces rather than new design documents.

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
Set `LLM_GOAL_COMPILER_MODEL` to use a stronger model for the start/revision compiler role while retaining the same
active provider and transport implementation; when omitted, ActionPolicy and GoalCompiler share the configured model port.
Set `LLM_GOAL_COMPILER_MODE=disabled` only for an explicit no-guidance diagnostic; it injects the existing unavailable
compiler and makes zero compiler provider calls. The default remains `model`.

### Local experiment console

The loopback-only flight recorder lets one operator choose a frozen MiniWoB case, the ActionPolicy model, the
GoalCompiler model (or explicitly disable that role), and the perception/profile labels before launching the existing
formal `run-case` entrypoint:

```bash
set -a
source .env
set +a
export PYTHONPATH=src:tests
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m affordance_runtime.benchmarks.console.server
```

Open `http://127.0.0.1:8765`. The middle rail follows the append-only `trace.jsonl` while the right inspector exposes
the exact event JSON and runner output. Evidence remains under `evidence/live`; the page neither reconstructs Runtime
facts nor creates a second benchmark path. It accepts only cases from the frozen manifest, validates bounded model and
profile identifiers, launches with an argv list rather than a shell, permits one active run, and never returns provider
keys or environment values. Remote binding is disabled unless explicitly requested with `--allow-remote`.

For complete local tracing set `AFFORDANCE_TRACE_DIR`. To add the read-only Langfuse/OTel viewer, install the
`observability` extra and set `AFFORDANCE_LANGFUSE_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and
optionally `LANGFUSE_BASE_URL`. Each provider exchange remains part of local JSONL; Langfuse receives only a bounded
project-event projection plus PydanticAI's official native model/tool spans. Public prompt/response content is enabled;
binary content, private bindings, selectors/BIDs, full World payloads, and screenshots are not sent. The separate
`LLM_ENABLE_PRIVATE_MODEL_CAPTURE` path is only an optional isolated raw-envelope copy.

## Current convergence boundary

The R2 checkpoint remains available in Git history. The current branch keeps the existing world, adapter,
semantic-action, tool, execution, and evaluation boundaries and uses one `CoreAgentLoop`, one `RunState`, one
`StepResult` per turn, one stable GUI-agent prompt, and one compact model projection. The public Runtime, CLI, and
target benchmark harness all use this core. The former control reducer, transition, feedback, session, and legacy-loop
modules have been removed. PydanticAI owns standard native tool transport, while 4.1V keeps one bounded compact wire
adapter. Superseded structured-package, native-tool, automatic-fallback, and model-conformance paths are deleted; the
obsolete `propose_done` branch is also deleted. Paired observation benchmarks remain an evidence gate, but the
goal-semantics gates below now come first because the fresh held-out failures expose a more immediate causal gap.

The previous GoalProgram/GoalEvaluator/GoalStateSnapshot production guidance design was reopened after the configured
4.7 witness exposed an internally inconsistent schema-to-lowering contract. The production chain now uses the static
five-field `GoalPlan` directly; symbolic relation lowering and deterministic goal snapshots have been removed from
composition, Core Loop, RunState, Context, provider delivery, and the public goal API. Compiler tracing is retained and
external-breadth now projects compiler metrics. Local implementation gates pass. After adding one bounded, fully
traced retry for transient compiler rate limits, a second formal Like run delivered a Ready three-item GoalPlan to
every ActionPolicy turn. The policy initially activated three different Like controls, then repeatedly reversed
already-active Likes and exhausted ten steps without Submit; official success remained 0. Ready delivery is witnessed,
but behavioral success and fresh-context audit remain open, so no G1/G2 closure is claimed. Optional action lineage and Binder changes remain
deferred. The phased gates are maintained in
[Benchmark](docs/benchmark.md).

A one-case ActionPolicy model swap to `glm-4.6` exposed missing provider recovery and folded failure evidence in the
PydanticAI path. That adapter now disables opaque SDK retries, records every physical attempt, distinguishes safe typed
provider categories, and permits one explicit retry with bounded `Retry-After`/exponential backoff inside a split
overall deadline. A fresh witness made four valid decisions and one Like execution without undoing it, then reached
the case watchdog during a later retried turn; official success remained 0. This proves the retry path is reachable and
observable, not that 4.6 solves the task. Goal semantics and the model comparison remain non-closed.

GLM-4.6 thinking is now explicitly disabled for the single-action PydanticAI role, with a 512-token output cap and
zero temperature. An exact-context latency probe fell from 29.8 seconds to 3.89 seconds with zero reasoning tokens,
and report latency is no longer zero. The one permitted formal replay completed ten turns in 76.8 seconds but looped
between action paging and waiting without executing a GUI action; official success remained 0. A clean same-guidance
thinking on/off A/B is therefore required before selecting this model setting as the default behavioral profile.
