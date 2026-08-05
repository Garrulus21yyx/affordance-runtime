# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-05
> **Target architecture:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Active queue:** [Current Implementation Plan](current-implementation-plan.md)

## 1. Executive status

The Task Contract-centered target is **not implemented as a whole**. Current
production code contains substantial ActionContract, approval, preflight,
execution, observation, verification, recovery, trace, planner-request, and
Coordinator-containment foundations. It also retains legacy source, TaskSpec,
TaskPlan/Subgoal/PlanProgress, action-choice, and completion paths that the new
evolution plan explicitly replaces.

Documentation consolidation does not promote any production capability.

## 2. Current-vs-target matrix

| Area | Current implementation truth | Target | Status |
|---|---|---|---|
| Source intake | heavy SourceLedger/clause/claim/obligation compatibility remains on default paths | lightweight SourceEnvelope + selective SourceAnchor; optional SemanticAudit | pending cutover |
| Task contract | TaskSpec still carries extraction-era execution/provenance fields | stable authorization/constraint/forbidden-effect/success contract | pending cutover |
| Task planning | legacy Step/Subgoal projections and obligation-shaped routing remain | observation-grounded replaceable TaskPlan<StepSpec> | pending cutover |
| Observation | UnifiedObservation foundation exists; presentation-derived paths remain | capture-built canonical observation is sole Runtime authority | pending cutover |
| Action choice | typed ActionChoice foundations exist; ownership/order still has compatibility paths | full Runtime Catalog before bounded ChoicePage | pending cutover |
| ActionContract and gates | versioning, authorization, capability, approval, preflight and stale checks have substantive foundations | retain and bind to canonical observation/catalog identity | retain + harden |
| Execution | backend-neutral execution and typed receipts exist | Executor proves dispatch only | retain + narrow |
| Verification | mechanical verifiers and typed reports exist; legacy Boolean/latest-report/fallback surfaces remain | loop-native typed evaluation with bounded evidence locations | pending cutover |
| Task completion | centralized success commit foundations exist; full TaskSpec.success closure is not the sole default authority | pure TaskCompletionEvaluator + RuntimeCommitter-only commit | P0-A pending |
| Recovery | typed owner/router and bounded recovery foundations exist | typed causes, no generic-string ownership, no blind external retry | retain + refine |
| Trace/evaluation | trace, artifacts, benchmark reports and evidence records exist | offline consumers, never synchronous completion authority | retain |

## 3. Architecture coverage state

```yaml
authoritative_target: current_not_implemented_as_a_whole
active_step_order: canonical_observation_then_full_catalog_then_bounded_choice_page
source_target: SourceEnvelope_plus_selective_SourceAnchor
semantic_audit: risk_triggered_veto_or_clarify_only
verification_shape: loop_native_typed_evaluation
task_completion_semantics: TaskCompletionEvaluator
task_completion_commit: RuntimeCommitter_only
evidence_locations: current_observation_plus_bounded_recent_ActionOutcome_plus_small_DurableEvidenceStore
source_invariants: SOU-01_through_SOU-12
observation_invariants: OBS-01_through_OBS-14
verification_invariants: VER-01_through_VER-14
recovery_invariants: REC-01
```

## 4. Evidence and promotion

- Git owns the exact current repository revision; this file does not self-record HEAD.
- Historical implementation and behavioral evidence remains under `docs/evidence/`.
- Change-admission decisions remain under `docs/change-admission/`.
- Historical local pass results do not imply current remote CI or promotion.
- Remote CI is intentionally disabled for the recorded iteration.
- Promotion remains held until the relevant architecture slice, behavior suite,
  safety suite, and breadth evidence pass at the same immutable revision.

## 5. Current documentation state

| Item | State |
|---|---|
| authoritative architecture/evolution plan | current |
| documentation manifest/governance | current |
| superseded prose/plans/audits | archived and indexed |
| maintained contract synchronization | complete for the 2026-08-05 authority baseline |
| simple documentation gate | active: lifecycle/path coverage, authority uniqueness, redirects, maintained links |
| production behavior change from this documentation slice | none |

## 6. Historical ledger

The complete pre-consolidation 1,582-line ledger is preserved at
[implementation-status-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/implementation-status-pre-consolidation.md).
Individual claims remain attributable through evidence and change-admission
records; the snapshot is not a current status source.
