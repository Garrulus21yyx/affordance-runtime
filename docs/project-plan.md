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

The roadmap follows **complete vertical loop, limited horizontal breadth**. The
MVP is one process, one run, one coordinator, one browser session, and one active
ActionContract with serialized state mutation, approval consumption, and
effectful execution. It is a GUI-agent research Runtime, not a production-grade,
multi-tenant transactional authorization kernel.

BrowserGym and other suites are external evaluators, not the product boundary.

## 2. Target contract model

```text
SourceEnvelope
→ MinimalIntentProposal
→ optional SemanticAudit
→ immutable TaskSpec
→ canonical current observation
→ replaceable TaskPlan<StepSpec>
→ TaskPlan semantic admission
→ Runtime-owned full ActionChoiceCatalog
→ validated ActionSelection
→ fresh preflight O1
→ materialize and freeze the complete executable ActionContract H
→ Task/Policy/Capability admission over H
→ exact Approval of H when required
→ final snapshot/page/target/expiry preflight
→ serial Execute of H with approved_hash == executed_hash
→ typed transport receipt
→ independent external-effect settlement
→ post-action observation
→ inline LoopEvaluator
→ actual typed OutputMaterialization when required
→ TaskCompletionEvaluator
→ RuntimeCommitter
```

The target has four stable authority roles/types (individual plan and contract
instances remain replaceable/expiring and are not thereby crash-durable):

| Object | Owns | Does not own |
|---|---|---|
| `TaskSpec` | user authorization, constraints, forbidden effects, success | steps or current UI facts |
| `TaskPlan<StepSpec>` | replaceable execution milestones under current observation | task meaning or concrete actions |
| `ActionContract` | one grounded, gated, expiring action transaction | self-authorization or task completion |
| `TaskProgress` | verified progress, facts/bindings, recent outcomes, durable evidence refs | duplicate plan or observation graphs |

### Cross-surface sources and backends

DOM, AX, Visual, SVG, WoT, API, and Device are composable sources/backends under
the same task and transaction authorities. Planner selects a backend-neutral
semantic action; the Runtime retains every current binding/conflict and the route owner inside
`ActionTransactionMaterializer` selects the concrete backend/binding. No surface receives
its own TaskSpec, plan, completion, or commit chain.

## 3. Delivery phases

The phase list below is a synchronized product-roadmap summary, not the owner of
migration order or exit gates. Any ordering/gate conflict is resolved by §6 of
the authoritative evolution plan; current implementation truth is maintained
only in `implementation-status.md`.

### P0 — Correctness boundaries

| Slice | Outcome |
|---|---|
| `P0-A` | Task completion comes only from full `TaskSpec.success` evaluation and actual typed `OutputMaterialization`; receipt/latest-report/plan-exhausted/declaration-metadata fallbacks are removed. Recursive evaluation and actual materialization are closed through P4-C1. |
| `P0-B` | `PerceptionCapture → CanonicalObservationBuilder` establishes the only current semantic observation authority behind immutable epoch refs/indexes for DOM/AX/Visual/SVG/WoT/API/Device. P4 closes snapshot/page/target freshness on the admitted GUI path; truthful per-adapter coverage remains a target rule with broader adapter/context breadth demand-gated. |
| `P0-C` | Runtime builds the surface-neutral, logically complete `ActionChoiceCatalog` before any bounded model-facing ChoicePage; production is currently eager, and any future demand-gated lazy/indexed realization must preserve membership/order/digest. |
| `P0-E` | Default intake uses lightweight `SourceEnvelope`; risk-proportionate typed MaterialBinding provides per-effect field coverage; exact anchors are reserved for indirect provenance; clause/claim/obligation coverage leaves the default path and SemanticAudit remains optional. |
| `P0-D` | After P0-A/B/C/E semantics are fixed, regression redlines freeze omitted target/state fields, conflicts, multi-binding, truncated pages, stale approval/contract identity, raw-text read sets, output closure, and physical-layout invariance. |

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
- TaskPlanAuthority performs typed semantic subsumption between every proposed StepSpec and its referenced requirements; ID membership is not sufficient and plan admission is never execution authority.

### P4-minimum — Mainline closure

Only five semantic invariants block P5:

1. Executor accepts only a finalized immutable ActionContract.
2. Policy/approval evaluates that exact contract; approved hash equals executed hash.
3. Stale snapshot/page/target rejection makes zero Executor calls.
4. Completion requires verifier evidence; receipt alone cannot produce DONE.
5. Effectful uncertain execution is never blindly retried.

Focused checks, full pytest/static checks, and the core benchmark are closure
evidence for those five invariants and the default-route cutover; the benchmark
is not a sixth invariant. Current status is **P4 CLOSED (MVP scope)**; P5
admission is unblocked, but P5 has not started.

This closure does not claim exhaustive TaskPlan destination/function/usage
policy, universal adapter coverage, tenant proof, permit isolation, or release
attestation. Those concerns remain supporting or future-hardening work unless a
new scenario admits them.

C0 owns zero-call containment, C1 verifier-backed completion, C3 the exact
final-contract hash, C4 the serial no-blind-retry rule, and C5 default-route/core
regression cutover. C2's tenant/profile/context envelope and the stronger C4/C5
permit, fencing, collateral, manifest, and multi-suite work are future hardening.

### P5 — Bounded stores, interruption recovery and legacy deletion

P5 may start once the five P4-minimum invariants have focused evidence and the
core benchmark demonstrates them on the default route. That benchmark is
evidence, not another product requirement. P5 does not wait for multi-tenant
proof, revocation linearizability, global permit
registries, multi-dimensional fencing, collateral attestation, P4-R0, or
AgentDojo/WASP/OSWorld release gates unless P5 explicitly adds the matching claim.

- Fact/Binding, observation, recent-outcome, and durable-evidence namespaces keep distinct lifetimes but may share lightweight in-process physical stores;
- a typed RunCheckpoint records only refs/digests—including budget/control/trace/effect/lifecycle refs—plus the exact `last_committed_observation_ref`; it never serializes live browser/backend handles or becomes a second state authority;
- the checkpoint persistence mechanism is selected only after the fault model is admitted; this roadmap does not freeze file, database or service technology;
- `runtime_resume.py` performs checkpoint validation and typed routing only; existing owners create the fresh session, reconcile effects, plan, authorize, approve, execute and complete;
- restart opens a fresh execution session and canonical observation, invalidates stale Catalog/contract/approval, and reconciles `MAY_HAVE_OCCURRED` external effects before any new live execution; it never auto-replays the old transaction;
- resumable interruption and terminal cancellation are distinct lifecycle requests, acknowledged only at safe stage/pre-dispatch boundaries; either request during dispatch enters uncertain-effect recovery before it can settle;
- compatibility projectors and alternate completion/progress owners are deleted or isolated;
- Trace, benchmark, and evolution remain offline consumers.

## 4. Safety and governance requirements

Every production slice must preserve:

- allowed-effect traceability to TaskSpec;
- typed TaskPlan semantic admission without granting execution authority;
- capability ceiling distinct from effective grant;
- one-shot approval bound to the exact ActionContract and state revision;
- adapter-owned SourceCoverage, with missing/failed/not-acquired distinct from complete absence;
- stale preflight rejection without silent relocation or partial old-contract patching;
- materialize-first policy/approval over one immutable contract, with stale rejection before Executor and exact approved/executed hash equality;
- no automatic retry of uncertain external effects;
- transport outcome separate from external-effect settlement;
- actual typed/source-bound output materialization rather than OutputSpec metadata;
- typed failure ownership and bounded recovery;
- one state/trace writer;
- benchmark neutrality; immutable evidence identity is required for release/claim publication, not ordinary P4/P5 scheduling;
- risk-derived profiles may enable optional machinery but never bypass required gates, output closure, or the single writer;
- logical authority names do not require independent services, processes, databases, queues, or model calls without measured need.

## 5. Explicit non-goals

- no mandatory clause/claim/obligation graph for ordinary intake;
- no workflow DSL or universal world model in TaskSpec;
- no default independent verifier platform or unbounded EvidenceIndex;
- no model-owned selector, coordinate, capability, approval, or completion;
- no benchmark task/family special cases in production semantics;
- no parallel authorities during migration;
- no production-grade security, multi-tenant, distributed-worker, or global exactly-once claim in the MVP.

## 6. Definition of program completion

The target is complete only when:

1. all P0–P4 foundations, the five P4-minimum gates, and P5 exit gates have code and reproducible evidence;
2. current production imports and call paths use the canonical owners;
3. legacy owners are deleted or explicit isolated adapters with removal gates;
4. focused checks and the core benchmark pass; immutable multi-suite breadth/security attestation is a separate release gate when such a claim is published;
5. documentation, status, and the machine-readable manifest agree.

Historical milestone detail is preserved in
[the 2026-08-05 status snapshots](archive/superseded-2026-08-05/status-snapshots/).
