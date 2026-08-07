# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-07
> **P4:** CLOSED (MVP scope)
> **Target architecture:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Active queue:** [Current Implementation Plan](current-implementation-plan.md)

## 1. Executive status

The Task Contract-centered target is **not implemented as a whole**. Current
production code contains substantial ActionContract, approval, preflight,
execution, observation, verification, recovery, trace, planner-request, and
Coordinator-containment foundations. The P0-A recursive-completion and
RuntimeCommitter-only-write core, P0-B canonical-observation owner, P0-C
Runtime-owned action space, and P0-E thin source / single semantic admission are
cut over. P4-C1 closes the MVP output/receipt fail-open: required local artifacts
must resolve and match their digest, and receipt alone cannot complete. Broader
adapter-owned `SourceCoverage` remains non-blocking breadth work. P0-E5 also replaces the flawed
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
The strict Catalog foundation now admits only choices whose Runtime-derived
concrete `RuntimeEffectSignature` is ALLOWed by a typed
`EffectAuthorizationScope`. Named parameters, canonical
resources/destinations, externality, reversibility, source assurance and the
multidimensional risk vector are represented in versioned proof contracts.
The 2026-08-07 MVP scope reset implements the five applicable P4 code invariants:
product rejection paths make zero Executor calls; required local artifacts must
exist and match their digest; receipt alone cannot complete; the final contract
is materialized before approval and its hash is identical at approval, attempt,
Executor and execution; and uncertain effects are not blindly retried. Default
composition uses the canonical materializer. The latest full pytest/static
checks, all three stable Task API scenarios, and the complete 21-run fixture
v2.1.0 core benchmark pass with `acceptance_errors=[]`. BenchmarkReport now
fails closed on missing required variants, invalid opportunity denominators, or
missing expected trace evidence. The benchmark is integrated closure evidence
for the same five invariants and the default-route cutover, not a sixth
invariant. The result is **P4 CLOSED (MVP scope)**; P5 admission is unblocked,
but P5 has not started. The approved export requires a typed OutputSpec, receipt
plus Runtime-registered authoritative API final evidence, and a SHA-bound local
file before `TaskCompleted` returns its `artifact_ref`. Approval displays the
final `contract.parameters`. Ordinary strong HTTP evidence remains
non-authoritative. P1 is
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
- P4-G1–G3 typed concrete-authority foundations: **RETAINED**
- P4-minimum five code invariants: **CLOSED (MVP SCOPE)**
- P4-C2 and production-grade C4/C5 hardening: **DEFERRED / NON-BLOCKING**
- P5 bounded state, interruption recovery and final compatibility deletion: **ADMISSION UNBLOCKED; NOT STARTED**

Documentation consolidation does not promote any production capability.

Status words are scoped to the exact row they annotate. P4-minimum closure uses
the current threat model, default product call path, focused negative evidence,
full suite/static checks, and the core benchmark as integrated closure evidence.
The benchmark does not add product semantics, but a failure prevents the five
invariants from being declared closed on the default route; current evidence
passes. Immutable revision,
concurrent-adversary probes and external multi-suite attestation are release
evidence only.

### 1.1 P4-G retained foundations and MVP redlines

The retained G1–G3 scope/signature/proof probes resolve at the typed authority
boundary. Transaction rematerialization, dispatch lifecycle, and approval-
freshness probes were re-run against the corrected default path:

| Probe | Current result | Closure owner |
|---|---|---|
| NAVIGATION TaskSpec + exact target + TYPE_TEXT choice | DENY | exact typed operation/effect subsumption |
| admitted `recipient=Alice, amount=100` + swapped concrete fields | DENY | named parameter authorization |
| uninstrumented DOM `Delete account` button | UNPROVEN | Runtime classification and source-assurance policy |
| valid Alice choice but actual affordance/locator targets Bob | DENY | route-specific signature plus Task Gate reauthorization |
| source/destination candidate semantic identity mismatch | DENY before signature sealing | classifier, builder and Task Gate exact endpoint checks |
| destination DELETE/operation mismatch hidden by source UPDATE | UNPROVEN/DENY | dual-endpoint effect/operation reducer |
| truncated action-bound source coverage or unsafe enabling action | UNPROVEN/DENY | shared fail-closed coverage/conflict/assurance/risk/capability gates |
| fresh preflight epoch changes route classification | old contract is discarded; route/payload/verifier/context rematerialize together from committed O1 | P4-C3 full O1 transaction materialization |
| timeout/ambiguous external dispatch | executor exceptions and ambiguous transport settle as `SENT_UNKNOWN`; recovery does not blindly retry | P4-C4 MVP uncertain-effect safety |
| strong or unbound authoritative high-risk absence evidence | rejected | attempt/transaction-bound authoritative settlement |
| approval followed by a changed observation epoch | stale exact-contract admission is rejected before permit issuance; Executor call count remains zero | P4-C0/P4-C3/C4 fresh O1 and exact approval ordering |
| public approval of H1 followed by a rebuilt H2 | H1 grant cannot issue an H2 token; a new pending request is returned | typed external pending request plus paused-run continuation |
| medium Catalog choice followed by a high-risk actual binding | final contract is HIGH and admission stops at APPROVAL_REQUIRED | route-specific proof risk plus contract/gate non-downgrade invariant |
| authoritative read with an asserted HIGH source/VLM risk | final signature is HIGH and admission stops at APPROVAL_REQUIRED | typed asserted-source raise-only risk floor |
| authoritative source plus weak/high-risk destination binding | signature uses weak assurance/high risk and independent Task Gate remains ALLOW for the exact pair | dual-endpoint classification and exact destination-candidate rebuild |
| CROSS_ORIGIN scope plus EXTERNAL_SYSTEM destination support | DENY with `EXTERNALITY_EXCEEDS_SCOPE` | shared classifier/authority externality ordering |
| material-conflict destination | UNPROVEN with `MATERIAL_SOURCE_CONFLICT` | dual-endpoint conflict reducer |
| authoritative source plus unasserted Visual destination | route assurance is WEAK and high-assurance scope is UNPROVEN | source-kind assurance floor |
| `REVERSIBLE_WRITE` proposal carrying `message.send@v1` | admission rejected | canonical effect-scope risk and closure validation |
| material source conflict with non-magic reason text | UNPROVEN | typed `ChoiceRejection.status` |

The typed scope/signature distinction and tri-state proof foundation remain
implemented. This table proves only the MVP redlines; it does not claim
cross-worker transaction isolation, revocation linearizability, clone-resistant
permits, complete context fencing, collateral attestation, or immutable release
provenance.

### 1.2 Interruption and restart truth

Current production supports typed in-run recovery and a same-process Local fast
path that pauses on one exact `PendingApprovalRequest` and continues the same
contract/session after the matching grant. Local cancellation can release that
approval waiter. These capabilities do **not** provide general cooperative
Coordinator/Executor interruption/cancellation or task-level process-crash
restoration.

Every normal Coordinator invocation still starts a fresh `StateKernel`; the
canonical ObservationStore is in-memory, and there is no durable typed
`RunCheckpoint`/restore ingress. A service status of `CANCELLED` therefore does
not by itself prove that an already dispatching action did not occur. BrowserGym
resume is separately scoped to immutable benchmark collection accounting and
completed episode reuse; it does not restore an interrupted product Runtime
episode. `P5-R1`–`P5-R4` retain the pending recovery design. The five
P4-minimum invariants and their default-route benchmark evidence now pass, so
P5 admission is unblocked; no P5 slice has started. The checkpoint payload is constrained to refs and
digests—including budget/control/trace/effect refs—plus the exact
`last_committed_observation_ref`; no
file, database or service implementation has been selected. Planned
`runtime_resume.py` is validation/routing only, not a state reconstruction,
effect-settlement or execution owner.

### 1.3 P4-minimum closure status

The five invariants are the only semantic admission gate. Focused checks, full
pytest/static checks, and the core benchmark are their closure evidence; the
benchmark is not invariant six. That integrated default-route evidence now
passes, so the overall P4 status is CLOSED in MVP scope.

| Boundary | Current truth | Status / owner |
|---|---|---|
| P4-C0 zero-call containment | Product composition fails closed and does not synthesize grants | **MVP CLOSED** — stale contract, missing capability/dependency and invalid/uncommitted contract tests all assert zero Executor calls |
| P4-C1 verifier-backed completion | Export has a required OutputSpec; receipt plus authoritative API final evidence and a SHA-bound local file are required before `TaskCompleted.artifact_ref` is returned | **MVP CLOSED** — receipt/nonexistent/mismatched-artifact fail-open paths are covered. Opaque/remote refs fail closed pending a future resolver |
| P4 plan semantics | A minimal read→mutation laundering guard remains while ordinary clicks do not require fabricated fields | **SUPPORTING FOUNDATION** — no claim of exhaustive destination/function/usage policy; not a sixth P4 invariant |
| P4-C2 context/capability/provenance | Existing experimental contracts are present, but account/profile/tenant live proof and full coordinate/provenance coverage are not claimed | **DEFERRED / NON-BLOCKING FUTURE HARDENING** |
| P4-C3 final contract | Final Task Authority evaluates materialized contract parameters; encoder injection such as unapproved `recipient=Bob` is denied; approval presents final `contract.parameters`; approval token, ExecutionAttempt, Executor-visible contract and final ActionContract hashes match | **MVP CLOSED** — canonical default materializer and focused negative/hash-equality tests |
| P4-C4 serial effect safety | Typed receipt/effect separation and no-blind-retry behavior are implemented for the trusted single-coordinator path | **MVP CORE CLOSED**; schema/policy revocation linearizability, clone-resistant/global permit registry, live-state fencing and attempt-bound collateral are explicitly not claimed |
| P4-C5 core cutover | Default product composition uses the canonical materializer and core fallback is isolated; stable Task API executes pricing/settings/export 3/3; held-out pricing binds semantic target ID on fixture v2.1.0 | **MVP CLOSED**; immutable revision plus AgentDojo/WASP/OSWorld attestation is release work, not a P5 blocker |
| Full pytest/static checks | Current combined working tree | **`1028 passed in 25.21s`; Ruff passed; mypy passed over 191 source files; `git diff --check` passed** |
| Core benchmark | Complete local fixture v2.1.0 core profile | **PASS** — 21 runs, `acceptance_errors=[]`, all 3 `full_runtime` tasks succeeded; required variants, opportunity denominators, and expected failure traces fail closed; `task_success_rate=1.0`, `unsafe_side_effect_rate=0.0`. Full Runtime has no failed-outcome opportunity, so its false-accept rate is not evidence; `no_structural_verifier` contributes 2 such opportunities with 0 false accepts |
| Stable Task API | Real pricing, settings and approval-gated export entrypoints | **PASS 3/3** — export returns `TaskCompleted.artifact_ref` only after typed output/final evidence/SHA closure |
| P5 | No durable checkpoint, runtime resume, generic persistence, or product crash restore exists | **ADMISSION UNBLOCKED; NOT STARTED**. P4-R0 is required only for a future hard-crash claim |

Two benchmark-reporting improvements remain explicitly non-blocking: display
zero-opportunity rates as `N/A`, and require the `no_recovery` ablation to fail
with its expected stale-state class/trace instead of accepting an arbitrary
failure delta. They are oracle hardening, not missing Runtime invariants.

### 1.4 P4-C5 compatibility-edge inventory

For this inventory, a **core fallback** is any alternate or proposal-era path
reachable from default product composition that can construct, authorize,
approve, execute, or commit without the finalized-contract chain. None is
allowed. An **edge-only compatibility** surface is an explicitly named
external/benchmark/conformance one-way adapter into canonical contracts; it is
not imported or called by product/canonical transaction-execution-commit code,
cannot grant Task Authority/capability, approve, seal, dispatch, or commit, and
must expire by P5-3. A listed edge therefore is deletion debt, not a core
fallback.

| Edge-only compatibility surface | Current consumers | Direction and authority boundary | Expiry |
|---|---|---|---|
| `ActionContractMaterializer` / `ActionContractBuilder` proposal-era implementation | `conformance.py::ConformanceContractBuilder`; `recovery_evolution.py::run_recovery_evolution`; `benchmarks/adaptive_routing.py::run_adaptive_routing_case`, `task_planning.py`, `generalization_rollout.py`, `browsergym_encoder.py`, and `benchmarks/composition.py`; legacy-specific tests | benchmark composition copies only requirements/resolver/gesture configuration into a new canonical owner; the legacy generalist BrowserGym subtype maps to the dedicated `GeneralistBrowserGymRouteEncoder`; proposal-bound `BrowserGymContractBuilder` is rejected; product `composition.py` imports neither legacy type and rejects route encoders | migrate every listed offline/benchmark/conformance consumer, then delete no later than P5-3 |
| re-export of `ActionTransactionMaterializer` and `ActionContractDraft` from `action_contract_builder.py` | direct-import compatibility tests and downstream imports not yet migrated | alias only, from the canonical module toward the old public import surface; it creates no second implementation or owner | move all imports to `transaction_materialization.py`, then delete no later than P5-3 |
| BrowserGym proposal-era builders and `encode_canonical_choice` hooks | `benchmarks/browsergym_encoder.py` exports plus legacy-specific tests; the compatibility episode itself now uses the dedicated canonical encoder | retained only for proposal-era benchmark tests/exports; canonical strict and compatibility episode routes use `GeneralistBrowserGymRouteEncoder`, which cannot grant capability, create Task Authority/approval, seal, admit, or dispatch | delete the legacy builders/hooks and facade exports no later than P5-3 |

No compatibility edge is imported by `transaction_materialization.py` or
`execution_phase.py`; benchmark safety ablations remain in
`benchmarks/composition.py` and are rejected by product composition.

## 2. Current-vs-target matrix

| Area | Current implementation truth | Target | Status |
|---|---|---|---|
| Source intake | default path is SourceEnvelope → MinimalIntentProposal → optional SemanticAudit → TaskSpecAuthority; default SourceLedger/claim/obligation owners are deleted | lightweight SourceEnvelope + risk-proportionate MaterialBinding/selective SourceAnchor; optional SemanticAudit | P0-E complete |
| Semantic authority | TaskSpecAuthority is the only canonical admission writer; `AdmittedTaskSpec` is an in-process object capability binding the exact TaskSpec, SourceEnvelope identity and revision predecessor; RunRequest and TaskRequest require that capability and have no goal-only branch; raw external `UserTaskSubmission` is admitted server-side before Runtime construction; the private P5-3 TaskSpec wrapper and explicitly named legacy request adapter are import-gated to compatibility profiles; execution consumers are denied source context | TaskSpecAuthority-only write barrier; bounded context-only readers; raw-text-free execution | P0-E/P3 complete |
| Task contract | TaskSpec v2 carries flat typed requirements, stable input bindings, fully covered authorization/constraint/preference/forbidden refs, capability ceiling, risk policy and source-bound outputs; typed success leaves carry CriterionPolicy; admission derives high-risk status from canonical `EffectAuthorizationScope`/operation semantics, rejects aggregate-operation downgrades, and requires operation-specific material fields/capability plus distinct allowed-effect-bound ACTION_CAUSED/RECENT_ACTION and AUTHORITATIVE/FINAL_RECHECK leaves; construction failures become typed issues; completion accepts a leaf result only after evidence satisfies that exact policy and the evaluation carries its criterion-bound policy digest; CURRENT_OBSERVATION never survives an epoch change, RECENT_ACTION is re-admitted only from the bounded Runtime outcome index, and DURABLE is re-admitted only from DurableEvidenceStore; accepted `semantic_value_constraints` and evidence-description fields are absent; every output requirement has exactly one required OutputSpec | stable canonical requirement identity plus authorization/constraint/forbidden-effect/success/output contract | P3 complete |
| Task planning | canonical TaskPlan stores StepSpec directly; TaskPlanAuthority validates current observation/state basis, identity/version, DAG, budgets, requirement refs and the admitted minimal read→mutation guard | observation-grounded replaceable TaskPlan<StepSpec>; plan admission is not execution authority | P1/P4 planning core complete; exhaustive destination/function/usage policy is not claimed or required for P4 MVP closure |
| Task progress | facts, bindings, bounded recent outcome refs, durable evidence refs and VerifiedStepRecord survive replacement without reinserting completed steps | progress is factual state, not a second plan owner | P1-P3 complete |
| Observation | PerceptionCapture is acquisition-only and CanonicalObservationBuilder retains targets, bindings and typed facts/conflicts behind immutable epoch refs. The admitted GUI path closes snapshot/page/target freshness; missing/error remains UNKNOWN | capture-built canonical observation is sole Runtime authority; each acquisition adapter should own truthful coverage | P0-B MVP freshness closed; comprehensive per-adapter coverage and tenant/profile/coordinate breadth are not claimed |
| Cross-surface foundations | DOM/AX/Visual/SVG/WoT/API/Device enter one canonical epoch; semantic choices retain all non-conflicting bindings, ActionContractBuilder selects the current route, and causal step evidence retains its actual subject/value/source/assurance | shared semantic target, surface-neutral Catalog, ActionContract route and LoopEvaluator | P0-B/P0-C/P1 plus P2 canonical step-completion cutover complete |
| Action choice | Runtime builds the logical Catalog before model projection and StepChoiceFlow owns deterministic 0/1/N/hidden-ID behavior. Typed scope/signature/proof and dual-endpoint classification consume truthful epoch coverage; Catalog admits only typed ALLOW and untrusted text is raise-only | `EffectAuthorizationScope ⊒ RuntimeEffectSignature → ALLOW/DENY/UNPROVEN`; Catalog admits ALLOW only using truthful adapter facts; Text/VLM is raise-only | P0-C/P4 and P4-C1/C5 MVP closed |
| ActionContract and gates | product composition uses `ActionTransactionMaterializer`; final material parameters/payload are frozen before Task Authority and approval. Unapproved encoder-added parameters are rejected, and approval/attempt/Executor/final contract hashes are equal | one final immutable executable contract evaluated by policy/approval and rechecked for snapshot/page/target freshness | P4-C0/C3 MVP closed; richer context/schema hardening deferred |
| Execution | trusted in-process execution is serial; rejection is zero-call, typed receipt remains distinct from effect, and unresolved external effects stop for inspection/block/handoff without blind replay | execute the same approved immutable contract; receipt never completes; uncertain effect never blindly retries | P4-C4/C5 MVP closed; transaction-isolation/permit/fencing/collateral claims explicitly deferred |
| Verification | `LoopEvaluator` feeds canonical observation, current contract, bounded lossless recent outcomes, durable evidence, latest final-recheck identity and resource versions directly to `PredicateEvaluator`; resource versions are derived from canonical target/fact content; Task completion uses the same Runtime-owned context and is recomputed without a CriterionEvaluation cache; observation metadata cannot assert causal lineage, durable admission, final-recheck authority or resource versions; action effect and TaskSpec completion retain their earlier owners | loop-native typed step evaluation with bounded evidence locations | P2 mandatory runtime closure complete; P2-6 deferred and P2-7 resolver demand-gated |
| Criterion contracts | canonical immutable Predicate/AllOf/AnyOf/Not/OpenSemantic AST and orthogonal satisfaction/validity/assurance policy are implemented; strict `StepSpec` accepts only canonical `CriterionExpr`, while legacy providers/benchmarks canonicalize at ingress; unresolved OpenSemantic routes to a typed clarification gap | one typed criterion vocabulary independent of provider coverage | P2-1/P2-2 core complete; P2-7 full resolver demand-driven |
| Evidence providers | shared mechanical contract groups structural DOM/AX/Visual/SVG, resource API/WoT/Device/transaction and artifact/file/materialization facts; unknown surfaces are not treated as DOM and bare artifact refs are not integrity proofs | focused fact providers feeding pure predicate evaluation | P2-5 complete; P2-6 model/human expansion deferred |
| Evidence lifetimes | current facts are epoch refs; exact current-contract/receipt/pre/post/effect lineage is retained in a 40-record recent index; final rechecks bind latest identity/current epoch/resource version; only explicitly durable records enter a bounded durable store | CurrentObservation + RecentActionOutcome + DurableEvidence | P2-3/P2-4 complete and production-wired |
| Task completion | recursive TaskSpec.success evaluation, constraint/effect/final-recheck checks and RuntimeCommitter-only terminal write exist; latest-report/plan/no-TaskSpec fallbacks are removed. The admitted local export requires typed OutputMaterialization, authoritative final evidence and matching file SHA before returning its artifact ref | pure TaskCompletionEvaluator consumes actual typed/source-bound `OutputMaterialization`; RuntimeCommitter-only commit | P0-A/P4-C1 MVP local-output path closed; opaque/remote resolution fails closed and broader output/privacy breadth is not claimed |
| Observation continuation | perception owner returns REUSE, AUGMENT_TARGETED, RECAPTURE or WAIT_AND_RECAPTURE from freshness/stability/coverage/conflict; fresh reusable capture is not immediately duplicated | typed continuation proposal outside Coordinator/Committer | P1-E2 complete |
| Recovery | RecoveryStage owns typed classification, handoff/exhaustion/error mapping and strategy choice; RecoveryObservationEvaluator and RecoveryActionEvaluator settle typed outcomes; Coordinator and RuntimeCommitSession only follow results | typed causes, no generic-string ownership, no blind external retry | P1-C1 complete |
| Interruption/restart | exact approval can pause/resume the same live Local session; typed in-run recovery exists. Durable task checkpoints, fresh-session crash restore and general cooperative interruption/cancellation do not yet exist | P5 cooperative checkpoint and fresh-state reconciliation; hard-crash dispatch proof remains separate future hardening | P5-R1–P5-R4 admitted but not started |
| Runtime commit/control | RuntimeCommitSession owns lifecycle, read projections stay separate, and RuntimeCommitter only validates/applies typed transitions/events/completion | orchestration and commit authority separated from domain evaluation | P1-C2 complete |
| Trace/evaluation | trace, artifacts, benchmark reports and evidence records exist | offline consumers, never synchronous completion authority | retain |

## 3. Architecture coverage state

```yaml
authoritative_target: current_not_implemented_as_a_whole
active_step_order: canonical_observation_then_full_catalog_then_bounded_choice_page
cross_surface_foundations: canonical_core_cutover_complete
cross_surface_target: DOM_AX_Visual_SVG_WoT_API_Device
cross_surface_adapter_coverage: target_rule_retained_broader_adapter_breadth_demand_gated
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
effect_authorization_scope: task_spec_typed_scope_foundation_retained_P4_G1
runtime_effect_signature: classifier_and_signature_foundation_retained_P4_G2
concrete_effect_authority: typed_subsumption_foundation_retained_P4_G3
action_authority_decision: ALLOW_DENY_UNPROVEN_foundation_retained
runtime_risk_policy: conservative_classifier_foundation_retained_MVP_evidence_passed_future_breadth_demand_gated
task_gate_actual_binding_revalidation: closed_through_P4_C3
high_risk_action_governance: P4_MVP_scope_closed_release_hardening_deferred
catalog_physical_minimality: logical_full_membership_and_layout_test_double_invariance_complete_production_eager_lazy_indexed_demand_gated_no_admitted_slice
observation_indexed_epoch: canonical_owner_and_MVP_freshness_closed_broader_adapter_coverage_not_claimed
authority_in_process_composition: shared_in_process_observation_store_complete
criterion_provider_phasing: P2_step_P2_1_through_P2_5_complete_P2_6_deferred_P2_7_resolver_pending
typed_task_planner_trigger: P4_typed_trigger_provider_cutover_and_semantic_admission_closed
risk_derived_feature_profiles: target_not_implemented
verification_shape: P2_typed_policy_predicates_and_mechanical_provider_matrix_complete
task_completion_semantics: recursive_P0_A_and_verified_actual_OutputMaterialization_MVP_closed
required_output_closure: local_artifact_must_exist_and_match_digest_remote_refs_fail_closed
task_completion_commit: RuntimeCommitter_only
same_process_exact_approval_continuation: exists_with_final_contract_hash_equality
task_level_durable_checkpoint: not_started_P5_R1_R2_admission_unblocked
checkpoint_payload: refs_digests_last_committed_observation_ref_only
checkpoint_physical_store: not_selected
task_level_process_restart_restore: not_started_P5_R3_validation_routing_only
resumable_runtime_interruption: not_started_P5_R4
cooperative_runtime_cancellation: not_started_P5_R4
benchmark_resume_scope: completed_episode_collection_only_not_product_task_restore
evidence_locations: current_observation_plus_bounded_recent_ActionOutcome_plus_small_DurableEvidenceStore
source_invariants: SOU-01_through_SOU-12_plus_MAT-01_through_MAT-07
observation_invariants: OBS-01_through_OBS-14
verification_invariants: VER-01_through_VER-14
recovery_invariants: REC-01
semantic_authority_invariants: NLI-01_through_NLI-08
requirement_invariants: REQ-01_through_REQ-05
dependency_invariants: DEP-01_through_DEP-03
choice_invariants: CHOICE-13
concrete_action_authority_invariants: P4_MVP_final_contract_and_hash_equality_closed
output_invariants: P4_MVP_verified_local_materialization_closed
runtime_threat_model: one_process_one_run_one_coordinator_one_browser_session_one_active_contract
p4_future_hardening: tenant_profile_proof_revocation_linearizability_global_permit_fencing_attempt_collateral_multisuite_attestation
physical_minimality_invariants: CAT-PHY-01_OBS-PHY-01_AUTH-PHY-01_CRIT-PHY-01_PLAN-PHY-01_PROFILE-01
cross_surface_invariants: SURFACE-01_through_SURFACE-03
```

## 4. Evidence and promotion

- Git owns the exact current repository revision; this file does not self-record HEAD.
- Historical implementation and behavioral evidence remains under `docs/evidence/`.
- Change-admission decisions remain under `docs/change-admission/`.
- Historical local pass results do not imply current remote CI or promotion.
- Remote CI is intentionally disabled for the recorded iteration.
- Published release/benchmark claims remain held until their selected behavior,
  safety and breadth evidence passes at one immutable revision. This does not
  block ordinary P5 implementation.

## 5. Current documentation state

| Item | State |
|---|---|
| authoritative architecture/evolution plan | current |
| documentation manifest/governance | current |
| superseded prose/plans/audits | archived and indexed |
| maintained contract synchronization | 2026-08-07 MVP scope reset: five P4 invariants are current; production-security hardening is deferred/non-blocking |
| simple documentation gate | active: lifecycle/path coverage, authority uniqueness, redirects, maintained links |
| production behavior change | C0 zero-call tests, C1 artifact/receipt completion fix and C3 final-parameter/hash fix implement the five MVP code invariants with existing no-blind-retry/default cutover; fresh core benchmark evidence passes, so P4 is closed in MVP scope and P5 admission is unblocked/not started |

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

P4-G1–G3 moved semantic generation and typed authority foundations into focused
builder, generation-support and policy modules; `action_choice_catalog.py`
retains membership/digest/query ownership. The P4-minimum closes only the five
MVP invariants; C2 and production-grade C4/C5 hardening remain deferred. Later P5-4 containment remains
blocked: `execution_phase.py` is currently 1,316 lines and strict
`browsergym_episode_runner.py` is 1,082 lines after legacy extraction; both must
be split by responsibility without reopening P4's completed presentation/port
boundary.

## 6. Historical ledger

The complete pre-consolidation 1,582-line ledger is preserved at
[implementation-status-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/implementation-status-pre-consolidation.md).
Individual claims remain attributable through evidence and change-admission
records; the snapshot is not a current status source.
## P5-0 review — 2026-08-07

The P4 MVP remains CLOSED. At HEAD `538be27f8a9aea3fa9d7f25d271b4d0bf6681f7f`,
P5-0A core is implemented, while P5-0B remains partial: transition dual-channel
support, failure atomicity, read-view closure, and compatibility containment
remain P5-0E entry debt. P5 admission remains UNBLOCKED, but P5-1 is not
started. See `docs/reviews/2026-08-07-p5-entry-hardening.md`.

P5-0E is partial: strict commit protocol and artifact/receipt lineage are in
place, but frozen domain read views and compatibility/god-file containment are
still open. P5-0 is not CLOSED and P5-1 is not READY.
