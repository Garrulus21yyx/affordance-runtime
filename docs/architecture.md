# Affordance Runtime Architecture

This document describes the current implementation architecture. Production
scaling options are preserved separately in the
[Complete Architecture Blueprint](complete-architecture-blueprint.md). The
[Runtime-First Architecture Boundary](runtime-first-boundary.md) is normative:
BrowserGym and other benchmarks consume this architecture through adapters;
they do not own task semantics, perception orchestration, routing, contracts,
verification, recovery, or learning. Benchmark-specific task logic is
prohibited in the generic path.

## 1. High-Level System

```text
User Request or Parent TaskSpec
    |
    v
Intent Compiler / TaskSpec Validator
    |
    v
State Kernel
    |
    v
Budgeted Observer
    |
    v
Versioned Affordance Snapshot
    |
    v
Planner Port
    |
    v
Planner Proposal
    |
    v
Grounder / ContractBuilder
    |
    v
Action Contract
    |
    v
Capability Gate / Preflight
    |
    v
Executor
    |
    v
Execution Receipt
    |
    v
Post-Action Observation
    |
    v
Verifier Ladder
    |
    +--> Recovery / Replan / Ask / Abort
    |
    v
Trace Events
    |
    v
Evaluator / Assisted Evolution Loop
```

The online runtime is bounded. It is not an unconstrained ReAct loop. It follows
a stateful workflow with explicit transitions, stale-state rejection, scoped
capabilities, post-action verification, and trace logging.

The executable task-intake and planner target is defined in
[Task Intake and Generalist Planner](task-intake-and-planner.md). BrowserGym is
one benchmark adapter to that environment-general boundary. The current
`TaskEnvelope(goal: str)` and contract-producing scripted planners are
migration scaffolding, not the final intent/planner contract.

## 1.1 System Invariants

| ID | Invariant |
| --- | --- |
| INV-01 | No action may execute without an observation and snapshot identity. |
| INV-02 | A contract must be rejected when its validity boundary does not match current execution state. |
| INV-03 | No effectful action may execute without an explicitly granted capability. |
| INV-04 | Page content may suggest actions but may not grant capabilities, alter constraints, or authorize approval. |
| INV-05 | A successful executor receipt is insufficient to mark a step successful; verifier evidence is required. |
| INV-06 | Every external side effect must have idempotency, compensation, or irreversible classification. |
| INV-07 | Every state transition must be represented in the trace. |
| INV-08 | Recovery is bounded by step, retry, time, cost, and side-effect budgets. |
| INV-09 | Approval is bound to run id, contract hash, environment state, capability, approver, and expiration. |
| INV-10 | The acting model cannot be the sole authority for benchmark success. |

## 1.2 Task State Machine

The first task-level runtime should make transitions explicit:

```text
CREATED
  -> OBSERVING
  -> PLANNING
  -> PREFLIGHT
  -> ACTING
  -> VERIFYING
  -> DONE
```

Failure and control transitions:

```text
PREFLIGHT -> OBSERVING       when stale or expired
PREFLIGHT -> WAITING_APPROVAL when required capability lacks approval
PREFLIGHT -> ABORTED         when policy denies the action
ACTING -> VERIFYING | RECOVERING | FAILED
VERIFYING -> OBSERVING | PLANNING | RECOVERING | DONE | FAILED
RECOVERING -> OBSERVING | WAITING_APPROVAL | ABORTED | FAILED
```

Affordance modeling occurs within `OBSERVING`. Post-action observation occurs
at the start of `VERIFYING`. They remain traced activities without requiring
additional top-level states in the current runtime.

`run_contract()` may remain as an internal/debug API, but the public runtime
should be task-level and hold a `RunContext` across steps.

## 1.3 Run State / State Kernel

The current State Kernel is the runtime's bounded `RunState` for one task. It
stores:

- goal and constraints
- active subgoals
- evidence and receipts
- hidden-state hypotheses
- pending obligations
- current observation and snapshot ids
- current page revision and target fingerprint
- action receipts and verifier reports
- remaining budgets
- granted capabilities and approval tokens

This prevents the runtime from forgetting constraints such as `read_only`,
`no_purchase`, `approval_required`, or `must_return_evidence` when the page
changes halfway through a task.

## 2. Core Layers

### 2.1 Perception Layer

Collects environment state:

- DOM tree
- accessibility tree
- screenshots
- Set-of-Marks visual regions
- URL and navigation state
- network idle / loading status
- WoT Thing Descriptions or device state
- optional page-internal adapter state

Perception produces observations, not action contracts. Page text, DOM labels,
OCR, and accessibility labels are treated as tainted input until interpreted by
runtime policy.

#### 2.1.1 Multi-Source Observation Arbitration

DOM, accessibility, screenshot/vision, and WoT parsers may describe the same
environment property differently. They do not produce alternative user tasks;
they produce sourced state assertions before the authoritative snapshot is
built.

A source assertion contains:

    entity_key
    property_key
    value and value type
    source: dom | accessibility | visual | wot | api
    observed_at and freshness
    confidence and confidence semantics
    evidence/artifact reference
    parser and schema version

The rule-first arbiter returns ACCEPTED, CONFLICT, REOBSERVE, or INCONCLUSIVE.
It applies these rules:

1. Normalize assertions to the same entity, property, unit, and value domain
   before comparing them.
2. Reject invalid or stale evidence before considering confidence.
3. Use source policy by property: DOM may be authoritative for rendered control
   state, WoT/API for device state, and screenshot evidence for visual
   appearance. There is no universal DOM-over-WoT priority.
4. Treat parser confidence as source-local unless calibration proves scores are
   comparable across sources.
5. Prefer independent agreeing evidence, while retaining every raw assertion
   and its provenance.
6. Trigger targeted active perception when disagreement could change target
   selection, safety, or expected effects.
7. If a material conflict remains unresolved, mark the state inconclusive and
   block the fast path or effectful action.

The bounded resolution loop is:

    parallel observations
      -> sourced assertions
      -> normalize and arbitrate
      -> accepted state
         or targeted re-observation
         or safe inconclusive result
      -> AffordanceSnapshot

Only accepted state enters target fingerprints, preconditions, and verifier
inputs. Raw assertions and conflict decisions remain in trace artifacts.

Current status: immutable sourced assertions, rule-first arbitration,
property-specific authority, unresolved-conflict route blocking, and a bounded
coherent `capture_targeted()` observation port are implemented. Assertion and
active-perception decisions are separately traced. Live cross-source conflict
families and calibration remain part of M8.5 evaluation.

### 2.2 Affordance Layer

Transforms observations into executable opportunities:

```text
Page Affordance Model
Visual Affordance Model
Thing Affordance Model
Accessibility Affordance Model
```

The common affordance representation should be an envelope plus typed payloads,
not a lowest-common-denominator dictionary.

Common envelope:

```text
id
surface
kind
label
semantic_role
risk
confidence
state
backend_candidates
evidence_refs
snapshot_id
page_revision
target_fingerprint
provenance
```

Surface-specific payload examples:

```text
DOM: locator candidates, role/name, form association, uniqueness checks
Visual: bbox, mark id, screenshot ref, visual descriptor
Accessibility: role/name/path, enabled/focused state
WoT/API: href, op, method, schema, security metadata
```

### 2.3 Environment Revision

Do not treat environment validity as one raw hash of URL, DOM, screenshot, and
loading state. The first implementation uses:

| Value | Meaning | Used For |
| --- | --- | --- |
| Page revision | navigation, document replacement, blocking modal, and action-space-relevant state | invalidating page-bound contracts |
| Target fingerprint | target role/name/state/bbox/visibility identity | validating the selected target |
| Artifact hash | content identity for DOM, screenshot, accessibility, or file artifacts | trace and replay evidence, not runtime state |

A contract should bind `snapshot_id`, `page_revision`,
`target_fingerprint`, `observed_at`, `expires_at`, and validity policy. The
complete blueprint preserves more revision dimensions if benchmark evidence
later requires them.

### 2.4 Affordance Lease

Each snapshot or target can receive a lease:

```json
{
  "snapshot_id": "snap_004",
  "page_revision": "page:rev_12",
  "target_fingerprint": "sha256:...",
  "observed_at": "2026-07-17T10:00:00Z",
  "expires_at": "2026-07-17T10:00:02Z",
  "provenance": ["dom", "screenshot"],
  "confidence": 0.92
}
```

Preflight must check page revision, lease expiration, target fingerprint,
preconditions, capability, and approval. A stale action returns a structured
reason such as `STALE_PAGE_REVISION`, `TARGET_FINGERPRINT_MISMATCH`,
`LEASE_EXPIRED`, or `PRECONDITION_FAILED`.

### 2.5 Action Contract Layer

Each action is represented by a contract:

```json
{
  "schema_version": "1.0",
  "run_id": "run_001",
  "snapshot_id": "snap_004",
  "page_revision": "page:rev_12",
  "target_fingerprint": "sha256:...",
  "contract_hash": "sha256:...",
  "intent": "submit the current form",
  "target": "button.submit",
  "backend": "dom",
  "preconditions": [
    "button.visible",
    "button.enabled",
    "form.valid"
  ],
  "expected_effects": [
    "url_changes_or_success_message",
    "no_error_banner"
  ],
  "risk": "medium",
  "required_capabilities": ["settings.write"],
  "idempotency_key": "task_1:submit_form:v1",
  "compensation": "restore_previous_setting",
  "timeout_ms": 5000,
  "fallbacks": ["visual_click", "keyboard_enter"]
}
```

The runtime executes contracts, not vague clicks.

### 2.6 Safety and Capability Layer

The safety layer checks three levels:

| Level | Examples |
| --- | --- |
| Task policy | `read_only`, `no_purchase`, `no_delete`, allowed domains |
| Capability scope | `settings.read`, `settings.write.reversible`, `report.export` |
| Action risk | delete, payment, external message, export, irreversible submit |

Unknown effectful actions should be denied or require clarification by default.
Approval tokens must be single-use and bound to run id, contract hash,
environment revision, capability, approver, and expiration.

Parent agents should call task-level APIs. Low-level click/type tools are
internal or debug-only because they bypass the harness.

### 2.7 Execution Layer

Backends:

- Playwright DOM actions
- keyboard / mouse actions
- visual click by mark id
- accessibility actions
- API / device actions
- page-internal JavaScript adapter when available

The executor should revalidate target-critical facts as close to action time as
possible to reduce TOCTOU risk between preflight and the physical click/type.

Gesture execution follows one dual-target Core binding. Core preflight checks
both endpoint leases, fingerprints, observation epoch, distinct identity,
shared route, policy, and current blocking overlays. Backend adapters only
encode the validated binding: BrowserGym uses marked or viewport drag actions,
Playwright uses `locator.drag_to()`, and Visual/Desktop uses a bounded pointer
move/down/move/up sequence. A backend never repairs or substitutes one endpoint
inside an existing contract.

#### 2.7.1 Optional System 1 / System 2 Execution Policy

System 1 and System 2 describe a fast/deliberative policy split above the same
contract runtime. They are not separate executors and may not bypass policy,
preflight, post-action observation, verification, or trace.

System 1 may reuse an accepted grounding or harness skill only when:

- task/skill identity and surface semantics match;
- snapshot lease and target fingerprint are current;
- multi-source arbitration has no material unresolved conflict;
- confidence is calibrated above the configured threshold;
- risk, capability, and approval policy allow the action;
- expected effects have an available verifier.

A System 1 cache hit still creates a fresh Action Contract and runs preflight.
Execution or verification failure invalidates the cached grounding.

System 2 is triggered by a new or complex task, missing exact skill, unresolved
source conflict, low confidence, stale state, failed precondition, unavailable
backend, failed/inconclusive verification, repeated recovery, or high-risk
decision. It may invoke active perception, the generalist/task planner, bounded
recovery, or human clarification.

Migration status:

| C009 mechanism | Affordance Runtime status |
| --- | --- |
| DOM/visual/WoT executors | migrated behind Action Contract |
| backend confidence and cost routing | migrated |
| bounded recovery and escalation reasons | partially migrated and extended; explicit recovery execution remains a governance gate |
| LM/action and shallow task planning | implemented through PlannerPort and TaskPlannerPort |
| System1ReflexLibrary grounding cache | grounding cache not migrated; accepted TaskSkill System 1 path implemented |
| StateAssertion/FusedAssertion conflict gate | implemented as SourceAssertion arbitration |
| active perception for cross-source conflict | implemented with bounded targeted perception |
| explicit System 1 latency/cache metrics | TaskSkill activation/fallthrough/model-call/latency replay metrics implemented; grounding-cache metrics not migrated |
| regression-gated skills and policies | implemented with stricter acceptance than the old proposal-only path |

The first implementation should add source arbitration before enabling a reflex
cache. Otherwise a fast path could amplify stale or conflicting state.

### 2.8 Verification Layer

Execution receipt and verification evidence are separate.

```text
ExecutionReceipt
  executor says a technical action was attempted or completed
  examples: click dispatched, download event fired

VerificationEvidence
  independent evidence for the expected effect
  examples: DOM state, fixture API value, file hash, audit log

VerificationReport
  judgment over expected effects using evidence strength and fallback policy
```

Verifier result states:

```text
PASSED
FAILED
INCONCLUSIVE
ERROR
NOT_APPLICABLE
```

Verifier ladder, strongest to weakest:

1. API, DB, file, network, download, or audit receipt.
2. DOM or accessibility state.
3. Screenshot / visual mark evidence.
4. Model judge.
5. Human review.

Benchmark grading should prefer independent fixture oracles and should not use
the acting model as the sole authority for success.

### 2.9 Recovery Layer

Handles failures through a bounded decision matrix:

| Failure Class | First Response | Max Attempts | Escalation | Side-Effect Rule |
| --- | --- | ---: | --- | --- |
| stale observation | re-observe | 2 | replan | no execution |
| locator missing | rebuild affordances | 2 | backend fallback | no duplicate side effect |
| blocking modal | classify modal | 1 | ask or abort | modal action must satisfy policy |
| timeout | inspect current state | 2 | retry or replan | require idempotency |
| verifier inconclusive | gather stronger evidence | 2 | ask parent or fail | do not repeat effectful action |
| capability denied | request approval | 1 | abort | no automatic downgrade |
| partial side effect | verify current state | 1 | compensate or abort | no blind retry |

### 2.10 Trace and Evaluation Layer

Records:

- task envelope
- observations and artifact refs
- affordance snapshots
- planner decisions
- action contracts
- policy and approval decisions
- execution receipts
- post-action observations
- verification reports
- recovery attempts
- final metrics

A JSONL event log can be the canonical storage format, with DAG parent links
used to derive causal views.

## 3. Repository Layout

```text
src/affordance_runtime/
  contracts.py
  state_kernel.py
  runtime.py
  coordinator.py
  artifacts.py
  browser_session.py
  executors.py
  routing.py
  recovery.py
  safety.py
  verification.py
  trace.py
  evolution.py
  evolution_replay.py
  fixtures.py
  planners.py
  cli.py
  adapters/
    dom.py
    som.py
    wot.py
  benchmarks/
    spec.py
    suites.py
    metrics.py
    runner.py
    local.py
  integrations/
    task_api.py
    local.py
tests/
docs/
```

Possible production expansion, still deferred:

```text
src/affordance_runtime/
  observers/playwright.py
  executors/playwright.py
  recovery/policies.py
  integrations/mcp_server.py
  integrations/rest.py
  workers/browser_worker.py
  persistence/checkpoints.py
```
