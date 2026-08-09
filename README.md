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
P5-M1.1 hardens hostile structured JSON and bridges that policy through the
existing ModelPort transport with one bounded, zero-retry/no-fallback attempt.
P5-M2 now composes criterion-specific production evaluation: mechanical checks
are deterministic, semantic judges can only propose current evidence, explicit
user evidence is isolated, and Runtime alone computes task completion.
P5-M2.1 binds action evidence to Runtime-derived criterion/output obligations,
lets low-risk local inconclusive actions continue from fresh state, and limits
semantic judges to evidence records actually presented in their request.
External full-agent benchmarks remain blocked and default cutover remains pending.

P5-M3 now provides a separate fixed-manifest internal harness for the non-default
`AgentEpisodeRunner`/`AgentLoop`. Its deterministic, scripted structured-policy,
and local-HTTP semantic-judge profiles are locally accepted with zero forbidden
effects, duplicate unknown attempts, or stale zero-call violations. No
BrowserGym, MiniWoB, WebArena, WorkArena, or OSWorld run was performed; external
admission still requires an exact live profile and exact-head remote CI.

P5-M3.1 makes that acceptance machine-verifiable: safety-critical metrics carry
measured/unmeasured state and typed expectations, lifecycle failures are
contained per case, and the fixed `internal-real-adapters` suite runs actual DOM,
Visual-only, and WoT production adapters. Secret-free reports can be hashed into
an exact-tree local attestation. Synthetic protocol cases remain explicitly
labelled synthetic; no external benchmark or default cutover is admitted.

P5-M3.2 closes manifest/result/attestation integrity and configures exact-head
full-regression plus opt-in live-policy workflows. A reviewed mechanical-only
`browsergym-miniwob==0.14.3` three-case manifest and pure admission checker now
exist in a separate optional package. The target-loop BrowserGym environment
wrapper is still partial, so preflight fails closed and no external task runs by
default. Local Ollama availability is not a live attestation until the exact
clean head completes the real-DOM profile.

P5-D6.1 is complete on the non-default path: effective risk, semantic
destination identity, confirmation presentation, immutable terminal sessions,
and evidence-lineage fields are closed. P5-M0 now resolves evidence against the
current world and validates declared-minimum target outputs; production model
evaluators have not started. P5-M0.1 is now closed on that same non-default path:
each policy turn receives a bounded disposable AgentContext, all decisions bind
an opaque current context ID, stale/replayed decisions are zero-call, and
deterministic relevance/paging plus DOM/Visual/WoT source summaries are live.
Criterion adjudicators are closed for the declared mechanical, semantic,
explicit-user, hybrid, bounded-expression, current-lineage and path/SHA/artifact
profiles. General semantic entailment remains partial.
Agents are not required to predict complete future state, and effect support is
an evidence-backed Runtime claim rather than general causal proof.

P5-M0.1.1 closes the ordinary Runtime correctness gaps on the same non-default
path: every policy call receives a monotonic one-shot context epoch; every
fresh-observation path rejects acquisition-identity reuse; deterministic pages
are traversable through Runtime-issued cursors; action/destination/task/world
budgets are enforced coherently; and non-action decisions recur as bounded
semantic history. P5-M1.1 closes the existing-transport bridge and local HTTP
transport proof; live-provider attestation remains unavailable without explicit
opt-in configuration. No retry platform, model evaluator, default cutover, or
weakening of exact-subject confirmation is included.

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
until a new-AgentLoop benchmark harness, exact live model-policy profile, and exact-head remote CI
evidence are all complete. P5-D/M0 do not by themselves admit an external run.

Exact local Ollama `qwen2.5:7b` and `llama3.1:8b` profiles are supported for
the tested `compact-contract` AgentPolicy profile: each passed L0--L4 at 20/20
on Ollama 0.32.0 with zero retry, fallback, response repair or Runtime
admission bypass. This is exact-profile/internal-DOM evidence, not external
benchmark admission or cross-platform model generalization. The production
grounding default remains `format-only` pending a separate adoption decision.

P5-M3.4 exposes `compact-contract` as an explicit, versioned production
grounding profile selected by argument or `LLM_DECISION_GROUNDING`. It does not
select by provider/model and never retries or falls back between groundings.
The global default remains `format-only`: exact GPU matrices found incomplete
Wait/Abort behavior for Qwen and broad non-SelectAction bias for Llama, while a
zero-retry Mistral compact matrices encountered provider unavailability. Default
cutover is therefore blocked, not executed.

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

## Exact model-profile diagnostics

P5-M3.3 measures the current real-DOM AgentContext as `SMALL`: 4,972 serialized
bytes, one action and no history. The canonical seven-variant provider schema
is 5,194 bytes with ten definitions and seven variants. Its completion summary
budget is now 1,024 characters. Exact installed Ollama Qwen/Llama profiles both
initialized the full union and passed a Level-2 format-only diagnostic; their
Level-3/4 attempts reached Runtime admission and were rejected for a hidden
destination. This corrects the former provider-grammar blocker without
weakening parser or Runtime authority. Stable profile support remains
unattested. A D0–D4 destination ladder now distinguishes empty/forbidden,
target/action confusion, cross-action and unknown public IDs without retaining
the model value. Qwen passed D0–D3 and confused the target ID at D4; Llama
passed D0–D2, then failed D3 and confused the target ID at D4. Compact
grounding remains diagnostic-only.
