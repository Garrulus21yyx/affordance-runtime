# Design Freeze and Implementation Gates

This document converts the project plan from an architecture proposal into an
implementation contract. Before expanding code, the runtime should be judged by
frozen semantics, testable hypotheses, scenario specs, and milestone gates.

The [Current Implementation Plan](current-implementation-plan.md) is the
authoritative implementation profile. The
[Complete Architecture Blueprint](complete-architecture-blueprint.md) preserves
future production options but does not add current design-freeze requirements.

## 1. Project Identity

Primary product:

```text
planner-neutral GUI execution runtime
```

Reference application:

```text
a minimal planner used only for local demos and benchmarks
```

External usage:

```text
parent agents call bounded task-level APIs and may replace the reference planner
through PlannerPort
```

The runtime is not trying to become a full general agent. It owns observation,
affordance modeling, action contracts, safety gates, execution, verification,
trace, recovery boundaries, and evaluation evidence.

## 2. Current Status Matrix

| Area | Status | Notes |
| --- | --- | --- |
| Domain models | Implemented skeleton | Affordances, contracts, receipts, risks, traces, metrics |
| DOM / SoM / WoT adapters | Implemented skeleton | Migrated from the earlier modular action system |
| Single-contract execution | Implemented skeleton | Useful as a debug API, not yet a task runtime |
| State Kernel | Partial | Data structure exists; task-level lifecycle must bind it across steps |
| Lease / preflight | Partial | Revision equality exists; TTL, snapshot identity, and target-level validity need implementation |
| Capability gate | Partial | Capability/risk fields exist; task constraints and approval tokens need stronger semantics |
| Post-action verification | Planned | Must compare pre-observation, receipt, and post-observation |
| Playwright observer/executor | Planned | First gold path backend |
| Recovery policy | Planned | Must be bounded by explicit budgets |
| Trace persistence/replay | Planned | Current trace idea must become JSONL/artifact-backed evidence |
| Benchmark runner | Planned | Needs baselines, ablations, oracles, and deterministic fixtures |
| MCP/REST | Deferred | CLI first, MCP second; REST is optional until the task API is stable |
| Harness evolution | Deferred | Begins only after trace schema and benchmark suite are stable |
| WoT smart-room | Deferred proof | Non-web adapter proof, not the main project story |
| OSWorld/mobile/desktop-native | Future | After the web harness is stable |

## 3. Testable Hypotheses

### H1: State Binding

Revision-bound action contracts reduce stale-action execution under injected
environment drift.

- Independent variable: lease/preflight enabled vs disabled.
- Perturbation: target replaced, disabled, hidden, covered by modal, or shifted.
- Primary metric: stale detection recall.
- Side metrics: false stale block rate, latency overhead.
- Baseline: direct Playwright locator execution.

### H2: Structural Verification

Independent structural verifiers reduce false-success judgments compared with
execution acknowledgment or model-only judgment.

- Compare executor receipt, DOM/API/file verifier, visual verifier, and model
  judge.
- A click receipt is not enough to prove a business effect.
- Benchmark grading must rely on independent oracles when available.

### H3: Capability Boundaries

Capability and approval policies prevent unauthorized side effects without
making permitted tasks unusable.

- Track unsafe side-effect count.
- Track allowed task completion rate.
- Track unnecessary approval rate.
- Page text is tainted and cannot grant capability.

### H4: Bounded Recovery

Recovery improves completion under defined failure classes without unbounded
retry loops or duplicate side effects.

- Track recovery success rate.
- Track recovery-induced damage.
- Track budget exhaustion.
- Effectful actions must not be blindly repeated.

### H5: Unified Affordance Envelope

A common affordance envelope permits backend substitution without discarding
surface-specific information.

- Common fields must support shared policy and trace.
- Surface payloads must preserve DOM, visual, accessibility, API, and WoT
  details.
- If the envelope degenerates into opaque dictionaries, split the design.

## 4. System Invariants

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

## 5. Core Semantics

| Concept | Creator | Lifecycle | Trust Boundary |
| --- | --- | --- | --- |
| Observation | Observer | raw environment facts captured at a time | untrusted if derived from page content |
| Affordance Snapshot | Affordance builder | immutable action-space view derived from observations | trusted as runtime output, but based on tainted inputs |
| Environment Revision | Observer / revision policy | semantic state identity used for validity checks | policy-defined, not a raw hash only |
| Affordance Lease | Lease policy | validity window for a snapshot or target | expires by time, revision, or target change |
| Action Contract | Planner / contract builder | immutable proposed action with preconditions and expected effects | cannot self-authorize capability |
| Execution Receipt | Executor | technical record of attempted execution | proves transport, not business success |
| Verification Evidence | Verifier | independent evidence for expected effects | strength depends on source |
| Verification Report | Verifier ladder | PASSED, FAILED, INCONCLUSIVE, ERROR, NOT_APPLICABLE | strongest available evidence should dominate |
| Trace Event | Runtime | append-only record with parent links and artifact refs | must be privacy filtered |

Observation is not a snapshot. A snapshot is a runtime-produced action-space
view. A lease is not a hash. A receipt is not a verifier.

## 6. Revision Model

Do not begin with one global hash that mixes URL, DOM, screenshot, and loading
state. The current implementation uses a compact validity boundary:

| Value | Meaning | Invalidates or Identifies |
| --- | --- | --- |
| Page revision | navigation, document replacement, blocking modal, and action-space-relevant page state | page-bound contracts |
| Target fingerprint | action target identity, enabled state, bbox, role/name, and visibility | target-bound contracts |
| Artifact hash | DOM, screenshot, accessibility, or file content identity | evidence links and replay, not runtime validity |

A contract should bind `snapshot_id`, `page_revision`,
`target_fingerprint`, validity policy, `observed_at`, and `expires_at`. The
complete blueprint may split page validity into more dimensions only after a
benchmark demonstrates the need.

Changes that usually invalidate a contract:

- blocking modal appears
- target disappears, disables, or changes role/name
- target bbox changes for a visual action
- navigation replaces the document
- form state invalidates the action preconditions

Changes that usually should not invalidate a contract by themselves:

- timer text changes
- irrelevant ad refresh
- unrelated DOM subtree mutation
- animation that does not affect target validity

## 7. Recovery Decision Matrix

| Failure Class | First Response | Max Attempts | Escalation | Side-Effect Rule |
| --- | --- | ---: | --- | --- |
| stale observation | re-observe | 2 | replan | no execution |
| locator missing | rebuild affordances | 2 | backend fallback | no duplicate side effect |
| blocking modal | classify modal | 1 | ask or abort | modal action must satisfy policy |
| timeout | inspect current state | 2 | retry or replan | require idempotency |
| verifier inconclusive | gather stronger evidence | 2 | ask parent or fail | do not repeat effectful action |
| capability denied | request approval | 1 | abort | no automatic downgrade |
| partial side effect | verify current state | 1 | compensate or abort | no blind retry |

Global runtime budgets:

```text
max primitive actions
max observations
max replans
max backend fallbacks
max recovery depth
max wall-clock time
max model cost
max effectful actions
```

## 8. MVP Boundaries

| Release | Purpose | Includes | Explicitly Deferred |
| --- | --- | --- | --- |
| v0.1 Core | one read-only Web gold path | DOM observer, Playwright executor, contracts, preflight, post-action verifier, trace writer, CLI | SoM, MCP, event bus, WoT, evolution |
| v0.2 Reliability and surface proof | prove differentiators and common contract reuse | stale injection, modal recovery, selector drift, approval gate, benchmark report, bounded SoM/WoT proofs | REST, many agent adapters, desktop/mobile |
| v0.3 Assisted Evolution | controlled learning loop | failure classification, declarative proposal, quarantine registry, regression replay | fully automatic production mutation |
| v0.4 Optional Integration | parent-agent handoff | task-level MCP, result/evidence/trace fetch, optional LLM/LangGraph adapter | low-level public click/type tools |

## 9. Scope-Cut Rules

| Rule | Trigger | Decision |
| --- | --- | --- |
| CUT-01 | Revision-bound contracts do not reduce stale execution versus target revalidation | simplify lease model |
| CUT-02 | Continuous watcher does not outperform post-action observation for selected tasks | defer event bus/watcher |
| CUT-03 | Visual fallback adds latency without improving selected benchmark success | move SoM out of MVP |
| CUT-04 | Unified affordance model hides surface-specific data in opaque dicts | keep common envelope, split typed payloads |
| CUT-05 | Evolution proposals cannot be evaluated reproducibly | keep manual failure analysis plus regression fixture generation |
| CUT-06 | MCP delays gold path | ship CLI first and expose MCP after task schema stabilizes |
| CUT-07 | A production feature has no measured current bottleneck | keep it in the complete blueprint |

## 10. Milestone Template

Each milestone must define:

```text
Objective
Entry Criteria
Deliverables
Exit Criteria
Evidence
Explicitly Deferred
Decision Gate
```

A feature is not complete because its class exists. It is complete when the
exit criteria are satisfied and the evidence is reproducible.
