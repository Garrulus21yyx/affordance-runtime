# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-06
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
external model-provider wire shape remain for later substitutive slices. P1 is
now cut over: accepted plans store StepSpec directly, TaskPlanAuthority is the
single plan admission/version owner, TaskProgress is step/fact/evidence based,
LoopEvaluator owns typed loop evaluation and perception owns four-state
continuation. P1-C1/P1-C2 closure is complete: RecoveryStage and its pure
evaluators own classification, handoff and recovery-outcome policy;
RuntimeCommitSession owns lifecycle only; RuntimeCommitter applies already
evaluated typed transitions/events/completion. The legacy Runtime planning
owner was deleted, leaving only a named one-way external provider adapter.
P2-1/P2-2/P2-3 are now cut over: canonical typed criterion policy and recursive
evaluation feed three mechanical provider groups, while current, recent-causal
and durable evidence have distinct bounded lifetimes. P2-4 remains deferred;
no model/human fallback provider was added.

Documentation consolidation does not promote any production capability.

## 2. Current-vs-target matrix

| Area | Current implementation truth | Target | Status |
|---|---|---|---|
| Source intake | default path is SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpecAuthority; default SourceLedger/claim/obligation owners are deleted | lightweight SourceEnvelope + risk-proportionate MaterialBinding/selective SourceAnchor; optional SemanticAudit | P0-E complete |
| Semantic authority | TaskSpecAuthority is the only admission writer; bounded SourceContextView readers exist; execution consumers are denied source context; effect-specific material completeness is deterministic authority policy rather than audit/span inference | TaskSpecAuthority-only write barrier; bounded context-only readers; raw-text-free execution | P0-E complete; P3 canonical requirement binding remains |
| Task contract | TaskSpec now carries narrow typed success/output closure plus admitted P0-E5 material bindings and their digest; the broader extraction-era compatibility shape remains | stable canonical requirement identity plus authorization/constraint/forbidden-effect/success/output contract | P0-A/P0-E narrow fields implemented; P3 contract cutover pending |
| Task planning | canonical TaskPlan stores StepSpec directly; TaskPlanAuthority alone validates current observation/state basis and binds identity/version/supersession; planner policy emits authority-free PlanCandidate | observation-grounded replaceable TaskPlan<StepSpec> | P1-P1/P1-P2 complete |
| Task progress | facts, bindings, bounded recent outcome refs, durable evidence refs and VerifiedStepRecord survive replacement without reinserting completed steps | progress is factual state, not a second plan owner | P1-P3 complete |
| Observation | PerceptionCapture is acquisition-only; CanonicalObservationBuilder deterministically retains targets, bindings, typed facts/conflicts and truthful source coverage; the shared in-process ObservationStore exposes immutable epoch refs/read-only indexes; default planning, action, post-action, targeted perception, progress and trace descriptors consume the canonical epoch | capture-built canonical observation is sole Runtime authority, exposed through immutable epoch refs/read-only indexes | P0-B complete |
| Cross-surface foundations | DOM/AX/Visual/SVG/WoT/API/Device enter one canonical epoch; semantic choices retain all non-conflicting bindings, ActionContractBuilder selects the current route and mechanical evidence is grouped by structural/resource/artifact responsibility | shared semantic target, surface-neutral Catalog, ActionContract route and LoopEvaluator | P0-B/P0-C/P1/P2 mechanical baseline complete |
| Action choice | Runtime builds one logically full, deterministic eager/lazy/indexed Catalog before any model request; bounded ChoicePage and displayed-ID validation are separate owners | logical full Runtime Catalog before bounded semantic ChoicePage | P0-C complete |
| ActionContract and gates | selected choice, Catalog digest, canonical observation and current binding are sealed into ActionContract; ordered Task/Capability/Approval/Freshness admission is in-process and typed | retain and bind to canonical observation/catalog identity | P0-C complete; later policy matrix refinement pending |
| Execution | backend-neutral execution and typed receipts exist | Executor proves dispatch only | retain + narrow |
| Verification | mechanical verifier facts feed typed predicate/composite evaluation; pure LoopEvaluator separates action effect, active-step completion, triggered task completion and continuation; disabled verification, receipt-only and unsupported operators cannot complete a step/task | loop-native typed evaluation with bounded evidence locations | P0-A/P1-E1 and P2-1/P2-2 complete; P2-4 deferred |
| Criterion contracts | canonical immutable Predicate/AllOf/AnyOf/Not/OpenSemantic AST and orthogonal satisfaction/validity/assurance policy are implemented; registered vocabulary without mechanical coverage returns UNSUPPORTED | one typed criterion vocabulary independent of provider coverage | P2-1 complete |
| Evidence providers | shared mechanical contract groups structural DOM/AX/Visual/SVG, resource API/WoT/Device/transaction and artifact/file/materialization facts; providers do not evaluate task completion or mutate state | focused fact providers feeding pure predicate evaluation | P2-2 complete; P2-4 model/human expansion deferred |
| Evidence lifetimes | current facts are epoch refs; exact contract/receipt/pre/post/effect lineage is retained in a 40-record recent index; only explicitly durable artifact/resource/transaction/human records enter a bounded durable store | CurrentObservation + RecentActionOutcome + DurableEvidence | P2-3 complete |
| Task completion | full typed TaskSpec.success closure, declared constraints/effects, authoritative final rechecks and source-bound required outputs are evaluated by the pure TaskCompletionEvaluator; RuntimeCommitter is the sole TaskCompleted writer; latest-report, plan/prose and no-TaskSpec fallbacks are removed | pure TaskCompletionEvaluator + typed/source-bound required outputs + RuntimeCommitter-only commit | P0-A complete |
| Observation continuation | perception owner returns REUSE, AUGMENT_TARGETED, RECAPTURE or WAIT_AND_RECAPTURE from freshness/stability/coverage/conflict; fresh reusable capture is not immediately duplicated | typed continuation proposal outside Coordinator/Committer | P1-E2 complete |
| Recovery | RecoveryStage owns typed classification, handoff/exhaustion/error mapping and strategy choice; RecoveryObservationEvaluator and RecoveryActionEvaluator settle typed outcomes; Coordinator and RuntimeCommitSession only follow results | typed causes, no generic-string ownership, no blind external retry | P1-C1 complete |
| Runtime commit/control | RuntimeCommitSession owns lifecycle, read projections stay separate, and RuntimeCommitter only validates/applies typed transitions/events/completion | orchestration and commit authority separated from domain evaluation | P1-C2 complete |
| Trace/evaluation | trace, artifacts, benchmark reports and evidence records exist | offline consumers, never synchronous completion authority | retain |

## 3. Architecture coverage state

```yaml
authoritative_target: current_not_implemented_as_a_whole
active_step_order: canonical_observation_then_full_catalog_then_bounded_choice_page
cross_surface_foundations: existing_not_canonical_cutover
cross_surface_target: DOM_AX_Visual_SVG_WoT_API_Device
cross_surface_cutover: P0_B_P0_C_P1_P2_mechanical_baseline_complete
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
criterion_provider_phasing: P2_mechanical_baseline_complete_P2_4_deferred
typed_task_planner_trigger: P1_canonical_plan_candidate_and_authority_complete
risk_derived_feature_profiles: target_not_implemented
verification_shape: P2_typed_policy_predicates_and_mechanical_provider_matrix_complete
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
| production behavior change | P0-A/B/C/D/E/E5, all P1 rows and P2-1/P2-2/P2-3 are complete; P2-4 remains deferred; the external provider `subgoals` wire adapter remains isolated and expires at P3-4; P3/P4/P5 have not started |

## 6. Historical ledger

The complete pre-consolidation 1,582-line ledger is preserved at
[implementation-status-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/implementation-status-pre-consolidation.md).
Individual claims remain attributable through evidence and change-admission
records; the snapshot is not a current status source.
