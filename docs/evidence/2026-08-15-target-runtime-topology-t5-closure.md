# Target Runtime topology T5 closure

Date: 2026-08-15

Status: `T5_COMPLETE / STATIC_AND_OFFLINE_VERIFIED / LIVE_NOT_RUN`

## Closure result

The Target Runtime physical topology is closed for its declared static and
offline scope. The installed product command resolves only to
`affordance_runtime.app.cli:main`; the separate benchmark command resolves only
to `affordance_runtime.benchmarks.cli:main`. The root module entrypoint delegates
to the same product CLI.

Repository-wide AST inspection found one definition and one construction site
for each lifecycle owner:

| Owner | Sole definition | Sole construction |
|---|---|---|
| `TargetRuntime` | `app/runtime.py` | `app/composition.py` |
| `AgentLoop` | `agent/loop.py` | `app/runtime.py` |
| `AgentRunSession` | `agent/session.py` | `agent/loop.py` |

Active benchmarks do not construct these values. The model-conformance replay
previously fabricated an `AgentRunSession` around a `SimpleNamespace`; it now
uses product composition and `TargetRuntime.start_task()`, which performs the
same bounded reset without an extra model call.

## Import-direction proof

Architecture properties now enforce:

- `agent` imports neither `model` nor `surfaces`;
- model policy/evaluator/provider adapters depend on agent public contracts,
  while AgentLoop imports none of those adapters;
- `world` owns `SurfaceAdapter` and imports no concrete surface package;
- surfaces import no app runtime/composition, AgentLoop or AgentRunSession;
- app, agent, actions, world, execution, evaluation, task, risk, confirmation,
  verification, model and surfaces import neither benchmarks nor testing;
- benchmarks consume product composition and admitted surface APIs instead of
  constructing a second lifecycle.

`AgentContext`, `ActorWorldSnapshot`, budgets and their disposable projections
therefore live under `agent/context`. The old `model/context` directory is
absent. Generic assertion arbitration remains world-owned; the BrowserSnapshot
projection that imports the DOM snapshot type remains surface-owned. Making the
evaluation package facade lazy prevents package initialization order from
reintroducing an import cycle; it does not add an owner or fallback.

## Deleted and unreachable paths

The architecture absence manifest contains 180 deleted production paths. T5
also removed the last unconsumed topology shim, `agent/types.py`, whose only
behavior was deprecated compatibility re-export. Production, active tests and
scripts are AST-scanned for imports of deleted owners. An isolated built and
installed wheel additionally reports no import spec for representative old
owners including `agent.runtime`, `agent.composition`, `agent.types`,
`model_boundary`, `model.context`, `model_policy`, `model_evaluator`, root target
CLI/composition, root browser session, `surfaces.base`, and the former world
ActionSpace/capability modules.

Retained wire normalization, derived state views and benchmark report-field
projections are bounded representation adapters; none constructs a Runtime,
loop, session, ActionSpace or dispatch route and none makes an old module
importable.

## Verification

- focused topology, lifecycle, context/model, world/surface and conformance
  tests: `162 passed`;
- full pytest: `1598 passed, 27 skipped`;
- collection: 1625 tests;
- Ruff: passed;
- repository-standard mypy: no issues in 335 source files;
- isolated sdist and wheel build: passed;
- installed product and benchmark console scripts: exact owner identities and
  separated help surfaces verified;
- installed representative old-module import-spec checks: all unreachable;
- `git diff --check`: passed.

No live benchmark was run. T5 proves topology ownership and reachability, not
StateFact cutover, activate effect-authority closure, new interaction actions or
benchmark generalization.
