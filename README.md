# Affordance Runtime

Affordance Runtime is a planner-neutral environment interface for GUI agents.
It lets one agent policy observe and act across DOM, Accessibility, Visual,
SVG, WoT, API, Device, and CLI surfaces through one semantic world model and one
short acquire–act–acquire–evaluate loop.

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
→ ExecutionOutcome(ActionResult + typed post-action acquisition)
→ fresh WorldObservation from execute or capability-admitted capture
→ validated ActionEvaluation / TaskEvaluation
→ bounded ControlTransition + AgentLoopState update
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
│ WorldObservation · ActionSpace · AgentLoopState     │
│ optional VerifiedTaskState frontier                 │
└──────────────────────────┬──────────────────────────┘
                           │ bounded one-way projection
┌──────────────────────────▼──────────────────────────┐
│ disposable AgentContext → typed AgentDecision       │
│ → validate → bind → execute/acquire → evaluate     │
│ → bounded ControlTransition                         │
└──────────────────────────┬──────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────┐
│ Unified World Interface                             │
│ WorldObservation · ObservationAcquisition           │
│ ActionSpace · BoundActionRequest · ExecutionOutcome │
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
policy. Semantic confirmation, one-shot disposable AgentContext, strict
model-policy parsing/transport, declared-minimum evaluation, the internal
harness, and the pinned `browsergym-miniwob==0.14.3` adapter are closed for their
declared non-default profiles. General semantic entailment, semantic fusion,
default cutover, and broad autonomous GUI competence remain open.

The BrowserGym breadth evidence now contains two immutable, non-combinable
exact runs: the historical clean `b3b64a2` run at 6/60 and the later clean
`83dc4fa` rerun-v3 at 4/60. Neither is a generalization or trend claim.
Rerun-v3 retains seven historical post-observation failures, nine unclassified
typed failures, and eleven Runtime rejections. The observation cases confirmed
the P5-M4 mismatch between public active observation and a consume-once
reset/step snapshot. M4.5-A now replaces that lifecycle with typed reset,
independent capture and execute-returned post acquisition on the non-default
target path.

The next target slices are deliberately narrow and separate:

```text
P5-M4.5-A typed acquisition lifecycle: COMPLETE_NON_DEFAULT
→ P5-M4.5-B bounded lossless ControlTransition accounting: COMPLETE_NON_DEFAULT
→ P5-M4.5-C same frozen MiniWoB-60 profile rerun: NEXT
→ supported-subset multi-seed gate
→ P5-E VerifiedTaskState + TaskProgressAuditor + milestone planning
```

`ProgressController` remains a fill/select local liveness guard, not a planner.
`ControlTransition` remains run-scoped, in-memory and non-replayable;
AgentLoopState remains current-state authority. The baseline is retained, not
rolled back, and transaction/commit/recovery machinery remains frozen. See
[Implementation Status](docs/implementation-status.md) for exact code truth and
[Current Implementation Plan](docs/current-implementation-plan.md) for the
active queue.

## Correctness invariants retained during simplification

1. Every bound action request binds to the observation and binding that produced it.
2. A stale observation or binding makes zero executor calls.
3. High-risk actions require a confirmed semantic subject that covers the current action: action/target/destination/material parameters remain exact, while effects may only narrow, risk/consequences may not strengthen, and reversibility may not worsen. Exact subject equality remains the conservative implementation until dominance is complete; a fresh private binding alone does not change what the user confirmed.
4. An execution receipt does not prove effect or task completion.
5. Every action—or strictly admitted no-barrier local batch—gets a typed post-action acquisition; evaluation uses it or an explicitly supported independent capture.
6. An unknown effect is never blindly retried.
7. Required artifacts must exist and match their expected content.
8. Models cannot directly provide raw selectors, coordinates, backend payloads, endpoints, or file paths.
9. One accepted policy decision produces one bounded root ControlTransition; it is not a durable ledger or state-reconstruction source.
10. VerifiedTaskState advances only through validated evidence; TaskPlan and model reflection remain hypotheses.

These are local action-boundary checks. They do not require a global
event-sourced transaction runtime.

## Product and benchmark boundary

Affordance Runtime—not BrowserGym or another benchmark—is the product.
Benchmarks evaluate the Runtime and may not provide task IDs, expected answers,
selectors, coordinates, or fixture semantics to production policy.

The DOM/Visual/WoT adapter-only shared-state matrix is complete for the current
declared single-surface profiles. Scoped BrowserGym/MiniWoB fixed and breadth
runs have been admitted under P5-M4; they are not full external-suite or
cross-platform evidence. WebArena/WorkArena/OSWorld expansion and any general
benchmark claim remain blocked by their own adapter, long-horizon, M4.5 and
breadth gates. P5-D/M0 did not by themselves admit those runs.

Exact local Ollama `qwen2.5:7b` and `llama3.1:8b` profiles are supported for
the tested `compact-contract.v1` **action-selection scope**: each passed L0--L4 at 20/20
on Ollama 0.32.0 with zero retry, fallback, response repair or Runtime
admission bypass. This is exact-profile/internal-DOM evidence, not external
benchmark admission or cross-platform model generalization. The production
grounding default remains `format-only` pending a separate adoption decision.

P5-M3.5 adds explicit `compact-contract-v2` / `compact-contract.v2`, a
decision-neutral guide with all seven field/domain contracts and no concrete
first-action answer. On the exact GPU candidate gate, Qwen passed 64/75 but
failed Page once and Wait/Abort 5/5 each; Llama passed 20/75 and showed five
wrong first-action selections. Neither profile qualified for the 20/20 full
recurrent gate. `compact-contract.v1` is therefore frozen as
`PRODUCTION_SUPPORTED_ACTION_SELECTION_PROFILE`; v2 remains an explicit
`EXPERIMENTAL_NOT_ADMITTED`. The factory default is unchanged.
Ordinary composition fails closed if v2 is selected without
`LLM_ENABLE_EXPERIMENTAL_GROUNDING=1`; that switch is reserved for explicit
conformance experiments and does not admit v2 for recurrent production use.

P5-M3.6 keeps that production boundary and decomposes the same public-context
cases only inside model-conformance diagnostics. On clean exact-profile runs,
Qwen scored baseline 20/35, routing 26/35, payload-only 35/35, end-to-end 25/35,
and critical 30/40; Llama scored 5/35, 25/35, 35/35, 25/35, and 0/40. Both are
`routing_bottleneck` diagnoses and failed the two-stage candidate gate. The
fixed-route payload-only result is diagnostic isolation, not policy support.
Two-stage composition is not in the production factory or AgentLoop.
Local-model compatibility research is closed for the current product scope and
is non-blocking. The exact local matrix is rerun only after a declared runtime,
model identity, canonical schema, AgentContext, or grounding-contract change,
or when a fully local recurrent agent becomes an explicit product objective.

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
weakening parser or Runtime authority. Stable full recurrent AgentPolicy support
remains unattested; compact.v1 action-selection support is attested only for its
exact profiles. A D0–D4 destination ladder now distinguishes empty/forbidden,
target/action confusion, cross-action and unknown public IDs without retaining
the model value. Qwen passed D0–D3 and confused the target ID at D4; Llama
passed D0–D2, then failed D3 and confused the target ID at D4. Compact
grounding v1 remains an explicit action-selection profile.

## BrowserGym target-loop adapter

P5-M4 returns the project to the GUI-agent mainline. The one-stage
`AgentPolicy.decide(context)` interface with `format-only.v1` remains the
primary recurrent profile; compact v2 is experimental and fail-closed, and
two-stage remains diagnostic-only. The pinned `browsergym-miniwob==0.14.3`
adapter projects structural targets into the existing target loop, keeps bids
private, and closes the reviewed click-button, enter-text, and choose-list
tasks with environment-native mechanical verification. This is fixed-profile
adapter conformance, not a model-generalization claim. Live external smoke is
separately gated and is not run without an existing explicit opt-in.

P5-M4.2 closes a local correctness gap without rerunning that smoke. Fresh,
complete structural evidence now confirms fill/select primitive effects. A
fill/select whose requested public value is already current is suppressed
before binding, probing, or execution; one unchanged exact repeat then fails
with `NO_PROGRESS_REPETITION`. The next disposable AgentContext receives at
most three route-free progress events, and a harness watchdog preserves a
privacy-safe partial episode snapshot instead of reporting zero activity. The
historical formal run at `cd49b8e` remains failed by case timeout; no local
result backfills it. Format-only and the default Coordinator remain unchanged.

## MiniWoB seeded breadth profile

P5-M4.3 adds `MINIWOB_60_SEEDED_BREADTH_PROFILE`. The installed
`browsergym-miniwob==0.14.3` registry and reviewed MiniWoB source are censused
before execution. A static primitive inventory admits only tasks expressible
with `activate`, `fill`, and `select`; SHA-256 ordering then freezes 60 cases
without using model outcomes. The formal campaign is seed 7, serial,
format-only, Mistral medium 3.5, 7.5-second fixed pacing, ten turns, 120 seconds,
zero retry, and zero fallback. Reports separate evidence validity from task
success and retain no prompt, response, oracle, reward, or private route. This
is in-family synthetic breadth evidence, not GUI generalization or a complete
MiniWoB benchmark.

P5-M4.4 records the completed run as a valid negative breadth result: 6/60 at
exact run SHA `b3b64a2`, with no change to the historical reports. Later
read-only analysis leaves 27 historical fallback/environment cases explicitly
`UNRESOLVED_LEGACY_EVIDENCE`. A source-bound, multi-axis capability inventory
v2 covers all 125 registry tasks and classifies the historical 60 as 15 declared
supported, 31 declared unsupported, and 14 unassessed. Local no-model probes
reset and project all 22 deterministic representatives, but project only 51 of
103 raw interactive nodes and expose 20 blank labels. M4.4 itself made no
provider call or product behavior change.

A later separately authorized formal rerun-v3 completed from clean
`83dc4fa313e49b6c8772052ca44f03564f68aa63` with valid 4/60 evidence. It is a
separate exact-run record, not a replacement/merge/trend against 6/60. Seven
post-observation failures confirmed the historical BrowserGym active-capture
contract gap; nine failures remain unclassified despite typed metadata. M4.5-A
acquisition is now closed, including real owner-thread active capture, origin
validation and final-fallback truth. M4.5-B ControlTransition accounting is now
closed; M4.5-C is the next admitted exact-profile rerun before a multi-seed
supported subset and P5-E.
