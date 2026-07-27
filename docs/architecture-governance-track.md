# Horizontal Architecture Governance Track

Status: **active / gate-enforced**  
Effective: **2026-07-27**  
Committed governance baseline: `627b5f76900c343d2d0af0ca7fae8645ce2088e0`.
The executable ratchets were first committed at that revision. The latest
implementation-bearing local-equivalent baseline is
`66747420c4d319d26a10a7c6fb6006871cf3310a`; later documentation-only sync
commits do not inherit broader runtime or promotion evidence unless their own
gate is recorded. Remote CI is intentionally disabled for the current
iteration, so these revisions have no remote-green or remote-fail claim and are
not promotion baselines.

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

## 3.1 Double-track, One-gate Execution

Work is scheduled through two independent lanes and one shared admission gate:

```text
vertical product lane ----\
                           -> architecture change admission -> integration
horizontal architecture --/
```

- the vertical lane advances the next user-observable capability or evidence
  gate;
- the horizontal lane removes one named ownership, dependency, mutation, or
  typing debt;
- every slice passes the same dependency, authority, growth, behavior, and
  evidence checks;
- at most one active vertical slice and one active horizontal slice may exist;
- each slice has a single production writer, although bounded read-only
  investigation and final diff review may run independently;
- a horizontal slice is not a vertical prerequisite unless the vertical change
  would otherwise grow, copy, or rely on the governed debt.

The current vertical lane is protected cross-family / PR breadth confirmation.
SG7 targeted protected-family confirmation is closed only within its recorded
2-task x 2-seed scope. The active-subgoal read/activation separation is locally
closed in the current governance-sync line; the current horizontal lane is
removal of mutable `StateKernel` from the standard Planner input. Neither lane
authorizes promotion while remote CI is disabled or required validation is
unavailable.

The token-minimizing default is one integrator agent carrying the slice from
interface decision through implementation and final acceptance. Subagents are
reserved for bounded, low-overlap, read-only investigation or a diff-first
independent review; they do not become parallel production writers for
Coordinator, StateKernel, public Planner contracts, canonical task schemas, or
state/trace authority.

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
  `StateKernel` method as read or mutation. The former
  `planner_context.active_subgoal()` hidden-mutation exception is closed and
  remains protected against reintroduction.
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
| standard `PlannerPort` still receives mutable `StateKernel` | `pending` | introduce frozen `PlannerStateView` / `PlanningRequest` before claiming immutable planner input |
| Generalist Planner semantic fallback ownership review | `pending_review` | move SG7-triggered deterministic semantic fallback ownership toward typed resolver/constraint owners when the next planning slice touches it |
| `LLMIntentCompiler` contains value-entry lexical normalization | `pending_review` | isolate source-bound value-entry normalization into a typed intent normalizer before declaring intake responsibility clean |
| `task_planning.py` combines models, provider schema, validation, routing, and implementations | `pending` | split by change reason when the relevant planning slice is touched |
| `LLMIntentCompiler.compile` is 253 lines | `pending` | isolate a typed phase without changing the three-call/authority boundary |
| `StateKernel.active_subgoal()` had a hidden progress mutation used by read-oriented consumers | `done` locally | `active_subgoal()` is read-only; `activate_next_subgoal()` is explicit and Coordinator-owned in production; planner context construction no longer activates progress |
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

The record may live in the active plan for a documentation-only or very small
slice. A production or public-contract slice must create a compact admission
record that includes `base_revision`, `single_responsibility`, `non_goals`,
`owner_before`, `owner_after`, `typed_input`, `typed_output`, `state_writer`,
`trace_writer`, authority/budget sources, dependency changes, removed old path,
required tests, and final admission status. This record is the task packet for
the single production writer and the contract for independent review.

Admission meanings:

- `pass`: no debt grows, no forbidden edge/writer appears, and required evidence
  is current;
- `fail`: the proposed change adds responsibility, growth, reverse dependency,
  authority duplication, benchmark specialization, or an untyped boundary;
- `waived`: a bounded exception is accepted, but the violation is not called a
  pass and remains visible as debt.

`fail` blocks only that change. A milestone may proceed through another design
that passes the same gates.

### 7.1 Module-level semantic owner gate

Line and method ratchets do not prove ownership cleanliness by themselves. A
change that moves semantic interpretation into module-level helper functions
still fails admission if it grows the wrong owner.

For strict planner and intake surfaces:

- strict planner module may not add new task-language parser logic unless the
  change is explicitly admitted as temporary debt;
- deterministic semantic behavior belongs in a typed resolver or constraint
  owner with declared applicability, input schema, negative examples, and
  non-BrowserGym evidence;
- Generalist Planner should orchestrate bounded proposal selection rather than
  accumulating raw-language interpretation;
- intent normalization may use source-bound user language, but it must not
  directly create READY authority or bypass canonical graph construction;
- SG7-triggered value-entry, observed-text, and submit fallback paths may not
  expand until their semantic ownership review is closed or waived.

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
