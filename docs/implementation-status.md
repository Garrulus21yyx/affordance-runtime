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
planning/port core is cut over: rolling task planning and closed step choice are separate
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
strength and assurance are authoritative.
The strict Catalog now admits only choices whose Runtime-derived concrete
`RuntimeEffectSignature` is ALLOWed by a typed `EffectAuthorizationScope`.
Named parameters, canonical resources/destinations, externality,
reversibility, source assurance and the multidimensional risk vector are sealed
in a versioned `ActionAuthorityProof`. Contract construction reclassifies the
selected route and the Task Gate independently reauthorizes the actual grounded
transaction. The high-risk matrix enforces effect-specific material fields,
capability, exact approval, authoritative preflight and causal/final recheck
criteria. P4-G is therefore cut over, with P5 now next. A Runtime-registered API final-recheck provider closes the approved
reference export path; ordinary strong HTTP evidence remains non-authoritative. P1 is
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
- P4 rolling planning and strict step-choice port: **COMPLETE**
- P4-G concrete action authority/high-risk governance: **COMPLETE**
- P5 bounded state and final compatibility deletion: **NOT STARTED; NEXT**

Documentation consolidation does not promote any production capability.

### 1.1 P4-G redline closure

The four negative probes that blocked the interim `8b91944` implementation now
close at the typed authority boundary:

| Probe | Current result | Closure owner |
|---|---|---|
| NAVIGATION TaskSpec + exact target + TYPE_TEXT choice | DENY | exact typed operation/effect subsumption |
| admitted `recipient=Alice, amount=100` + swapped concrete fields | DENY | named parameter authorization |
| uninstrumented DOM `Delete account` button | UNPROVEN | Runtime classification and source-assurance policy |
| valid Alice choice but actual affordance/locator targets Bob | DENY | route-specific signature plus Task Gate reauthorization |
| approval followed by a changed observation epoch | token rejected; contract must be rebuilt and reapproved | snapshot/page/environment-bound approval plus full Task/Freshness revalidation |
| public approval of H1 followed by a rebuilt H2 | H1 grant cannot issue an H2 token; a new pending request is returned | typed external pending request plus paused-run continuation |
| `REVERSIBLE_WRITE` proposal carrying `message.send@v1` | admission rejected | canonical effect-scope risk and closure validation |
| material source conflict with non-magic reason text | UNPROVEN | typed `ChoiceRejection.status` |

The implementation keeps the two contracts deliberately distinct and joins
them only through the versioned tri-state proof; no label-keyword, risk-string
or test-specific action-enum fallback remains on the canonical path.

## 2. Current-vs-target matrix

| Area | Current implementation truth | Target | Status |
|---|---|---|---|
| Source intake | default path is SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpecAuthority; default SourceLedger/claim/obligation owners are deleted | lightweight SourceEnvelope + risk-proportionate MaterialBinding/selective SourceAnchor; optional SemanticAudit | P0-E complete |
| Semantic authority | TaskSpecAuthority is the only canonical admission writer; `AdmittedTaskSpec` is an in-process object capability binding the exact TaskSpec, SourceEnvelope identity and revision predecessor; RunRequest and TaskRequest require that capability and have no goal-only branch; raw external `UserTaskSubmission` is admitted server-side before Runtime construction; the private P5-3 TaskSpec wrapper and explicitly named legacy request adapter are import-gated to compatibility profiles; execution consumers are denied source context | TaskSpecAuthority-only write barrier; bounded context-only readers; raw-text-free execution | P0-E/P3 complete |
| Task contract | TaskSpec v2 carries flat typed requirements, stable input bindings, fully covered authorization/constraint/preference/forbidden refs, capability ceiling, risk policy and source-bound outputs; typed success leaves carry CriterionPolicy; admission derives high-risk status from canonical `EffectAuthorizationScope`/operation semantics, rejects aggregate-operation downgrades, and requires operation-specific material fields/capability plus distinct allowed-effect-bound ACTION_CAUSED/RECENT_ACTION and AUTHORITATIVE/FINAL_RECHECK leaves; construction failures become typed issues; completion accepts a leaf result only after evidence satisfies that exact policy and the evaluation carries its criterion-bound policy digest; CURRENT_OBSERVATION never survives an epoch change, RECENT_ACTION is re-admitted only from the bounded Runtime outcome index, and DURABLE is re-admitted only from DurableEvidenceStore; accepted `semantic_value_constraints` and evidence-description fields are absent; every output requirement has exactly one required OutputSpec | stable canonical requirement identity plus authorization/constraint/forbidden-effect/success/output contract | P3 complete |
| Task planning | canonical TaskPlan stores StepSpec directly; TaskPlanAuthority alone validates current observation/state basis and binds identity/version/supersession; TaskPlanningRequest → PlanProposal is typed and rolling triggers distinguish initial, reuse, exhausted, infeasible, assumption, environment and task-revision cases; default composition and PlanningStage contain no legacy Planner proposal fallback | observation-grounded replaceable TaskPlan<StepSpec> | P1-1/P1-2 plus P4 complete |
| Task progress | facts, bindings, bounded recent outcome refs, durable evidence refs and VerifiedStepRecord survive replacement without reinserting completed steps | progress is factual state, not a second plan owner | P1-P3 complete |
| Observation | PerceptionCapture is acquisition-only; CanonicalObservationBuilder deterministically retains targets, bindings, typed facts/conflicts and truthful source coverage; the shared in-process ObservationStore exposes immutable epoch refs/read-only indexes; default planning, action, post-action, targeted perception, progress and trace descriptors consume the canonical epoch | capture-built canonical observation is sole Runtime authority, exposed through immutable epoch refs/read-only indexes | P0-B complete |
| Cross-surface foundations | DOM/AX/Visual/SVG/WoT/API/Device enter one canonical epoch; semantic choices retain all non-conflicting bindings, ActionContractBuilder selects the current route, and causal step evidence retains its actual subject/value/source/assurance | shared semantic target, surface-neutral Catalog, ActionContract route and LoopEvaluator | P0-B/P0-C/P1 plus P2 canonical step-completion cutover complete |
| Action choice | Runtime builds the logical Catalog before model projection and StepChoiceFlow owns deterministic 0/1/N/hidden-ID behavior. A pure typed subsumption evaluator compares exact operation/effect, canonical resource/destination, named parameters, externality/reversibility, assurance, capability ceiling and multidimensional risk; Catalog admits ALLOW only and preserves `AuthorityStatus` plus typed reason tuples for DENY/UNPROVEN rejection reports; callers never infer status from reason text | `EffectAuthorizationScope ⊒ RuntimeEffectSignature → ALLOW/DENY/UNPROVEN`; Catalog admits ALLOW only; Text/VLM is raise-only | P0-C/P4/P4-G complete |
| ActionContract and gates | selected choice, Catalog/observation refs, route-specific signature and versioned proof are sealed into the contract hash; internal and public approval are contract-hash/snapshot/page/environment/capability bound and present operation/resource/destination/material parameters/risk/reversibility/backend/source uncertainty. The task API exposes an expiring `PendingApprovalRequest` and accepts only its exact ID/hash; Local execution preserves the paused contract/session, while lost continuation or rebuild returns a new request instead of converting approval to a Boolean capability grant. Approval revalidation keeps the same epoch and reruns Task Authority plus Capability/Approval/Freshness. Task Gate rebuilds authority from TaskSpec, current observation and the actual transaction | route-specific Runtime signature + versioned proof + actual binding in contract hash; independent Task Gate reauthorization | P0-C/P4-G complete |
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
execution_raw_text_input: prohibited_cutover_complete
requirement_identity: canonical_TaskRequirement_and_StepSpec_traceability_complete
dependency_model: typed_value_refs_plus_StepSpec_depends_on
choice_presentation_contract: canonical_P0_C_cutover_complete
effect_authorization_scope: task_spec_typed_scope_complete_P4_G
runtime_effect_signature: actual_candidate_backend_binding_complete_P4_G
concrete_effect_authority: typed_subsumption_and_versioned_proof_complete_P4_G
action_authority_decision: ALLOW_DENY_UNPROVEN_complete_P4_G
runtime_risk_policy: conservative_multidimensional_max_and_text_VLM_raise_only_complete_P4_G
task_gate_actual_binding_revalidation: complete_P4_G
high_risk_action_governance: exact_material_capability_approval_preflight_causal_final_recheck_complete_P4_G
catalog_physical_minimality: logical_full_membership_P0_C_complete_physical_lazy_indexed_deferred_P5_4
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
concrete_action_authority_invariants: AUTHZ-01_through_AUTHZ-10_plus_HRA-01_through_HRA-03_complete_P4_G
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
| production behavior change | P0-A/B/C/D/E/E5, all P1 rows, P2 core, P3, P4 planning/port core and P4-G typed concrete action authority/high-risk governance are complete; P2-6/full P2-7 remain demand-driven and P5 is next |

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

P4-G moved semantic generation and typed authority into focused builder,
generation-support and policy modules; `action_choice_catalog.py` now retains
membership/digest/query ownership. Remaining production containment debt is
separately queued at `P5-4`: `execution_phase.py` is currently 1,142 lines and strict
`browsergym_episode_runner.py` is 1,082 lines after legacy extraction; both must
be split by responsibility without changing P4's completed planning boundary.

## 6. Historical ledger

The complete pre-consolidation 1,582-line ledger is preserved at
[implementation-status-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/implementation-status-pre-consolidation.md).
Individual claims remain attributable through evidence and change-admission
records; the snapshot is not a current status source.
