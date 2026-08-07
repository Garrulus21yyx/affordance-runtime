# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **P4:** CLOSED (MVP scope)
> **Execution-table revision:** 2026-08-07 P4-minimum scope reset and closure; five code invariants plus default-route evidence pass, P5 admission unblocked, P5 not started
> **Target:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Migration authority:** [Architecture evolution plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
> **Implementation truth:** [Implementation Status](implementation-status.md)

## 1. How to use this plan

This is the only maintained implementation scheduler. It expands the P0–P5
architecture phases into independently reviewable cutover slices. It does not
create another architecture authority and does not claim that a pending target
already exists in production.

A slice moves to `done` only when its canonical owner is wired into the default
path, the displaced owner is deleted or explicitly isolated, the minimal
failure-localizing checks pass, and `implementation-status.md` is updated.
`done` requires the applicable owner, default route and focused positive/negative
behavior checks. Immutable revisions, concurrency attacks and external
multi-suite attestations are release evidence only; they do not block P4/P5
unless the matching product claim is explicitly admitted.

The core benchmark is integrated closure evidence that the same five P4-MVP
invariants hold on the default product route after cutover. It is not a sixth
semantic invariant or Runtime authority. The fresh passing run now demonstrates
default-route integration and closes P4 in MVP scope.

At most one vertical authority migration and one independent horizontal
containment slice may write production behavior at a time. No slice may create
a shadow owner merely to postpone deletion.

## 2. Target identity

```yaml
authoritative_architecture: docs/superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md
authoritative_evolution_plan: docs/superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md
documentation_manifest: docs/documentation-manifest.yaml
execution_table: granular_P0_through_P5
migration_mode: substitutive_no_bidirectional_legacy_coupling
default_source_target: SourceEnvelope_plus_selective_SourceAnchor
material_binding_target: effect_specific_risk_proportionate_typed_coverage
optional_audit_target: SemanticAudit_veto_or_clarify_only
semantic_context_target: bounded_read_only_SourceContextView
semantic_write_owner: TaskSpecAuthority_only
requirement_identity_target: canonical_TaskRequirement_refs
planning_target: observation_grounded_TaskPlan_of_StepSpec
choice_target: full_Runtime_ActionChoiceCatalog_before_ChoicePage
choice_presentation_target: bounded_semantic_context_without_execution_bindings
effect_authority_target: typed_EffectAuthorizationScope_subsumes_RuntimeEffectSignature
action_authority_result: ALLOW_DENY_UNPROVEN_proof
runtime_risk_target: conservative_max_with_text_and_VLM_raise_only
high_risk_target: effect_specific_material_assurance_exact_approval_preflight_and_causal_final_recheck
catalog_realization_target: logical_complete_eager_or_lazy_indexed
observation_realization_target: immutable_epoch_ref_plus_read_only_indexes
authority_realization_target: modular_monolith_in_process_policy_composition
runtime_threat_model: one_process_one_run_one_coordinator_one_browser_session_one_active_contract
effectful_execution_model: trusted_in_process_and_serial
criterion_rollout_target: canonical_vocabulary_with_phased_provider_coverage
task_planner_invocation_target: typed_trigger_with_reuse_and_direct_fast_paths
feature_profile_target: risk_derived_optional_machinery_without_gate_bypass
cross_surface_target: DOM_AX_Visual_SVG_WoT_API_Device
verification_target: loop_native_typed_LoopEvaluator
completion_semantics_owner: TaskCompletionEvaluator
required_output_target: materialized_and_source_bound_before_completion
completion_commit_owner: RuntimeCommitter_only
interruption_recovery_target: P5_cooperative_checkpoint_and_fresh_state_reconciliation
checkpoint_payload_target: refs_digests_and_last_committed_observation_ref_only
checkpoint_realization_target: physical_store_unfrozen_pending_fault_model_and_P4_R0_decision
runtime_control_target: separate_resumable_interrupt_and_terminal_cancel_at_safe_boundaries
test_strategy: failure_localizing_minimal_gates
p4_semantic_gate: five_P4_MVP_invariants_only
p4_closure_evidence: focused_checks_full_pytest_static_checks_and_default_route_core_benchmark
p4_status: CLOSED_MVP_scope
p4_blocker: none_for_MVP_scope
p5_admission: unblocked_not_started
future_hardening_non_blocking: tenant_profile_live_proof_revocation_linearizability_global_permit_registry_worker_fencing_attempt_bound_collateral_multisuite_attestation
```

## 3. Delivery laws

1. **Substitutive cutover:** add the canonical owner, migrate every in-scope
   caller, switch default composition, then remove/isolate the old owner in the
   same slice.
2. **One responsibility per module:** split by contract/decision ownership, not
   by arbitrary class count or framework layer.
3. **Coordinator only sequences:** it starts the run, invokes typed stages,
   follows `LoopDirective`, and returns a result. It does not classify domain
   failures, build choices/contracts, evaluate criteria, or write state.
4. **RuntimeCommitter only commits:** it applies admitted transitions/events;
   it does not calculate completion, recovery, evidence, or planning results,
   and it does not own checkpoint serialization, file I/O or restore policy.
5. **Stage façade stays thin:** a phase may compose collaborators, but domain
   algorithms live with the contract they own.
6. **No service forest:** a logical authority may be a pure function or small
   in-process policy object. A new process/store/model call needs measured need.
7. **No test-driven architecture:** tests locate a declared failure and protect
   a boundary; they do not define production semantics or justify keeping a
   legacy owner.
8. **No old/new round-trip:** canonical data may not be projected into a legacy
   type and converted back; no dual read, dual write, shadow comparison owner or
   fallback from canonical semantics to legacy prose is allowed.
9. **Compatibility is edge-only and one-way:** when an external caller cannot
   migrate in the same slice, an explicitly named adapter may translate old
   input into the canonical API. Canonical modules never import that adapter or
   legacy models, and every adapter has a last-allowed slice.
10. **Checkpoint is not authority:** a checkpoint records the last committed
    typed identities and effect state. Resume must revalidate versions, open a
    fresh execution session, acquire a fresh canonical observation, and obtain
    new authority for every stale contract or approval.

## 4. Anti-God-File ownership map

Line count is a review trigger, not a correctness metric. A file above roughly
600 lines, or a slice adding a second domain responsibility to a file, requires
an explicit split decision before merge. Existing oversized files are debt to
remove inside their owning migration slice, not through an unrelated rewrite.

| Physical owner | Allowed responsibility | Must not absorb | Planned split/cutover |
|---|---|---|---|
| `coordinator.py` | serial stage ordering and typed directives | recovery classification, semantic parsing, contract construction, evaluation, state mutation | P1-C1 complete; Coordinator only invokes typed RecoveryStage results |
| `runtime_committer.py` | authoritative transition and trace commit; P5-R2 may expose an immutable refs/digests-only projection of already committed state | run-session lifecycle, read projections, evaluator/recovery policy, checkpoint serialization/storage or restore routing | P1-C2 and the P4-C3/C4 MVP pre-dispatch boundary are complete; P5-R2 may build only on that committed boundary |
| `run_checkpoint.py` (planned) | immutable checkpoint schema containing refs/digests and `last_committed_observation_ref`; persistence through an unfrozen focused store port | StateKernel/object-graph serialization, raw source/context, live browser/backend handles, physical-store policy, execution, planning, approval grant or completion | P5-R1–R2 admitted but not started; P4 MVP prerequisites and closure evidence pass, and no file/database/service mechanism is selected here |
| `runtime_resume.py` (planned) | validate checkpoint identity/version/dependencies and return a typed route to fresh-session startup, effect reconciliation or rejection | state reconstruction, effect adjudication, planning, authorization, approval, dispatch, completion or persistence | P5-R3; validation/routing only |
| `execution_phase.py` | compose one admitted action attempt | Catalog construction, planner logic, completion logic | P0-C4 action admission extracted; later phase-containment cleanup remains |
| `effect_authority_contracts.py` / `action_effect_classifier.py` / `action_choice_authority.py` | distinct scope/signature/proof contracts / Runtime signature-risk-assurance derivation / typed subsumption and narrow enabling policy | TaskSpec admission, Catalog membership, model projection, backend route, approval or execution; no independent service | P4-G must keep `EffectAuthorizationScope` and `RuntimeEffectSignature` as distinct types; proof binds evaluator-policy version and classifier is Harness-owned pure policy |
| `choice_contracts.py` / `action_choice_builder.py` / `action_choice_generation.py` / `action_choice_catalog.py` | immutable semantic choice contract / generation and rejection / logical membership-digest-query | effect classification, typed authority evaluation, model projection, backend route selection, TaskSpec admission or copied-field-only gate proof | P4-G moved generation into focused modules and retained membership/digest/query in the 160-line Catalog owner; no parallel authority or service exists |
| `action_contract_builder.py` | selected-choice validation and current binding materialization | execution, approval grant or completion | P0-C4 complete |
| `task_planner.py` / `step_choice_planner.py` | strict typed task-planning / closed step-choice provider ports | Runtime authority objects, hidden Catalog entries or action dispatch | P4-2 complete; `generalist_planner.py` is an isolated historical compatibility profile used only by the generalization comparison and expires at P5-3 |
| `progress_phase.py` | thin post-action stage façade and route-outcome composition | observation repair, task completion evaluation or TaskSkill algorithms | P1 closure complete; focused collaborators own each algorithm |
| `intent_compiler.py` / `task_spec_authority.py` | untrusted minimal proposal interpretation / sole accepted TaskSpec admission | source graphs, planning, capability grant or observation-derived authority | P0-E complete |
| `material_contracts.py` / `material_binding_policy.py` | typed material binding vocabulary / deterministic per-effect field coverage and provenance-form admission | graph/store/model call, SemanticAudit policy, capability/approval/grounding/contract decisions | P0-E5 complete; P3 folds values into canonical requirements without a second registry |
| `verification/mechanical.py` | mechanical verifier reports used as admitted evidence input | root completion, progress decisions or commit | P0-A package cutover complete; further provider/evidence-policy refinement remains in `P1-E1`/`P2` |

New files are justified only when they own one durable contract or decision.
Do not create one file per dataclass, provider instance, gate result, or surface.

### 4.1 Legacy deletion protocol

Every migration row follows this order:

```text
canonical contract
→ canonical implementation
→ migrate callers
→ switch composition/default route
→ delete legacy owner, conversion and tests
```

The default route never contains both owners. A compatibility adapter may exist
only at an external ingress boundary, must be one-way old-input→canonical-input,
and cannot expose legacy state to canonical planners, evaluators or committers.

Here, **core fallback** means any path reachable from default product
composition that can construct, authorize, approve, execute, or commit through
proposal-era, partial-contract, or otherwise alternate semantics instead of the
finalized-contract chain. It is forbidden. **Edge-only compatibility** means an
explicitly named external ingress, benchmark, or conformance adapter that maps
legacy input one-way into canonical contracts, is neither imported nor called
by product/canonical transaction-execution-commit modules, and cannot grant
Task Authority/capability, approve, seal, dispatch, or commit. Such an edge does
not violate the no-core-fallback rule, but every surviving edge is inventoried
and expires no later than P5-3.

| Legacy surface | Last allowed slice | Required deletion evidence |
|---|---|---|
| `verification.py` implementation / `verification/legacy.py` | `P0-A4` | no production import of legacy verifier or Boolean/synthetic completion API |
| `runtime_terminal.py::TaskCompletionVerifier` latest-report authority | `P0-A4` | only typed TaskCompletionEvaluation reaches RuntimeCommitter |
| `UnifiedObservation.from_planner_observation` and reverse projection | `P0-B4` | canonical builder is the only production constructor |
| algorithm/presentation/selection ownership in `action_choice.py` | `P0-C5` | callers import focused canonical modules; temporary re-exports removed |
| `planning.py::ContractBuilder` | `P0-C4` | ActionContractBuilder owns canonical observation/catalog binding |
| default SourceLedger/claim/obligation intake route | `P0-E4` | ordinary composition cannot import or invoke ledger graph construction |
| default StepSpec→SubgoalSpec→StepSpec and completed-subgoal carry-forward | `P1-P3` | **deleted** — current TaskPlan stores StepSpec directly and progress survives by facts/bindings/verified records |
| external model provider `subgoals` wire schema in `legacy_task_plan_provider.py::LegacyTaskPlanProviderAdapter` | `P3` common legacy-exit gate | **deleted** — strict task planning emits canonical PlanProposal/StepSpec contracts |
| strict planner StateKernel/BrowserSnapshot/ActionChoiceBuilder signature and `planner_compatibility.py` | `P4-2` | **deleted** — strict ports accept only typed TaskPlanningRequest or ChoicePlanningRequest |
| `TaskSemanticPayload.target_identity/destination_identity/operation_class` + unordered scalar input values as sole action authorization proof; Boolean `ChoiceAuthorityDecision.authorized`; copied choice authority fields as Task Gate proof | `P4-C5` | complete the physical canonical cutover to typed `EffectAuthorizationScope`, named parameter bindings, Runtime-derived route-specific `RuntimeEffectSignature` and versioned tri-state proof; no proposal/fallback compatibility in the canonical action path |
| historical `generalist_planner.py` / `compatibility_planner_algorithms.py` comparison profile | `P5-3` | isolated from strict/default construction; sole production consumer is `benchmarks/generalization_rollout.py::_run_compatibility_pair`; delete after that comparison migrates |

P5 is not a dumping ground for deletion deferred from earlier slices. Only a
documented external/public adapter with a consumer and expiry may survive to P5.

## 5. P0 correctness cutovers

### P0-A — Completion authority

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-A0` | Convert `verification.py` to `verification/__init__.py` + `verification/legacy.py`; list and migrate production callers toward focused package APIs | canonical contracts/modules never import `legacy.py`; the package root may expose a one-way temporary external compatibility surface only until A4 | none | existing verification/contract imports plus one canonical-does-not-import-legacy sentinel | done |
| `P0-A1` | Add `verification/contracts.py` with typed `CriterionEvaluation`, `LoopEvaluation`, `TaskCompletionEvaluation`, evidence metadata and `ObservationContinuation`; add the narrow typed `TaskSpec.success`/required-output references needed for P0-A closure without performing the full P3 TaskSpec-v2 cutover | prohibit Boolean/synthetic-PASSED types from new APIs; missing typed success remains UNKNOWN and is never recovered from prose | `P0-A0` | contract construction/immutability checks; reuse criteria tests | done |
| `P0-A2` | Add `verification/task_completion.py`; recursively evaluate `TaskSpec.success`, constraints, unresolved effects, final rechecks and required outputs | `runtime_terminal.py::TaskCompletionVerifier` becomes adapter-only and cannot inspect latest report as root authority | `P0-A1` | one parametrized closure test covering receipt/report/plan/prose rejection and output absence | done |
| `P0-A3` | Wire typed completion through `progress_phase.py`, `planning_phase.py`, `runtime_terminal.py` and `runtime_committer.py` | remove direct `TaskCompleted` construction outside RuntimeCommitter | `P0-A2` | reuse progress/planning/coordinator vertical tests; one initial-already-satisfied case | done |
| `P0-A4` | Remove disabled-verification PASSED and receipt/latest-report/plan-exhausted fallbacks from `contract_execution_loop.py`, `runtime_terminal.py` and compatibility call sites | delete `verification/legacy.py`, temporary package re-exports, superseded fallback branches and their dedicated tests after all production callers migrate | `P0-A3` | affected verification suite + one external-effect final-recheck sentinel + legacy-import absence scan | done |
| `P0-A5` | Introduce actual typed `OutputMaterialization`; required local artifacts must resolve and match content digest | declarations, mappings, Planner prose, receipt or nonexistent artifact cannot satisfy required output | `P0-A1`–`P0-A4`, P3 | declaration/receipt rejection plus artifact existence/digest | **MVP closed through P4-C1 (2026-08-07)** — local artifacts are resolved and SHA-256 checked; opaque/remote refs fail closed until a future resolver is admitted |

### P0-B — Canonical observation

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-B1` | Complete immutable capture/coverage contracts in `perception_session.py` and `unified_observation.py` for DOM/AX/Visual/SVG/WoT/API/Device | BrowserSnapshot remains acquisition DTO only | none | reuse perception/DOM/WoT/visual tests | done |
| `P0-B2` | Add `canonical_observation_builder.py` and `observation_store.py`; build target/binding/fact/coverage indexes and immutable epoch ref | no model presentation settings in builder/store | `P0-B1` | one multi-binding/conflict/coverage builder test | done |
| `P0-B3` | Wire canonical build/ref through `perception_phase.py`, `active_perception.py`, `execution_phase.py`, `progress_phase.py`, `composition.py`, `runtime_loop_phase.py`, `runtime_committer.py` and `state_kernel.py` | no Runtime semantic consumer reads long-lived BrowserSnapshot facts; StateKernel accepts only typed observation commits/refs | `P0-B2` | one normal + targeted + post-action epoch continuity test | done |
| `P0-B4` | Change `planning_request_builder.py` to one-way bounded projection from canonical observation; migrate strict/default planner and trace descriptors to the supplied canonical epoch | delete production `UnifiedObservation.from_planner_observation`, reverse reconstruction, the legacy converter test, and the raw-observation StateKernel compatibility owner | `P0-B3` | one projection-budget invariance sentinel; reuse request-builder/generalist/coordinator tests | done |
| `P0-B5` | Improve adapter-owned SourceCoverage as benchmarks expose real acquisition gaps | builder must not claim task completion from coverage alone | `P0-B1`–`P0-B4` | scenario-specific limit/truncation probes | **ONGOING NON-BLOCKING breadth work** — not part of the five P4-minimum gates |

### P0-C — Runtime-owned action space

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-C1` | Move immutable choice/request/result types from `action_choice.py` to `choice_contracts.py`; migrate canonical callers and keep only an edge-only temporary re-export list | canonical choice modules never import `action_choice.py`; no algorithms in contracts | `P0-B2` | existing serialization/equality tests plus canonical-import direction scan | done |
| `P0-C2` | Add `action_choice_catalog.py` for deterministic logical membership, digest, rejections and surface-neutral semantic choices under a realization-independent contract; current production realization is eager | presentation/page size, physical realization and backend preference cannot alter membership | `P0-C1`, `P0-B4` | count/order/digest invariance across presentation budgets plus layout test doubles | **done (logical contract)** — current physical implementation is eager; production lazy/indexed realization is demand-gated and has no admitted implementation slice |
| `P0-C3` | Add `choice_presentation.py` and `action_selection.py` for bounded pages, continuation, validation and `UNPRESENTED_CHOICE_ID` | remove presentation and selection branches from `action_choice.py` | `P0-C2` | reuse action-choice tests; add one hidden-ID rejection vertical test | done |
| `P0-C4` | Move `planning.py::ContractBuilder` to `action_contract_builder.py`; add `action_admission.py` for ordered Task/Capability/Approval/Freshness policies; shrink `execution_phase.py` to composition | no contract binding from planner/model views; no gate decides completion | `P0-C2`, `P0-B3` | reuse contract/preflight tests and one DOM→visual/WoT fresh-contract reroute case | done |
| `P0-C5` | Wire Catalog-before-model in `planning_phase.py`; strict `generalist_planner.py` only receives `ChoicePlanningRequest` | delete strict planner ownership of ActionChoiceBuilder, BrowserSnapshot, StateKernel and dispatcher; remove temporary `action_choice.py` re-exports after callers migrate | `P0-C2`–`P0-C4` | one 0/1/N vertical test using the normal Coordinator path + legacy-import absence scan | done |

### P0-E — Thin source and single semantic admission

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-E1` | Add `source_envelope.py` with immutable SourceEnvelope, selective SourceAnchor and deterministic builders | ordinary path performs no clause/claim/obligation graph work | none | one low-risk envelope test and one exact material-anchor case | **completed (2026-08-05)** — immutable hash/length/ref envelope plus whole-request and exact material anchors; no clause parsing or raw trace payload |
| `P0-E2` | Add `task_spec_authority.py`; make `intent_compiler.py` emit untrusted MinimalIntentProposal only | compiler cannot admit TaskSpec or derive steps | `P0-E1` | one admission/rejection test; reuse intake cases | **completed (2026-08-05)** — compiler exposes proposal-only `propose`; `TaskSpecAuthority` alone validates/admit revisions and binds Envelope identity |
| `P0-E3` | Add `source_context.py` and `semantic_audit.py` with consumer allowlist and risk-triggered pass/veto/clarify contract | no audit repair/write authority; execution receives no source context | `P0-E2` | one low-risk no-audit path and one high-risk veto/clarify path | **completed (2026-08-05)** — three-consumer bounded read set; ordinary audit skipped; triggered audit is PASS/VETO/CLARIFICATION_REQUIRED only |
| `P0-E4` | Cut default `task_intake.py`/`task_pipeline.py` to Envelope→Proposal→Authority; move reusable high-risk audit capability behind `semantic_audit.py` rather than wrapping the default SourceLedger route | delete default SourceLedger/claim/obligation prompt, schema, converters, call paths and graph-only tests | `P0-E2`–`P0-E3` | one default-path import/call sentinel and one optional-audit entry test | **completed (2026-08-05)** — default pipeline is Envelope→Proposal→optional Audit→Authority; SourceLedger/coverage/obligation compiler owners and graph-only tests deleted |
| `P0-E5` | Add `material_contracts.py` + `material_binding_policy.py`; extend `source_envelope.py` with prevalidated external exact-anchor ingress; make proposal/effect IDs carry risk-proportionate typed bindings and make TaskSpecAuthority validate SEND/PAYMENT/DELETE/SHARE field groups | remove SemanticAudit's “any material exact anchor passes” shortcut; exact SourceAnchor remains provenance-only; no graph/store/service or second semantic owner | `P0-E2`–`P0-E4` | three focused regressions: direct explicit send without span admitted; indirect attachment recipient clarifies; amount-only payment clarifies; page-authority and operation-downgrade rejection reuse the same suite | **completed (2026-08-05)** — direct/indirect/typed/confirmed binding forms, per-effect coverage, binding digest and typed clarification/policy failures are on the default authority path |

### P0-D — Required redlines without a test-building project

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P0-D1` | Add one data-driven `tests/architecture/test_runtime_redlines.py` covering omitted target/state fields, presentation invariance, conflict, multi-binding, raw-text execution read-set, output closure and realization test-double equivalence | consolidate equivalent scattered architecture assertions; do not create one test file per invariant or claim test doubles are a production lazy/indexed implementation | `P0-A4`, `P0-B4`, `P0-C5`, `P0-E4` | one parametrized matrix plus existing vertical behavior suites | **completed (2026-08-05; P1 boundary row added 2026-08-06)** — the shared matrix guards logical layout invariance plus recovery/committer/provider ownership; current production Catalog remains eager |

## 6. P1–P5 execution table

### P1 — Direct plan, loop evaluation and control-plane containment

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P1-P1` | Make `task_plan_contracts.py::TaskPlan` store typed StepSpec directly and migrate canonical consumers | delete default StepSpec→SubgoalSpec→StepSpec converters; no canonical plan passes through SubgoalSpec | P0-B | one composite criterion/value round-trip sentinel + conversion absence scan | **completed (2026-08-05)** — canonical TaskPlan stores immutable StepSpec tuples directly; binder/projector round-trip and their path-only tests are deleted |
| `P1-P2` | Strengthen `TaskPlanAuthority` in `task_plan_contracts.py`; move planner policy to `task_planner.py` | binder/projector cannot admit or invent plan semantics | P1-P1 | reuse plan validation tests; one stale-observation rejection | **completed (2026-08-05)** — TaskPlanAuthority alone validates identity/DAG/budgets/current observation and state basis, then binds version/supersession; planner policy is authority-free in `task_planner.py` |
| `P1-P3` | Refactor `task_plan_flow.py` and `task_plan_progress.py` to facts/bindings/verified step records | delete completed-subgoal carry-forward and internal Subgoal progress ownership; any external adapter is one-way and expiry-bound | P1-P2 | one replan-preserves-facts vertical case + legacy progress import scan | **completed (2026-08-05)** — progress namespaces are facts/bindings/recent outcomes/durable evidence/VerifiedStepRecord; replan preserves records without reinserting steps |
| `P1-E1` | Add `verification/loop_evaluator.py` and `verification/step_completion.py`; integrate typed action/step/task results in `progress_phase.py` | mechanical provider/report cannot own root completion | P0-A, P1-P1 | one receipt≠effect≠step≠task vertical case | **completed (2026-08-05)** — pure LoopEvaluator produces distinct action-effect, step-completion and task-completion results; RuntimeCommitter remains the only writer |
| `P1-E2` | Implement four-state ObservationContinuation in `active_perception.py` and `perception_phase.py` | remove unconditional recapture/repeat paths | P0-B, P1-E1 | one parametrized continuation decision test | **completed (2026-08-05)** — REUSE/AUGMENT_TARGETED/RECAPTURE/WAIT_AND_RECAPTURE are perception-owned; fresh reusable captures flow into the next loop without immediate duplicate capture |
| `P1-C1` | Move `_available_action_recovery_kinds` and other failure classification from `coordinator.py` to `recovery_owner_dispatcher.py`/`recovery_phase.py` | Coordinator contains no domain failure policy | P1-E1 | existing recovery vertical suite; one forbidden-import/AST boundary | **completed (2026-08-06 closure)** — RecoveryStage owns classification, handoff exhaustion/error mapping and typed routing; RecoveryObservationEvaluator/RecoveryActionEvaluator own outcome verification and settlement; RuntimeCommitSession is lifecycle-only |
| `P1-C2` | Move RuntimeCommitSession lifecycle to `runtime_loop_phase.py` and read projections to new `runtime_state_projection.py`; leave writes in `runtime_committer.py` | RuntimeCommitter contains no evaluation/session/view algorithms | P1-E1 | existing coordinator/committer suite; no new scenario unless a failure is exposed | **completed (2026-08-06 closure)** — RuntimeCommitter's handoff/action recovery algorithms were deleted; it only validates and applies typed transitions/events/completion. ProgressStage is a 458-line façade over observation/repair, completion evaluation and TaskSkill collaborators; the 1,486-line legacy task_planning owner was deleted in favor of a 207-line edge adapter |

### P1 authoritative crosswalk (2026-08-07)

The evolution authority uses target-capability IDs `P1-1`–`P1-7`; the execution
rows above group implementation slices and are not a renumbering. The two
control-plane rows are supplemental containment work.

| Evolution-plan ID | Execution row(s) | Current status |
|---|---|---|
| `P1-1` direct typed StepSpec plan | `P1-P1` | complete |
| `P1-2` single TaskPlan admission/version owner | `P1-P2` | complete |
| `P1-3` remove obligation-shaped planning and bind plans to current observation | `P0-E4` + `P1-P1`/`P1-P2`/`P1-P3` | complete; source graph left the default path, TaskPlanAuthority validates current observation/state basis, and progress no longer reinserts plan shape |
| `P1-4` loop-native evaluator | `P1-E1` | complete |
| `P1-5` four-state observation continuation | `P1-E2` | complete |
| `P1-6` clause/span/coverage to optional audit | `P0-E1`–`P0-E4` | completed earlier as the thin-source cutover |
| `P1-7` canonical requirement refs on StepSpec | `P3-4` | traceability and the MVP action-semantics subsumption are closed through `P4-7` / `P4-C1` |

`P1-C1` and `P1-C2` harden recovery/commit ownership; they do not add or replace
an evolution-plan P1 target capability.

### P2 — Criterion and evidence

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P2-1` | Freeze canonical AST/operators in `criteria.py` and policy types in `verification/contracts.py` | no source-specific criterion subclasses or prose fallback | P1-E1 | one parametrized operator/policy matrix | **completed (2026-08-06)** — immutable Predicate/AllOf/AnyOf/Not/OpenSemantic contracts, registered vocabulary, orthogonal satisfaction/validity/assurance policy and pure typed recursive evaluation are canonical; unsupported/no-evidence remain UNSUPPORTED/UNKNOWN without model or prose fallback |
| `P2-2` | Add `verification/predicates.py` and focused providers under `verification/providers/` for structural, API/device/WoT, artifact and external evidence | providers return facts/metadata only | P2-1 | one provider contract suite with shared cases | **completed (2026-08-06)** — one provider contract is grouped into structural/resource/artifact modules; providers only select typed facts/metadata, material conflict remains CONFLICT, insufficient/policy-rejected evidence is typed UNKNOWN/STALE, and weak/model-only evidence cannot satisfy authoritative final recheck |
| `P2-3` | Add bounded recent causality and durable evidence contracts in `runtime_evidence.py`; expose logical namespaces through `task_plan_progress.py` | current observation facts do not become durable automatically | P2-1 | one STATE_HOLDS vs ACTION_CAUSED and one epoch-validity case | **completed (2026-08-06)** — current facts are epoch refs, recent causal outcomes require exact contract/receipt/pre/post/effect evidence and use a bounded index, and only typed artifact/resource/transaction/human records enter the small durable store; TaskProgress stores these records without observations or plan history |
| `P2-4` | Add optional `verification/providers/model.py` and human evidence adapter only after mechanical gaps are measured | high-risk external effect cannot complete with model-only evidence | P2-2 | only add tests when a real open-semantic use case is admitted | deferred |

### P2 authoritative crosswalk (2026-08-06)

The architecture plan uses seven P2 capability IDs; the execution table above
groups implementation slices and therefore is not a renumbering of those
capabilities.

| Architecture-plan ID | Execution-table row | Current status |
|---|---|---|
| `P2-1` Criterion AST | `P2-1` | implemented for step completion; strict `StepSpec` stores only canonical `CriterionExpr` and rejects legacy criteria, which are canonicalized at dated provider/benchmark ingress |
| `P2-2` CriterionPolicy | `P2-1` | implemented; current-contract and latest-final-recheck admission are enforced |
| `P2-3` causal evidence | `P2-3` | implemented and wired to the current contract; subject, before/after value, source, assurance and effect identity survive projection |
| `P2-4` three evidence locations | `P2-3` | implemented and consumed by `LoopEvaluator` |
| `P2-5` mechanical providers | `P2-2` | implemented and owned by `PredicateEvaluator`; surface and artifact admission are fail-closed |
| `P2-6` model/human providers | execution `P2-4` | deferred until a measured mechanical gap exists |
| `P2-7` OpenSemanticResolver | no execution row yet | demand-gated; `UNSUPPORTED` now routes to typed `OPEN_SEMANTIC_UNRESOLVED` clarification/gap without model fallback |

Overall **P2 core is complete**: the canonical mechanical step-completion
cutover and strict canonical ingress are closed. Action/task evaluation retain
their prior owners; P2-6 and the full P2-7 resolver remain demand-driven
extensions rather than core closure gates.

### P3 — Stable TaskSpec v2

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P3-1` | Freeze TaskSpec v2 and TaskSpecAuthority in `task_intake.py` / `task_spec_authority.py`: stable authorization/constraints/forbidden effects/success, no steps/current UI, and Authority-issued `AdmittedTaskSpec` at Runtime/API ingress | no goal-only/raw-task canonical ingress, execution-shaped TaskSpec, retained evaluation cache, or alternate TaskSpec writer | P0-E, P2-1 | construction/ingress plus current/recent/durable evidence-lifetime and final-recheck cases | **completed (2026-08-06; seventh redline reverified)** — typed success root/leaf policies, admitted-task capability, evidence lifetime re-admission, authoritative final recheck, and typed construction failures are cut over |
| `P3-2` | Keep `SemanticAudit` risk-triggered and pass/veto/clarify-only; default intake remains `SourceEnvelope → MinimalIntentProposal → TaskSpecAuthority` | no default clause/claim/obligation graph, planning-shape writer, capability grant, or TaskSpec patch from audit | P0-E, P3-1 | one ordinary no-audit path plus one conflict veto/clarify case | **completed (2026-08-06)** — default claim/obligation owners are deleted and optional audit cannot write accepted meaning |
| `P3-3` | Freeze risk-proportionate typed `MaterialBinding` plus selective `SourceAnchor`; direct explicit values need no synthetic span, indirect unstructured values require exact excerpts | no second material registry, any-anchor shortcut, or provenance proof treated as capability/approval/grounding | P0-E5, P3-1 | direct/indirect/typed-external and operation-specific field-coverage matrix | **completed (2026-08-06)** — material values fold into canonical requirement/input payloads with stable binding refs/digest |
| `P3-4` | Give every material `TaskRequirement` one canonical identity and carry admitted requirement/effect refs through `StepSpec` / `task_plan_contracts.py` | ID possession is traceability only; reject missing refs and do not claim action-time semantic legality | P3-1–P3-3, P1-P2 | lossless requirement/input schema plus read-only/effectful StepSpec trace cases | **completed (2026-08-06; semantic closure through P4-C1 on 2026-08-07)** — canonical requirements, StepSpec refs and semantics-required typed subsumption are cut over |
| `P3-5` | Bind `SourceContextView` to admitted requirement/material-binding/anchor IDs in `source_context.py`; return typed TaskSpecGap | no downstream patch/reinterpret path; direct explicit bindings do not acquire synthetic spans | P3-1–P3-4 | one allowed planner context and one prohibited execution read-set case | **completed (2026-08-06; second redline reverified)** — context projects only associated anchors/digest and execution consumers remain denied |
| `P3-6` | Freeze stable required `OutputSpec` identity, materialization criterion and source-binding policy in `verification/contracts.py` / TaskSpec admission | declaration metadata cannot enter actual result namespace or prove task completion | P3-1, P3-3–P3-4 | required-output schema/admission and declaration-not-result sentinel | **closed through P4-C1 (2026-08-07)** — actual source-bound materialization, digest, lineage and privacy fields are required |

P3's common exit gate deleted compatibility `TaskSpec.source_claims`/`obligations`,
legacy criterion/task-plan providers and graph-shaped default intake. Remaining explicitly
named external `legacy_run_request` consumers are P5-3 edge debt, not a P3 authority.

### P4 — Rolling task planning and strict step choice

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P4-1` | Separate `task_plan_flow.py` from new `step_choice_flow.py`; define distinct typed requests/responses | neither flow accepts the other's authority object | P1, P3 | one import/signature boundary and one two-horizon vertical case | **completed (2026-08-06)** — TaskPlanFlow and StepChoiceFlow own separate typed horizons; boundary and two-stage reuse tests pass |
| `P4-2` | Move strict provider implementation from `generalist_planner.py` to focused `task_planner.py` and `step_choice_planner.py` | delete internal StateKernel/BrowserSnapshot/ActionChoiceBuilder signatures and converters; any external planner adapter translates one-way into typed requests and has an expiry | P4-1, P0-C | reuse planner behavior tests; delete legacy signature tests; add import-direction scan | **completed (2026-08-06; sixth redline closure reverified)** — strict providers accept only TaskPlanningRequest/ChoicePlanningRequest; `PlanningStage` and default composition have no proposal fallback or duck-typed `select` compatibility; strict BrowserGym preserves Authority-admitted task success, constructs the two strict providers, records official reward only as independent benchmark evidence, and its runner import no longer loads generalist planner/context or legacy request code; legacy BrowserGym planner/episode code is isolated in `browsergym_compatibility_episode.py` for P5-3 deletion |
| `P4-3` | Keep one logical full `ActionChoiceCatalog`, then deterministic narrowing and a bounded `ChoicePage`; add typed paging/retrieval only when measured | presentation limits/cursors cannot change Catalog membership; hidden IDs are never selectable | P4-2, P0-C | 0/1/N, hidden-ID, oversized/effectful-truncated-page and continuation cases | **completed (2026-08-06)** — logical membership precedes presentation; 0/1/N is deterministic, hidden IDs are rejected and oversized pages fail closed |
| `P4-4` | Make `planning_request_serializer.py` a pure provider-format projection | no request/context serializer reconstructs task/step/progress/observation authority | P4-2–P4-3 | one serializer snapshot and authority read-set/import boundary | **completed (2026-08-06)** — serializers expose only admitted/displayed IDs and do not rebuild Runtime authority |
| `P4-5` | Freeze the bounded `ChoicePresentation` semantic contract: target/state/requirement/effect/conflict/risk/reason, with no binding, hidden ID or raw source text | presentation cannot invent route/locator/backend or silently omit required semantics for displayed choices | P4-3–P4-4 | one lossless displayed-choice contract and one prohibited binding/raw-text case | **completed (2026-08-06)** — displayed choices retain Runtime-derived risk/destination and required bounded semantics while execution bindings remain hidden |
| `P4-6` | Add typed planning trigger/reuse/direct fast paths in `planning_phase.py` | no TaskPlanner call while current active step remains feasible | P4-2 | one parametrized trigger decision test | **completed (2026-08-06)** — typed initial/reuse/exhausted/infeasible/assumption/environment/task-revision triggers are explicit; active feasible plans reuse without a planner call and completed steps cannot be reinserted |
| `P4-7` | Retain semantics-required typed guards without turning TaskPlan into a universal field DSL | matching IDs alone cannot authorize unrelated mutation; ordinary click does not need fabricated destination/usage | P3, P4-1–P4-6 | read→mutation denial plus valid ordinary click/read | **SUPPORTING FOUNDATION** — no claim of exhaustive destination/function/usage policy; not a sixth P4 invariant |

`P3-4` and `P4-3`–`P4-6` remain complete for their deliberately narrow owners:
requirement traceability, Catalog/presentation/serialization, and planning
triggers respectively. They do not prove `P4-7` semantic admission or the P4-G
transaction/dispatch cutover.

### P4-G — Concrete action authority and high-risk governance closure

The typed G1–G3 foundation remains useful, while the MVP consumes only the
final-contract/approval-hash and no-blind-retry portions of G4–G6. Production-
security transaction isolation, context and release attestation are explicitly
outside the active queue.

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P4-G1` | Add focused `effect_authority_contracts.py` for distinct `EffectAuthorizationScope` and `RuntimeEffectSignature`, plus `ResourceScopeRef`, named `ParameterAuthorization`, `Externality`, `Reversibility`, `AuthorityStatus` and immutable proof with evaluator-policy version; update intake/TaskSpec admission so effect requirements own only the scope payload | do not add an effect graph, TaskType enum or second requirement registry; TaskSpec cannot store current action/backend/binding/signature; remove coarse `operation_class`, free-form label and unordered scalar values as authority in the same final cutover | P3 | one schema/admission matrix for operation + resource/destination + named slots + externality/reversibility | **retained foundation; MVP evidence passed** — typed scope/signature/risk/proof contracts are distinct and versioned; no production-security transaction claim |
| `P4-G2` | Add focused `action_effect_classifier.py`; extend canonical observation and existing DOM/AX/Visual/SVG/WoT/API/Device adapters to emit typed operation/effect/externality/reversibility/risk/assurance assertions; derive Runtime risk as the conservative max of effect, externality, reversibility, resource, amount/recipient, capability, source uncertainty and conflict | source hints remain evidence, never sole authority; missing material classification does not default effectful action to LOW; Text/VLM may raise risk or request observation/clarification only | G1, P0-B | reuse cross-surface fixtures plus one unknown-risk/conflict/assurance and VLM raise-only matrix | **retained foundation; MVP evidence passed** — broader adapter/context/capability coverage remains demand-gated C2 hardening |
| `P4-G3` | Rewrite `action_choice_authority.py` as pure `EffectAuthorizationScope ⊒ RuntimeEffectSignature` subsumption; move semantic generation out of 1,143-line reviewed-baseline Catalog into `action_choice_builder.py`; keep membership/digest/query in Catalog; presentation carries proof-derived effect summary and authorization/generation reasons | delete Boolean scope proof, value-set admission, label authority and Planner-owned role/effect/risk branches; enabling policy is restricted to requirement-bound observe/focus/hover/scroll/non-commit UI/allowed-domain navigation/wait/local reversible draft and proves no external commit or unauthorized disclosure | G1-G2 | one data-driven redline: operation mismatch, swapped named params, label alias, source assurance, enabling disclosure/UNKNOWN effect, DENY vs UNPROVEN | **retained foundation; MVP evidence passed** — Catalog ALLOW/tri-state core and C5 default cutover are closed; C2 breadth remains deferred |
| `P4-G4` | Finalize complete executable contract before policy/approval; seal material parameters and payload in one hash | delete copied-choice-fields-only gate and any approval-before-encoding path | G3 | encoder-injected material parameter denial plus approved/executed hash equality | **MVP CODE INVARIANT IMPLEMENTED (2026-08-07)** — injected `recipient=Bob` is rejected; approval, attempt, Executor and final ActionContract hashes are identical |
| `P4-G5` | Preserve typed receipt/effect separation and uncertain-effect no-blind-retry | no site/workflow enumeration or transaction-isolation subsystem | G4, P2 | existing uncertain-effect/recovery verticals | **MVP CORE CLOSED** — uncertain effect routes to post-state inspection/block/handoff; permit/fencing/collateral hardening is non-blocking future work |
| `P4-G6` | Keep the default finalized-contract route and isolate core fallback | release suites remain offline and optional | G1-G5 | focused imports/callability + full suite + core benchmark | **MVP CLOSED** — default-route evidence passes; immutable multi-suite attestation remains a release concern |

### P4-C — P4-minimum closure

Only five invariants block P5: finalized immutable contract, exact
approval/execution hash, stale-preflight zero calls, verifier-backed completion,
and uncertain-effect no-blind-retry. C2 and the production-hardening portions of
C4/C5 are not in the active queue.

Focused checks, full pytest/static checks, and the core benchmark are evidence
for those five invariants and the default-route cutover. The benchmark adds no
sixth invariant; all applicable evidence now passes, so P4 is closed in MVP
scope.

Final P4-MVP code/call-boundary inventory (keep current during P5; a future
focused module may replace, but not duplicate, the listed owner):

| Slice | Initial files/call boundaries in scope |
|---|---|
| `P4-C0` | `coordinator.py::RuntimeFeatures`, `composition.py`, `contract_execution_loop.py`, product CLI/API composition, and benchmark-only `benchmarks/local.py`/evolution profile entrypoints |
| `P4-C1` | `perception_session.py`, `unified_observation.py` and acquisition adapters; `task_plan_contracts.py`; `verification/contracts.py`, `verification/task_completion.py`, `progress_phase.py`, `task_plan_progress_flow.py`, and result commit/projection callers |
| `P4-C2` | future hardening only; no active P4/P5 blocker |
| `P4-C3` | `action_contract_builder.py`, `action_contract_authority.py`, `contract_execution_loop.py`, and the contract/preflight portions of `execution_phase.py` |
| `P4-C4` | existing serial execution, typed receipt/effect and uncertain-effect recovery owners only |
| `P4-C5` | `composition.py` and default callers/imports; core tests and benchmark only |

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P4-C0` | Gate/preflight rejection is a product zero-call boundary | benchmark ablations stay outside product composition | current baseline | stale contract, missing capability/dependency, invalid or uncommitted contract all assert `executor.calls == 0` | **MVP CLOSED (2026-08-07)** — default-routed implementation plus focused product zero-call tests |
| `P4-C1` | Completion requires verifier evidence and real required output; artifact must exist and match SHA-256 | receipt/ACK/prose/metadata and nonexistent artifact cannot produce DONE | C0 | export has required OutputSpec, receipt plus authoritative API final evidence, file SHA binding, and `TaskCompleted.artifact_ref`; receipt/nonexistent/mismatched artifact fail closed | **MVP CLOSED (2026-08-07)** — typed local export path closed; opaque/remote artifact refs fail closed pending a future resolver; no exhaustive TaskPlan-field or adapter-coverage claim |
| `P4-C2` | **Future hardening only:** multi-account/profile/tenant live proof, full surface/coordinate identity, provider/schema manifest and multidimensional provenance | must not become a P4/P5 blocker or a new platform without benchmark/deployment evidence | none | admitted only with a new scenario-specific threat model | **DEFERRED / NON-BLOCKING** |
| `P4-C3` | Materialize and freeze the complete executable contract before policy/approval; Executor sees the same hash | encoder cannot add/change typed material parameters after choice authorization; no partial patch | C1, G1–G3 | injected `recipient=Bob` denial; approval presents final `contract.parameters`; approval token, attempt, Executor and final contract hashes equal | **MVP CLOSED (2026-08-07)** |
| `P4-C4` | Preserve trusted in-process serial execution, typed receipt/effect separation and uncertain-effect no-blind-retry | no concurrent-worker, revocation-transaction, clone-resistant permit, global registry, fencing or collateral subsystem in MVP | C3, P2 | reuse uncertain-effect/recovery verticals | **MVP CORE CLOSED; HARDENING DEFERRED** |
| `P4-C5` | Default product composition uses the finalized-contract path; core fallback remains isolated | immutable manifest and AgentDojo/WASP/OSWorld attestation are release work | C0/C1/C3/C4 | stable Task API executes pricing/settings/export 3/3; fixture v2.1.0 held-out pricing uses semantic target IDs; 21-run core report fails closed on missing variants/denominators/expected traces and passes with `acceptance_errors=[]` | **MVP CLOSED; RELEASE ATTESTATION DEFERRED** — latest full/static suite and default-route gates pass |
| `P4-R0` | Optional narrow durable dispatch journal only for a hard-crash claim | not a P4/P5 prerequisite | explicit future claim | crash-window tests when admitted | **DEFERRED / NON-BLOCKING** |

### P5 — Bounded state, interruption recovery and legacy deletion (**admission unblocked; not started**)

The five P4-minimum code invariants, full/static suite, and fresh core benchmark
now pass. The benchmark is default-route closure evidence for the same five
invariants—not a sixth invariant. P5 admission is therefore unblocked, but no
P5 slice has started. C2 hardening, production-grade C4/C5 machinery and P4-R0
do not block it. A later hard-crash
or multi-tenant claim must add its own local prerequisites without reopening the
GUI MVP baseline.

Non-blocking benchmark debt is recorded without reopening P4: zero-opportunity
rates should render as `N/A`, and the `no_recovery` ablation should eventually
require its expected stale-state failure class/trace rather than any failure
delta.

| ID | Deliverable and exact files | Legacy deletion/isolation | Depends on | Minimal verification | Status |
|---|---|---|---|---|---|
| `P5-1` | Add lightweight `run_ledger.py` namespaces for facts, bindings, recent outcomes and durable evidence; keep distinct lifetimes | no separate database/service per namespace | P1–P4, P4-C5 | one lifetime/invalidation matrix | not started |
| `P5-2` | Finish `observation_store.py` + Catalog refs; shrink StateKernel to current identities and committed progress | no copied presentation or full observation graph in StateKernel | P0-B/C, P5-1 | one epoch/catalog stale-reference case | not started |
| `P5-R1` | Add focused `run_checkpoint.py` with an immutable version/identity envelope containing only canonical refs/digests—including budget/control/trace/effect/lifecycle refs—plus the exact `last_committed_observation_ref`; select a focused persistence implementation only after the fault model is admitted | do not pickle `StateKernel`, copy TaskProgress/RunLedger/observation graphs, persist raw source/context or live handles, create a database/service per namespace, or freeze file/database technology in this plan | P5-1, P5-2, P4-C5 | schema round-trip, missing/mismatched referenced object and incomplete/corrupt checkpoint-generation rejection | not started |
| `P5-R2` | Make `RuntimeCommitter` expose an immutable refs/digests-only `CommittedCheckpointSnapshot` after admitted safe-boundary commits: waiting approval/clarification, committed pre-effect dispatch state, receipt/uncertain outcome, post-action evaluation/progress and terminal | RuntimeCommitter cannot absorb serialization, storage, restore or routing policy; Coordinator/RuntimeCommitSession may sequence persistence but cannot assemble/modify snapshot state; no second snapshot writer or per-stage persistence API | P5-R1, P1-C2, P4-C4 | reuse committer/event-order tests and add one boundary-order/ref-integrity sentinel | not started |
| `P5-R3` | Add focused `runtime_resume.py` as pure validation/routing plus a typed Coordinator resume ingress. Validate TaskSpec/plan/progress/ledger refs, `last_committed_observation_ref`, budget/control/trace/attempt/receipt/effect refs and policy/profile/schema/code digests; return only `REJECT`, `START_FRESH_SESSION`, `ROUTE_EFFECT_RECONCILIATION` or another typed route | `runtime_resume.py` does not reconstruct StateKernel, perform effect reconciliation, plan, authorize, approve, dispatch or complete; never restore DOM/page/backend handles; stale Catalog/contract/approval is invalidated and rebuilt/reapproved by existing owners after fresh capture | P5-R2, P4-C5 | safe pre-dispatch route, unknown-effect reconciliation route, stale identity rejection and proof that no executor/authority owner is called by validation | not started |
| `P5-R4` | Add separate cooperative interruption and cancellation through the task API, Coordinator stage boundaries and final pre-dispatch boundary: `INTERRUPT_REQUESTED → SUSPENDED` is resumable, while `CANCEL_REQUESTED → CANCELLED` is terminal only after a safe stop and no unresolved external effect. A request during atomic dispatch records `MAY_HAVE_OCCURRED` and enters reconciliation before either state can settle | a service status flip is not proof that execution stopped; neither control request may interrupt an executor mid-transaction, classify an unknown dispatch as `NOT_DISPATCHED`, bypass final recheck, resume `CANCELLED`, or resume `SUSPENDED` without a valid checkpoint | P5-R3 | reuse task API/recovery tests plus one interrupt/cancel state matrix; no standalone control test platform | not started |
| `P5-3` | Remove only documented external/public compatibility adapters whose consumers have migrated, including `browsergym_compatibility_episode.py`; verify earlier slices already deleted all internal legacy owners | P5 cannot accept internal deletion debt from P0–P4; no parallel owner remains importable from production composition | P5-R4 and all earlier slices | adapter consumer inventory, architecture import scan and normal product vertical suite | not started |
| `P5-4` | Final containment pass over `coordinator.py`, `runtime_committer.py`, `execution_phase.py` (currently 1,316 lines), strict `browsergym_episode_runner.py` (currently 1,082 lines after legacy extraction), planners and builders | any remaining multi-owner file must split or carry a dated removal gate; execution and strict BrowserGym lifecycle/metrics are the current production god-file risks | P5-3 | reuse boundary tests; no test added for line count alone | not started |

#### P5-R interruption-state contract

The smallest recoverable unit is one task run at a committed Runtime boundary.
The existing same-process Local approval continuation is retained as a fast
path, but it is not evidence of crash/restart recovery. BrowserGym matrix
resume remains an offline benchmark facility that reuses completed episode
results; it cannot restore an interrupted product Runtime episode.

The names below are a read-only recovery projection, not a second truth owner:
`NOT_DISPATCHED` requires canonical `DispatchState.NOT_SENT` evidence;
`MAY_HAVE_OCCURRED` covers `SENT_UNKNOWN`, a missing receipt, or
`SENT + STILL_UNCERTAIN`; the two `CONFIRMED_*` values require identity-bound
effect settlement. A control-plane status cannot synthesize any of them.

| Last durable effect state | Resume rule |
|---|---|
| `NOT_DISPATCHED` | open a fresh session, recapture, rebuild the Catalog/contract and continue only after ordinary authority and freshness gates pass |
| `MAY_HAVE_OCCURRED` or dispatch/receipt identity is incomplete | perform effect-specific authoritative post-state reconciliation first; do not retry, reroute or change backend |
| `CONFIRMED_NOT_OCCURRED` | a new contract may be considered only through normal idempotency, authority, approval and preflight policy |
| `CONFIRMED_OCCURRED` | continue causal verification/completion from admitted evidence without replaying the action |

`RunCheckpoint` stores references and digests, not typed object graphs: admitted
TaskSpec and TaskPlan refs/revision digests, TaskProgress/RunLedger refs, the
exact `last_committed_observation_ref`, pending control/contract/approval refs,
attempt/transaction/receipt/effect/budget/trace refs, and
policy/profile/schema/code digests. Every referenced canonical object needed after restart
must resolve from the same committed checkpoint generation or an immutable
registered store. The physical persistence mechanism remains deliberately
unfrozen. Resume rejects a missing or mismatched dependency rather than guessing
or silently starting from stale state.

## 7. Test portfolio policy

### 7.1 Current evidence and decision

Audit baseline on 2026-08-06 at the latest reviewed push:

| Measure | Current observation | Decision |
|---|---:|---|
| collected tests | 930 | high count alone is not a deletion reason |
| test files | 107 | consolidate only where ownership/failure signal is duplicated |
| full local runtime | 15.52 seconds | acceptable; no performance-driven rewrite |
| test/source LOC | about 31.6k / 53.9k | ratio is no longer near 1:1; maintenance risk is concentrated, not suite-wide |
| largest test files | `test_browsergym_adapter.py` 2,648; `test_coordinator.py` 1,681; `test_planning.py` 1,230 | prune/split only while their production owner is already changing |

The suite is not too slow, but parts are too historical and text-coupled. Test
cleanup therefore follows owner cutover and failure-localization value, not an
arbitrary target count.

### 7.2 Test admission rule

A new test is allowed only when all are named:

1. the concrete failure it localizes;
2. the canonical owner whose behavior failed;
3. why an existing test cannot cover it;
4. the cheapest useful level: contract, focused behavior, or vertical path;
5. its retirement condition if it protects a compatibility seam.

Default per production slice: reuse the affected suite, add at most one
contract/boundary sentinel and one vertical behavior case. More requires a
specific uncovered failure matrix, not a desire for exhaustive permutations.

Do not add tests solely to freeze prose, line counts, call-site counts, current
class names, or historical admission wording when an import boundary, typed
contract, manifest rule, or real behavior test can locate the same failure.

### 7.3 When to run what

| Checkpoint | Required checks |
|---|---|
| inner edit loop | the one focused test that exposes the current failure |
| task row complete | focused owner suite + relevant boundary sentinel |
| slice cutover | affected contract/vertical/safety suites, deletion/import scan, then full pytest once after the default-route switch |
| phase checkpoint, commit or push | reuse the fresh cutover result when no file changed; otherwise rerun full pytest, Ruff and diff checks |

Full pytest is not required after every small edit. Repeated green runs without
a changed failure surface are test activity, not delivery evidence.
The repository pytest configuration includes `src`, `tests`, and the repository
root, so the canonical local entrypoint is simply `pytest -q`; collection does
not depend on an operator remembering a `PYTHONPATH` override.

### 7.4 Cleanup queue

| ID | Scope | Action | Exit |
|---|---|---|---|
| `T0` | former `tests/test_horizontal_architecture_governance.py` | **complete/deleted**; do not recreate a prose-coupled replacement | current documentation gate + compact runtime redline matrix remain sufficient |
| `T1` | tests bound to SourceLedger, Subgoal, old completion and planner compatibility | delete in the same slice that removes the owner; retain only explicit adapter contract until its dated removal | every compatibility test names a live adapter and removal gate |
| `T2` | repeated model-port local HTTP fixtures | share transport fixture/fake clock; keep one real local transport sentinel; remove fixed shutdown/backoff cost from unit cases when this module is next touched | retry semantics remain covered without repeated wall-clock waits |
| `T3` | `test_browsergym_adapter.py`, `test_coordinator.py`, `test_planning.py`, and P4-G-touched `test_action_choice_catalog.py` | consolidate shared setup and parameterize equivalent failure matrices during the owning production slice, not as a standalone rewrite | fewer duplicated fixtures/assertions with unchanged boundary coverage |

`T0` is time-boxed and may run as the one independent horizontal containment
slice. `T1`–`T3` are performed only while their production owner is already
being changed; they must not delay a correctness cutover to chase test count.

## 8. Slice admission and completion checklist

Before starting:

- canonical owner, input and typed output are named;
- exact files to create/modify/delete are listed in the row;
- legacy owner and same-slice deletion/isolation gate are named;
- canonical modules do not import legacy modules or compatibility adapters;
- no new→old→new conversion, dual read/write or shadow owner is introduced;
- no target file receives a second unrelated responsibility;
- test action is `REUSE`, `ADD-SENTINEL`, `ADD-VERTICAL`, `CONSOLIDATE`, or
  `DELETE-WITH-OWNER` rather than an open-ended “add tests”.

Before marking done:

- default composition calls only the canonical owner;
- legacy code and its tests are deleted or behind an explicit adapter/removal gate;
- every surviving adapter is external-ingress-only, one-way and before its last-allowed slice;
- TaskSpec authorization, approval binding and completion authority did not expand;
- TaskSpec effect scope and Runtime concrete signature are distinct typed contracts; neither is reconstructed from objective/label/Planner fields;
- TaskPlanAuthority proves typed semantic subsumption for each StepSpec; requirement-ID membership alone is not semantic admission or execution authority;
- SourceCoverage comes from the acquisition adapter for the exact epoch/scope/budget, and missing coverage remains UNKNOWN;
- concrete action proof binds operation, canonical resource/destination, named parameters, actual candidate/binding, externality/reversibility, risk/assurance, evaluator-policy version and current epoch; UNKNOWN is not LOW;
- Text/VLM may only raise risk or request targeted observation/clarification; it cannot produce ALLOW, lower risk or create authorization;
- Task Authority revalidates the actual ActionContract rather than fields copied from the selected choice; approval never repairs DENY/UNPROVEN;
- MVP approval presentation is derived from the final contract and displays its final `contract.parameters`; any sealed parameter/hash change invalidates the token. A production-grade disclosure schema for every resource/context/backend field is not claimed;
- full executable contract is materialized before policy/approval; stale preflight is zero-call and the approved/executed hashes are equal;
- the complete RouteBinding/contract projection is secret-free; auth/signature/signed-URL material is closed-allowlist dispatch-late-bound and never enters trace/checkpoint;
- transport receipt, external effect, step, plan and task results remain distinct;
- required output closure consumes actual typed OutputMaterialization records, not OutputSpec metadata, arbitrary mappings or Planner prose;
- Planner/Executor/Evaluator do not write StateKernel;
- Coordinator and RuntimeCommitter contain no new domain algorithm;
- focused and slice-level checks identify failures at the owning boundary;
- full suite ran once at the cutover checkpoint;
- implementation status records the current working-tree truth; immutable evidence is required only for release/claim publication.

## 9. Current execution order

| Order | Slice | Reason |
|---:|---|---|
| 1 | `P0-A` | close false-completion authority first |
| 2 | `P0-B` | establish canonical current state before rebuilding choices |
| 3 | `P0-C` | establish Runtime-owned legal action space and contract binding |
| 4 | `P0-E` | replace extraction-heavy default intake without coupling it to planning |
| 5 | `P0-D` | freeze the completed P0 boundaries in one compact matrix |
| 6 | `P1`–`P4` | completed core plan/evaluation/TaskSpec/strict-choice cutovers |
| 7 | `P4-G1`–`P4-G3` | **MVP EVIDENCE PASSED** — retain typed scope/signature/proof foundations; broader hardening is demand-gated |
| 8 | `P4-C0` | **CLOSED** — product safety containment and false-oracle replacement |
| 9 | `P4-C1` | **CLOSED** — verifier-backed typed local export output; no universal adapter/TaskPlan-field claim |
| 10 | `P4-C3` | **MVP CLOSED** — final contract materialized before approval; hash equality proven |
| 11 | `P4-C4` | **MVP CORE CLOSED** — serial typed receipt/effect and no-blind-retry; production hardening deferred |
| 12 | `P4-C5` | **MVP CLOSED** — default-route benchmark passes; release attestation deferred |
| 13 | `P4-C2` | **DEFERRED / NON-BLOCKING** — context/tenant/coordinate/provenance hardening |
| 14 | `P4-R0` | **DEFERRED / NON-BLOCKING** — only for an admitted hard-crash claim |
| 15 | `P5` | **ADMISSION UNBLOCKED; NOT STARTED** — no future-hardening blocker |

`P0-A5` and the P4-required P0-B behavior are complete. P4-G1–G3 remain retained
foundations; P4-G4–G6 contributed only their MVP subsets through P4-C3–C5.
P5 is admitted but not started, and its future vertical cutovers remain subject
to the one-writer/one-authority migration rules above.

## 10. Historical detail

The pre-consolidation 3,203-line queue is preserved at
[current-implementation-plan-pre-consolidation.md](archive/superseded-2026-08-05/status-snapshots/current-implementation-plan-pre-consolidation.md).
It is implementation history, not the active scheduler.
