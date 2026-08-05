# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-05
> **Target architecture:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Active queue:** [Current Implementation Plan](current-implementation-plan.md)

## 1. Executive status

The Task Contract-centered target is **not implemented as a whole**. Current
production code contains substantial ActionContract, approval, preflight,
execution, observation, verification, recovery, trace, planner-request, and
Coordinator-containment foundations. P0-A completion authority, P0-B canonical
observation authority, P0-C Runtime-owned action space, and P0-E thin source /
single semantic admission are cut over. P0-E5 also replaces the flawed
"any material exact anchor" shortcut with effect-specific typed material
binding coverage. The broader compatibility TaskSpec shape and
TaskPlan/Subgoal/PlanProgress paths remain for later substitutive slices.

Documentation consolidation does not promote any production capability.

## 2. Current-vs-target matrix

| Area | Current implementation truth | Target | Status |
|---|---|---|---|
| Source intake | default path is SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpecAuthority; default SourceLedger/claim/obligation owners are deleted | lightweight SourceEnvelope + risk-proportionate MaterialBinding/selective SourceAnchor; optional SemanticAudit | P0-E complete |
| Semantic authority | TaskSpecAuthority is the only admission writer; bounded SourceContextView readers exist; execution consumers are denied source context; effect-specific material completeness is deterministic authority policy rather than audit/span inference | TaskSpecAuthority-only write barrier; bounded context-only readers; raw-text-free execution | P0-E complete; P3 canonical requirement binding remains |
| Task contract | TaskSpec now carries narrow typed success/output closure plus admitted P0-E5 material bindings and their digest; the broader extraction-era compatibility shape remains | stable canonical requirement identity plus authorization/constraint/forbidden-effect/success/output contract | P0-A/P0-E narrow fields implemented; P3 contract cutover pending |
| Task planning | legacy Step/Subgoal projections and obligation-shaped routing remain | observation-grounded replaceable TaskPlan<StepSpec> | pending cutover |
| Observation | PerceptionCapture is acquisition-only; CanonicalObservationBuilder deterministically retains targets, bindings, typed facts/conflicts and truthful source coverage; the shared in-process ObservationStore exposes immutable epoch refs/read-only indexes; default planning, action, post-action, targeted perception, progress and trace descriptors consume the canonical epoch | capture-built canonical observation is sole Runtime authority, exposed through immutable epoch refs/read-only indexes | P0-B complete |
| Cross-surface foundations | DOM/AX/Visual/SVG/WoT/API/Device enter one canonical epoch; semantic choices retain all non-conflicting bindings and ActionContractBuilder selects the current route | shared semantic target, surface-neutral Catalog, ActionContract route and LoopEvaluator | P0-B/P0-C complete; P1–P2 pending |
| Action choice | Runtime builds one logically full, deterministic eager/lazy/indexed Catalog before any model request; bounded ChoicePage and displayed-ID validation are separate owners | logical full Runtime Catalog before bounded semantic ChoicePage | P0-C complete |
| ActionContract and gates | selected choice, Catalog digest, canonical observation and current binding are sealed into ActionContract; ordered Task/Capability/Approval/Freshness admission is in-process and typed | retain and bind to canonical observation/catalog identity | P0-C complete; later policy matrix refinement pending |
| Execution | backend-neutral execution and typed receipts exist | Executor proves dispatch only | retain + narrow |
| Verification | mechanical verifier reports remain evidence providers; disabled verification is INCONCLUSIVE and receipt-only reports cannot complete a task; loop-wide evidence policy remains incomplete | loop-native typed evaluation with bounded evidence locations | P0-A completion cutover complete; P1/P2 evidence cutover pending |
| Task completion | full typed TaskSpec.success closure, declared constraints/effects, authoritative final rechecks and source-bound required outputs are evaluated by the pure TaskCompletionEvaluator; RuntimeCommitter is the sole TaskCompleted writer; latest-report, plan/prose and no-TaskSpec fallbacks are removed | pure TaskCompletionEvaluator + typed/source-bound required outputs + RuntimeCommitter-only commit | P0-A complete |
| Recovery | typed owner/router and bounded recovery foundations exist | typed causes, no generic-string ownership, no blind external retry | retain + refine |
| Trace/evaluation | trace, artifacts, benchmark reports and evidence records exist | offline consumers, never synchronous completion authority | retain |

## 3. Architecture coverage state

```yaml
authoritative_target: current_not_implemented_as_a_whole
active_step_order: canonical_observation_then_full_catalog_then_bounded_choice_page
cross_surface_foundations: existing_not_canonical_cutover
cross_surface_target: DOM_AX_Visual_SVG_WoT_API_Device
cross_surface_cutover: P0-B_P0-C_complete_P1_P2_pending
source_target: SourceEnvelope_plus_risk_proportionate_MaterialBinding_and_selective_SourceAnchor
semantic_audit: risk_triggered_veto_or_clarify_only
material_binding_policy: P0_E5_effect_specific_coverage_complete
exact_span_policy: indirect_unstructured_provenance_only
semantic_authority_boundary: P0_E_admission_and_read_set_cutover_complete_P3_requirement_binding_pending
semantic_context_visibility: bounded_context_only_allowlist
execution_raw_text_input: prohibited_target_not_cut_over
requirement_identity: target_not_implemented
dependency_model: typed_value_refs_plus_StepSpec_depends_on
choice_presentation_contract: canonical_P0_C_cutover_complete
catalog_physical_minimality: logical_eager_lazy_indexed_P0_C_complete
observation_indexed_epoch: canonical_P0_B_cutover_complete
authority_in_process_composition: shared_in_process_observation_store_complete
criterion_provider_phasing: target_not_implemented
typed_task_planner_trigger: target_not_implemented
risk_derived_feature_profiles: target_not_implemented
verification_shape: loop_native_typed_evaluation
task_completion_semantics: canonical_P0_A_cutover_complete
required_output_closure: narrow_typed_P0_A_complete_full_P3_contract_pending
task_completion_commit: RuntimeCommitter_only
evidence_locations: current_observation_plus_bounded_recent_ActionOutcome_plus_small_DurableEvidenceStore
source_invariants: SOU-01_through_SOU-12_plus_MAT-01_through_MAT-07
observation_invariants: OBS-01_through_OBS-14
verification_invariants: VER-01_through_VER-14
recovery_invariants: REC-01
semantic_authority_invariants: NLI-01_through_NLI-08
requirement_invariants: REQ-01_through_REQ-05
dependency_invariants: DEP-01_through_DEP-03
choice_invariants: CHOICE-13
output_invariants: OUT-01_through_OUT-03
physical_minimality_invariants: CAT-PHY-01_OBS-PHY-01_AUTH-PHY-01_CRIT-PHY-01_PLAN-PHY-01_PROFILE-01
cross_surface_invariants: SURFACE-01_through_SURFACE-03
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
| production behavior change | P0-A completion, P0-B canonical observation, P0-C Runtime action-space, P0-E thin-source/single-admission, and P0-D compact redlines are complete; P1 and later slices remain pending |

## 6. Historical ledger

The complete pre-consolidation 1,582-line ledger is preserved at
[implementation-status-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/implementation-status-pre-consolidation.md).
Individual claims remain attributable through evidence and change-admission
records; the snapshot is not a current status source.
