# Horizontal Architecture Governance Track

Status: **active / gate-enforced**  
Effective: **2026-07-27**  
Baseline source: local working-tree snapshot derived from `db0d877a0fda`; the
executable ratchets record the later uncommitted containment slices. This is a
locally reproducible snapshot, not immutable revision evidence; immutable
status requires the same committed tree to be reverified.

This document owns the execution semantics of the project's **independent
horizontal governance track**. Structural ownership rules remain normative in
[Responsibility Containment Boundary](responsibility-containment-boundary.md).
The current feature sequence remains normative in
[Current Implementation Plan](current-implementation-plan.md).

## 1. Decision

Architecture governance applies immediately to every production change as a
**synchronous change-admission gate**. It runs alongside M8, M9, correctness,
security, evidence, and integration work.

It is **not a unified-rewrite prerequisite**. Existing debt is baselined and
may remain while compliant milestone work proceeds. A gate failure blocks the
change that introduced or expanded the violation; it does not require the
repository to complete a single large refactor before unrelated work can
continue.

## 2. Goals and Non-goals

Goals:

- prevent new reasons to change from accumulating in frozen control modules;
- prevent control modules and long methods from growing above measured
  baselines;
- keep dependency arrows toward neutral typed contracts and owning ports;
- prevent extracted collaborators from reacquiring authoritative state or
  execution-trace commit authority;
- reduce named responsibilities incrementally in the same slices that touch
  them;
- keep implementation status, executable gates, and current plans synchronized.

Non-goals:

- no repository-wide rewrite, framework replacement, or microservice migration;
- no requirement to reach the 2,000/1,500-line health targets before unrelated
  feature or correctness work;
- no file splitting solely to lower line counts;
- no claim that line count proves architectural quality;
- no second state manager, trace manager, workflow engine, or policy owner;
- no weakening of safety, authority, evidence, benchmark, or intake boundaries
  to make a gate pass.

## 3. Independent Status Axes

The horizontal track is not a milestone and does not become `done` after one
green change.

| Axis | States | Meaning |
| --- | --- | --- |
| Track lifecycle | `active`, `retired` | `active` is the normal project state; retirement requires an explicit governance decision |
| Change admission | `pass`, `fail`, `waived`, `not_evaluated` | result for one proposed change |
| Remediation item | `pending`, `in_progress`, `done`, `blocked` | state of one named debt item |
| Snapshot | `passing`, `violated`, `evidence_stale`, `waiver_active` | evidence state of the whole current tree |

Capability maturity remains a separate axis: `protocol`, `injectable`,
`normal-entrypoint`, and `empirical`. A milestone can complete at its declared
maturity while the architecture track remains active. Architecture debt alone
does not fail an unrelated change; increasing or copying that debt does.

Retirement requires no active feature-frozen control surface, every named
remediation item either `done` or transferred to another normative gate,
current full-tree structural evidence, and a recorded architecture-owner
decision. LOC thresholds alone cannot authorize retirement.

## 4. Immediate Growth Freeze

The following ceilings are the active ratchets. They are measured physical
Python lines, including comments and docstrings. They may decrease as ownership
is removed. An implementation change may not increase its own ceiling. Any
increase requires a separately recorded, prior, time-bounded waiver decision
naming the approver and immutable baseline; the governed implementation remains
`waived`, never `pass`.

### Control modules

| Module | Active ceiling | Governance reason |
| --- | ---: | --- |
| `coordinator.py` | 3,473 lines / 26 `RunCoordinator` methods | feature-frozen task-level control center |
| `compatibility_planner_algorithms.py` | 2,042 lines | frozen historical compatibility quarantine |
| `task_planning.py` | 1,642 lines | growth-controlled mixed planning surface |

### Control methods

| Method | Active ceiling | Governance reason |
| --- | ---: | --- |
| `RunCoordinator.run_sync` | 2,039 lines | known long-method debt; may only shrink |
| every other/new `RunCoordinator` method | 250 lines | prevents moving new phase algorithms into another Coordinator method |
| `GeneralistLMPlanner.propose` | 222 lines | preserves the extracted model-orchestration boundary |
| `LLMIntentCompiler.compile` | 253 lines | grandfathered over-threshold intake method; may only shrink |
| `TaskPlanValidator.validate` | 239 lines | preserves the current validation boundary |

The long-term Coordinator health targets remain below 2,000 lines and then
below 1,500 lines. These are remediation targets and escalation thresholds,
not completion evidence and not prerequisites for unrelated milestones.

## 5. Semantic Architecture Gates

Mechanical ratchets are necessary but insufficient. Every production change
must also pass these semantic gates:

1. **Dependency direction.** Neutral planning and approval contracts may not
   import Coordinator, CLI, benchmark, or adapter layers. Extracted
   collaborators may not import Coordinator or the execution trace API.
2. **Execution commit authority.** Task-level phase transitions, observation
   commits, and TaskPlan install/replace calls remain in `RunCoordinator` or the
   explicitly bounded legacy `runtime.py` conformance harness.
3. **Authority-free extraction.** A new collaborator needs typed input and
   output, may not construct or mutate authoritative Runtime state, and may not
   append canonical execution trace. It must be added to the executable
   authority-free collaborator manifest in the same change. Coordinator
   validates and commits its result. The manifest classifies every public
   `StateKernel` method as read or mutation and freezes the known
   `planner_context.active_subgoal()` hidden-mutation debt.
4. **Benchmark isolation.** Existing non-adapter benchmark import debt is
   frozen to `cli.py`, `conformance.py`, `evolution.py`, and
   `evolution_replay.py`. The allowlist may shrink, not spread to a new module.
5. **Behavior preservation.** Extraction requires focused positive, negative,
   stale, no-op, failure, and authority tests appropriate to the contract. LOC
   reduction without responsibility removal is not admission evidence.
6. **Compatibility forwarding.** A compatibility re-export must preserve the
   same object identity; it may not retain a second implementation or policy.

Trace ownership is scoped. Coordinator owns the canonical task-execution trace;
intake/upstream, compatibility-harness, and benchmark traces retain their
declared scopes. This track does not falsely impose a single global `TraceDag`
writer before those scopes are migrated and proven equivalent.

## 6. Known Baselined Debt

Baselining debt prevents it from spreading; it does not declare it healthy.

| Debt | State | Required direction |
| --- | --- | --- |
| `RunCoordinator.run_sync` contains multiple phase algorithms | `in_progress` | extract one named responsibility at a time through immutable context and typed result |
| `task_planning.py` combines models, provider schema, validation, routing, and implementations | `pending` | split by change reason when the relevant planning slice is touched |
| `LLMIntentCompiler.compile` is 253 lines | `pending` | isolate a typed phase without changing the three-call/authority boundary |
| `StateKernel.active_subgoal()` has a hidden progress mutation used by read-oriented consumers | `pending` | separate read view from activation command before claiming strict single-writer semantics |
| non-adapter benchmark imports remain in four allowlisted entry/core/evolution modules | `pending` | move shared contracts out of benchmark packages and shrink the allowlist |
| broad `dict[str, Any]` remains at locator/parameter/evidence boundaries | `pending` | introduce tagged types incrementally at authority, persistence, and adapter boundaries |

`done` requires named responsibility removal plus dependency, authority, and
behavior evidence. A lower LOC value alone cannot close an item.

## 7. Change Admission

Each production change records:

1. the single responsibility and current owner;
2. touched control modules and before/after ratchets;
3. typed inputs and outputs;
4. authority, budget, state-writer, and trace-writer sources;
5. dependency edges added and removed;
6. behavior and architecture tests;
7. the old path or duplicated responsibility removed;
8. admission result: `pass`, `fail`, or `waived`.

Admission meanings:

- `pass`: no debt grows, no forbidden edge/writer appears, and required evidence
  is current;
- `fail`: the proposed change adds responsibility, growth, reverse dependency,
  authority duplication, benchmark specialization, or an untyped boundary;
- `waived`: a bounded exception is accepted, but the violation is not called a
  pass and remains visible as debt.

`fail` blocks only that change. A milestone may proceed through another design
that passes the same gates.

## 8. Exceptions and Anti-circumvention

Exceptions are limited to correctness, security, evidence preservation,
necessary compatibility, or a demonstrable net responsibility reduction. A
waiver must include scope, owner, reason, risk, expiry, repayment item,
before/after measurements, and approving decision. The architecture owner for
the current plan records that prior decision in `implementation-status.md`;
the implementation change may only reference it.

No waiver may authorize a second authoritative writer within the same declared
execution-state or trace scope,
capability or approval escalation, benchmark specialization in shared Runtime,
or bypass of safety/evidence gates.

The following are circumvention and fail admission:

- raising a ceiling, deleting a gate, or shrinking its scan set merely to admit
  the same growth;
- moving code to a helper while passing mutable state or trace authority;
- deleting unrelated lines to create room for a new responsibility;
- renaming a benchmark-specific rule as a generic helper;
- adding a compatibility re-export that contains behavior;
- reporting LOC reduction without naming the removed responsibility and owner.

## 9. Executable Evidence

The active local gate is:

```bash
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest -q \
  tests/test_horizontal_architecture_governance.py \
  tests/test_r8_architecture_boundaries.py \
  tests/test_responsibility_containment.py
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m ruff check src tests scripts
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m mypy --ignore-missing-imports src
git diff --check
```

The full repository test suite remains required before claiming a completed
implementation slice. Architecture gates prove structural admission, not
generalization, recovery effectiveness, benchmark score, or release readiness.
