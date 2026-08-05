# Affordance Runtime Project Plan

> **Lifecycle:** CURRENT PRODUCT ROADMAP
> **Authority:** subordinate to the [authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md) and [evolution plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
> **Status source:** [Implementation Status](implementation-status.md)
> **Active queue:** [Current Implementation Plan](current-implementation-plan.md)

## 1. Product position

Affordance Runtime is a planner-neutral GUI execution Runtime. A parent agent,
reference planner, or benchmark submits a bounded task; the Runtime owns current
observation, legal action construction, concrete action contracts, safety gates,
execution, typed evaluation, bounded recovery, authoritative commits, and trace.

BrowserGym and other suites are external evaluators, not the product boundary.

## 2. Target contract model

```text
SourceEnvelope
→ MinimalIntentProposal
→ optional SemanticAudit
→ immutable TaskSpec
→ canonical current observation
→ replaceable TaskPlan<StepSpec>
→ Runtime-owned full ActionChoiceCatalog
→ concrete ActionContract
→ Task Authority / Capability / Approval / Preflight
→ Execute
→ post-action observation
→ inline LoopEvaluator
→ RuntimeCommitter
```

The target has four durable authority objects:

| Object | Owns | Does not own |
|---|---|---|
| `TaskSpec` | user authorization, constraints, forbidden effects, success | steps or current UI facts |
| `TaskPlan<StepSpec>` | replaceable execution milestones under current observation | task meaning or concrete actions |
| `ActionContract` | one grounded, gated, expiring action transaction | self-authorization or task completion |
| `TaskProgress` | verified progress, facts/bindings, recent outcomes, durable evidence refs | duplicate plan or observation graphs |

### Cross-surface sources and backends

DOM, AX, Visual, SVG, WoT, API, and Device are composable sources/backends under
the same task and transaction authorities. Planner selects a backend-neutral
semantic action; the Runtime retains every current binding/conflict and
ActionContractBuilder selects the concrete backend/binding. No surface receives
its own TaskSpec, plan, completion, or commit chain.

## 3. Delivery phases

The phase order is normative; status is maintained only in
`implementation-status.md`.

### P0 — Correctness boundaries

| Slice | Outcome |
|---|---|
| `P0-A` | Task completion comes only from full `TaskSpec.success` evaluation; receipt/latest-report/plan-exhausted fallbacks are removed. |
| `P0-B` | `PerceptionCapture → CanonicalObservationBuilder` establishes the only current semantic observation authority behind immutable epoch refs/indexes for DOM/AX/Visual/SVG/WoT/API/Device. |
| `P0-C` | Runtime builds the surface-neutral, logically complete `ActionChoiceCatalog` before any bounded model-facing ChoicePage; eager/lazy/indexed realizations preserve membership/order/digest. |
| `P0-D` | Regression redlines cover omitted target/state fields, conflicts, multi-binding, truncated pages, stale approval/contract identity, and physical-layout invariance. |
| `P0-E` | Default intake uses lightweight `SourceEnvelope`; risk-proportionate typed MaterialBinding provides per-effect field coverage; exact anchors are reserved for indirect provenance; clause/claim/obligation coverage leaves the default path and SemanticAudit remains optional. |

### P1 — Direct plan and loop-native evaluation

- accepted TaskPlan stores `StepSpec` directly;
- obligation presence cannot decide plan shape;
- `LoopEvaluator` returns typed effect, step, task, and observation-continuation results;
- only RuntimeCommitter mutates authoritative state.

### P2 — Typed criteria and bounded evidence

- closed semantic AST plus restricted open semantic criterion;
- mandatory mechanical operator baseline; registered unsupported operators fail typed instead of falling back to prose/model approval;
- minimum `CriterionPolicy`: satisfaction, validity, assurance;
- current observation, bounded recent ActionOutcome, and small DurableEvidenceStore;
- mechanical verifiers become internal evidence providers.

### P3 — Stable TaskSpec v2

- TaskSpecAuthority is the only admission and revision owner;
- TaskSpec contains authorization and terminal semantics, not execution graphs;
- risk-proportionate MaterialBindings are frozen into `source_binding_digest`; direct explicit values do not require spans, while indirect unstructured values require exact excerpts;
- SemanticAudit remains pass/veto/clarify-only.

### P4 — Observation-grounded rolling planning

- separate task-planning and active-step choice horizons;
- reuse/direct planning fast paths and TaskPlanner calls only on typed triggers;
- deterministic narrowing first, then staged paging/refinement over a Runtime-owned logical full Catalog;
- Planner selects only displayed IDs and never invents concrete bindings.

### P5 — Bounded stores and legacy deletion

- Fact/Binding, observation, recent-outcome, and durable-evidence namespaces keep distinct lifetimes but may share lightweight in-process physical stores;
- compatibility projectors and alternate completion/progress owners are deleted or isolated;
- Trace, benchmark, and evolution remain offline consumers.

## 4. Safety and governance requirements

Every production slice must preserve:

- allowed-effect traceability to TaskSpec;
- capability ceiling distinct from effective grant;
- one-shot approval bound to the exact ActionContract and state revision;
- stale preflight rejection without silent relocation;
- no automatic retry of uncertain external effects;
- typed failure ownership and bounded recovery;
- one state/trace writer;
- benchmark neutrality and immutable evidence identity.
- risk-derived profiles may enable optional machinery but never bypass required gates, output closure, or the single writer;
- logical authority names do not require independent services, processes, databases, queues, or model calls without measured need.

## 5. Explicit non-goals

- no mandatory clause/claim/obligation graph for ordinary intake;
- no workflow DSL or universal world model in TaskSpec;
- no default independent verifier platform or unbounded EvidenceIndex;
- no model-owned selector, coordinate, capability, approval, or completion;
- no benchmark task/family special cases in production semantics;
- no parallel authorities during migration.

## 6. Definition of program completion

The target is complete only when:

1. all P0–P5 exit gates have code and reproducible evidence;
2. current production imports and call paths use the canonical owners;
3. legacy owners are deleted or explicit isolated adapters with removal gates;
4. focused, breadth, safety, and cross-surface evaluations pass at the same immutable revision;
5. documentation, status, and the machine-readable manifest agree.

Historical milestone detail is preserved in
[the 2026-08-05 status snapshots](archive/superseded-2026-08-05/status-snapshots/).
