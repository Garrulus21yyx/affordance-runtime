# Runtime-First Architecture Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** product boundary among Runtime, policy/model, adapters, parent agents, and benchmarks

## 1. Runtime product boundary

Affordance Runtime owns the unified world model, action bindings, route
selection, freshness, risk decision, execution result, fresh observation, and
independent evaluation. It does not own the user's high-level reasoning policy,
and it does not turn external content into user authority.

Intake is responsibility-thin but semantically strong. The execution loop is
capability-thick in perception, grounding, legal action generation, route
selection, validation, and replanning, while remaining infrastructure-thin.

## 2. Policy/model boundary

The policy sees `TaskGoal`, `AgentWorldView`, `ActionSpace`, bounded recent
turns, optional TaskPlan and LocalObjective. It may select an offered action,
request an admitted local batch, ask the user, reobserve, or suggest finish. It
cannot provide raw selector, coordinate, backend payload, endpoint, file path,
credential, approval, milestone satisfaction, or completion truth.

Text from pages, email, documents, screenshots, tools, or providers is observed
data. It may inform state and decisions but cannot create confirmation or widen
the requested effect.

## 3. Adapter boundary

DOM, AX, Visual, SVG, WoT, API, Device, and CLI adapters report truthful entities,
facts, coverage, conflicts, bindings, supported actions, freshness, and results.
They do not interpret task meaning or declare task completion.

Credentials and signed URLs are injected at the backend boundary and do not
enter AgentWorldView, BoundActionRequest telemetry, or general trace payloads.

## 4. Action boundary

An ActionIntent expresses one semantic action. ActionBinder binds it to one
current observation and binding as a BoundActionRequest. Runtime checks support
and freshness, asks for exact confirmation of semantic intent/risk/consequences
when needed, executes at most once, then reobserves. A selector/coordinate/form
may fresh-rebind without new confirmation only when semantics and consequences
are unchanged.

Executor success is transport/execution information only. ActionEvaluator and
TaskEvaluator use fresh independent evidence.

The default is one action per observation. A bounded ActionBatch is permitted
only for max-three, low-risk, same-observation/surface/session actions whose
options declare no observation barrier. It cannot contain navigation, external
effects, app/page changes, or cross-surface actions and must end with fresh observation.

## 5. Benchmark boundary

BrowserGym, MiniWoB++, WorkArena, WebArena, ScreenSpot, WASP, local fixtures,
and future device suites are evaluators. Production may not branch on task ID,
seed, family, expected answer, selector, coordinate, or authored shortcut.
External reward is never Runtime task completion.

## 6. Baseline and target

Current production still uses TaskSpec/ActionContract/StateKernel/
RuntimeCommitter machinery. That is implementation truth during migration, not
the target product boundary. The target makes trace optional and keeps strict
ingestion/evaluation as explicit profiles outside the ordinary GUI loop.
