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

The current default path follows SAR-0 authoritative optimized architecture.
S0/S1/S2, TPA-0 through TPA-5, and ODG-0 through ODG-9 are historical
foundation/diagnostic records where they conflict with SAR-0; advanced
attribution remains `EXPERIMENTAL_ONLY`. Future Runtime work follows
substitutive one-in/one-out migration: replace an old authority, switch the
real production path, then retire the old owner or projector.

The implementation sequence has advanced through SAR-8C default RecoveryPhase
cutover, Planner Selection ActionChoice fallback retirement, FOR-1
FailureOwner vocabulary, and FOR-2A Runtime RecoveryPhase narrowing for their
recorded local scopes. `RecoveryPhase` now rejects non-`RUNTIME_RECOVERY`
owners before state mutation; a temporary owner handoff seam preserves existing
planner/user/progress/terminal behavior until the remaining router cleanup.
The selected SAR-9 prerequisite remains the rest of Failure Ownership Router:
delete semantic-owner `RecoveryKind` values and duplicate owner mappings, add
structured step/task/user/progress handoff, and run the behavioral
classification gate.
Neither lane authorizes promotion while remote CI is disabled or required
validation is unavailable.

ODG-2 may add typed, authority-free progress and attribution contracts, but
those contracts are not progress authority until later slices add shadow
comparison and Coordinator commit gates. A module defining obligation progress
contracts may depend on canonical task-intake types, but must not import
Coordinator, StateKernel, TaskPlan, BrowserGym, CLI, trace writers, or planner
implementations.

ODG-3 may let StateKernel hold an optional obligation progress ledger and
return an immutable progress view. This is a one-way dependency from
StateKernel to the obligation progress contracts; the reverse dependency
remains forbidden. ODG-3 does not authorize Coordinator satisfaction commit,
finish-gate replacement, PlannerContext projection, TaskPlan replacement,
trace shadow comparison, recovery behavior, BrowserGym changes, benchmark
reruns, or promotion claims.

ODG-4 may add executable role decisions and a safe ready-obligation projection
result inside the obligation progress contract module. Role decisions must be
derived from canonical `TaskObligationSpec` fields and source-lineage-compatible
metadata only; task names, URLs, selectors, coordinates, benchmark families,
Planner state, TaskPlan state, and model-authored progress are forbidden
inputs. Ambiguous predicates remain `role_pending` and must not become ready
progress obligations until an explicit source-derived rule is added.

ODG-5 may add authority-free shadow comparison between a legacy TaskPlan
projection and the canonical obligation ready projection. The comparator may
produce stable trace payload data, but must not initialize or mutate
StateKernel, change PlannerContext, replace TaskPlan semantics, or affect finish
authority. The comparison exists to classify divergence; it is not a second
progress authority. ODG-5.1/5.2 harden that contract with a trace identity
envelope and add a read-only runtime projection seam using
`legacy_verified_projection`: exact-ID mapping only, no lexical subject/objective
mapping, no obligation-ledger initialization, and no completed-without-evidence
credit. ODG-5.3 may write exactly one diagnostic
`ObligationProgressShadowCompared` event through the existing post-observation
progress seam, or `ObligationProgressShadowFailed` if the diagnostic projector
unexpectedly fails. This hookup must replace existing inline Coordinator
control flow, reduce `run_sync()`, and remain diagnostic-only.

ODG-6 may add a typed, authority-free current-observation satisfaction
evaluator for explicitly role-resolved `IS_AVAILABLE` / `IS_VISIBLE`
obligations. The evaluator may prepare `ObligationSatisfactionPreparation`
with `source=current_observation`, but it must not import Coordinator,
StateKernel, TaskPlan, trace writers, BrowserGym, planner implementations, or
benchmark packages. It must not consume `ExecutionReceipt`, external reward,
task names, URLs, selectors, coordinates, or model proposals as completion
authority. Coordinator commit remains ODG-10 and finish-gate authority remains
ODG-11.

ODG-6.1 hardens shared attribution contracts before ODG-7. Attribution tickets
and satisfaction preparations must carry `task_spec_identity`; current
observation satisfaction must use a typed source object rather than a synthetic
contract ID; and current observation facts must include evidence kind, strength,
and source identity compatible with the canonical typed evidence requirement.
Multiple independent current-observation satisfactions are not ambiguity, but
multiple targets for one obligation remain fail-closed.

ODG-7 may add an authority-free attribution action view and candidate ticket
resolver. The resolver scopes which ready canonical obligations an accepted
action may later satisfy, but it must not decide completion, save tickets
through Coordinator, mutate StateKernel or the obligation ledger, change
ActionContract/Executor/Verifier interfaces, read TaskPlan active subgoals, or
consume PlannerProposal, task names, URLs, selectors, coordinates, BrowserGym
reward, or benchmark family. Multiple candidate obligations in one ticket are
allowed because post-action evidence, not pre-action planning, chooses the
final satisfaction target. ODG-7.1 additionally requires stale and invalid
ready-projection statuses to remain distinct, ticket identity to use canonical
JSON hashing rather than delimiter concatenation, ready views to be checked
against the current canonical obligation, and target matching to use
Runtime-supplied `AttributionTargetView.canonical_subject_ids` rather than
lexical matching.

ODG-8 may add authority-free post-action evidence normalization. It may project
immutable `VerificationEvidenceView` / `VerificationReportView` inputs and
Runtime-owned `VerifierSemanticEvidenceDeclaration` values into
`PostActionEvidenceFact` values, but those facts must not carry obligation IDs
and must not decide satisfaction. ODG-8 must not persist tickets, change
ActionContract, pass tickets to Executor or Verifier, change verifier pass/fail
behavior, mutate StateKernel or the obligation ledger, change finish authority,
change PlannerContext, consume TaskPlan progress, or use BrowserGym reward,
task names, URLs, selectors, coordinates, or benchmark family as evidence
authority. Receipt and external-evaluator sources remain weak; ODG-9 may not
complete an obligation from weak evidence alone.

ODG-8.1 hardens ODG-8 before attribution. A normalizer must receive a
`PostVerificationContext` and verify that contract ID, contract hash, and
pre-action snapshot match the `ProgressAttributionTicket`. Semantic evidence
declarations bind through stable `semantic_evidence_key` values, not dynamic
post-snapshot evidence IDs. Effective strength is the minimum of verifier
reported strength and source cap; weak post-action observations remain weak,
receipt and external-evaluator sources remain weak even if reported strong, and
unknown strength values fail closed.

ODG-8B may improve verifier evidence fidelity by adding `VerifierEvaluation`
and making `verify()` a compatibility wrapper for `evaluate().passed`.
Verification reports may store real observed values for receipt evidence,
observation metadata, DOM attributes, control state, and HTTP JSON projections.
This must not change verifier pass/fail semantics. `state_delta_or_terminal`
remains weak generic evidence and must not be converted into concrete
`EQUALS`, `HAS_CHANGED`, or `IS_CHECKED` progress facts without explicit typed
before/after state.

ODG-9 may add a pure `PostVerificationObligationAttributor`. It may consume the
canonical `TaskSpec`, immutable `ObligationProgressStateView`,
`ProgressAttributionTicket`, and `PostActionEvidenceFact` values to return an
`ObligationAttributionResult`. A satisfaction preparation is allowed only when
exactly one candidate obligation is fully covered by sufficiently strong,
identity-consistent evidence and its dependencies are still satisfied. ODG-9
must not persist tickets, mutate StateKernel or the obligation ledger, write
trace, change Coordinator, change finish authority, change PlannerContext, or
require TaskPlan. Weak receipt, weak state-delta, and weak external-evaluator
facts may classify as `weak_evidence`, but may not complete an obligation.

ODG-9 runtime carry may add `BoundActionExecution` and a diagnostic shadow
projection seam. The ticket may be carried beside the accepted `ActionContract`
only; it must not be added to the `ActionContract` schema or passed to Executor
or Verifier. The shadow projection may create a versioned payload describing
the ODG-9 attribution result, but it is trace-payload-only until a separate
hookup writes a diagnostic event. It must not mutate StateKernel or the
obligation ledger, change Coordinator progress commit, change finish authority,
change PlannerContext, require TaskPlan, or claim PR breadth / promotion.

S0 simplified architecture freeze superseded ODG-0 as the default production
target during the active-step design period, but SAR-0 now supersedes both the
S0 simplified target and the TPA additive default sequence. The S0 and TPA
documents are archived under `docs/archive/superseded-2026-07-29/` and remain
historical context only. ODG-2 through ODG-9 remain foundation/diagnostic code;
ODG-9 hookup, ODG-10 obligation-ledger progress commit, and ODG-11 obligation
finish-authority migration are stopped for the default path. Advanced
attribution is `EXPERIMENTAL_ONLY`. New default-path work must follow
`docs/superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md`
and
`docs/superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md`.
No change may create simultaneous completion authorities across legacy TaskPlan
progress, active-step progress, obligation-ledger progress, or future
TaskProgress.

S1 simplified core contracts may add a neutral contract module for
`SourceReference`, criterion policies, `StepSpec`, `TaskPlanView`,
`StepProgressView`, `ExecutionAttempt`, `VerificationResult`, and
`ActionOutcome`. This module is a foundation-only boundary: it must not import
Coordinator, StateKernel, adapters, benchmarks, trace, executors, verifier
implementations, PlannerContext, or TaskPlan implementation code; it must not
change production authority, complete steps from receipts or external reward,
or authorize ODG hookup / ODG-10 / ODG-11. The next default-path slice after S1
is exact-ID legacy-to-step compatibility projection.

S2 legacy-step compatibility projection may read TaskPlan, PlanProgress,
TaskSpec, and StateKernel as a read-only projection source. It may project exact
subgoal ID to canonical obligation ID, completed step identity, active step
identity, and evidence references into the simplified Step contracts. It must
not use lexical mapping, task name, URL, selector, seed, benchmark family,
PlannerContext, trace writing, Coordinator logic, or any StateKernel mutation.
The projected view has no completion authority until a later explicit cutover.
S2.1 hardens this projection before TPA-2: completed plans must project with no
active step, ready-but-not-activated steps must remain unactivated until the
Coordinator explicitly activates them, source-unit lineage must not be confused
with claim identity, criterion evidence policy must come from typed evidence
requirements rather than semantic task-obligation provenance, and legacy
progress IDs must be exact and verifier-evidenced.

TPA-0 freezes the TaskPlan and Step Planner owner matrix without changing
production behavior. TPA-1 records the current TaskPlan construction, plan
commit, replan, Step Planner triple-signature, Planner read-set, TaskSkill
progress, CLI, integration, and benchmark surfaces and protects the exact
baselines with AST tests. TPA-2 adds immutable PlanningRequest contracts and
one read-only builder; it does not switch PlannerPort, TaskPlan admission,
progress, finish, Coordinator control flow, or benchmark behavior. TPA-3 is the
first slice allowed to migrate standard StepPlannerPort call sites to
`propose(request)` and must preserve provider-facing payload and behavior unless
it triggers a separately authorized breadth rerun. TPA-3.1 adds the
request-based PlannerContextBuilder serialization path only; the legacy
three-object PlannerContextBuilder path remains temporarily available until
standard StepPlannerPort cutover is complete. TPA-3.2A/B hardens the immutable
request surface by preserving stale/invalid Step projection status, adding
PlannerAdmissionView / TargetAdmissionDecision / PlannerAdmissionSummary
contracts, and making DecisionConstraintSet target mappings deeply immutable.
It does not connect terminal admission, change PlannerPort, touch Coordinator,
or change progress/finish authority. The next authorized sub-slice is the
legacy terminal admission projector. TPA-3.2C adds that projector as the only
migration owner allowed to read legacy TaskPlan/PlanProgress plus
BrowserSnapshot terminal-grounding details and embed the resulting immutable
PlannerAdmissionView in PlanningRequest. It does not consume the admission in
DecisionConstraintBuilder yet and still does not change PlannerPort,
Coordinator, progress, finish, or benchmark behavior. The next authorized
sub-slice is TPA-3.2D, where DecisionConstraintBuilder applies the immutable
admission instead of rereading StateKernel and BrowserSnapshot. TPA-3.2D adds
that request-only admission application and typed summary result; the legacy
`narrow_terminal_candidates(context, state, snapshot)` method remains a
temporary compatibility path until Generalist internals are switched to the
request core. TPA-3.3 routes GeneralistLMPlanner internals through immutable
PlanningRequest and consumes request-sourced terminal admission diagnostics
without changing the public PlannerPort signature, Coordinator call site,
progress authority, or finish authority. TPA-3.4 routes
ParentAgentPlannerAdapter through the same immutable request/context path while
preserving parent-agent proposal validation and provenance. The next authorized
sub-slice was TPA-3.5 reference contract planner request migration; it routes
Pricing/Settings/Export through PlanningRequest when TaskSpec identity is
available while preserving legacy snapshot ActionContract binding. The next
authorized sub-slice was TPA-3.6 conformance/recovery fixture planner request
migration; it routes ConformancePlanner and RecoveryFixturePlanner through
PlanningRequest when TaskSpec identity is available while preserving fixture
contract behavior. The latest authorized sub-slice is TPA-3.7 BrowserGym and
benchmark planner compatibility migration; it routes BrowserGymPlanner through
PlanningRequest when TaskSpec identity is available while preserving
BrowserGymPolicyRequest as the benchmark-policy compatibility boundary.
TPA-3.8 makes the public PlannerPort contract request-only and moves remaining
three-argument planner invocation behind `planner_compatibility.py` for legacy
ActionContract-returning fixtures. TPA-4 adds neutral TaskPlanAuthority draft,
initial/revision request, issue-report, decision, binder, and generator-port
contracts without connecting them to Coordinator, StateKernel mutation,
TaskPlanLifecycle, generator migration, progress authority, finish authority,
or PR breadth claims. The next authorized sub-slice is TPA-5 TaskPlan generator
draft migration. TPA-5 adds draft-producing rule, router, and reference
generator compatibility surfaces plus exact semantic projection tests. It keeps
legacy TaskPlannerPort production generation active, does not change provider
schema or prompts, and leaves LLM draft migration as a separate pending slice.
SAR-0 then freezes
`docs/superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md`
as the single long-term target architecture and
`docs/superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md`
as the active execution plan. Future default-path work stops additive
foundation-only expansion, including TPA-5B, and uses substitutive one-in/
one-out migration. The next authorized slice is SAR-1 deep immutability and
stale contract-hash repair.

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
| `coordinator.py` | 3,461 lines / 26 `RunCoordinator` methods | feature-frozen task-level control center |
| `compatibility_planner_algorithms.py` | 2,042 lines | frozen historical compatibility quarantine |
| `task_planning.py` | 1,642 lines | growth-controlled mixed planning surface |

### Control methods

| Method | Active ceiling | Governance reason |
| --- | ---: | --- |
| `RunCoordinator.run_sync` | 2,034 lines | known long-method debt; may only shrink |
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
| standard `PlannerPort` still receives mutable `StateKernel` | `done for public contract / compatibility pending` | public `PlannerPort` is request-only; legacy compatibility signatures must continue shrinking behind explicit adapters |
| failure routing and runtime recovery ownership are still mixed | `FOR-2A local candidate / FOR-2B selected` | `FailureOwner` replaces `FailureDisposition`, and RecoveryPhase now accepts only `RUNTIME_RECOVERY`; next delete semantic-owner RecoveryKind values and duplicate owner mappings, then add structured non-runtime owner handoff without a second recovery workflow |
| Generalist Planner semantic fallback ownership review | `in_progress` | Planner Selection Simplification deleted the strict `semantic_action_resolver.py` default path and strict page/exact text/terminal-submit fallback functions; remaining historical-profile grammar must retire through ActionChoice or explicit compatibility-only owners |
| `semantic_action_resolver.py` output/input boundary | `retired` | the module is removed from production source; historical V-PRB records remain archival evidence only |
| PR breadth V-PRB-5A button-sequence semantics | `done` | clean `151fbef` PR breadth rerun passed both `click-button-sequence` seeds after dependency/terminal, clicked-navigation relation, and completed-click progress-evidence repairs |
| PR breadth V-PRB-5B entry action-family resolution | `done` | clean `3daf779` PR breadth rerun confirms the original `entry_action_family_unavailable` rejection is gone and textbox value-entry inference is restored; `task_action_family_resolution.py` is now in the executable authority-free manifest; remaining form failures moved to V-PRB-5C strict-planner empty proposal generation |
| PR breadth V-PRB-5C form-sequence strict-planner proposal generation | `done` | `a805f0d`, `9c1b58c`, and `d50a631` resolver repairs are admitted and cleanly rerun; clean `d50a631` PR breadth reaches 12/12 official reward, and the prior form terminal-submit / negative-slider official failures no longer reproduce |
| PR breadth V-PRB-6 terminal-completion guard | `in_progress` | clean `d50a631` PR breadth still has 3 Runtime aborts after external reward succeeds; first trace classification narrows form cases to stale subgoal/progress evidence binding; classify external reward versus Runtime verifier/terminal authority separately before fresh diagnostic or promotion |
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
