# Architecture Governance Track

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** architecture change admission and migration discipline
> **Target:** [Canonical GUI Agent Execution Architecture](task-execution-authority-map.md)

## 1. Decision

The architecture center is environment generalization through one semantic
observe–act–observe interface. Changes are admitted when they improve
observation quality, grounding, route selection, execution, evaluation, or
cross-surface task success while preserving local correctness invariants.

## 2. Admission questions

Every behavior-changing proposal must answer:

1. Which exact stage in the canonical authority map changes?
2. Which agent/environment behavior improves?
3. Which canonical contract owns it, and what are its authoritative input and
   typed output?
4. Which consumers receive that output, and does any projection incorrectly
   become an owner?
5. Does the change preserve the action-only main Agent boundary?
6. Which positive vertical case and held-out variation prove it?
7. Does it keep surface-specific payload below the world interface?
8. Which old owner is displaced and when is it deleted?
9. Which freshness, semantic-confirmation/current-rebind, observation-barrier,
   no-retry, and evaluation invariants apply?
10. Does it add a service/store/protocol without a measured product need?

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

## 7. Authority-map gate

Task, planning, execution, evidence, and completion changes must update and
conform to the [Canonical GUI Agent Execution Architecture](task-execution-authority-map.md).
Before adding a state field, decision variant, tool, or schema, the change must
name its existing canonical owner and the displaced path that will be deleted.
Model transport and benchmark modules may project canonical state but may not
introduce task-semantic domain owners.

This comparison is mandatory before implementation, not a documentation step
performed after code exists. The change record must include the completed
change-impact table from section 12 of the authority map. A proposal that cannot
identify one owner is escalated to an architecture review; it cannot proceed as
a schema, prompt, state-field, or benchmark repair.

The following changes always require an authority-map review before editing
production code:

- adding or changing an `AgentDecision` variant;
- adding a model-facing action tool or nested action schema;
- adding retained AgentLoop state;
- adding a planner/objective/predicate/scope contract;
- changing observation refresh, binding, execution, effect, or completion
  ordering;
- adding a new evidence provider that appears to need a separate lifecycle;
- changing benchmark composition in a way that bypasses the default target
  chain.

## 8. Normative-promotion gate

An implementation may not be described as the current canonical or closed path
until all of the following agree:

1. authority-map invariants and owner matrix;
2. implementation status at the exact revision;
3. property/state-machine/boundary tests;
4. fresh real benchmark evidence;
5. removal of the displaced implementation, tests, and maintained prose.

Deterministic tests may establish implementation consistency, but they cannot
promote an unverified model interface or benchmark path to normative authority.
