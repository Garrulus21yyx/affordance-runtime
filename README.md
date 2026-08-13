# Affordance Runtime

Affordance Runtime is a planner-neutral environment interface for GUI agents.
It lets one agent policy observe and act across DOM, Accessibility, Visual,
SVG, WoT, API, Device, and CLI surfaces through one semantic world model and
one serial acquire-act-acquire-evaluate loop.

The design center is a simple Agent boundary backed by explicit Runtime
authority:

```text
UserRequest -> TaskGoal -> admitted TaskSpec
-> initial WorldObservation
-> admitted TaskPlan<StepSpec.execution>
-> active StepExecutionState + current ActionChoiceCatalog
-> disposable AgentContext + ordinary action/control tools
-> action-only AgentDecision
-> Runtime admission / risk / currentness / private binding
-> execute once -> fresh observation -> validated evaluations
-> plan/task progress
```

Semantic task and step meaning may persist. DOM IDs, E-refs, action IDs,
routes, bindings, and points are observation-bound and are rebuilt from every
fresh world state. The main Agent chooses the next current action; it does not
construct Runtime objective, predicate, scope, aggregate, binding, or
completion state.

## Documentation authority

Start at the [Documentation Index](docs/README.md).

- [Canonical GUI Agent Execution Architecture](docs/task-execution-authority-map.md)
  is the only target owner map and lifecycle contract.
- [Canonical GUI Agent Authority Cutover Plan](docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
  owns migration order and deletion gates only.
- [Implementation Status](docs/implementation-status.md) alone states current
  reviewed code truth.
- [Current Implementation Plan](docs/current-implementation-plan.md) alone
  schedules the active slice.

The current branch has not completed the canonical authority cutover. The
recurrent Agent-created LocalObjective ingress is reopened and must be replaced
by admitted TaskPlan/StepSpec semantics before another closure claim. Consult
Implementation Status for the exact revision and evidence; this README does not
mirror phase statuses.

## Core invariants

1. No exact GUI identity exists before observation.
2. Every effectful dispatch belongs to the active plan step, current choice,
   current ActionSpace option, and current private binding.
3. A stale observation, context, action, or binding makes zero executor calls.
4. One accepted effectful decision produces at most one dispatch.
5. Dispatch, effect, step completion, and task completion have different
   owners.
6. `SENT_UNKNOWN` is never blindly retried.
7. DOM, derived geometry, and Vision are evidence sources under one lifecycle;
   no evidence provider owns action authority.
8. AgentContext, tools, E-refs, traces, and benchmark reports are one-way
   projections, never Runtime truth.
9. Benchmark task names, answers, and fixture-specific rules never enter
   production behavior.
10. Unsupported or ambiguous states fail with typed outcomes.

## Repository layout

- `src/affordance_runtime/` — Runtime contracts and implementation
- `tests/` — unit, property, architecture, integration, and harness tests
- `docs/` — authority, governance, status, plans, records, and evidence
- `scripts/` — validation and benchmark entrypoints

## Validation and reproduction

Repository-governed commands and revision-scoped evidence are recorded in
[Implementation Status](docs/implementation-status.md) and
[Evidence](docs/evidence/README.md).

```bash
./scripts/reproduce_container.sh
AFFORDANCE_WOT_PROOF=1 ./scripts/reproduce_container.sh
```

Benchmark configuration and local BrowserGym facts are governed by
`AGENTS.md`; benchmark outputs are evidence, never production authority.
