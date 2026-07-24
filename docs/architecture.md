# Affordance Runtime Architecture

This document describes the current implementation architecture. Production
scaling options are preserved separately in the
[Complete Architecture Blueprint](complete-architecture-blueprint.md). The
[Runtime-First Architecture Boundary](runtime-first-boundary.md) is normative:
BrowserGym and other benchmarks consume this architecture through adapters;
they do not own task semantics, perception orchestration, routing, contracts,
verification, recovery, or learning. Benchmark-specific task logic is
prohibited in the generic path.

The operational design for evidence-gap-driven observation and phase-spanning
recovery is defined in
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md).
It is part of the current M8.6 skeleton, not a future distributed-service
option.

## 1. High-Level System

~~~text
User Request / Parent TaskSpec
  -> IntentCompiler / TaskSpecValidator
  -> TaskPlanRouter
       -> one flat subgoal
       -> accepted TaskSkill
       -> validated shallow TaskPlan
  -> RunCoordinator (single authoritative state writer)

For each active subgoal:

  PerceptionRequirements
    -> PerceptionSession base coherent epoch
    -> SourceAssertions and unified candidates
    -> rule-first arbitration
         -> accepted snapshot
         or ActivePerceptionController
              -> ProbePlan / ProbeCommand
              -> new coherent epoch
              -> re-arbitrate
         or safe inconclusive FailureEnvelope

  accepted snapshot
    -> GeneralistStepPlanner
    -> semantic PlannerProposal
    -> PlannerProposalValidator
    -> semantic target resolution and route selection
    -> ContractBuilder
    -> ActionContract
    -> capability / approval / preflight
    -> execute
    -> post-action observation
    -> criteria-bound verification
         -> continue / complete

Any phase may emit:

  FailureEnvelope
    -> RecoveryCoordinator
    -> RecoveryPlanValidator
    -> one typed RecoveryCommand
    -> owning Runtime port
    -> RecoveryReceipt + non-empty RecoveryDelta
    -> re-enter changed phase
         or wait for approval/user
         or abort/fail

All paths
  -> canonical Trace Events and Artifacts
  -> Evaluator
  -> offline quarantined proposal
  -> regression replay
  -> accept / reject / rollback
~~~


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
| INV-11 | RunCoordinator is the only authoritative RunState writer. |
| INV-12 | Observation probes are read-only; any environment-changing inspection uses an ActionContract. |
| INV-13 | Active perception produces a new coherent epoch and preserves source provenance. |
| INV-14 | Another attempt requires a non-empty RecoveryDelta over evidence, assumption, plan, route, verifier, context, authority, or user input. |
| INV-15 | An uncertain effect is inspected before retry, reroute, or compensation. |
| INV-16 | Failures from every Runtime phase use one FailureEnvelope and bounded RecoveryCoordinator protocol. |
| INV-17 | Benchmark identity and external reward never enter generic perception or recovery decisions. |

## 1.2 Task State Machine

The top-level state machine stays small:

~~~text
CREATED
  -> OBSERVING
  -> PLANNING
  -> PREFLIGHT
  -> ACTING
  -> VERIFYING
  -> PLANNING or DONE
~~~

Affordance building, arbitration, active perception, proposal validation, and
binding remain traced activities inside these phases. They do not require new
public states.

Any phase may emit FailureEnvelope and enter RECOVERING:

~~~text
INTAKE / OBSERVING / PLANNING / PREFLIGHT / ACTING / VERIFYING
  -> RECOVERING
       -> OBSERVING
       -> PLANNING
       -> PREFLIGHT
       -> VERIFYING
       -> WAITING_APPROVAL
       -> WAITING_USER
       -> ABORTED / FAILED
~~~

The RecoveryReceipt declares the re-entry phase. Coordinator accepts it only
when RecoveryDelta proves a meaningful change. Stale or no-op recovery is
rejected.

run_contract may remain an internal/debug API, but the public runtime is
task-level and holds one RunContext across steps.


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
coherent capture_targeted observation port are implemented. Source-arbitration
and bounded ActivePerceptionRequest decisions can be traced at the foundation
level. The complete EvidenceGap-to-ProbePlan controller, shared call-site
integration, live conflict families, and calibration remain M8.6 work.

#### 2.1.2 Active Perception Control

Active perception converts a decision-relevant evidence gap into one bounded,
read-only probe plan. It is used both in normal observation and as a recovery
strategy.

~~~text
PerceptionRequirements
  -> base coherent epoch
  -> SourceAssertions
  -> rule-first arbitration
  -> EvidenceGap
  -> ActivePerceptionController
  -> ProbePlan / ProbeCommand
  -> PerceptionSession.capture_targeted
  -> new coherent epoch
  -> re-arbitrate
  -> accepted state or safe inconclusive
~~~

The controller selects probes only after hard gates for relevance, source
authority, availability, coherence, risk, and budget. It prefers the cheapest
probe that can close a blocking gap and uses an independent source for material
conflict. It does not compare numeric confidence across sources without
calibration.

A probe transport receipt cannot resolve a gap; a new arbitration decision is
required. Any inspection that changes environment state uses a normal
ActionContract rather than hiding inside the observer.

The SourceAssertion/arbiter foundation is now joined by typed EvidenceGap,
probe capability, ProbePlan/Receipt, and PerceptionResolution contracts plus a
single ActivePerceptionController. Normal observation, preflight,
verification-evidence repair, and lower-half recovery inspection use the same
bounded read-only protocol and new coherent epochs. Accepted perception-policy
learning remains later work. Phase-general recovery is complete under G3 and
requests this controller through typed commands without acquiring observation
authority. See
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md).

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
| bounded recovery and escalation reasons | migrated through the phase-general typed RecoveryCoordinator protocol; execution remains with owning Runtime ports |
| LM/action and shallow task planning | implemented through PlannerPort and TaskPlannerPort |
| System1ReflexLibrary grounding cache | grounding cache not migrated; accepted TaskSkill System 1 path implemented |
| StateAssertion/FusedAssertion conflict gate | implemented as SourceAssertion arbitration |
| active perception for cross-source conflict | typed controller and bounded targeted-capture integration complete; G3 recovery requests it through typed evidence-gap commands |
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

### 2.9 Online Recovery Layer

Recovery is a phase-spanning control protocol, not a contract retry helper. Any
Runtime phase may emit a FailureEnvelope, including phases where proposal,
snapshot, or ActionContract does not yet exist.

~~~text
FailureEnvelope
  -> RecoveryCoordinator
  -> semantic cascade and effect-status assessment
  -> RecoveryPlanValidator
  -> one typed RecoveryCommand
  -> owning Runtime port
  -> RecoveryReceipt
  -> non-empty RecoveryDelta
  -> Coordinator re-entry
       or wait / ask / abort
~~~

Recovery follows this safety-first order:

1. determine whether an external effect may have occurred;
2. stop on authority violation or duplicate-effect risk;
3. inspect post-state when effect status is uncertain;
4. acquire missing facts through reobserve or active perception;
5. repair intent, context, task plan, or step plan;
6. reground or reroute using a fresh current candidate;
7. retry only after confirmed non-dispatch or missing effect and idempotency;
8. compensate only through a separately authorized and verified contract;
9. request approval or user information;
10. abort when no safe changed strategy exists.

| Failure phase | Primary recovery |
| --- | --- |
| intake | clarification or new TaskSpec revision |
| observation / fusion | reobserve, active perception, safe inconclusive |
| task / step planning | compact context, schema repair, provider policy, replan |
| proposal validation | bounded repair or replan |
| grounding / binding | new-epoch reground or reroute |
| preflight | reobserve and build a new contract |
| execution not dispatched | fresh reroute or idempotent retry |
| execution uncertain | inspect post-state before any repeat |
| verification | stronger evidence, replan, or explicit compensation |
| skill activation | invalidate and fall through to System 2 |

RecoveryCoordinator chooses but never executes. RunCoordinator applies one
validated command through PerceptionSession, PlannerContextBuilder, ModelPort,
IntentCompiler, TaskPlanLifecycle, GeneralistStepPlanner, router,
ContractBuilder, contract execution, verifier, or parent/user boundary.

Another attempt is accepted only when RecoveryDelta changes evidence,
assumption, plan, candidate, route, verifier, provider/context, skill use,
authority, or user input. Exact signatures remain for debugging; semantic
cascade keys exclude volatile selector, coordinate, mark, target, and backend
values.

The prior RecoveryHandler, FailureSignature, RecoveryIncident,
RecoveryCascadeDetector, BoundedRecoveryPolicy, inspect-before-repeat, and
replay-gated artifacts remain the lower-half foundation. G3 now adds the
phase-general FailureEnvelope, RecoveryCommand/Delta/Receipt, representative
pre-contract strategies, changed-strategy validation, and explicit accepted
recovery-profile loading. Capability-specific transports remain available only
when their owning Runtime port is configured. See
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md).

The initial recovery matrix remains:

| Failure Class | First Response | Max Attempts | Escalation | Side-Effect Rule |
| --- | --- | ---: | --- | --- |
| stale observation | re-observe | 2 | replan | no execution |
| missing/ambiguous evidence | active perception | bounded by probe budget | ask or safe inconclusive | read-only probes only |
| planner/context failure | compact, repair, or replan | bounded by planning budget | configured provider or ask | no authority change |
| locator/grounding missing | rebuild candidates | 2 | alternate source/route | fresh contract |
| blocking modal | classify modal | 1 | ask or abort | modal action passes policy |
| timeout | inspect current state | 2 | retry or replan | require absent effect and idempotency |
| verifier inconclusive | gather stronger evidence | 2 | ask or fail | do not repeat effectful action |
| capability denied | request approval | 1 | abort | no backend bypass |
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
  active_perception.py        # bounded read-only probe selection
  failure_envelope.py         # phase-general failure contract
  recovery_coordinator.py     # pure changed-strategy decision
  recovery_commands.py        # typed command/receipt/delta
  evaluation_audit.py         # complete-run identity and case ledger
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

The M8.6 collaborators above are implemented internal contracts, not services.
Perception and recovery reuse the current PerceptionSession, source arbitration,
planners, router, verifiers, RecoveryHandler, and Coordinator-owned state. They
may not create a second mutable world model, browser owner, or execution
authority. EvaluationAudit is outside the action loop: it reconciles immutable
collection evidence and cannot influence a PlannerProposal or ActionContract.

Complete-run consumers retain environment-specific scheduling and score
translation. The generic audit layer knows only immutable identity, scheduled
case ids, collection/outcome facts, validity, resume lineage, and batch-stop
category. Formal repair clusters are consumer reports built only after the
typed ledger is complete and comparable.

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
