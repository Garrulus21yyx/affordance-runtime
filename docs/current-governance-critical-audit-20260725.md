# Current Governance Critical Audit - 2026-07-25

## 1. Scope and Identity

This audit reviews the clean SL09 working tree at:

~~~text
b01e73ba34f55726c2e29925ce545a4131269c99
agent/migrate-runtime-components
82 commits ahead of origin/agent/migrate-runtime-components
~~~

It evaluates the current M8.6 completion claim, the M8.2B repair direction,
the default strict planner, online recovery wiring, responsibility containment,
and evidence publication. It distinguishes four different statements that must
not be collapsed into one status:

1. a typed component exists;
2. a component is reachable through `RunCoordinator` when configured;
3. a normal standalone or benchmark entrypoint configures the component;
4. broad real-environment evidence supports a generalization claim.

## 2. Executive Decision

The Runtime-first direction remains correct. The repository contains substantial
working implementation and the M8.6 semantic repair gate is not documentation-
only. However, the unqualified statement that planner, recovery, and
responsibility governance are complete is broader than current code and evidence
support.

The correct status is:

> **M8.6 internal governance gate complete at `c939051`; operational recovery,
> planner generalization, obligation-complete task intake, and responsibility
> reduction remain open follow-through work.**

M8.2B is a completed diagnostic collection, not a completed planner milestone.
The current strict planner remains under repair and no nightly, release, or
external-suite score may be promoted.

## 3. Fresh Verification

The following checks were rerun at `b01e73b` using the fixed Python 3.12
environment:

~~~text
pytest -p no:cacheprovider -q
863 passed in 11.63s

ruff check src tests scripts
All checks passed

mypy --ignore-missing-imports src
Success: no issues found in 105 source files
~~~

The 11-case provider-free G5 Runtime rollout was also rerun at this exact HEAD.
All expected outcomes passed with no reported safety regression. The checked-in
`c939051` G5 manifest contains 82 indexed files and all hashes revalidate.

These facts establish local code health and internal Runtime conformance. They
do not establish production recovery wiring, open-world planner robustness, or
external-suite generalization.

## 4. Claim Matrix

| Claim | Decision | Supported boundary |
| --- | --- | --- |
| Budget authority only narrows during active perception | supported | policy and Coordinator negative controls pass |
| Screenshot transport alone cannot satisfy semantic visual evidence | supported | a current relevant linked candidate is required |
| Recovery owner results reject unavailable, failed, no-op, or unevidenced work | supported | typed dispatcher and tests pass |
| All normal entrypoints can compact context, repair schema, or switch provider online | not supported | normal generalist runner does not configure concrete owners |
| Complete-run benchmark collection continues after ordinary failures | supported | strict 60/60 diagnostic is complete and clustered |
| Default planner contains no hard benchmark task-id dispatch | supported | adapter isolation and source scan pass |
| Default planner is proven free of soft benchmark specialization | not supported | lexical scans cannot prove behavioral independence |
| Coordinator responsibility containment is complete | not supported | first ratchet passes; 3,643-line module and 2,098-line `run_sync` remain |
| Strict planner is robust enough for nightly or release promotion | not supported | latest diagnostic is 24/60 with cross-family regressions |
| Latest claims are remotely reviewable | not supported | local branch is 82 commits ahead of origin |

## 5. Blocking Findings

### F-01 - Task intake is not obligation-complete

`TaskSpec` carries requested effects, semantic values, criteria, and evidence
requirements, but it does not yet carry a typed, sourced obligation graph for
explicit terminal effects and data dependencies. `IntentDraftValidator` checks
that at least one effect exists; it does not prove that every explicit user
effect and dependency is represented. `RuleTaskPlanner` can therefore emit a
flat synthetic plan without a typed outcome or action family.

The clean `scroll-text:seed-0` replay proves this gap: terminal-readiness code is
present but is never entered because the required authority and dependency were
lost upstream. Adding another terminal label rule or Planner branch would treat
the symptom and violate the architecture boundary.

### F-02 - Full-phase recovery lacks production owner wiring

`RecoveryCommandDispatcher` is a valid typed boundary. It exposes only configured
owners and requires before/after evidence plus a non-empty delta. The default
Coordinator dispatcher is empty, however, and the BrowserGym generalist runner
does not inject concrete context-compaction, model-schema-repair, or provider-
switch owners. The only concrete provider-switch owner in current source is the
G5 fault-injection implementation.

Consequently, ordinary reobserve, reground, replan, verifier escalation, loop
detection, and safe abort are real, but provider/context/schema self-repair is
only an injectable protocol proof. It is not yet an end-to-end capability of
the normal runner.

### F-03 - The strict planner is becoming a policy concentration point

`GeneralistLMPlanner.propose()` currently combines terminal-readiness filtering,
active-subgoal scope, semantic text obligations, global ordinal/pagination
resolution, provider schema selection, model orchestration, bounded repair, and
trace projection. The code contains no MiniWoB task id, which is necessary but
insufficient evidence of generality.

The post-`c939051` repair stream repeatedly promoted benchmark-discovered
residuals into general semantic structures. Several structures are reasonable
generic abstractions, but they require independent non-BrowserGym held-out
evidence and must be consumed as typed constraints rather than accumulated as
new branches inside `propose()`.

### F-04 - Responsibility containment is a checkpoint, not closure

The Coordinator ratchet decreased and prevents new growth. That is useful.
Current measured surfaces remain:

~~~text
coordinator.py                  3,643 lines
RunCoordinator.run_sync()       2,098 lines
generalist_planner.py             880 lines
GeneralistLMPlanner.propose()      271 lines
task_planning.py                1,478 lines
~~~

The normative containment target is below 2,000 Coordinator lines first and
below 1,500 after the current extraction sequence. A test that freezes the
current ceiling proves non-expansion; it does not prove completed ownership.

### F-05 - Diagnostic improvement is non-monotonic

The first strict 30 x 2 diagnostic completed at 19/60. The later clean
`df5b820` diagnostic completed all 60 episodes at 24/60 with zero provider
failure, retry, missing episode, invalidation, or batch stop. This is meaningful
progress in collection and attribution.

It is not monotonic behavior progress. At least `text-transform` regressed from
2/2 to 0/2 and `enter-date` from 2/2 to 1/2 while other families improved. Any
future targeted repair must pass an explicit protected-family regression set
before a larger benchmark is authorized.

### F-06 - Status and evidence publication drift

At the audited `b01e73b` baseline, `implementation-status.md` still reported the
old 19/60 diagnostic while the current implementation plan reported 24/60.
This documentation change synchronizes the diagnostic and scoped M8.6 status,
but the newer report remains under a temporary path rather than a versioned
evidence directory. The latest 82 commits are also absent from origin.

Status, immutable evidence, branch identity, and remote reviewability must be
synchronized before any release or resume claim.

## 6. Substantive Completed Work

Retain the following implementation:

- unified DOM, accessibility, SVG/visual, SoM, WoT, and API candidate envelope;
- current snapshot, lease, target fingerprint, ActionContract, and preflight;
- independent post-action verification and criteria/evidence matching;
- typed TaskSpec, TaskPlan, PlanProgress, lineage, and bounded replacement;
- task-derived perception requirements, coherent epochs, evidence gaps, and
  budget-narrowing active perception;
- phase-general FailureEnvelope, RecoveryIncident, repeated/no-progress/A-B
  detection, uncertain-effect inspection, and bounded stop;
- declarative TaskSkill, RecoverySkill, policy/verifier artifacts, quarantine,
  replay, acceptance, rollback, and accepted-profile loading;
- complete-run benchmark accounting, immutable identities, failure clustering,
  and explicit non-promotion of historical scores;
- task-level API, external process boundary, and parent-agent integration.

## 7. Ordered Correction Plan

1. Freeze benchmark-family behavior changes and keep nightly/release held.
2. Add a provider-neutral `TaskObligationSpec` with source lineage, effect,
   typed value/data dependency, terminal relation, and evidence requirement.
3. Validate obligation coverage before `READY`; missing, cyclic, duplicate, or
   unsourced obligations produce repair, clarification, or unsupported status.
4. Compile both flat and dependent tasks into typed outcomes. Use the LLM task
   planner only where dependency or open-world decomposition is required.
5. Move terminal, semantic-value, ordinal, and current-state admission into a
   typed `DecisionConstraintSet`; the step planner consumes constraints and
   proposes one action rather than owning every semantic resolver.
6. Implement concrete context-compaction, schema-repair, and provider-switch
   owners and inject them into standalone and benchmark generalist entrypoints.
7. Continue Coordinator extraction without adding a second state writer: first
   contract lifecycle, recovery application, and task-plan commit preparation.
8. Run non-BrowserGym conformance across different layouts, applications, and
   effect classes before using any benchmark result as promotion evidence.
9. Restart the staged ladder at the original failure, then the relevant family,
   protected families, PR breadth, cross-family regression, and a fresh
   diagnostic. Nightly remains held until every preceding gate passes.
10. Store reports, traces, hashes, and exact run identity under a versioned
    repository evidence path; temporary directories are execution scratch only.
11. Synchronize a reviewable remote branch only after explicit user approval.
    Local gates are authoritative by default; do not spend GitHub Actions quota
    or push environment/secrets as an implicit implementation step.

## 8. Immediate Exit Contract

The next implementation slice is complete only when all of the following are
true:

1. raw-request compilation carries a sourced claim ledger and a typed
   `TaskObligationSpec` graph into immutable TaskSpec authority;
2. structural coverage is deterministic against that ledger, while unresolved
   natural-language semantic coverage fails closed or enters one bounded repair
   inside the existing total model-call/cost envelope;
3. duplicate, cyclic, unsourced, uncovered, stale, or invalid value-dependency
   graphs cannot produce `READY`;
4. TaskPlan outcomes retain obligation ids and verifier evidence can satisfy
   only the obligation it names;
5. `DecisionConstraintSet` is a typed, stateless owner outside
   `GeneralistLMPlanner.propose()` and no new semantic admission branch is added
   to that method;
6. Coordinator remains the sole state/trace writer and its 3643/26 ratchet does
   not grow;
7. direct, ordinary-form, derived read/write/submit, navigation-open,
   external-send, ambiguity, stale-lineage, and missing-evidence controls pass
   without BrowserGym task ids, URLs, selectors, coordinates, or suite grammar;
8. immutable local evidence is published before any remote review, benchmark
   breadth expansion, resume, nightly, release, or capability-completion claim.
