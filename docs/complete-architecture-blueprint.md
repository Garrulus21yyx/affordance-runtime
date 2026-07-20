# Complete Architecture Blueprint

## 1. Purpose and Status

This document preserves the complete architecture considered for a future
service-grade Affordance Runtime. It explains how the current domain model could
support durable runs, multiple workers, asynchronous agents, richer context and
memory, container isolation, crash recovery, and production integrations.

It is a reference architecture, not the current implementation contract.
Current releases follow the [Current Implementation Plan](current-implementation-plan.md).
Nothing in this document becomes required merely because it is described here.

Promotion into the current plan requires all of the following:

1. a concrete benchmark, integration, or operational failure needs it
2. the simpler design has been measured and shown insufficient
3. ownership, persistence, safety, and compatibility semantics are specified
4. the project plan names an entry criterion, deliverable, and exit criterion

## 2. Target Product Boundary

The eventual product can support three modes without changing its execution
semantics:

```text
Reference Agent Mode
  natural-language intake + reference planner + runtime

Subagent Mode
  parent agent submits a typed bounded task

Harness Mode
  evaluator controls fixtures, perturbations, replay, and grading
```

The runtime remains planner-neutral. A reference manager or LLM is an adapter,
not the authority for policy, side effects, or verification.

## 3. Complete Topology

```text
CLI / MCP / REST / Parent Agent
                |
                v
        Intake and Run Service
 task compile / submit / cancel / approve / query
                |
                v
        Durable Run Scheduler
 queue / backpressure / ownership / deadlines
                |
                v
       Per-Run Coordinator Worker
 single authoritative writer / state machine / budgets
       /          |           |          \
 PlannerPort   PolicyPort  VerifierPort  RecoveryPort
       \          |           |          /
                ExecutorPort
                    |
          Browser / Device Worker Pool
                    |
             Target Environment

Persistence
  Run Store
  Event Store
  Checkpoint Store
  Artifact Store
  Evolution Registry

Operations
  Metrics / logs / traces
  image and fixture identity
  worker health and resource limits
```

The system still follows one critical rule: one coordinator owns authoritative
state for a run, and one effectful Action Contract is active per browser session.

## 4. Lifecycle Model

At production scale, three state dimensions may be separated.

### 4.1 Run Lifecycle

```text
QUEUED
STARTING
RUNNING
WAITING_APPROVAL
WAITING_PARENT_CONTEXT
SUSPENDING
SUSPENDED
RESUMING
CANCELLING
CANCELLED
SUCCEEDED
FAILED
FAILED_UNCERTAIN
EXPIRED
```

This state answers whether a run is scheduled, waiting, resumable, cancelled,
or terminal.

### 4.2 Execution Phase

```text
OBSERVING
MODELING
PLANNING
PREFLIGHT
ACTING
OBSERVING_POST_ACTION
VERIFYING
RECOVERING
```

This state answers what the domain runtime is doing now.

### 4.3 Session Lifecycle

```text
ALLOCATING
READY
BUSY
WAITING
LOST
RELEASING
RELEASED
```

This state answers whether the browser or device resource still exists and who
owns it. These dimensions should remain separate instead of creating combined
states such as `WAITING_APPROVAL_WITH_BROWSER_READY_AT_PREFLIGHT`.

The current plan deliberately collapses this model into one task phase plus
ordinary browser fields. Separation is promoted only when durable pause/resume
or independent workers exist.

## 5. Asynchronous Concurrency and Ownership

### 5.1 Single Writer

For each run:

- one coordinator writes authoritative state and run sequence numbers
- planners, observers, verifiers, recovery agents, and executors return
  immutable proposals or results
- every asynchronous result binds `run_id`, `based_on_state_version`, and the
  relevant snapshot or observation epoch
- stale results are recorded and discarded, never silently merged

Example proposal envelope:

```json
{
  "proposal_id": "prop_017",
  "run_id": "run_001",
  "based_on_state_version": 12,
  "snapshot_id": "snap_004",
  "candidate_contract": {}
}
```

### 5.2 Safe Parallel Work

The following may run concurrently when inputs are immutable and share an
observation epoch:

- DOM, screenshot, and accessibility capture
- independent read-only verifiers
- multiple planner candidates
- artifact compression, checksums, and persistence
- independent benchmark oracle queries
- independent complete rollouts in isolated environments

The following remain serial per session:

- effectful actions
- capability and approval consumption
- authoritative state mutation
- event sequence assignment
- compensation and effectful retry

Multiple planner candidates are selected by deterministic policy over validity,
capability, verifier strength, risk, cost, confidence, and recovery complexity.
They do not share a mutable chat history.

### 5.3 Cross-Run Limits

The service may enforce:

```text
max_concurrent_runs
max_browser_sessions
max_model_calls
max_observation_tasks
max_downloads
per-caller quotas
```

Queueing, rejection, timeout, and backpressure behavior must be explicit.

## 6. Durable Commands, Events, and Queries

Cross-process contracts are split by purpose:

```text
Commands
  request a state change

Domain Models
  immutable runtime values

Events
  append-only facts that already occurred

Queries / Projections
  caller-facing views of current state

Artifact Manifests
  references to large or sensitive content
```

Representative commands:

```text
SubmitTask
CancelRun
ApproveAction
RejectAction
ProvideContext
ResumeRun
```

Representative events:

```text
RunCreated
ObservationCaptured
SnapshotBuilt
ContractProposed
PolicyDecided
ActionStarted
ActionCompleted
VerificationCompleted
RunSuspended
RunCompleted
```

Event envelope:

```json
{
  "schema_version": "1.0",
  "event_id": "evt_017",
  "run_id": "run_001",
  "sequence": 17,
  "event_type": "action.completed",
  "occurred_at": "2026-07-20T12:00:00Z",
  "correlation_id": "run_001",
  "causation_id": "cmd_009",
  "actor": {"kind": "executor", "id": "browser_worker_03"},
  "state_version_before": 11,
  "state_version_after": 12,
  "payload": {},
  "artifact_refs": []
}
```

Sequence is ordered within a run. Events are immutable; corrections are new
events. Contract, event, artifact, and API schemas are versioned independently.

Wire boundaries may use Pydantic and JSON Schema while internal domain logic
uses immutable dataclasses. Surface and evidence payloads should be tagged
unions instead of unrestricted dictionaries.

Contract hashing requires canonical JSON rules, an explicit included-field
set, stable list semantics, and immutability after approval.

## 7. Context and Intent Architecture

### 7.1 Intent Compilation

Standalone mode may add:

```text
Raw User Request
  -> Intent Interpreter
  -> Task Compiler
  -> Policy Resolver
  -> immutable TaskSpec revision
  -> Planner
```

Intent interpretation may use an external or local LLM, but cannot grant
capability, remove constraints, or authorize side effects. High-risk ambiguity
returns `NEEDS_CLARIFICATION`.

Benchmark mode should normally begin from a canonical TaskSpec so intent errors
and runtime errors can be measured separately. Parent agents may submit TaskSpec
directly but the runtime still validates policy, capabilities, ambiguity, and
success criteria.

Intent changes create a new TaskSpec revision. Pending contracts based on an
older revision must be rejected or revalidated.

### 7.2 Context Views

Only the coordinator receives the complete authoritative context.

| View | Contents |
| --- | --- |
| RunContext | task, constraints, lifecycle, state version, snapshot, budgets, approvals, obligations, evidence index, session binding |
| PlannerContext | goal, active subgoal, constraints, affordance summary, capabilities, budgets, recent relevant failures, state/snapshot version |
| ExecutorContext | validated contract, session handle, validity token, timeout, artifact sink |
| VerifierContext | expected effects, pre/post evidence refs, receipt, oracle handles, verification policy |

Secrets, cookies, stale locators, full DOM history, and unrelated traces are not
copied into model context. Parent updates arrive as version-bound ContextPatch
commands. Constraint relaxation follows a stronger policy than ordinary context
addition.

## 8. Memory Model

The complete design distinguishes four layers:

| Layer | Purpose |
| --- | --- |
| Authoritative working state | current facts required for safe execution |
| Working memory | sourced hypotheses, unresolved questions, obligations, and recovery history |
| Episodic memory | events, observations, contracts, receipts, reports, and artifacts for a run |
| Cross-run semantic memory | accepted skills, policies, verifier rules, negative examples, and fixtures |

Working-memory items carry source event ids, confidence, creation time,
revision-based expiration, status, taint, and sensitivity. Episodic data lives in
event and artifact stores; state holds references and projections.

Cross-run knowledge can influence execution only after versioning, review, and
regression validation. Unreviewed run summaries do not become policy.

Planner summaries bind the event sequence, state version, and snapshot from
which they were derived, allowing invalidation after environment change.

## 9. Persistence and Crash Recovery

A durable run may store:

```text
run record
append-only events
periodic checkpoints
artifact manifests and content
approval records
benchmark/evaluation records
```

Checkpoint opportunities include before and after effectful actions, before
waiting for approval, before suspension, at terminal states, and every bounded
number of events.

Recovery performs:

```text
load latest checkpoint
  -> replay later events
  -> rebuild runtime projection
  -> inspect worker and session availability
  -> re-observe the real environment
  -> verify unresolved side effects
  -> resume, recover, compensate, or fail uncertain
```

Worker ownership may use:

```text
run_owner_worker_id
worker_lease_id
lease_expires_at
fencing_token
```

Each effectful execution carries the current fencing token. A former worker
cannot continue after ownership transfers.

A process or container crash never proves that an external side effect did not
occur. The recovered coordinator inspects and verifies post-state before retry.

Cancellation also uses safe points. If an effect may already be in flight, the
run enters `CANCELLING`, observes post-state, verifies or compensates, and then
becomes `CANCELLED` or `FAILED_UNCERTAIN`.

## 10. Container and Security Architecture

A service deployment may separate:

```text
control plane
coordinator workers
browser/device workers
fixture or target environments
durable data stores
```

Operational bindings record run, coordinator, worker, browser session/context,
image digests, fixture version/seed, acquisition time, and lease expiration.
Operational identity must not alter domain policy.

Security requirements include:

- non-privileged containers and bounded CPU, memory, process, and time limits
- target-specific network policy and no sensitive host mounts
- isolated download and artifact staging
- cleanup of browser contexts and temporary files
- secrets excluded from images, traces, screenshots, and model context
- deterministic fixture reset for evaluation
- tenant, caller, capability, and artifact-access boundaries if multi-tenancy is
  ever introduced

Page DOM, accessibility text, OCR, and screenshots are tainted. They may suggest
an action but cannot grant capability, rewrite user constraints, or authorize an
approval. Unknown effectful actions default to deny or clarification.

Approval tokens are single-use and bind run, contract hash, TaskSpec revision,
environment validity, capability, approver, and expiration.

## 11. Operational Observability

Domain/audit trace answers why an action was proposed, authorized, executed,
verified, and recovered. Operational telemetry records queue wait, container
startup, worker heartbeat, resource use, RPC retry, browser failure, artifact
latency, and model latency.

The two streams correlate through run, event, worker, and session ids but remain
semantically separate. Operational telemetry is not business verification
evidence.

## 12. Framework Boundary

LangGraph, AutoGen, or another agent framework may orchestrate coarse-grained
outer work:

```text
intake_task
decompose_task
run_bounded_gui_task
await_approval
run_non_gui_subtask
aggregate_results
```

The framework does not own authoritative GUI state and does not replace
Action Contract validation, preflight, post-action observation, verification,
or side-effect recovery. Low-level runtime phases should not each become graph
nodes.

External interfaces may expose:

```text
gui_submit_task
gui_get_run
gui_approve_action
gui_reject_action
gui_provide_context
gui_cancel_run
gui_resume_run
gui_get_result
gui_get_trace
gui_get_artifacts
```

## 13. Complete Benchmark Program

A service-grade benchmark program may add:

- multiple resettable web suites and hidden perturbation seeds
- visual, accessibility, and WoT surface suites
- public benchmarks such as MiniWoB++ or WebArena-compatible tasks
- model/provider/version, temperature, timeout, cache, and environment identity
- repeated runs with variance or confidence intervals
- direct automation, primitive-agent, and full-runtime baselines
- component and policy ablations
- deterministic crash, cancellation, duplicate-command, and worker-loss tests
- concurrency and backpressure evaluation
- security suites for prompt injection, deceptive UI, approval replay, stale
  replay, capability escalation, and trace leakage

Every release metric defines numerator, denominator, direction, unit, oracle,
aggregation, and threshold. The acting model is never the sole final grader.

## 14. Complete Evolution Architecture

The evolution system may eventually contain:

```text
Failure Analyzer
  -> trace segmentation and causal attribution
Proposal Generator
  -> skill, policy, verifier, affordance, prompt, or fixture artifact
Quarantine Registry
  -> source version, target suites, TTL, reviewer, rollback target
Regression Runner
  -> original failure, family suite, safety suite, broad smoke suite
Decision Policy
  -> accept, reject, quarantine, expire, or roll back
```

Metric acceptance rules are directional; success rate has a minimum threshold,
unsafe-side-effect rate has a maximum threshold, and cost has an allowed budget
or regression. Automatic production mutation remains outside the plan until
artifact generation and evaluation are reproducible and safe.

## 15. Additional Production Invariants

The complete architecture adds these invariants to the current ten:

| ID | Invariant |
| --- | --- |
| INV-11 | Each run has at most one authoritative state writer. |
| INV-12 | At most one effectful contract is active per session. |
| INV-13 | Every asynchronous result is state-version-bound and stale results are rejected. |
| INV-14 | A waiting run is durably recoverable or explicitly expires. |
| INV-15 | Duplicate commands do not create duplicate runs, approvals, or effects. |
| INV-16 | Worker failure never implies an external action did not occur. |
| INV-17 | Large artifacts are referenced; working state remains bounded. |
| INV-18 | Cross-run knowledge is activated only after review and regression. |
| INV-19 | Operational identity cannot change domain authorization. |
| INV-20 | Cancellation of an uncertain effect requires post-state inspection. |

## 16. Possible Production Milestones

These milestones begin only after the current M3 harness evolution loop is
working:

### P1: Durable Single-Run Service

Run API, durable event/checkpoint storage, approval/cancel/resume, and restart
recovery while retaining a single coordinator process.

### P2: Independent Browser Workers

Worker protocol, session ownership, artifact store, worker loss injection, and
fencing around effectful actions.

### P3: Bounded Multi-Run Scheduling

Queue, concurrency limits, backpressure, per-run ownership, resource quotas,
and concurrent benchmark execution.

### P4: Outer Agent Orchestration

LangGraph or another coarse-grained integration, parent-agent handoffs,
long-running approval, and independent rollout aggregation.

### P5: Production Governance

Authentication, tenant isolation if required, retention/redaction, artifact
access policy, audit controls, release gates, and rollback operations.

## 17. Scope Warning

This blueprint exists to prevent accidental architectural dead ends, not to
maximize component count. A production concept should remain documentation-only
until evidence makes it part of the current plan. The core project remains the
GUI harness loop: reliable execution, independent verification, trace-based
diagnosis, benchmark evidence, and regression-gated evolution.
