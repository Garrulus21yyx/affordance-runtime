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
binding coverage. P3 is now cut over: TaskSpec v2 owns flat admitted
requirements, stable input bindings, authorization/constraint/preference refs,
risk policy and source-bound outputs. A typed success root is mandatory, each
criterion leaf cites exact admitted requirement IDs plus typed CriterionPolicy,
semantic value constraints are canonical constraint requirements, and every requested output
enters completion through one required OutputSpec; StepSpec traceability is enforced and the
legacy claim/obligation owners and task-plan provider adapter are deleted. P4
is also cut over: rolling task planning and closed step choice are separate
typed flows, strict providers receive only bounded typed requests, pure
serializers expose only admitted/displayed IDs, and explicit triggers reuse an
active feasible plan without calling the task planner. Default composition no
longer accepts or discovers a legacy Planner, `PlanningStage` has no proposal
fallback, and strict BrowserGym constructs the strict task and choice providers
directly. Canonical Runtime and Task API entrypoints accept only the
Authority-issued `AdmittedTaskSpec` object capability, whose source identity and
revision predecessor are fixed at admission; neither canonical type contains a
goal-only/no-TaskSpec branch and no process-global receipt registry remains. Raw
external submissions enter a separate `UserTaskSubmission` boundary and are
admitted by the server-side TaskSpecAuthority before Runtime construction.
Success evidence is admitted against each leaf's exact policy and bound back to
that policy digest before tree evaluation. Completion is recomputed each epoch
from current, bounded recent-action and admitted durable evidence; no retained
CriterionEvaluation cache acts as a second authority. Causal, final-recheck and
canonical resource-version authority comes from Runtime-owned
contract/outcome/report/fact state, never observation metadata. BrowserGym
official reward remains an independent benchmark evaluation and is never copied
into Runtime success criteria. High-risk admission requires distinct
allowed-effect-bound external ACTION_CAUSED/RECENT_ACTION and authoritative
FINAL_RECHECK success leaves. Invalid canonical construction becomes a typed
admission issue, and Runtime accepts final-recheck identity only when source,
strength and assurance are authoritative. P1 is
now cut over: accepted plans store StepSpec directly, TaskPlanAuthority is the
single plan admission/version owner, TaskProgress is step/fact/evidence based,
LoopEvaluator owns typed loop evaluation and perception owns four-state
continuation. P1-C1/P1-C2 closure is complete: RecoveryStage and its pure
evaluators own classification, handoff and recovery-outcome policy;
RuntimeCommitSession owns lifecycle only; RuntimeCommitter applies already
evaluated typed transitions/events/completion. The legacy Runtime planning
owner was deleted, leaving only a named one-way external provider adapter.
The P2 canonical mechanical **step-completion core** is complete: typed
criterion policy and recursive evaluation own production step completion, while current,
recent-causal and durable evidence have distinct bounded lifetimes. `StepSpec`
is a strict canonical owner and rejects legacy criteria; dated providers and
benchmarks canonicalize before construction. Optional model/human evidence
(`P2-6`) and the full `OpenSemanticResolver` (`P2-7`) remain demand-driven
extensions, with fail-closed unresolved routing already present.

- P2 mandatory runtime closure: **COMPLETE**
- P2-6 optional extension: **DEFERRED**
- P2-7 resolver capability: **DEMAND-GATED**
- P2-7 unresolved fail-closed routing: **COMPLETE**
- P3 canonical TaskSpec v2 cutover: **COMPLETE**
- P4 rolling planning and strict step choice: **COMPLETE**
- P5 bounded state and final compatibility deletion: **NOT STARTED**

Documentation consolidation does not promote any production capability.

## 2. Current-vs-target matrix

| Area | Current implementation truth | Target | Status |
|---|---|---|---|
| Source intake | default path is SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpecAuthority; default SourceLedger/claim/obligation owners are deleted | lightweight SourceEnvelope + risk-proportionate MaterialBinding/selective SourceAnchor; optional SemanticAudit | P0-E complete |
| Semantic authority | TaskSpecAuthority is the only canonical admission writer; `AdmittedTaskSpec` is an in-process object capability binding the exact TaskSpec, SourceEnvelope identity and revision predecessor; RunRequest and TaskRequest require that capability and have no goal-only branch; raw external `UserTaskSubmission` is admitted server-side before Runtime construction; the private P5-3 TaskSpec wrapper and explicitly named legacy request adapter are import-gated to compatibility profiles; execution consumers are denied source context | TaskSpecAuthority-only write barrier; bounded context-only readers; raw-text-free execution | P0-E/P3 complete |
| Task contract | TaskSpec v2 carries flat typed requirements, stable input bindings, fully covered authorization/constraint/preference/forbidden refs, capability ceiling, risk policy and source-bound outputs; typed success leaves carry CriterionPolicy; high-risk admission requires distinct allowed-effect-bound ACTION_CAUSED/RECENT_ACTION and AUTHORITATIVE/FINAL_RECHECK leaves and converts construction failures to typed issues; completion accepts a leaf result only after evidence satisfies that exact policy and the evaluation carries its criterion-bound policy digest; CURRENT_OBSERVATION never survives an epoch change, RECENT_ACTION is re-admitted only from the bounded Runtime outcome index, and DURABLE is re-admitted only from DurableEvidenceStore; accepted `semantic_value_constraints` and evidence-description fields are absent; every output requirement has exactly one required OutputSpec | stable canonical requirement identity plus authorization/constraint/forbidden-effect/success/output contract | P3 complete |
| Task planning | canonical TaskPlan stores StepSpec directly; TaskPlanAuthority alone validates current observation/state basis and binds identity/version/supersession; TaskPlanningRequest → PlanProposal is typed and rolling triggers distinguish initial, reuse, exhausted, infeasible, assumption, environment and task-revision cases; default composition and PlanningStage contain no legacy Planner proposal fallback | observation-grounded replaceable TaskPlan<StepSpec> | P1-P1/P1-P2 plus P4 complete |
| Task progress | facts, bindings, bounded recent outcome refs, durable evidence refs and VerifiedStepRecord survive replacement without reinserting completed steps | progress is factual state, not a second plan owner | P1-P3 complete |
| Observation | PerceptionCapture is acquisition-only; CanonicalObservationBuilder deterministically retains targets, bindings, typed facts/conflicts and truthful source coverage; the shared in-process ObservationStore exposes immutable epoch refs/read-only indexes; default planning, action, post-action, targeted perception, progress and trace descriptors consume the canonical epoch | capture-built canonical observation is sole Runtime authority, exposed through immutable epoch refs/read-only indexes | P0-B complete |
| Cross-surface foundations | DOM/AX/Visual/SVG/WoT/API/Device enter one canonical epoch; semantic choices retain all non-conflicting bindings, ActionContractBuilder selects the current route, and causal step evidence retains its actual subject/value/source/assurance | shared semantic target, surface-neutral Catalog, ActionContract route and LoopEvaluator | P0-B/P0-C/P1 plus P2 canonical step-completion cutover complete |
| Action choice | Runtime builds one logically full, deterministic eager/lazy/indexed Catalog before any model request; StepChoiceFlow receives a bounded ChoicePlanningRequest, handles deterministic 0/1/N selection, rejects hidden IDs and fails closed on an oversized truncated page | logical full Runtime Catalog before bounded semantic ChoicePage | P0-C plus P4 complete |
| ActionContract and gates | selected choice, Catalog digest, canonical observation and current binding are sealed into ActionContract; ordered Task/Capability/Approval/Freshness admission is in-process and typed | retain and bind to canonical observation/catalog identity | P0-C complete; later policy matrix refinement pending |
| Execution | backend-neutral execution and typed receipts exist | Executor proves dispatch only | retain + narrow |
| Verification | `LoopEvaluator` feeds canonical observation, current contract, bounded lossless recent outcomes, durable evidence, latest final-recheck identity and resource versions directly to `PredicateEvaluator`; resource versions are derived from canonical target/fact content; Task completion uses the same Runtime-owned context and is recomputed without a CriterionEvaluation cache; observation metadata cannot assert causal lineage, durable admission, final-recheck authority or resource versions; action effect and TaskSpec completion retain their earlier owners | loop-native typed step evaluation with bounded evidence locations | P2 mandatory runtime closure complete; P2-6 deferred and P2-7 resolver demand-gated |
| Criterion contracts | canonical immutable Predicate/AllOf/AnyOf/Not/OpenSemantic AST and orthogonal satisfaction/validity/assurance policy are implemented; strict `StepSpec` accepts only canonical `CriterionExpr`, while legacy providers/benchmarks canonicalize at ingress; unresolved OpenSemantic routes to a typed clarification gap | one typed criterion vocabulary independent of provider coverage | P2-1/P2-2 core complete; P2-7 full resolver demand-driven |
| Evidence providers | shared mechanical contract groups structural DOM/AX/Visual/SVG, resource API/WoT/Device/transaction and artifact/file/materialization facts; unknown surfaces are not treated as DOM and bare artifact refs are not integrity proofs | focused fact providers feeding pure predicate evaluation | P2-5 complete; P2-6 model/human expansion deferred |
| Evidence lifetimes | current facts are epoch refs; exact current-contract/receipt/pre/post/effect lineage is retained in a 40-record recent index; final rechecks bind latest identity/current epoch/resource version; only explicitly durable records enter a bounded durable store | CurrentObservation + RecentActionOutcome + DurableEvidence | P2-3/P2-4 complete and production-wired |
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
cross_surface_cutover: P0_B_P0_C_P1_plus_P2_canonical_step_completion_complete
source_target: SourceEnvelope_plus_risk_proportionate_MaterialBinding_and_selective_SourceAnchor
semantic_audit: risk_triggered_veto_or_clarify_only
material_binding_policy: P0_E5_effect_specific_coverage_complete
exact_span_policy: indirect_unstructured_provenance_only
semantic_authority_boundary: P0_E_admission_and_P3_ID_bound_read_set_cutover_complete
semantic_context_visibility: bounded_context_only_allowlist
execution_raw_text_input: prohibited_target_not_cut_over
requirement_identity: canonical_TaskRequirement_and_StepSpec_traceability_complete
dependency_model: typed_value_refs_plus_StepSpec_depends_on
choice_presentation_contract: canonical_P0_C_cutover_complete
catalog_physical_minimality: logical_eager_lazy_indexed_P0_C_complete
observation_indexed_epoch: canonical_P0_B_cutover_complete
authority_in_process_composition: shared_in_process_observation_store_complete
criterion_provider_phasing: P2_step_P2_1_through_P2_5_complete_P2_6_deferred_P2_7_resolver_pending
typed_task_planner_trigger: P4_typed_trigger_reuse_and_strict_provider_cutover_complete
risk_derived_feature_profiles: target_not_implemented
verification_shape: P2_typed_policy_predicates_and_mechanical_provider_matrix_complete
task_completion_semantics: canonical_P0_A_cutover_complete
required_output_closure: P3_source_bound_output_contract_complete
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
| production behavior change | P0-A/B/C/D/E/E5, all P1 rows, P2 core (P2-1..P2-5), P3 and P4 are complete; TaskSpec v2 and StepSpec requirement/effect traceability are canonical, rolling task planning and strict closed step choice are cut over, and legacy internal planner signatures are deleted; P2-6 and the full P2-7 resolver remain demand-driven extensions; P5 is not started |

The remaining planner compatibility debt is explicit and bounded:
`generalist_planner.py`, `compatibility_planner_algorithms.py`, their one-way
`planner_context.py` projection, the public `BrowserGymGeneralistPlanner`, the
non-strict BrowserGym benchmark façade and the isolated
`browsergym_compatibility_episode.py` path, and the corresponding CLI
benchmark command remain compatibility consumers. The historical generalization
comparison is an additional consumer. None is imported by strict/default Runtime
composition or the strict BrowserGym path; the full consumer inventory expires
at `P5-3`.

The private `_admit_legacy_task_spec` wrapper and named `legacy_run_request`
bridge are also P5-3 debt. An architecture gate permits the private wrapper to
be imported only by `runtime.py` and inventories every production compatibility
profile that may import `legacy_run_request`; canonical pipeline, external
submission, strict BrowserGym, RunRequest and TaskRequest do not accept a raw
TaskSpec or a missing admitted task.

The remaining production containment debt is separately queued at `P5-4`:
`execution_phase.py` is currently 1,142 lines and strict
`browsergym_episode_runner.py` is 1,082 lines after legacy extraction; both must
be split by responsibility without changing P4's completed planning boundary.

## 6. Historical ledger

The complete pre-consolidation 1,582-line ledger is preserved at
[implementation-status-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/implementation-status-pre-consolidation.md).
Individual claims remain attributable through evidence and change-admission
records; the snapshot is not a current status source.
