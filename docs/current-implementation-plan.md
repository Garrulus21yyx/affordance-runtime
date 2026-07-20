# Current Implementation Plan

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
        -> ACTING -> VERIFYING -> PLANNING | DONE
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

At least one real failed trace must complete this loop before the project claims
harness self-evolution.

## 10. Milestones

### M0: Design Alignment

Freeze one state machine, current wire contracts, trace schema, scenario specs,
and declarative evolution artifact schema. Mark planned features honestly.

### M1: Web Runtime Core

Deliver the pricing fixture, Playwright observer/executor, DOM affordances,
scripted planner, contract/preflight, post-action verification, artifact-backed
trace, CLI, and Direct Playwright baseline.

### M2: Reliability and Cross-Surface Proof

Deliver settings and export fixtures, stale/modal/selector/download
perturbations, capability/approval, bounded recovery, benchmark runner, visual
SoM proof, and local WoT proof. Visual and WoT demonstrate contract reuse; they
do not become separate products.

### M3: Harness Evolution

Deliver failure classification, declarative proposals, registry, regression
replay, and a before/after report for at least one real failure.

### M4: Optional Integrations and Observer UI

Add a task-level MCP API, LLM reference planner, LangGraph outer adapter, public
benchmark adapters, or an optional Picture-in-Picture observer according to
demonstrated need. None blocks M3.

PiP is an observer and human-takeover UI, not browser session isolation and not
a second execution runtime. It may show the live environment, current subgoal,
pending action, approval state, and verification status. It is view-only by
default; pause and takeover are explicit Coordinator commands.

PiP work may begin only after trace streaming, pause/cancel/resume, approval,
and the Web gold path are stable. Its acceptance checks cover focus stealing,
input leakage, stream latency, pause/takeover correctness, close/restore
behavior, trace consistency, and resource overhead.

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
