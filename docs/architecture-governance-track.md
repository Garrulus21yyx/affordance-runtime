# Architecture Governance Track

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** architecture change admission and migration discipline
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## 1. Decision

The architecture center is environment generalization through one semantic
observe–act–observe interface. Changes are admitted when they improve
observation quality, grounding, route selection, execution, evaluation, or
cross-surface task success while preserving local correctness invariants.

## 2. Admission questions

Every behavior-changing proposal must answer:

1. Which agent/environment behavior improves?
2. Which canonical contract owns it?
3. Which positive vertical case proves it?
4. Does it keep surface-specific payload below the world interface?
5. Which old owner is displaced and when is it deleted?
6. Which freshness, semantic-confirmation/current-rebind, observation-barrier,
   no-retry, and evaluation invariants apply?
7. Does it add a service/store/protocol without a measured product need?

## 3. One-default-path rule

Migration order is:

```text
new contract
→ focused implementation
→ migrate one vertical caller
→ positive and negative evidence
→ switch default composition
→ delete or edge-isolate old owner
```

Core code may not dual-read, dual-write, or round-trip new contracts through
legacy objects. Compatibility is one-way at an external edge with an expiry.

## 4. Redlines

Do not admit work whose primary output is more RuntimeDelta kinds, global
atomic commit, StateKernel/CAS surface area, durable ledger/checkpoint, generic
recovery transaction, trace authority, or capability-proof machinery unless a
separate approved product fault model requires it.

Do not admit benchmark-specific production branches or tests that only prove a
surface entered the old contract/trace pipeline. Cross-surface work needs a
positive completed task.

## 5. Evidence

Focused tests localize failures. The cross-surface matrix measures product
behavior. Full pytest/static checks protect integration. Evidence is bound to
the exact revision/profile and never becomes online authority.

LOC is only a responsibility-review signal. File or function length alone does
not fail architecture admission and must not trigger mechanical helper
extraction. Automated gates prioritize dependency direction, forbidden imports,
cycle-free public facades, single semantic authorities, collaborator boundaries
and behavior invariants. A split is justified only when it moves a complete,
independently testable responsibility with a coherent reason to change.

## 6. Record rule

Large or irreversible architecture changes receive a scoped record under
`docs/change-admission/`. Historical records remain immutable but cannot
override the current architecture or evolution plan.
