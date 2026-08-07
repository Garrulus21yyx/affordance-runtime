# Affordance Runtime

Affordance Runtime is a planner-neutral environment interface for GUI agents.
It lets one agent policy observe and act across DOM, Accessibility, Visual,
SVG, WoT, API, Device, and CLI surfaces through one semantic world model and one
short observe–act–observe–evaluate loop.

Its design rule is: **responsibility-thin, semantics-strong intake; capability-
thick, infrastructure-thin execution**. The loop is powerful because it sees,
grounds, generates legal actions, validates, and replans well—not because it
contains a large transaction kernel.

The project center is:

```text
TaskGoal
→ Unified World Observation
→ optional TaskPlan / LocalObjective
→ semantic ActionSpace
→ ActionIntent
→ current BoundActionRequest
→ environment executes
→ ActionResult
→ fresh observation
→ action/task evaluation
→ continue / ask / stop
```

One semantic target may have several surface-specific bindings. The agent sees
stable target IDs, roles, labels, state, relations, and supported actions; the
Runtime retains selectors, coordinates, WoT forms, API handles, freshness, and
route evidence. This lets the Runtime choose the most effective executable
route without teaching the policy a separate action language for each platform.

## Target architecture

The current target is defined only by:

- [Unified World Interface and E2E AgentLoop Architecture](docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
- [Unified World Interface and E2E AgentLoop Evolution Plan](docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

```text
┌─────────────────────────────────────────────────────┐
│ AgentLoop                                           │
│ observe → evaluate → decide → bind → confirm → act │
│         → fresh observe → evaluate → continue      │
└──────────────────────────┬──────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────┐
│ Unified World Interface                             │
│ WorldObservation · AgentWorldView · ActionSpace     │
│ ActionIntent · BoundActionRequest · ActionResult    │
└──────────────────────────┬──────────────────────────┘
                           │
       DOM · AX · Visual · SVG · WoT · API · Device · CLI
```

The target deliberately does not center event sourcing, typed state deltas,
global atomic commit, a durable ledger, checkpoint/resume, or a general
authorization-proof platform. Those mechanisms do not make an agent observe
or act across environments more effectively.

## Current implementation truth

The code at baseline
`agent/migrate-runtime-components@8d7cfd6b7d43c72f9b45bb4144a62553d90c23a8`
still uses the older TaskSpec/TaskPlan/ActionContract/StateKernel/
RuntimeCommitter control path. It also contains the most valuable foundations
for the new target: `UnifiedObservation`, multi-surface grounding candidates,
semantic entity fusion, backend-neutral actions, executor routing, active
perception, fresh post-action observation, and independent evaluation.

The baseline is retained, not rolled back. Transaction/commit/recovery
machinery is frozen against further expansion while a new short-loop path is
built in vertical slices. See [Implementation Status](docs/implementation-status.md)
for exact code truth and [Current Implementation Plan](docs/current-implementation-plan.md)
for the completed docs-only consolidation slice and next, not-yet-started code work.

## Correctness invariants retained during simplification

1. Every bound action request binds to the observation and binding that produced it.
2. A stale observation or binding makes zero executor calls.
3. High-risk actions require confirmation of exact semantic intent, effects, risk, and consequences; a fresh binding alone does not change what the user confirmed.
4. An execution receipt does not prove effect or task completion.
5. Every action—or strictly admitted no-barrier local batch—is followed by fresh observation and independent evaluation.
6. An unknown effect is never blindly retried.
7. Required artifacts must exist and match their expected content.
8. Models cannot directly provide raw selectors, coordinates, backend payloads, endpoints, or file paths.

These are local action-boundary checks. They do not require a global
event-sourced transaction runtime.

## Product and benchmark boundary

Affordance Runtime—not BrowserGym or another benchmark—is the product.
Benchmarks evaluate the Runtime and may not provide task IDs, expected answers,
selectors, coordinates, or fixture semantics to production policy.

The next core benchmark is a positive cross-surface matrix: the same TaskGoal,
AgentPolicy, semantic action vocabulary, and evaluator must succeed against
DOM, AX, Visual, SVG, and WoT implementations where only the adapter differs.
It records task success, steps, observations, model/visual calls, latency,
fallbacks, route mistakes, confirmations, long-horizon constraint retention,
batch utilization, and cache-currentness rejection.

## Documentation

Start with [docs/README.md](docs/README.md). The
[documentation manifest](docs/documentation-manifest.yaml) records authority
and lifecycle.

- [Project Plan](docs/project-plan.md)
- [Current Implementation Plan](docs/current-implementation-plan.md)
- [Implementation Status](docs/implementation-status.md)
- [Architecture Governance](docs/architecture-governance-track.md)
- [Documentation Governance](docs/documentation-governance.md)

Historical evidence and change-admission records remain immutable and do not
define the current target.

## Repository layout

```text
src/affordance_runtime/   current Runtime implementation
tests/                    unit, integration, architecture, and benchmark tests
docs/                     current authority, status, policy, and references
docs/archive/             superseded design and planning history
scripts/                  reproduction and benchmark entrypoints
```

## Validation and reproduction

Repository-governed commands and revision-scoped evidence are recorded in
[Implementation Status](docs/implementation-status.md) and
[Evidence](docs/evidence/README.md).

```bash
./scripts/reproduce_container.sh
AFFORDANCE_WOT_PROOF=1 ./scripts/reproduce_container.sh
```

## One sentence

Affordance Runtime gives agents one semantic observe–act–observe interface for
acting effectively across heterogeneous digital and physical surfaces.
