# Current Implementation Plan

Implementation status: M0-M7 are complete for the controlled local profile.
See [Implementation Status and Forward Gates](implementation-status.md). M8-M9
below are the authoritative next steps; M5-M7 are retained as completed evidence,
and production-scale options remain non-blocking.

## 1. Authority

This document is the implementation profile for the current repository. It is
the plan contributors should follow when deciding what to build now.

The [Complete Architecture Blueprint](complete-architecture-blueprint.md)
describes a possible production-scale destination. It does not create current
release requirements. When the two documents differ, this implementation plan
wins until a production feature is explicitly promoted through the decision
gate in the main [Project Plan](project-plan.md).

The governing strategy is:

```text
complete vertical loop
limited horizontal breadth
```

The runtime must demonstrate reliable execution, evaluation, diagnosis, and
controlled evolution end to end. It does not need distributed infrastructure
or many interchangeable implementations of every component.

## 2. Product Definition

Affordance Runtime is a single-process, asynchronous, planner-neutral GUI agent
harness runtime. It converts DOM, visual, accessibility, and WoT observations
into versioned affordances, executes one validated Action Contract at a time,
verifies effects, records evidence, evaluates traces, and regression-gates
harness improvements derived from failures.

The complete product loop is:

```text
TaskSpec
  -> Observe
  -> Affordance Snapshot
  -> Planner Proposal
  -> Action Contract
  -> Policy + Preflight
  -> Route + Execute
  -> Post-Action Observe
  -> Verify
  -> Recover / Continue / Finish
  -> Trace
  -> Benchmark
  -> Failure Classification
  -> Skill / Policy / Verifier Proposal
  -> Regression Replay
  -> Accept / Quarantine / Reject
```

The implementation is a modular monolith:

```text
User / Parent Agent / Benchmark
                |
                v
       Reference Intake or PlannerPort
                |
                v
          RunCoordinator
     observe / gate / act / verify
        /          |           \
   Adapters     Trace Store   Recovery
        \          |           /
                Evaluator
                    |
              Evolution Gate
```

## 3. What Must Exist

The following capabilities are required to prove the project thesis:

| Capability | Current implementation target |
| --- | --- |
| Unified Affordance Model | common envelope plus typed DOM, visual, accessibility, and WoT payloads |
| Planner boundary | `PlannerPort` with scripted, reference LLM, and parent-agent-compatible implementations over time |
| Coordinator | one authoritative state writer and action scheduler per run |
| Action Contract | the only object that may enter an executor |
| State validity | snapshot identity, page revision, target fingerprint, and expiration |
| Policy | task constraints, capability checks, and approval for effectful actions |
| Execution routing | Playwright DOM first; visual and WoT as bounded adapter proofs |
| Verification | receipt separated from independent postcondition evidence |
| Recovery | small deterministic matrix with explicit budgets and no blind effectful retry |
| Trace | append-only event log plus artifact references |
| Evaluation | resettable fixtures, baselines, perturbations, ablations, and independent oracles |
| Evolution | failure classification, declarative artifact proposal, replay, and registry decision |

## 4. What Is Intentionally Narrow

Each required capability begins with one useful implementation:

| Area | First implementation |
| --- | --- |
| Planner | scripted planner for deterministic benchmark diagnosis |
| Browser backend | Playwright |
| DOM observation | Playwright DOM and accessibility state |
| Visual adapter | Set-of-Marks fixture-level grounding |
| WoT adapter | Thing Description parser plus local device fixture |
| State | in-memory `RunState` for one active run |
| Trace | JSONL and filesystem artifacts |
| Benchmark | three local SaaS scenarios |
| Recovery | stale, locator, modal, timeout, verifier, and capability cases |
| Evolution | declarative skill, policy, verifier, affordance-rule, or fixture patches |
| External interface | CLI first; task-level MCP later |

Completeness comes from connecting these components, not from adding many
providers, frameworks, backends, or services.

## 5. Core Runtime

### 5.1 Coordinator Rule

Each run has one `RunCoordinator` that owns authoritative state transitions and
dispatches every executable contract. Other components return immutable
observations, proposals, decisions, receipts, or reports.

```text
Parent Agent -> task, context, approval
Planner      -> proposal
Policy       -> allow, deny, or approval required
Executor     -> execution receipt
Verifier     -> verification report
Recovery     -> bounded recovery proposal
Coordinator -> only component that advances RunState
```

The planner cannot grant capability or execute actions. The executor cannot
reinterpret a contract. The verifier cannot mutate task state.

### 5.2 Runtime State Machine

The current implementation uses one task-level state machine:

```text
CREATED
OBSERVING
PLANNING
PREFLIGHT
WAITING_APPROVAL
ACTING
VERIFYING
RECOVERING
DONE
FAILED
ABORTED
```

Main path:

```text
CREATED -> OBSERVING -> PLANNING -> PREFLIGHT
        -> ACTING -> VERIFYING -> OBSERVING | PLANNING | DONE
```

Control and failure paths:

```text
PREFLIGHT -> OBSERVING          stale or expired state
PREFLIGHT -> WAITING_APPROVAL   approval required
PREFLIGHT -> ABORTED            policy denied
ACTING -> RECOVERING            execution failed or became uncertain
VERIFYING -> RECOVERING         expected effect not established
RECOVERING -> OBSERVING         bounded recovery is safe
RECOVERING -> FAILED            budget exhausted or risk too high
```

Browser and container availability remain ordinary runtime fields until an
independent worker actually exists.

### 5.3 RunState and Memory

`RunState` stores only information needed for the next safe decision:

```text
run_id, task_spec, phase
current observation, snapshot, contract
constraints, capabilities, pending approval
active subgoal, obligations, evidence refs
step and recovery budgets
latest receipt and verification
final result
```

Memory has three practical layers:

| Layer | Contents |
| --- | --- |
| Working state | current goal, constraints, snapshot, contract, evidence obligations, and budgets |
| Episodic trace | all events and artifact references from this run |
| Accepted harness knowledge | regression-approved skills, policies, verifier rules, and fixtures |

Raw DOM, screenshots, downloads, and complete histories are stored as artifacts,
not accumulated in `RunState`. No vector database is required for the current
runtime.

## 6. Affordance and Contract Model

### 6.1 Affordance

The shared envelope supports common routing, policy, trace, and evaluation:

```text
id, surface, kind, label, semantic role
state, confidence, risk
backend candidates, evidence refs
snapshot id, target fingerprint
typed payload
```

Typed payloads preserve surface detail:

```text
DOM: locator candidates, role/name, form context, uniqueness
Visual: bbox, mark id, screenshot ref, descriptor
Accessibility: role/name/path, enabled/focused state
WoT: href, operation, method, schemas, security metadata
```

### 6.2 Validity Boundary

The first implementation uses:

```text
snapshot_id
page_revision
target_fingerprint
expires_at
artifact content hash
```

Preflight checks that the snapshot is current, the lease has not expired, the
target fingerprint still matches, preconditions hold, and capability/approval
is valid. More revision dimensions are introduced only if benchmark evidence
shows this representation is insufficient.

### 6.3 Action Contract

An Action Contract binds semantic intent to an executable target and verifier:

```text
schema_version, contract_id, run_id
snapshot_id, page_revision, target affordance, target fingerprint
intent, action, backend, parameters
preconditions, expected effects, verifier plan
required capabilities, risk, approval binding
idempotency key, compensation, timeout
```

Contract data is immutable after approval and must be canonicalizable for
hashing and trace replay.

## 7. Execution, Verification, and Recovery

Execution follows:

```text
pre-observation
  -> policy and preflight
  -> execute contract
  -> ExecutionReceipt
  -> post-observation
  -> VerificationEvidence
  -> VerificationReport
```

An executor receipt proves a technical attempt, not task success. Verification
states are `PASSED`, `FAILED`, `INCONCLUSIVE`, and `ERROR`.

The first verifier set is deliberately small:

- DOM state and URL verifiers
- fixture API or database verifier
- file/download receipt and hash verifier
- screenshot evidence verifier
- model judgment only as weak supporting evidence

Recovery is bounded:

| Failure | Response |
| --- | --- |
| stale snapshot | re-observe and replan |
| locator missing | rebuild affordances, then one backend fallback |
| blocking modal | apply a registered low-risk modal policy or ask/abort |
| execution timeout | observe first, then decide whether retry is safe |
| inconclusive verification | gather one stronger evidence source, then replan/fail |
| capability denied | request approval or abort |

Effectful actions are never blindly retried after timeout or uncertain
execution.

## 8. Async and Docker Boundary

The runtime uses `async` I/O while preserving serial action semantics:

```text
one run
one coordinator
one browser session
one active Action Contract
```

Read-only observation capture, independent verifiers, and artifact hashing may
run concurrently when they refer to the same observation epoch. State mutation,
approval consumption, effectful execution, compensation, and trace sequencing
remain serial.

Docker is used for reproducibility and isolation:

```text
docker compose
  fixture-web
  fixture-db
  artifact-volume
  optional runtime container
```

It is not used to create scheduler, coordinator, browser-worker, event-broker,
or memory microservices in the current plan.

## 9. Trace, Benchmark, and Evolution

### 9.1 Trace

Canonical run storage is an append-only `events.jsonl` file plus artifacts:

```text
artifacts/<run_id>/
  run.json
  events.jsonl
  observations/
  screenshots/
  dom/
  receipts/
  downloads/
  eval_report.json
```

Events cover observation, snapshot, proposal, contract, policy/preflight,
approval, execution, verification, recovery, and final result. Parent links may
derive causal views without requiring a graph database.

### 9.2 Benchmark

The primary fixtures are:

1. read-only pricing extraction
2. reversible settings update
3. approval-gated report export

The core comparison is Direct Playwright versus Affordance Runtime. Required
ablations are no preflight, no structural verifier, no capability gate, and no
recovery.

Release-facing metrics are limited to:

```text
task_success_rate
stale_detection_recall
verifier_false_accept_rate
constraint_violation_rate
recovery_success_rate
regression_delta
```

Latency, cost, action count, observation count, and fallback count remain
supporting telemetry.

MiniWoB++ is a secondary generalization suite, not a replacement for the local
SaaS fixtures. The official Farama HTML tasks may be driven through Playwright,
but release claims require a runtime adapter that owns episode start/reset,
instruction extraction, termination/reward collection, artifact capture, and
report aggregation. A one-episode compatibility smoke is not a benchmark result.

The M8 subset will pin the official source; cover click, type, select, dialog,
sequence, and form families; run repeated unmodified episodes; and report
official success/reward beside runtime diagnostics. It must be labelled a
curated runtime subset, never a full MiniWoB++ score.

### 9.3 Controlled Harness Evolution

The evolution loop is required, but it operates on declarative artifacts rather
than arbitrary source-code mutation:

```text
failed trace
  -> classify perception / planning / grounding / execution /
     verification / recovery / safety failure
  -> propose Skill, PolicyPatch, VerifierPatch, AffordanceRule,
     or BenchmarkFixture
  -> replay the original failure and related task family
  -> run safety smoke tests
  -> accept, quarantine, reject, or roll back
```

A failure classifier and a report comparing an existing full-runtime variant
against a broken ablation are useful prototype evidence, but do not yet prove
self-evolution. The claim requires a typed artifact with executable payload,
loading it into a fresh candidate runtime, rerunning the suites, persisting the
registry decision, and proving rollback.

## 10. Milestones

### M0: Design Alignment - done

Freeze one state machine, current wire contracts, trace schema, scenario specs,
and declarative evolution artifact schema.

### M1: Web Runtime Core - done

Deliver the pricing fixture, Playwright observer/executor, DOM affordances,
scripted planner, contract/preflight, post-action verification, artifact-backed
trace, CLI, and Direct Playwright baseline.

### M2: Reliability and Cross-Surface Proof - done for the local profile

The three local scenarios and 3 x 7 matrix run successfully. The current seed
argument does not yet generate distinct variants. SoM and WoT prove common
contract reuse in controlled tests, not live-environment generalization.

### M3: Assisted Evolution Prototype - done through M6

Implemented: classification, proposal types, direction-aware gates,
replay-category accounting, and before/after reporting.

M6 applied a SHA-bound executable verifier proposal to a fresh candidate,
generated new replay traces, persisted the registry decision, and proved
rollback.

### M4: Local Integration Boundary - done through M7

Implemented: in-process task service, bounded parent-agent-shaped tool adapter,
external task JSON-RPC, and a real LangGraph parent in a separate process. The
parent has no access to primitive click/type/observe operations.

### M5: Evidence Freeze - done

- commit the current implementation as a reviewable unit
- add CI for tests, Ruff, mypy, package build, and focused Chromium smoke
- record runtime commit, browser version, fixture version, and seed semantics
- publish reproducible benchmark and evolution summaries
- keep README and status claims aligned with generated evidence

Exit: a clean checkout reproduces the local gold path, 3 x 7 matrix, and
evolution prototype.

Evidence: `./scripts/reproduce_local.sh` passed from a clean clone at commit
`4528f25baab0778a6eec4ce37a9fba82f2a7635e`; see
`evidence/m5-4528f25.md`. The recorded seed semantics remain
`label_only_v1`, so randomized/generalization claims stay gated on M8.

### M6: Executable Harness Evolution - done

- add an executable payload for at least one verifier or policy patch
- load it into a fresh candidate runtime
- replay original, task-family, global-smoke, and safety-smoke suites
- persist artifact/registry versions and demonstrate rollback

Exit: one failed trace produces an applied artifact that fixes the failure with
zero safety regression.

Evidence: a clean clone at `4cccc96a0dc14ebdd5c11f03896ff307835ad69c`
loaded `verifier_patch-reversible_settings_update@1.0.0` into a fresh
no-verifier runtime, produced six new Chromium traces across all mandatory
categories, persisted acceptance, and proved runtime plus registry rollback.
See `evidence/m6-4cccc96.md`.

### M7: Real Parent-Agent Integration - done

Expose the bounded API through MCP or an equivalent external protocol. One real
Codex, Claude, OpenHands, or LangGraph parent must complete the pricing flow and
the approval-gated export flow while Runtime remains authoritative.

Evidence: a clean clone at `9a9796e66be882b03a9f8059e89dbb22c9e5b056`
compiled LangGraph 1.2.9 and called a separate runtime process through
`affordance-task-rpc/1.0`. Pricing succeeded; export stopped for scoped
approval and then succeeded with file-hash evidence; only eight task-level
tools were exposed. See `evidence/m7-9a9796e.md`.

### M8: Generalization Evaluation - required for broad claims

- make seeds produce distinct fixture variants
- add unseen layouts or hidden perturbations
- add a pinned official MiniWoB++ adapter and repeated curated subset
- cover click, type, select, dialog, sequence, and form families
- add a real visual grounding path, not only a static SoM contract proof
- report official MiniWoB success/reward and runtime failure diagnostics

Current MiniWoB++ evidence is compatibility-only: on 2026-07-20 the official
Farama source at commit `eb59fed60fabe8951350275ba8650633b740013b` served the
real `click-button` task; BrowserSession built a DOM affordance, DomExecutor
executed an ActionContract, and the task returned `WOB_DONE_GLOBAL=true` and
raw reward `1.0`. No suite adapter or repeated report exists yet.

### M9: Durable Single-Run Recovery - conditional

Promote only after restart, approval-wait, or uncertain-effect tests expose a
real need. Use a simple durable store for run state, events, idempotent commands,
and effect inspection. Do not add a worker pool or distributed queue.

### PiP Decision Gate

PiP remains optional. It is an observer/human-takeover UI, not browser isolation
or a second runtime. Begin it only if M7 testing shows trace streaming and the
normal run console are insufficient.

## 11. Explicitly Deferred

- durable run queue and scheduler
- browser worker pool and independent browser RPC
- worker lease, heartbeat, and fencing token
- distributed checkpoint and takeover
- multi-tenant authorization and quotas
- Kubernetes, Kafka, or a distributed event bus
- multiple planners competing online for one browser session
- multiple agents controlling the same page
- unrestricted cross-run vector memory
- automatic arbitrary source-code mutation
- continuous watcher until it beats post-action observation
- Picture-in-Picture implementation before the M4 entry conditions and a
  demonstrated standalone or human-takeover use case

These remain available in the complete blueprint. They become current work only
after a measured bottleneck, a scenario requirement, and an explicit project
plan update justify them.
