# Architecture Governance Track

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** synchronous architecture admission for production changes
> **Authority:** subordinate to the [authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Active queue:** [Current Implementation Plan](current-implementation-plan.md)

## 1. Decision

Every production change passes an architecture admission check in the same
change. Existing debt does not block unrelated work, but a touched authority
boundary cannot grow, duplicate, or move into a less suitable owner.

The track is independent of feature priority: one vertical behavior/authority
slice and one horizontal containment slice may be active, with one production
writer for each affected state surface.

Current admission is scoped to the trusted single-process, single-run,
single-coordinator, single-browser-session MVP. Production-grade multi-tenant,
concurrent-worker and hard-crash guarantees require a separate admitted threat
model and cannot be smuggled into an ordinary P4/P5 gate.

Trusted Runtime-selected/configured in-process adapter/provider implementation
code belongs to the TCB. The external page, document, tool, or provider content
it observes or returns remains untrusted data and cannot create local authority.

## 2. Non-negotiable authority rules

1. `TaskSpecAuthority` owns accepted task meaning and revision.
2. `TaskPlanAuthority` admits one current replaceable execution hypothesis.
3. `CanonicalObservationBuilder` owns current observed semantics.
4. `ActionChoiceBuilder` owns the full current legal Catalog before model presentation.
5. `ActionTransactionMaterializer` is the only full Draft/Sealed construction entrypoint; its pure route owner binds the concrete backend, while independent gates own authorization decisions.
6. Materialization finishes and freezes the executable ActionContract before policy/approval; `Executor` consumes that same hash, returns a typed transport receipt, and never owns effect or completion truth.
7. `LoopEvaluator` returns typed evaluations and never writes state.
8. `TaskCompletionEvaluator` owns pure closure semantics but not commits.
9. `RuntimeCommitter` is the single production state/trace writer.
10. Trace, benchmark, evolution, model evidence, and archived documents have no synchronous authority.
11. Acquisition adapters own truthful epoch/scope/budget coverage; missing or failed coverage is UNKNOWN, never builder-inferred COMPLETE.
12. Product composition cannot disable applicable mandatory safety gates or synthesize capability grants; unknown actual adapter support fails closed.
13. Fresh O1 precedes final materialization; approval/policy evaluates the final contract, stale preflight is zero-call, and approved/executed hashes are equal. Transport, effect and actual output materialization are separate typed facts.
14. Third-party observation content cannot create TaskSpec, capability, approval, policy, or control flow; effectful source→sink values require admitted typed flow.
15. Replay has no live fallback. P5's semantic gate contains only the five P4-minimum invariants; focused/full/static checks and the core benchmark are closure evidence for those invariants and the default route, not a sixth invariant. P4-C2, permit/fencing/collateral hardening, P4-R0 and multi-suite attestation are non-blocking unless their matching claim is admitted.

The `TaskSpecAuthority` rule is the Task Meaning Write Barrier. Raw language
visibility and semantic authority are separate: TaskPlanner,
OpenSemanticResolver, and ClarificationComposer may receive explicitly bounded
`context_only` source excerpts, but cannot create or revise accepted IDs.
Action construction, binding, gates, execution, evaluation, completion, and
commit remain raw-text-free.

No change may create simultaneous progress, plan-admission, observation,
choice-space, completion, or commit authorities.

Logical authority does not require a physical service boundary. The default is
an in-process modular monolith; extraction into a service/store/queue/model call
requires measured isolation, scale, concurrency, reliability, or regulatory
need. Catalog/observation completeness may use immutable indexes and refs, but
physical realization cannot change logical membership, coverage, conflict,
digest, deny, or write semantics.

## 3. Substitutive migration rule

Every authority migration names:

```text
canonical replacement
→ production call-site cutover
→ legacy deletion or explicit isolated adapter
```

Compatibility requires a narrow allowlist, owner, reason, and deletion gate. A
shadow object or projector cannot become a permanent second authority.

## 4. Responsibility containment

Planner, Coordinator, StateKernel, adapters, verifiers, benchmarks, and trace
must not acquire responsibility merely because they possess useful context.
Domain algorithms return typed results; the committer applies transitions.

Neutral contracts and authority-free collaborators must not depend on:

- adapters or benchmark packages;
- Coordinator or StateKernel mutation APIs;
- trace/evolution implementations;
- mutable planner/provider objects.

## 5. Benchmark and semantic neutrality

Production logic must not branch on benchmark task ID, seed, family, URL,
selector, coordinate, or expected answer. Benchmark failure can motivate a
generic invariant and regression; it cannot define Runtime semantics.

Natural-language fallback logic belongs in typed intake/semantic owners, not in
strict Step Planner, Coordinator, recovery policy, or benchmark adapters.
Source-assisted downstream reasoning must reference existing canonical IDs;
missing semantics returns TaskSpecGap/clarification rather than silent plan or
contract expansion.

## 6. Horizontal ratchets

The executable governance tests freeze known control hotspots. Ceilings may
decrease; increases require an explicit time-bounded admission exception.

| Surface | Ceiling |
|---|---:|
| `coordinator.py` | 3,461 lines |
| `compatibility_planner_algorithms.py` | 2,042 lines |
| `task_planning.py` | 1,642 lines |
| `RunCoordinator.run_sync` | 2,034 lines |
| `GeneralistLMPlanner.propose` | 222 lines |
| `LLMIntentCompiler.compile` | 253 lines |
| `TaskPlanValidator.validate` | 239 lines |
| `RunCoordinator` method count | 26 methods |

These are maximum debt ratchets, not design targets.

## 7. Change-admission record

A production slice records:

- changed authority and owner;
- production behavior change or foundation-only scope;
- legacy deletion/isolation result;
- focused tests and immutable evidence identity;
- architecture admission, promotion, and remote-CI status;
- explicit non-claims.

Foundation-only work cannot claim production cutover. Historical admissions
remain immutable even when their parent design is later archived.

## 8. Simple documentation gate

Documentation lifecycle is governed by
[Documentation Governance](documentation-governance.md). Its mechanical gate is
deliberately small: manifest/path validity, one current architecture and plan,
current-entry links outside archive, valid redirect/archive targets, and
maintained relative links. It does not inspect historical prose semantics.

## 9. Historical track

The detailed pre-consolidation governance chronology is preserved at
[architecture-governance-track-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/architecture-governance-track-pre-consolidation.md).
It is evidence of prior decisions, not the current policy surface.
