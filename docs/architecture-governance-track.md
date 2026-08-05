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

## 2. Non-negotiable authority rules

1. `TaskSpecAuthority` owns accepted task meaning and revision.
2. `TaskPlanAuthority` admits one current replaceable execution hypothesis.
3. `CanonicalObservationBuilder` owns current observed semantics.
4. `ActionChoiceBuilder` owns the full current legal Catalog before model presentation.
5. `ActionContractBuilder` owns concrete binding; gates own authorization decisions.
6. `Executor` returns receipt and never completion.
7. `LoopEvaluator` returns typed evaluations and never writes state.
8. `TaskCompletionEvaluator` owns pure closure semantics but not commits.
9. `RuntimeCommitter` is the single production state/trace writer.
10. Trace, benchmark, evolution, model evidence, and archived documents have no synchronous authority.

No change may create simultaneous progress, plan-admission, observation,
choice-space, completion, or commit authorities.

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
