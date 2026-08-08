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
→ Runtime authoritative WorldObservation / Internal ActionSpace
→ disposable bounded AgentContext
→ typed AgentDecision
→ Runtime validation / semantic confirmation
→ current BoundActionRequest
→ execute once
→ ActionResult
→ fresh WorldObservation
→ validated ActionEvaluation / TaskEvaluation
→ continue / ask / stop
```

One semantic target may have several surface-specific bindings. The agent sees
stable target IDs, roles, labels, state, relations, and supported actions; the
Runtime retains selectors, coordinates, WoT forms, API handles, freshness, and
route evidence. This lets the Runtime choose the most effective executable
route without teaching the policy a separate action language for each platform.

## Target architecture

The current target is defined only by:

- [AgentContext Recurrent E2E Agent Architecture](docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
- [AgentContext Recurrent E2E Agent Evolution Plan](docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

```text
┌─────────────────────────────────────────────────────┐
│ Runtime authoritative state                         │
│ WorldObservation · Internal ActionSpace · progress │
└──────────────────────────┬──────────────────────────┘
                           │ bounded one-way projection
┌──────────────────────────▼──────────────────────────┐
│ disposable AgentContext → typed AgentDecision       │
│ → validate → bind → execute once → fresh evaluate  │
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

The older TaskSpec/TaskPlan/ActionContract/StateKernel/RuntimeCommitter control
path remains the default baseline. A non-default target path now implements the
strong TaskGoal and world/action/evaluation contracts and integrated DOM,
Visual full-digest, and WoT local HTTP JSON single-surface verticals. The
three-surface adapter-only shared-state matrix is proven with one deterministic
policy. P5-D semantic confirmation, fresh semantic rebind, and unknown-effect
no-replay are closed. P5-M0 model-safe policy inputs and evaluator trust
validation are complete. P5-M1 now supplies one injected, provider-neutral
structured model call, canonical AgentContext JSON and strict typed-decision parsing.
External full-agent benchmarks remain blocked and default cutover remains pending.

P5-D6.1 is complete on the non-default path: effective risk, semantic
destination identity, confirmation presentation, immutable terminal sessions,
and evidence-lineage fields are closed. P5-M0 now resolves evidence against the
current world and validates declared-minimum target outputs; production model
evaluators have not started. P5-M0.1 is now closed on that same non-default path:
each policy turn receives a bounded disposable AgentContext, all decisions bind
an opaque current context ID, stale/replayed decisions are zero-call, and
deterministic relevance/paging plus DOM/Visual/WoT source summaries are live.
Criterion adjudicators remain unimplemented and belong to P5-M2.

P5-M0.1.1 closes the ordinary Runtime correctness gaps on the same non-default
path: every policy call receives a monotonic one-shot context epoch; every
fresh-observation path rejects acquisition-identity reuse; deterministic pages
are traversable through Runtime-issued cursors; action/destination/task/world
budgets are enforced coherently; and non-action decisions recur as bounded
semantic history. P5-M1 is closed only for an injected
`StructuredDecisionModelPort`; no real provider profile, retry platform, model
evaluator, default cutover, or weakening of exact-subject confirmation is included.

The baseline is retained, not rolled back. Transaction/commit/recovery
machinery is frozen against further expansion while a new short-loop path is
built in vertical slices. See [Implementation Status](docs/implementation-status.md)
for exact code truth and [Current Implementation Plan](docs/current-implementation-plan.md)
for exact slice status and the next evaluator-composition work queue.

## Correctness invariants retained during simplification

1. Every bound action request binds to the observation and binding that produced it.
2. A stale observation or binding makes zero executor calls.
3. High-risk actions require a confirmed semantic subject that covers the current action: action/target/destination/material parameters remain exact, while effects may only narrow, risk/consequences may not strengthen, and reversibility may not worsen. Exact subject equality remains the conservative implementation until dominance is complete; a fresh private binding alone does not change what the user confirmed.
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

The DOM/Visual/WoT adapter-only shared-state matrix is complete for the current
declared single-surface profiles. Full external agent benchmarks remain blocked
until a model-backed target AgentPolicy, production evaluator
composition, a new-AgentLoop benchmark harness, and exact-head remote CI
evidence are all complete. P5-D/M0 do not by themselves admit an external run.

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
