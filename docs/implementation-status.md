# Implementation Status and Forward Gates

This file is the durable execution ledger for the milestones defined in
`project-plan.md`. Update it in the same change that adds implementation or
verification evidence. A milestone is complete only when every exit criterion
has reproducible evidence.

Status values:

- `pending`: not started or no implementation evidence
- `in_progress`: implementation exists but exit evidence is incomplete
- `done`: exit criteria are covered by code, tests, and reproducible commands
- `blocked`: external input or state is required

Live state is represented on separate axes; compound labels such as `done
locally` or `component done` are explanatory headings only and are not valid
milestone status values.

| Axis | Values | Purpose |
| --- | --- | --- |
| Milestone status | `pending`, `in_progress`, `done`, `blocked` | progress against the milestone's declared exit criteria |
| Completed scope | concise factual scope | what is actually implemented or verified |
| Evidence maturity | `none`, `protocol`, `injectable`, `normal_entrypoint`, `local_reproducible`, `ci_reproduced`, `immutable_empirical` | strongest current evidence level |
| Promotion status | `held`, `eligible`, `promoted`, `not_applicable` | whether broader claims or runs are authorized |
| Architecture admission | `pass`, `fail`, `waived`, `not_evaluated` | result of the horizontal gate for the change |
| Remote CI | `pass`, `fail`, `pending`, `not_run`, `disabled` | state of CI for the exact committed revision |

### Current Evidence Identity

| Field | Current value |
| --- | --- |
| Repository HEAD | Not self-recorded in this file; use `git rev-parse HEAD` as authority. Latest reviewed SAR-7 behavioral gate revision is `25ec6745ce08f6337c8d040cf1b31bd2a384ff6e`. Verifier-backed active-step progress commits live in `task_plan_progress_flow`; planner terminal requests and final success `TaskCompleted` commits live in `runtime_terminal`; TaskSkill progress is removed from default `StateKernel` authority; legacy pending/ODG progress state is removed from default `StateKernel`; bounded typed recent action outcomes replace the old string-signature action progress list. Clean SAR-7 PR breadth passed 12/12 at this revision. Fresh diagnostic completed 60/60 with 15/60 Runtime and external pass. SAR-9A extracts TaskPlan prepare / commit / trace-projection detail from `RunCoordinator.run_sync`; SAR-9B routes post-observation and post-TaskPlan current-state progress through `progress_phase.ProgressPhase`; SAR-9C moves TaskSkill exposure / activation / accepted-skill provenance and planner-decision awaitable resolution into `task_skill_phase.TaskSkillPhase`; SAR-9D moves PlannerDecision trace, semantic proposal validation, planner terminal handling, clarification, and legacy empty-decision classification into `planning_phase.PlanningDecisionPhase`; SAR-9E moves semantic / legacy contract binding, ContractBuilt / RouteSelected trace projection, progress guard handling, TaskSkill contract-requirement fallthrough, and preflight visual/SVG rebound binding into `contract_binding_phase.ContractBindingPhase`; SAR-9F moves preflight, approval, environment-drift recovery, authorization, and pending retry-contract validation into `preflight_phase.PreflightPhase`; SAR-9G moves action dispatch, receipt state/artifact recording, pending execution recovery completion, and receipt-failure recovery handling into `execution_phase.ExecutionPhase`; SAR-9H moves post-action observation, verification, evidence repair, ActionOutcomeRecorded, action-progress recording, postcondition trace, and route outcome recording into `verification_phase.VerificationPhase`; SAR-9I moves TaskSkill active-step verification, checkpoint/fallthrough traces, and no-TaskPlan TaskSkill terminal compatibility into `task_skill_progress_phase.TaskSkillProgressPhase`; SAR-9J moves grounding recovery completion, verifier-backed TaskPlan progress commit, task-completion verification, and final success commit delegation into `verified_progress_phase.VerifiedProgressPhase`; SAR-9K moves failed-verification terminal/recovery handling into `verification_failure_phase.VerificationFailurePhase`; SAR-9L moves observation capture, ObservationCaptured trace, pending post-state inspection, pending observation recovery completion, and perception-block terminal handling into `perception_phase.PerceptionPhase`; SAR-9M moves TaskPlan failure, TaskSkill activation failure, provider deferral, unexpected planner exception, and PlanningDecision failure recovery handoff into `planning_failure_phase.PlanningFailurePhase`. Focused and adjacent local gates passed. This is not PR breadth, fresh diagnostic, remote CI, or promotion evidence. Promotion remains held. |
| Latest admitted production repair revision | `d17a1f3` (`feat: integrate verifier-backed progress accounting`), Coordinator-integrated current-state completion; clean `66dae07` remains the latest useful pre-integration V-PRB-6B PR breadth diagnostic baseline |
| Latest PR breadth evidence revision | `25ec6745ce08f6337c8d040cf1b31bd2a384ff6e`: SAR-7 clean PR breadth completed 12/12 observed and 12/12 passed, with 0 Runtime failures, 0 external failures, no missing/unrun/invalidated/provider failure, and `official_score_claimed=false`. Evidence: `docs/evidence/runs/sar-7-behavioral-gate-25ec674/`. |
| Latest V-PRB-6A foundation | Core-only progress target contract foundation in `docs/change-admission/v-prb-6a-progress-target-foundation.yaml`; focused planning/governance/static gates pass, but a dirty-tree form-sequence diagnostic stayed negative. It remains `foundation_only` and is now compatibility-only under ODG-0. |
| Historical ODG experiment | `docs/change-admission/odg-0-obligation-driven-progress-architecture.yaml` records the superseded default-route proposal in which Canonical Obligation Graph was the target progress authority and TaskPlan an optional strategy. ODG-1 through ODG-9 remain immutable foundation/diagnostic history and advanced attribution is `EXPERIMENTAL_ONLY`; SAR-0 governs the current default target. No ODG foundation has Coordinator commit or finish authority. |
| Current simplified architecture decision | `docs/change-admission/s0-simplified-architecture-freeze.yaml`: the default production path is redirected to Runtime-owned active step progress plus independent task-level completion verification. ODG advanced attribution is retained as `EXPERIMENTAL_ONLY`; ODG-9 hookup, ODG-10 obligation progress commit, and ODG-11 finish-authority migration are stopped for the default path. |
| Current simplified core contracts | `docs/change-admission/s1-simplified-core-contracts.yaml`: `SourceReference`, criterion policies, `StepSpec`, `TaskPlanView`, `StepProgressView`, `ExecutionAttempt`, `VerificationResult`, and `ActionOutcome` are added as neutral foundation contracts. No Coordinator, StateKernel, Executor, Verifier behavior, TraceDag, PlannerContext, runtime authority, PR breadth, or promotion change is authorized by S1. |
| Current simplified step projection | `docs/change-admission/s2-legacy-step-compatibility-projection.yaml` plus `docs/change-admission/s2-1-step-projection-hardening.yaml`: current TaskPlan/Subgoal/PlanProgress can be projected into simplified Step contracts by exact ID only. The projector is read-only, rejects stale plan identity, lexical mapping, unknown progress IDs, completed-without-evidence progress, and unsupported typed evidence policy; completed plans project with no active step and have no completion authority. |
| Latest implementation-bearing local-equivalent baseline | `66747420c4d319d26a10a7c6fb6006871cf3310a` |
| Baseline local equivalent gate | pass at that implementation-bearing baseline: 957 tests, Ruff, mypy over 116 source files, `uv build`, Chromium smoke, BrowserGym bridge smoke, diagnostic benchmark smoke, Docker runtime-test, Docker benchmark diagnostic, Docker WoT conformance, and diff check |
| Current documentation-sync identity | documentation/evidence commits after `c382592` classify the V-PRB-6B negative rerun; later documentation-only sync commits inherit no broader runtime evidence unless their own gate is recorded in the change ledger |
| Current worktree local gate | must be checked for the active change; do not infer full local-equivalent or promotion evidence from an older implementation-bearing baseline |
| Architecture admission | mechanical gates passed for the recorded implementation-bearing baseline; SG7 targeted protected-family confirmation remains bound to clean repair revision `3d44a9d222decd1de272d7a4d3eb14b025a8738a`, while PR breadth/nightly/release promotion remains held |
| Semantic ownership review | `pending_review`: SG7 generic repair preserved the benchmark/authority hard boundaries, but introduced deterministic semantic fallback in Generalist Planner and value-entry lexical normalization in intent/task-planning surfaces; these are baselined as ownership-review debt rather than declared architecturally clean |
| Remote CI | disabled: GitHub Actions is intentionally closed for the current iteration, so no remote-green or remote-fail claim is made for the implementation-bearing baseline or later documentation-sync commits |
| Promotion status | held |

```yaml
status_alignment:
  snapshot: current
  state: passing
  meaning: not a one-time milestone closure

coordinator_reduction:
  interpretation: sar_9m_planning_failure_phase_extraction_local_candidate
  current_size_expected_for_stage: true
  within_ratchet: true
  current_lines: 1478
  run_sync_lines: 534
  method_count: 17
  actual_reduction_stage: sar_7_to_sar_9
  sar_9a_before:
    coordinator_lines: 2995
    run_sync_lines: 1993
    runcoordinator_methods: 19
  sar_9a_after:
    coordinator_lines: 2939
    run_sync_lines: 1940
    runcoordinator_methods: 19
  sar_9b_after:
    coordinator_lines: 2934
    run_sync_lines: 1936
    runcoordinator_methods: 19
  sar_9c_after:
    coordinator_lines: 2859
    run_sync_lines: 1869
    runcoordinator_methods: 19
  sar_9d_after:
    coordinator_lines: 2694
    run_sync_lines: 1701
    runcoordinator_methods: 19
  sar_9e_after:
    coordinator_lines: 2351
    run_sync_lines: 1363
    runcoordinator_methods: 19
  sar_9f_after:
    coordinator_lines: 2104
    run_sync_lines: 1136
    runcoordinator_methods: 18
  sar_9g_after:
    coordinator_lines: 2013
    run_sync_lines: 1043
    runcoordinator_methods: 18
  sar_9h_after:
    coordinator_lines: 1918
    run_sync_lines: 949
    runcoordinator_methods: 18
  sar_9i_after:
    coordinator_lines: 1804
    run_sync_lines: 859
    runcoordinator_methods: 17
  sar_9j_after:
    coordinator_lines: 1785
    run_sync_lines: 845
    runcoordinator_methods: 17
  sar_9k_after:
    coordinator_lines: 1748
    run_sync_lines: 806
    runcoordinator_methods: 17
  sar_9l_after:
    coordinator_lines: 1594
    run_sync_lines: 651
    runcoordinator_methods: 17
  sar_9m_after:
    coordinator_lines: 1478
    run_sync_lines: 534
    runcoordinator_methods: 17
  sar_9b_after:
    coordinator_lines: 2934
    run_sync_lines: 1936
    runcoordinator_methods: 19
  current_local_after_sar_7_3:
    coordinator_lines: 3397
    run_sync_lines: 1963
    runcoordinator_methods: 26
  reduction_prerequisites:
    - canonical_action_outcome
    - single_progress_finish_authority
    - single_recovery_protocol

immutable_planner_input:
  public_contract_migrated: true
  internal_request_projection: complete_foundation
  compatibility_retirement: pending
  standard_path_migrated: compatibility_window
  record: docs/change-admission/tpa-2-immutable-planning-request.yaml
  public_cutover_record: docs/change-admission/tpa-3-8-plannerport-public-request-cutover.yaml
  design: planned
  tests: focused_foundation

obligation_driven_progress:
  decision: frozen
  decision_record: docs/change-admission/odg-0-obligation-driven-progress-architecture.yaml
  role_audit: docs/audits/obligation-execution-role-audit.md
  contracts_record: docs/change-admission/odg-2-obligation-progress-contracts.yaml
  contracts: foundation_only
  ledger_record: docs/change-admission/odg-3-statekernel-obligation-ledger-foundation.yaml
  ledger: foundation_storage_only
  ready_projection_record: docs/change-admission/odg-4-role-decisions-ready-projection.yaml
  ready_projection: authority_free_foundation
  shadow_comparison_record: docs/change-admission/odg-5-obligation-progress-shadow-comparison.yaml
  shadow_comparison: post_observation_trace_hookup
  shadow_diagnostic_evidence: docs/evidence/runs/odg-5-shadow-diagnostic-04a2fcd/
  current_observation_satisfaction_record: docs/change-admission/odg-6-current-observation-obligation-satisfaction.yaml
  current_observation_satisfaction: foundation_evaluator_only_hardened
  shared_attribution_contract_hardening_record: docs/change-admission/odg-6-1-shared-attribution-contract-hardening.yaml
  shared_attribution_contract_hardening: complete
  attribution_ticket_resolver_record: docs/change-admission/odg-7-attribution-ticket-resolver.yaml
  attribution_ticket_resolver: foundation_only_hardened
  post_action_evidence_normalization_record: docs/change-admission/odg-8-post-action-evidence-normalization.yaml
  post_action_evidence_normalization: foundation_hardened_with_verifier_fidelity
  post_action_causality_strength_record: docs/change-admission/odg-8-1-causality-strength-hardening.yaml
  post_action_causality_strength: complete
  verifier_evidence_fidelity_record: docs/change-admission/odg-8b-verifier-evidence-fidelity.yaml
  verifier_evidence_fidelity: foundation_only
  post_verification_attribution_record: docs/change-admission/odg-9-post-verification-obligation-attribution.yaml
  post_verification_attribution: foundation_only
  runtime_ticket_carry_shadow_record: docs/change-admission/odg-9-runtime-ticket-carry-shadow-diagnostic.yaml
  runtime_ticket_carry_shadow: foundation_only
  next_odg_slice: stopped_for_default_path
  advanced_attribution: experimental_only
  coordinator_commit: authorized_for_bounded_sar_9m_phase_extraction_only
  finish_gate_change: not_authorized
  planner_context_change: not_authorized
  benchmark_rerun: not_required
  standard_path_migrated: false
  taskplan_authority: compatibility_only_target
  promotion_status: held

simplified_runtime_architecture:
  target_architecture: docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-simplified-target-architecture.md
  execution_plan: docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-simplification-execution-plan.md
  freeze_record: docs/change-admission/s0-simplified-architecture-freeze.yaml
  core_contracts_record: docs/change-admission/s1-simplified-core-contracts.yaml
  step_projection_record: docs/change-admission/s2-legacy-step-compatibility-projection.yaml
  step_projection_hardening_record: docs/change-admission/s2-1-step-projection-hardening.yaml
  status: superseded_by_sar_0
  implementation: foundation_contracts_started
  core_contracts: foundation_only
  step_projection: foundation_hardened
  current_production_progress_authority: legacy_taskplan_subgoal_planprogress
  target_production_progress_authority: runtime_owned_active_step
  target_task_completion_authority: task_spec_completion_criterion_independent_verification
  planning_request_record: docs/change-admission/tpa-2-immutable-planning-request.yaml
  planning_request: foundation_contracts_and_builder
  next_slice: stopped_by_sar_0
  odg_default_path: stopped
  odg_advanced_attribution: experimental_only
  odg_10_progress_commit: not_authorized
  odg_11_finish_authority_migration: not_authorized
  promotion_status: held

authoritative_optimized_architecture:
  architecture: docs/superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md
  execution_plan: docs/superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md
  docs_index: docs/README.md
  superseded_archive: docs/archive/superseded-2026-07-29/README.md
  freeze_record: docs/change-admission/sar-0-authoritative-architecture-freeze.yaml
  status: approved_with_guardrails
  conflict_precedence: replaces_simplified_taskplan_authority_and_odg_default_target_architectures
  migration_style: substitutive_one_in_one_out
  old_default_docs: archived
  legacy_root_architecture_docs:
    status: archived_with_redirects
    archived:
      - docs/archive/superseded-2026-07-29/architecture.md
      - docs/archive/superseded-2026-07-29/complete-architecture-blueprint.md
      - docs/archive/superseded-2026-07-29/design-freeze.md
    redirects:
      - docs/architecture.md
      - docs/complete-architecture-blueprint.md
      - docs/design-freeze.md
  stopped_additive_next_slice: tpa-5b-llm-taskplan-generator-draft-migration
  next_slice: sar-2-relation-criterion-evidence-vocabulary-unification
  production_behavior_change: false
  promotion_status: held

sar_2_semantic_vocabulary_unification:
  record: docs/change-admission/sar-2-relation-criterion-evidence-vocabulary-unification.yaml
  status: local_completion_candidate
  canonical_module: src/affordance_runtime/semantics.py
  criterion_relation_enums: 1
  canonical_evidence_policy_count: 1
  canonical_atomic_criterion_model_count: 1
  internal_relation_mapping_functions: 0
  production_enum_value_cross_casts: 0
  task_obligation_relation: compatibility_alias_to_criterion_relation
  subgoal_outcome_relation: compatibility_alias_to_criterion_relation
  state_criterion_relation: compatibility_alias_to_criterion_relation
  criterion_evidence_policy: compatibility_alias_to_evidence_policy
  nominal_criterion_subclasses: compatibility_aliases_to_state_criterion
  runtime_authority_changed: false
  next_slice: sar-3a-direct-rule-plan-candidate-generation

sar_1_deep_immutability:
  record: docs/change-admission/sar-1-deep-immutability-and-stale-contract-hash.yaml
  closure_record: docs/change-admission/sar-1-1-hash-reachable-hidden-mutability-closure.yaml
  threat_model: docs/security/action-contract-digest-threat-model.md
  status: local_complete_after_sar_1_1
  current_scope: all_non_benchmark_frozen_dataclass_runtime_payload_boundaries_with_container_fields_plus_hash_reachable_any_checks
  hash_reachable_contract_graph: covered
  hidden_any_mutability_checks: passed
  supplied_contract_hash_consistency: enforced
  immutable_helper: src/affordance_runtime/immutable.py
  frozen_runtime_payloads:
    - ActionContract locator / parameters / hash-critical list fields
    - ExecutionReceipt evidence
    - PlannerDecision result / planner_context
    - Observation metadata / target_fingerprints / artifact_refs
    - Affordance locator / state / payload / backend_candidates / evidence / lease provenance
    - GestureTargetBinding locator
    - VerifierSpec expected / criterion_ids / requirement_ids
    - SourceAssertion value
    - VerificationEvidence observed / expected
    - VerificationReport evidence
    - VerifierEvaluation observed
    - TraceNode payload / parents
    - RecoveryTraceProjection payload
    - TaskPlanTraceProjection payload
    - RecoveryContext tried_backends
    - BrowserSnapshot accessibility_tree
    - PageAffordanceModel affordances
    - ThingAffordanceModel affordances / state_sources
    - ConformanceSurfaceResult contract_capabilities / event_types / screenshot_refs
    - EvolutionProposal applicability / validation_plan
    - RuntimePatchPayload task_ids / feature_overrides
    - RecoveryPolicyPatchPayload task_ids / signature_match / required_evidence / postconditions
    - RecoverySkillPayload task_ids / signature_match / steps / required_evidence / postconditions
    - RecoveryReplayEvidence recovery_actions
    - RecoveryEvolutionReport source_incident / replays
    - CanonicalTrace rows
    - ConfiguredApprovalProvider allowed_capabilities
    - RoutingDecision candidate_backends / scores
    - TaskEnvelope constraints / capabilities
    - TaskRequest constraints / capabilities
    - TaskExecution result / artifacts
    - SemanticActionResolution parameters
    - SemanticCompilation parameters
    - SemanticConstraints compatible_target_ids
    - CanonicalProposalGraph proposal_claim_ids
    - IntentDraftRepairAttempt proposal_claim_ids
    - SnapshotAffordanceView ordinal collection state
    - TaskSkillReplayDecision metrics
  json_persistence_boundary: TraceDag and ArtifactStore project frozen containers to canonical JSON-compatible data
  adapter_boundary_thaw: explicit_only
  legacy_compatibility_boundary: frozen payload readers use Mapping and Sequence rather than mutable dict/list assumptions
  production_behavior_change: false
  progress_authority_change: prohibited
  finish_authority_change: prohibited
  remaining_scanner_findings: none_for_non_benchmark_frozen_dataclasses_with_container_fields_missing_post_init
  next_slice: sar-2-relation-criterion-evidence-vocabulary-unification
  promotion_status: held

taskplan_authority_program:
  architecture: docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-taskplan-authority-architecture.md
  execution_plan: docs/archive/superseded-2026-07-29/2026-07-29-affordance-runtime-taskplan-authority-execution-plan.md
  freeze_record: docs/change-admission/tpa-0-taskplan-authority-freeze.yaml
  inventory_record: docs/change-admission/tpa-1-authority-read-set-audit.yaml
  call_site_audit: docs/audits/taskplan-authority-call-sites.md
  step_planner_read_set: docs/audits/step-planner-standard-input-read-set.md
  taskskill_authority_audit: docs/audits/taskskill-progress-authority.md
  tpa_0: completed
  tpa_1: completed
  tpa_2: completed_foundation
  tpa_3_1: completed_foundation
  tpa_3_2a: completed_foundation
  tpa_3_2c: completed_foundation
  tpa_3_2d: completed_foundation
  tpa_3_3: completed_foundation
  tpa_3_4: completed_foundation
  tpa_3_5: completed_foundation
  tpa_3_6: completed_foundation
  tpa_3_7: completed_foundation
  tpa_3_8: completed_foundation
  tpa_4: completed_foundation
  tpa_5: completed_foundation
  planning_request_record: docs/change-admission/tpa-2-immutable-planning-request.yaml
  planner_context_request_record: docs/change-admission/tpa-3-1-planner-context-request-path.yaml
  planner_projection_admission_contract_record: docs/change-admission/tpa-3-2a-step-projection-admission-contracts.yaml
  legacy_terminal_admission_projector_record: docs/change-admission/tpa-3-2c-legacy-terminal-admission-projector.yaml
  decisionconstraint_apply_admission_record: docs/change-admission/tpa-3-2d-decisionconstraint-apply-admission.yaml
  generalist_request_core_record: docs/change-admission/tpa-3-3-generalist-request-only-core.yaml
  parent_agent_request_record: docs/change-admission/tpa-3-4-parent-agent-planner-request-migration.yaml
  reference_planner_request_record: docs/change-admission/tpa-3-5-reference-scripted-planners-request-migration.yaml
  conformance_recovery_planner_request_record: docs/change-admission/tpa-3-6-conformance-benchmark-planners-request-migration.yaml
  browsergym_policy_planner_compatibility_record: docs/change-admission/tpa-3-7-browsergym-and-benchmark-planners-compatibility.yaml
  plannerport_public_request_cutover_record: docs/change-admission/tpa-3-8-plannerport-public-request-cutover.yaml
  taskplan_authority_contracts_record: docs/change-admission/tpa-4-taskplan-authority-contracts.yaml
  taskplan_generator_draft_migration_record: docs/change-admission/tpa-5-taskplan-generator-draft-migration.yaml
  plan_candidate_owner_target: TaskPlanGeneratorPort
  plan_decision_owner_target: TaskPlanAuthority
  plan_commit_owner: RunCoordinator
  plan_storage_owner: StateKernel
  standard_step_planner_target: StepPlannerPort.propose(PlanningRequest)
  current_standard_triple_signature_implementations: 15
  current_production_authority: legacy_taskplan_subgoal_planprogress
  public_request_contract: complete
  request_projection_foundation: complete
  legacy_implementation_retirement: pending
  draft_generator_foundation: complete
  llm_generator_migration: pending
  next_slice: stopped_by_sar_0
  superseded_by: sar-0-authoritative-architecture-freeze
  production_authority_changed: false
  promotion_status: held

pr_breadth_initial_negative:
  revision: d66760f76bb4668f610d2ebfac2c8ba0bf83c71a
  evidence: docs/evidence/runs/m8.2a-pr-breadth-d66760f/
  status: failed
  expected: 12
  observed: 12
  passed: 0
  failed: 12
  provider_failures: 0
  missing: 0
  unrun: 0
  invalidated: 0
  official_score_claimed: false
  promotion_status: held
  root_owner_next: INTENT / PLANNING
  next_change_admission: docs/change-admission/v-pr-breadth-intent-planning-repair.yaml

pr_breadth_latest:
  revision: 407133d1a1c902436ae2576175f834a7a74b1367
  evidence: docs/evidence/runs/m8.2a-pr-breadth-407133d/
  status: failed
  expected: 12
  observed: 12
  passed: 11
  failed: 1
  runtime_failed: 3
  provider_failures: 0
  missing: 0
  unrun: 0
  invalidated: 0
  official_score_claimed: false
  promotion_status: held
  root_owner_next: V-PRB-6A form-sequence dependent-subgoal progress-scope binding
  external_reward_closed: false
  v_prb_6b_enter_text_closed: true
  failed_official_episode:
    - click-button:seed-1
  comparison_baseline:
    revision: 66dae07eb6de259a17c8f9604e30189a74fcc357
    evidence: docs/evidence/runs/m8.2a-pr-breadth-66dae07/
    result: 12/12 external reward, 3 Runtime failures
    interpretation: V-PRB-6B closes enter-text:seed-1 relative to this baseline, while click-button:seed-1 regresses externally as a separate json_invalid cluster
  remaining_runtime_guard:
    planner_cannot_finish_before_verifier_backed_subgoal_completion: 2
  affected_episodes:
    - form-sequence:seed-0
    - form-sequence:seed-1
  monitored_nonreproduced_episode:
    - click-button:seed-1
  latest_negative_repair: docs/change-admission/v-prb-6b-current-state-discard-replacement.yaml
  latest_negative_repair_2: docs/change-admission/v-prb-6b-has-changed-text-progress-binding.yaml
  latest_rejected_repair: docs/change-admission/v-prb-6b-empty-has-changed-fill-delta-binding.yaml
  latest_rejected_repair_2: docs/change-admission/v-prb-6b-current-state-progress-reconciliation.yaml
  latest_residual_classification: docs/change-admission/v-prb-6-post-9ad1288-residual-classification.yaml
  latest_residual_classification_2: docs/change-admission/v-prb-6b-obligation-subgoal-missing-after-discard.yaml
  latest_residual_classification_3: docs/change-admission/v-prb-6-post-95fe00b-residual-classification.yaml
  latest_red_contract: docs/change-admission/v-prb-6b-verifier-backed-progress-accounting.yaml
  latest_green_contract: docs/change-admission/v-prb-6b-verifier-backed-progress-accounting.yaml
  latest_clean_rerun: docs/evidence/runs/m8.2a-pr-breadth-407133d/
  click_button_recheck:
    revision: 47932a2d84266983c632258afdfacae9b1cdcd94
    evidence: docs/evidence/runs/v-prb-6-post-407133d-click-button-recheck/
    result: 2 observed, 2 official reward passed, 2 Runtime passed
    interpretation: json_invalid did not reproduce in targeted recheck; no production repair admitted yet
  historical_next_change_before_odg_0: V-PRB-6A form-sequence dependent-subgoal progress-scope binding
  current_next_change_admission: SAR-9M PlanningFailurePhase extraction. SAR-9A moved TaskPlan prepare / commit / trace-projection detail from RunCoordinator.run_sync into task_plan_phase.commit_task_plan_phase. SAR-9B routes post-observation and post-TaskPlan current-state progress through progress_phase.ProgressPhase. SAR-9C moves TaskSkill exposure / activation / accepted-skill provenance and planner-decision awaitable resolution into task_skill_phase.TaskSkillPhase. SAR-9D moves PlannerDecision trace, semantic proposal validation, planner terminal handling, clarification, and legacy empty-decision classification into planning_phase.PlanningDecisionPhase. SAR-9E moves contract build/bind, ContractBuilt / RouteSelected trace projection, progress guard handling, TaskSkill contract-requirement fallthrough, and preflight visual/SVG rebound binding into contract_binding_phase.ContractBindingPhase. SAR-9F moves preflight, approval, environment-drift recovery, authorization, and pending retry-contract validation into preflight_phase.PreflightPhase. SAR-9G moves action dispatch, receipt state/artifact recording, pending execution recovery completion, and receipt-failure recovery handling into execution_phase.ExecutionPhase. SAR-9H moves post-action observation, verification, evidence repair, ActionOutcomeRecorded, action-progress recording, postcondition trace, and route outcome recording into verification_phase.VerificationPhase. SAR-9I moves TaskSkill active-step verification, checkpoint/fallthrough traces, and no-TaskPlan TaskSkill terminal compatibility into task_skill_progress_phase.TaskSkillProgressPhase. SAR-9J moves grounding recovery completion, verifier-backed TaskPlan progress commit, task-completion verification, and final success commit delegation into verified_progress_phase.VerifiedProgressPhase. SAR-9K moves recovery-disabled failed verification terminal handling, TaskSkill failure context construction, verification-failure recovery dispatch, recovery-start trace projection, and terminal recovery status selection into verification_failure_phase.VerificationFailurePhase. SAR-9L moves observation capture, ObservationCaptured trace projection, artifact indexing, source arbitration, targeted perception, post-state recovery inspection, pending observation recovery completion, and perception-block terminal handling into perception_phase.PerceptionPhase. SAR-9M moves TaskPlan failure, TaskSkill activation failure, provider deferral, unexpected planner exception, and PlanningDecision failure recovery handoff into planning_failure_phase.PlanningFailurePhase. Promotion remains held.
  pre_sar_8_planner_failure_classification:
    record: docs/change-admission/sar-8-pre-planner-failure-classification.yaml
    evidence: docs/evidence/runs/sar-7-planner-failure-classification-25ec674/
    planner_waiting_clarification: 26
    planner_waiting_owner: planner_model_or_action_choice_builder
    entry_outcome_already_satisfied: 9
    already_satisfied_owner: progress_precheck
    future_execution_provider_profile: local_ollama
  already_satisfied_owner_repair:
    record: docs/change-admission/sar-7-6-already-satisfied-progress-precheck.yaml
    status: local_repair_candidate
    behavior: accepted_plan_then_current_state_subgoal_completion_before_planner
    planner_reached_for_already_satisfied_active_step: false
    recovery_protocol_changed: false
  sar_8:
    status: sar_8c_canonical_decision_outcome_state_local_candidate
    record: docs/change-admission/sar-8-single-recovery-protocol.yaml
    current_slice: sar_8c_legacy_recovery_state_deletion
    recovery_strategy_owner: recovery_protocol.FailureClassification
    recovery_decision_owner: recovery_protocol.RecoveryDecision
    recovery_outcome_owner: recovery_protocol.RecoveryOutcome
    recovery_application_owner: recovery_phase.RecoveryPhase
    planner_waiting_clarification_default_ask_user: false
    planner_waiting_clarification_default_replan: false
    planner_waiting_clarification_requires_typed_action_space: true
    already_satisfied_recovery_kind: progress_precheck_not_recovery
    coordinator_phase_general_entry: RecoveryPhase.handle_phase_failure
    coordinator_cutover: default_recovery_entries_migrated
    coordinator_lines_after_callsite_migration: 3357
    coordinator_lines_after_legacy_state_deletion: 3298
    run_sync_lines_after_legacy_state_deletion: 1944
    runcoordinator_methods_after_legacy_state_deletion: 24
    statekernel_current_recovery_decision: canonical
    statekernel_current_recovery_outcome: canonical
    compatibility_adapter: removed_from_default_path
    legacy_recovery_protocol_deletion: recovery_plan_command_and_incident_protocols_removed_at_09d4304
  planner_selection_simplification:
    status: ps_strict_free_action_model_fallback_retirement_local_candidate
    record: docs/change-admission/planner-selection-actionchoice.yaml
    actionchoice_contract: foundation
    actionchoice_builder:
      exact_text_equals: foundation
      slider_numeric_equals_press_key: foundation
      checkbox_activation: foundation
      select_option: foundation
      terminal_activation: foundation
      has_changed_activation: foundation
    dispatch:
      zero_choices: typed_failure_without_model_call
      one_choice: runtime_selection_without_model_call
      multiple_choices: step_planner_choice_id_selection
    strict_generalist_unique_choice_cutover: exact_text_and_slider
    strict_generalist_multiple_choice_selector: choice_id_only_schema
    fallback_deletion: strict_free_action_model_fallback_retired
    production_planner_cutover: partial_runtime_actionchoice_paths
    provider_schema_change: choice_id_only_for_multiple_actionchoices
    behavioral_gate: targeted_non_qwen_ollama_llama3_1_8b_3_case_run_2_of_3_pass_at_local_7af5ec6_no_promotion
  failure_ownership_router:
    status: for_1_local_candidate
    record: docs/change-admission/for-1-failure-owner-router.yaml
    goal: single_failure_owner_router_before_phase_extraction
    sequence:
      - FOR-2A Runtime RecoveryPhase narrowing
      - FOR-2B runtime recovery policy cleanup
      - FOR-3 structured step/task/user/progress handoff
      - FOR-4 deletion and behavioral gate
    sar_9_blocker: true
  immutable_planner_input: PlannerPort public contract is request-only and uses PlanningRequest with TaskSpec, Step projection, UnifiedObservation, recent ActionOutcome summaries, and budgets where a validated TaskSpec is available; legacy ActionContract-returning planners remain behind planner_compatibility.py, BrowserGymPolicyRequest remains a compatibility-only benchmark policy boundary, and Coordinator no longer directly calls self.planner.propose(envelope, state, snapshot)
  sar_5:
    unified_observation_contract: foundation_complete
    exact_active_target_gate: complete_for_selected_slice
    action_family_and_destination_scope: implemented_for_exact_active_step
    terminal_framework_default_path: removed
    canonical_scope_resolver: compatibility_fail_open_pending
    behavioral_exit_evidence: pending
    overall_status: in_progress
  sar_6:
    selected_next: true
    record: docs/change-admission/sar-6-actioncontract-actionoutcome-canonicalization.yaml
    goal: canonical_execution_and_action_outcome_with_same_unit_one_out_deletion
    status: in_progress
    sar_6a_action_outcome_recording: local_candidate
    implementation_revision: "2338432"
    default_final_action_event: ActionOutcomeRecorded
    legacy_action_completed_default_event: removed
  sar_7:
    status: sar_7_behavioral_gate_local_complete
    record: docs/change-admission/sar-7-single-progress-finish-authority.yaml
    sar_7a_verifier_backed_progress_flow_extraction: complete
    sar_7b_planner_terminal_flow: complete
    sar_7c_terminal_success_flow: complete
    implementation_revision: "25ec6745ce08f6337c8d040cf1b31bd2a384ff6e"
    coordinator_lines: 3453
    run_sync_lines: 2001
    runcoordinator_methods: 25
    planner_done_finish_path: runtime_terminal_flow
    taskskill_direct_finish_path: progress_flow_then_terminal_success_flow
    task_completed_success_event_owner: runtime_terminal.commit_task_terminal_success
    coordinator_inline_taskcompleted_sites: 0
    coordinator_inline_decision_done_finish_sites: 0
    progress_authority_changed: compatibility_legacy_progress_committed_through_progress_flow
    finish_authority_changed: terminal_success_commit_centralized
  sar_7_full_milestone:
    canonical_taskprogress_cutover: sar_7_4_default_field_cutover
    independent_task_completion_verifier: sar_7_1_local_complete
    taskskill_progress_authority_removal: sar_7_5_local_complete
    odg_and_pending_obligation_state_removal: sar_7_2_local_complete
    action_dedupe_replacement: sar_7_3_local_complete
    required_pr_breadth: passed_at_25ec674
    fresh_diagnostic: complete_with_residuals_at_25ec674
    behavioral_evidence: docs/evidence/runs/sar-7-behavioral-gate-25ec674/
    status: local_complete_promotion_held
  sar_7_1:
    status: local_completion_candidate
    record: docs/change-admission/sar-7-1-semantic-closure.yaml
    task_completion_verifier: foundation
    terminal_success_requires_completion_result: true
    taskskill_progress_commit_requests_task_completion: false
    compatibility_allowances:
      - legacy_no_task_spec_completion
      - legacy_no_effect_no_receipt_completion
  sar_7_2:
    status: local_completion_candidate
    record: docs/change-admission/sar-7-2-default-progress-state-cleanup.yaml
    default_pending_obligations_state: removed
    default_odg_obligation_progress_state: removed
    planning_request_pending_evidence_obligations: compatibility_empty
  sar_7_3:
    status: local_completion_candidate
    record: docs/change-admission/sar-7-3-bounded-action-dedupe.yaml
    action_progress_list: removed
    recent_action_outcomes: bounded_typed_index
    legacy_colon_signature: rejected
  sar_7_4:
    status: local_completion_candidate
    record: docs/change-admission/sar-7-4-taskprogress-default-cutover.yaml
    default_progress_field: task_progress
    plan_progress: compatibility_alias_and_property
    legacy_planprogress_class: removed
  sar_7_5:
    status: local_completion_candidate
    record: docs/change-admission/sar-7-5-taskskill-progress-state-removal.yaml
    statekernel_taskskill_field: removed
    statekernel_taskskill_mutation_methods: removed
    taskskill_progress_owner: AcceptedTaskSkillRuntime_compatibility_state
    progress_fingerprint_reads_taskskill: false
    clean_pr_breadth: passed_at_25ec674
    behavioral_evidence: docs/evidence/runs/sar-7-behavioral-gate-25ec674/
  sar_4:
    plannerport_response_contract: complete
    standard_generalist_response_contract: complete
    parent_adapter_response_contract: complete
    legacy_plannerdecision_consumer: compatibility_window
    plannercontext_provider_path: pending_deletion
    legacy_three_argument_planners: compatibility_window
  hard_guardrails:
    - no_new_foundation_only_chain
    - every_canonical_object_requires_same_unit_legacy_deletion
    - no_second_execution_result_authority
    - no_second_progress_or_finish_authority
    - no_coordinator_shortening_by_relocating_unchanged_branches
    - total_core_complexity_must_decrease

active_local_repair:
  slice: sar-9m-planning-failure-phase-extraction
  base_revision: 9fc34e7ebe43e51e810b9ed99f7aeca919b2eb88
  status: local_candidate
  freeze_record: docs/change-admission/tpa-0-taskplan-authority-freeze.yaml
  inventory_record: docs/change-admission/tpa-1-authority-read-set-audit.yaml
  planning_request_record: docs/change-admission/tpa-2-immutable-planning-request.yaml
  planner_context_request_record: docs/change-admission/tpa-3-1-planner-context-request-path.yaml
  planner_projection_admission_contract_record: docs/change-admission/tpa-3-2a-step-projection-admission-contracts.yaml
  legacy_terminal_admission_projector_record: docs/change-admission/tpa-3-2c-legacy-terminal-admission-projector.yaml
  decisionconstraint_apply_admission_record: docs/change-admission/tpa-3-2d-decisionconstraint-apply-admission.yaml
  generalist_request_core_record: docs/change-admission/tpa-3-3-generalist-request-only-core.yaml
  parent_agent_request_record: docs/change-admission/tpa-3-4-parent-agent-planner-request-migration.yaml
  reference_planner_request_record: docs/change-admission/tpa-3-5-reference-scripted-planners-request-migration.yaml
  conformance_recovery_planner_request_record: docs/change-admission/tpa-3-6-conformance-benchmark-planners-request-migration.yaml
  browsergym_policy_planner_compatibility_record: docs/change-admission/tpa-3-7-browsergym-and-benchmark-planners-compatibility.yaml
  plannerport_public_request_cutover_record: docs/change-admission/tpa-3-8-plannerport-public-request-cutover.yaml
  taskplan_authority_contracts_record: docs/change-admission/tpa-4-taskplan-authority-contracts.yaml
  taskplan_generator_draft_migration_record: docs/change-admission/tpa-5-taskplan-generator-draft-migration.yaml
  sar_0_freeze_record: docs/change-admission/sar-0-authoritative-architecture-freeze.yaml
  sar_1_record: docs/change-admission/sar-1-deep-immutability-and-stale-contract-hash.yaml
  sar_1_1_record: docs/change-admission/sar-1-1-hash-reachable-hidden-mutability-closure.yaml
  sar_2_record: docs/change-admission/sar-2-relation-criterion-evidence-vocabulary-unification.yaml
  sar_3a_record: docs/change-admission/sar-3a-direct-rule-plan-candidate-generation.yaml
  sar_3b_record: docs/change-admission/sar-3b-llm-plan-candidate-generation.yaml
  sar_3c_record: docs/change-admission/sar-3c-taskplanauthority-initial-cutover.yaml
  sar_3d_record: docs/change-admission/sar-3d-taskplanauthority-replacement-cutover.yaml
  sar_3e_record: docs/change-admission/sar-3e-plan-candidate-naming-retirement.yaml
  sar_4a_record: docs/change-admission/sar-4a-planner-response-and-provider-serialization.yaml
  sar_5a_record: docs/change-admission/sar-5a-unified-observation-active-step-scope.yaml
  sar_5b_record: docs/change-admission/sar-5b-active-step-scope-validator-hookup.yaml
  sar_6_record: docs/change-admission/sar-6-actioncontract-actionoutcome-canonicalization.yaml
  sar_9a_record: docs/change-admission/sar-9a-taskplan-phase-extraction.yaml
  sar_9b_record: docs/change-admission/sar-9b-progress-phase-extraction.yaml
  sar_9c_record: docs/change-admission/sar-9c-taskskill-phase-extraction.yaml
  sar_9d_record: docs/change-admission/sar-9d-planning-decision-phase-extraction.yaml
  sar_9e_record: docs/change-admission/sar-9e-contract-binding-phase-extraction.yaml
  sar_9f_record: docs/change-admission/sar-9f-preflight-phase-extraction.yaml
  sar_9g_record: docs/change-admission/sar-9g-execution-phase-extraction.yaml
  sar_9h_record: docs/change-admission/sar-9h-verification-phase-extraction.yaml
  sar_9i_record: docs/change-admission/sar-9i-taskskill-progress-phase-extraction.yaml
  sar_9j_record: docs/change-admission/sar-9j-verified-progress-phase-extraction.yaml
  sar_9k_record: docs/change-admission/sar-9k-verification-failure-phase-extraction.yaml
  sar_9l_record: docs/change-admission/sar-9l-perception-phase-extraction.yaml
  sar_9m_record: docs/change-admission/sar-9m-planning-failure-phase-extraction.yaml
  sar_1_threat_model: docs/security/action-contract-digest-threat-model.md
  sar_authoritative_architecture: docs/superpowers/specs/2026-07-29-affordance-runtime-authoritative-optimized-architecture.md
  sar_execution_plan: docs/superpowers/plans/2026-07-29-affordance-runtime-substitutive-refactor-execution-plan.md
  behavior_change: planned_for_sar_6_execution_outcome_contract_shape_only_until_cutover
  standard_path_authority: candidate_capable_initial_and_replacement_admission_cutover_only
  coordinator_commit: authorized_for_bounded_sar_9m_phase_extraction_only
  finish_gate_change: not_authorized
  planner_context_change: unchanged
  taskplan_generator_change: unchanged_after_plan_candidate_naming_retirement
  planner_response_change: closed_response_union_foundation_only
  provider_serialization_change: direct_serializer_foundation_only
  unified_observation_change: target_centric_contract_foundation_only
  active_step_scope_change: exact_legacy_active_subgoal_validator_hookup
  sar_5_overall_status: in_progress
  canonical_scope_resolver: pending
  terminal_framework_deletion: pending
  taskplan_required: false
  additive_foundation_expansion: stopped
  current_runtime_slice: sar-9m-planning-failure-phase-extraction
  next_runtime_slice: sar-9n-final-loop-cleanup-and-closure-gate
  sar_8_blocked_until: unblocked
  historical_required_before_sar_7:
    - sar_4_standard_generalist_parent_response_cutover
    - sar_5_default_terminal_framework_deletion
    - sar_6a_action_outcome_recording
  promotion_status: held

attribution_classification:
  evidence: docs/evidence/runs/m8.2a-pr-breadth-d66760f/episode-attribution.yaml
  child_record: docs/change-admission/v-prb-0-failure-attribution-fidelity.yaml
  status: complete
  episodes_classified: 12
  unclassified: 0
  production_change_admitted: false
  mechanisms:
    invalid_coverage_audit_handling: 2
    provider_graph_proposal_normalization: 4
    typed_semantic_action_constraints: 5
    structured_decoding_or_attribution_projection: 1

v_prb_1_invalid_coverage_audit_handling:
  child_record: docs/change-admission/v-prb-1-invalid-coverage-audit-handling.yaml
  status: implemented_locally
  production_change_admitted: true
  mechanism: invalid_coverage_audit_handling
  affected_prior_episodes:
    - click-dialog:seed-0
    - enter-text:seed-0
  non_browsergym_red_test: tests/test_intent_compiler.py::test_invalid_coverage_audit_quote_cannot_veto_deterministic_ready
  promotion_status: held
  rerun_required: new generic repair before any breadth completion or promotion claim

v_prb_1_clean_rerun:
  revision: d40f8f1792e85f391fe6c94dd88f9b5e0235d481
  evidence: docs/evidence/runs/m8.2a-pr-breadth-d40f8f1/
  status: failed
  expected: 12
  observed: 12
  passed: 0
  failed: 12
  provider_failures: 0
  missing: 0
  unrun: 0
  invalidated: 0
  official_score_claimed: false
  promotion_status: held
  invalid_coverage_audit_handling_closed: true
  remaining_mechanisms:
    waiting_clarification: 7
    invalid_provider_graph: 4
    structured_decoding_or_attribution_projection: 1
  next_selectable_child_slice: V-PRB-3 typed semantic action constraints

v_prb_3_typed_semantic_action_constraints:
  child_record: docs/change-admission/v-prb-3-typed-semantic-action-constraints.yaml
  status: implemented_locally
  production_change_admitted: true
  mechanism: typed_semantic_action_constraints
  affected_prior_episodes:
    - choose-list:seed-0
    - choose-list:seed-1
    - click-button:seed-0
    - click-dialog:seed-0
    - click-dialog:seed-1
    - enter-text:seed-0
    - enter-text:seed-1
  non_browsergym_red_tests:
    - tests/test_generalist_planner.py::test_strict_planner_resolves_empty_clarification_to_unique_requested_button
    - tests/test_generalist_planner.py::test_strict_planner_resolves_empty_clarification_to_selected_option_submit
    - tests/test_generalist_planner.py::test_strict_planner_resolves_empty_clarification_to_target_derived_text_value
  owner: strict semantic action resolver
  production_boundaries:
    coordinator_touched: false
    statekernel_touched: false
    planner_port_touched: false
    prompt_or_budget_changed: false
    benchmark_specific_logic_added: false
  promotion_status: held
  rerun_required: PR breadth 6-task x 2-seed matrix on a clean committed revision

v_prb_3_clean_rerun:
  revision: 9b951ed968314aa7a139611d00256adb17b3cbb7
  evidence: docs/evidence/runs/m8.2a-pr-breadth-9b951ed/
  status: failed
  expected: 12
  observed: 12
  passed: 8
  failed: 4
  provider_failures: 0
  missing: 0
  unrun: 0
  invalidated: 0
  official_score_claimed: false
  promotion_status: held
  typed_semantic_action_constraints_closed: true
  remaining_mechanisms:
    invalid_provider_graph: 4
    planner_terminal_completion_guard: 1
  next_selectable_child_slice: V-PRB-2 provider graph proposal normalization

v_prb_2_provider_graph_proposal_normalization:
  child_record: docs/change-admission/v-prb-2-provider-graph-proposal-normalization.yaml
  status: implemented_locally
  production_change_admitted: true
  mechanism: provider graph proposal normalization
  affected_current_episodes:
    - click-button-sequence:seed-0
    - click-button-sequence:seed-1
    - form-sequence:seed-0
    - form-sequence:seed-1
  non_browsergym_red_tests:
    - tests/test_intent_compiler.py::test_llm_compiler_canonicalizes_multistage_requested_effects_when_provider_graph_is_incomplete
  owner: canonical obligation compiler boundary
  production_boundaries:
    coordinator_touched: false
    statekernel_touched: false
    planner_port_touched: false
    prompt_or_budget_changed: false
    benchmark_specific_logic_added: false
  promotion_status: held
  rerun_required: PR breadth 6-task x 2-seed matrix on a clean committed revision

v_prb_2_clean_rerun:
  revision: c24b277a93712191c626a1db87cc1f3fc1c166bd
  evidence: docs/evidence/runs/m8.2a-pr-breadth-c24b277/
  status: failed
  expected: 12
  observed: 12
  passed: 8
  failed: 4
  runtime_failed: 5
  provider_failures: 0
  missing: 0
  unrun: 0
  invalidated: 0
  official_score_claimed: false
  promotion_status: held
  invalid_provider_graph_closed: true
  remaining_mechanisms:
    waiting_clarification: 2
    entry_action_family_unavailable: 2
    planner_terminal_completion_guard: 1
  next_selectable_child_slice: V-PRB-5 task planning / planner constraint follow-up

v_prb_5_downstream_planning_follow_up:
  child_record: docs/change-admission/v-prb-5-downstream-planning-follow-up.yaml
  status: diagnostic_open
  production_change_admitted: false
  source_evidence: docs/evidence/runs/m8.2a-pr-breadth-c24b277/
  mechanisms:
    v_prb_5a_button_sequence_progress_next_subgoal:
      child_record: docs/change-admission/v-prb-5a-button-sequence-effect-semantics.yaml
      status: closed_for_pr_breadth_matrix
      production_change_admitted: true
      episodes:
        - click-button-sequence:seed-0
        - click-button-sequence:seed-1
      candidate_owner: source-bound requested-effect semantics / canonical obligation relation-dependency boundary
      observed_failure: first activation succeeds, active subgoal remains button ONE is available, planner returns ask_user
      review_refinement: non-BrowserGym RED proved compiler-local missing dependency/intermediate terminal semantics; repair preserves sequence only when multi-stage requested-effect fallback opts in
      rerun_result: docs/evidence/runs/m8.2a-pr-breadth-0565e2e/
      rerun_impact: mechanism not closed; both click-button-sequence seeds still fail with planner_waiting_clarification
      rerun_trace_classification: dependency/terminal boundaries are present, but clicked targets are still predicate/is_available obligations and weak execution evidence is correctly rejected
      second_repair: clicked/activated multi-stage navigation targets now compile as effect/is_completed obligations under source-bound canonical requested-effect fallback
      second_repair_verification: non-BrowserGym RED/GREEN plus focused 143-test suite, full local pytest 976/976, Ruff, mypy, and diff check passed
      second_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-e4795c1/
      second_rerun_impact: official reward improved to 8/12 and click-button:seed-1 schema_incompatible no longer reproduces, but both click-button-sequence seeds still fail with planner_waiting_clarification
      second_rerun_trace_classification: effect/is_completed obligations are present; Runtime rejects weak execution/state_delta evidence after first click, active subgoal remains button ONE is completed, and the planner returns ask_user
      progress_evidence_repair: completed click outcomes now add active-subgoal observation_metadata active_control evidence; generic state_delta_or_terminal remains weak and terminal-only
      progress_evidence_repair_verification: non-BrowserGym RED/GREEN plus focused 100-test suite, full local pytest 978/978, Ruff, mypy, and diff check passed
      progress_evidence_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-c75fc3b/
      progress_evidence_rerun_impact: official reward remained 8/12 and both click-button-sequence seeds still failed; trace showed the new verifier did not enter real contracts because active action_family metadata was empty
      refined_progress_repair: absent action_family metadata no longer blocks typed is_completed click progress evidence when the target matches and concrete action is click/click_no_navigation; a present action_family still must match
      refined_progress_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-151fbef/
      refined_progress_rerun_impact: button-sequence seeds 0 and 1 now pass; V-PRB-5A is closed for the current PR breadth matrix
    v_prb_5b_form_sequence_entry_action_family:
      child_record: docs/change-admission/v-prb-5b-entry-action-family-resolution.yaml
      episodes:
        - form-sequence:seed-0
        - form-sequence:seed-1
      candidate_owner: typed TaskPlan action-family resolution / current affordance mapping
      repair_revisions:
        - 5c7a2abf17c6e15f497cb613856730ddd9080242
        - 2b67ffd
      first_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-5c7a2ab/
      first_rerun_impact: original form-sequence entry_action_family_unavailable rejection no longer reproduces; PR breadth still fails 8/12 with empty ask_user / planner_waiting_clarification in form-sequence and enter-text
      followup_repair: 2b67ffd restores textbox value-entry inference from typed current textbox affordance evidence after the first rerun exposed an enter-text regression
      closure_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-3daf779/
      closure_rerun_impact: V-PRB-5B is closed for action-family resolution in the current matrix; original form-sequence entry_action_family_unavailable remains gone and enter-text seed 0 is restored
      architecture_manifest: complete; task_action_family_resolution.py is listed in the executable authority-free collaborator manifest and strict pure-owner dependency gate
      status: done_for_current_pr_breadth_matrix
    v_prb_5c_form_sequence_strict_planner_proposal:
      child_record: docs/change-admission/v-prb-5c-form-sequence-strict-planner-proposal.yaml
      episodes:
        - form-sequence:seed-0
        - form-sequence:seed-1
      candidate_owner: semantic_action_resolver
      observed_failure: accepted TaskPlan with press_key permitted still receives empty ask_user proposal from strict planner
      first_repair: a805f0d adds a bounded slider press_key resolver for empty clarification proposals when one current focused slider and one requested/current numeric direction are available
      first_repair_verification: non-BrowserGym RED/GREEN, focused generalist planner suite, architecture gates, full local pytest 982/982, Ruff, mypy, and diff check passed
      first_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-a805f0d/
      first_rerun_impact: PR breadth remains failed at 10/12 official reward with 3 Runtime failures; the resolver enters the real form path and verifies slider press_key actions, but both form seeds later fail with empty ask_user after replan/progress normalizes the active slider subgoal
      second_repair: 9c1b58c advances from a verifier-backed slider effect to the uniquely requested checkbox, and from a current-state satisfied requested checkbox to unique terminal submit, using only current PlannerContext and typed affordance summaries
      second_repair_verification: non-BrowserGym RED/GREEN plus focused generalist/architecture suite, full local pytest 984/984, Ruff, mypy, and diff check passed
      second_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-9c1b58c/
      second_rerun_impact: PR breadth remains failed at 10/12 official reward with 3 Runtime failures; seed 0 now reaches the requested checkbox after verified slider progress but stops before terminal submit, while seed 1 still repeats press_key through the negative target boundary
      third_repair: d50a631 prevents requested numeric extraction from checkbox ordinal text and permits terminal submit after a requested checkbox is current-state satisfied even when the active subgoal is stale
      third_repair_verification: non-BrowserGym RED/GREEN plus focused generalist/architecture suite, full local pytest 986/986, Ruff, mypy, and diff check passed
      third_rerun_result: docs/evidence/runs/m8.2a-pr-breadth-d50a631/
      third_rerun_impact: PR breadth reaches 12/12 official reward; the previous form terminal-submit and negative-slider official failures no longer reproduce, but both form seeds still abort at the Runtime terminal-completion guard after external reward succeeds
      status: closed_for_current_pr_breadth_matrix
      next_requirement: do not continue form-specific planner proposal repairs unless a new official reward failure appears; route the remaining accounting failure to V-PRB-6
    v_prb_6_terminal_completion_guard:
      child_record: docs/change-admission/v-prb-6-terminal-completion-guard.yaml
      episodes:
        - enter-text:seed-1
        - form-sequence:seed-0
        - form-sequence:seed-1
      candidate_owner: not_selected
      latest_evidence: docs/evidence/runs/m8.2a-pr-breadth-d50a631/
      compact_projection: docs/evidence/runs/v-prb-6-compact-d50a631/
      observed_failure: official_reward is 1.0 while Runtime records planner cannot finish before verifier-backed subgoal completion
      review_refinement: track separately; BrowserGym reward is not Runtime completion authority; form traces show dependent checkbox/submit progress is not credited before finish, so the first RED targets active-subgoal/progress-scope evidence binding rather than accepting finish with incomplete TaskPlan progress
      packet_lifecycle: diagnostic_parent_only; production_change_allowed is false until a child production packet selects one typed owner after RED evidence
      child_diagnostics:
        v_prb_6a_dependent_subgoal_evidence_binding:
          child_record: docs/change-admission/v-prb-6a-dependent-subgoal-evidence-binding.yaml
          episodes:
            - form-sequence:seed-0
            - form-sequence:seed-1
          status: red_archived_strict_xfail
          executable_red: tests/test_browsergym_encoder.py::test_browsergym_checkbox_has_changed_click_declares_active_subgoal_progress
          forced_red_result: fails with task_terminal vs active_subgoal progress scope under --runxfail
        v_prb_6b_single_subgoal_terminal_completion:
          child_record: docs/change-admission/v-prb-6b-single-subgoal-terminal-completion.yaml
          child_production_slice: docs/change-admission/v-prb-6b-read-only-availability-cardinality.yaml
          episodes:
            - enter-text:seed-1
          status: matrix_negative_followup_required
          current_evidence_label: read-only terminal-availability progress binding / TaskPlan cardinality
          reclassification_reason: compact trace shows two subgoals; text-change is completed and independent submit_button availability remains incomplete
          executable_red: tests/test_task_planning.py::test_validator_repairs_current_submit_button_availability_after_text_progress
          red_to_green_result: passes locally without xfail after generic TaskPlan current-state/cardinality repair
          focused_gate: 147 passed, 1 xfailed; remaining xfail is V-PRB-6A
          clean_rerun: docs/evidence/runs/m8.2a-pr-breadth-17f2e50/
          clean_rerun_result: negative; 12 observed, 11 official reward passed, 4 Runtime failures
          clean_rerun_impact: enter-text:seed-1 moved from terminal-completion guard to task_planning repairable entry_outcome_already_satisfied loop
          followup_child_slice: docs/change-admission/v-prb-6b-current-state-discard-replacement.yaml
          followup_status: matrix_negative_insufficient
          followup_result: TaskPlanFlow prepares an accepted current-state discard replacement that preserves verified prior subgoals; focused regression 155 passed, 1 xfailed
          followup_rerun: docs/evidence/runs/m8.2a-pr-breadth-9ad1288/
          followup_rerun_result: negative; 12 observed, 11 official reward passed, 4 Runtime failures
          followup_rerun_impact: current-state discard replacement did not close enter-text:seed-1 Runtime completion and did not affect the separate form-sequence V-PRB-6A or click-button json_invalid clusters
          residual_classification: docs/evidence/runs/v-prb-6-post-9ad1288-classification/
          has_changed_text_progress_slice: docs/change-admission/v-prb-6b-has-changed-text-progress-binding.yaml
          has_changed_text_progress_status: matrix_negative_insufficient
          has_changed_text_progress_rerun: docs/evidence/runs/m8.2a-pr-breadth-c382592/
          progress_accounting_slice: docs/change-admission/v-prb-6b-verifier-backed-progress-accounting.yaml
          progress_accounting_rerun: docs/evidence/runs/m8.2a-pr-breadth-407133d/
          progress_accounting_rerun_result: mixed; 12 observed, 11 official reward passed, 3 Runtime failures
          progress_accounting_impact: enter-text:seed-1 is closed; form-sequence remains V-PRB-6A; click-button:seed-1 json_invalid did not reproduce in targeted recheck
  next_requirement: keep V-PRB-6B closed for enter-text required read-only availability unless it regresses; retain V-PRB-6A progress-target foundation as compatibility-only; continue through ODG role/projection/attribution contracts before any new production progress authority; monitor the click-button json_invalid schema/provider robustness cluster separately; do not claim breadth completion, fresh diagnostic, or promotion
  promotion_status: held

v_prb_3_architecture_follow_up:
  status: retired_by_planner_selection_simplification
  resolver_manifest: retired; semantic_action_resolver.py is removed from production source and from executable authority-free collaborator manifests
  action_family_resolver_manifest: done; task_action_family_resolution.py is listed in the executable authority-free collaborator manifest and strict pure-owner dependency gate
  deep_immutable_output: not_applicable_after_module_deletion
  typed_input_boundary: replaced_by_runtime_actionchoice
  extracted_cluster: V-PRB-3 empty clarification resolution
  still_in_generalist_planner: []
```

Earlier remote failures were classified and repaired as narrow CI/harness or
runtime-diagnostic issues: core pytest now runs through the active interpreter,
the BrowserGym bridge job uses the documented isolated BrowserGym dependency
profile, diagnostic benchmark execution is separated from promotion
acceptance, and cross-surface conformance checks the authoritative
`ACTION_CONTRACT_SCHEMA_VERSION` instead of a stale hard-coded schema value.
After those commits, a subsequent GitHub Actions attempt did not start jobs
because account billing/spending limits were exhausted. Remote CI has now been
closed for this iteration, so the current status is `disabled`, not a code
failure. Local success must not be described as remote-CI or immutable
promotion evidence.

## Horizontal Architecture Governance

This is an independent, always-active track rather than an `M*` milestone. Its
normative execution semantics are in
[Horizontal Architecture Governance Track](architecture-governance-track.md).
A failed gate blocks the violating change, not unrelated milestone work or the
repository until a unified rewrite is complete.

| Track state | Snapshot | Admission baseline | Active waiver | Next remediation |
| --- | --- | --- | --- | --- |
| `active` | SAR-0 authoritative optimized architecture is the current default target; TPA-0 through TPA-5, S0 through S2.1, and ODG-0 through ODG-9 are retained as historical foundation/diagnostic records; SAR-4 standard Generalist/Parent Planner response cutover, SAR-5 exact action/destination scope plus default terminal-readiness admission removal, SAR-6A canonical ActionOutcome recording, SAR-7 writer centralization plus SAR-7.1-7.5 semantic cleanup, SAR-8C default RecoveryPhase cutover, and Planner Selection ActionChoice fallback retirement are local-complete for their recorded scopes. Clean SAR-7 PR breadth passed 12/12; fresh diagnostic completed 60/60 with 15/60 pass and residual broad capability failures. Local `7af5ec6` targeted non-qwen Ollama `llama3.1:8b` run observed 2/3 pass but does not close behavioral promotion. Failure Ownership Router is the selected SAR-9 prerequisite. Remote CI disabled. | Coordinator ratchets are checked by executable governance tests; planning/intake/control ratchets plus TaskPlan commit/constructor, Step Planner signature, TaskSkill default-state removal, dependency, PlanningRequest contract/builder, PlannerContext request-path, admission-contract, DecisionConstraintSet immutability, active-step admission, Generalist request-core, ParentAgent adapter request-core, reference contract planner request-core, conformance/recovery fixture request-core, BrowserGym compatibility request projection, PlannerPort request-only public contract, TaskPlanAuthority contract, PlanCandidate generator, execution-commit gates, SAR-1 deep-immutability gates, SAR-2 canonical semantic vocabulary gates, SAR-5 exact ActiveStepScope proposal gate, SAR-6A ActionOutcome recording gate, SAR-7 progress-flow extraction gate, SAR-7 planner-terminal gate, SAR-7 terminal-success gate, SAR-7.2 default-progress-state cleanup gate, SAR-7.3 bounded action-dedupe gate, SAR-7.4 TaskProgress default-field gate, SAR-7.5 TaskSkill progress-state removal gate, SAR-8 recovery taxonomy/phase-cutover gates, Planner Selection ActionChoice gates, and the planned Failure Ownership Router gate | none | Implement FOR-1..FOR-4 before SAR-9: replace disposition with six-way FailureOwner, narrow RecoveryPhase to Runtime-owned mechanical recovery, add structured step/task/user/progress handoff, delete duplicate owner routing, then run behavioral classification. TPA-5B foundation expansion, ODG-9 hookup, ODG-10, ODG-11, unauthorized alternate progress authority, official score claim, and promotion remain unauthorized |

The current SG7 repair also has a semantic ownership review state:
`semantic_ownership_review: pending_review`. Its deterministic fallback behavior is accepted as a
targeted, generic repair candidate under existing tests, but the ownership of
value-entry interpretation, page-observed value binding, and terminal-submit
fallback must be revisited before planner/intake responsibility can be called
clean. Until then, these paths may not expand through task-name, URL, selector,
Prompt-only, budget, or benchmark-family branches.

Change admission uses `pass | fail | waived | not_evaluated`; remediation items
use `pending | in_progress | done | blocked`. These states do not replace the
milestone maturity labels below.

## Summary

| Milestone | Status | Current evidence | Remaining gate |
| --- | --- | --- | --- |
| M0 Design Freeze | done | contracts, state machine, approvals, trace schema, scenarios, gates | none |
| M1 Web Gold Path | done | real Chromium pricing, pre/post observation, verification, artifacts, CLI, baseline | none |
| M2 Local Reliability | done | three scenarios, distinct deterministic perturbations, approval/download oracle, 3 x 7 matrix | none |
| M3 Assisted Evolution | done | classifier, typed executable proposal, fresh replay, direction-aware decision, persistence, rollback | none |
| M4 Integration Boundary | done | in-process task service, bounded adapter, external JSON-RPC, real LangGraph parent | none |
| M5 Evidence Freeze | done | CI, package build, environment manifest, versioned reports, clean-clone reproduction at `4528f25` | none |
| M6 Executable Evolution | done | SHA-bound verifier payload, fresh candidate, six new Chromium replays, persisted acceptance and rollback proof at `4cccc96` | none |
| M7 External Integration | done | separate runtime process plus real LangGraph 1.2.9 parent completes pricing and approval export at `9a9796e` | none |
| M8 Generalization Eval | done | three distinct training layouts, six held-out runs, five visual runs, and 18 pinned official MiniWoB++ episodes at `e463e16` | none |
| M8.1 Container Reproducibility | done | digest-pinned non-root profile, exact 63-run host/container agreement, and real DOM/visual/WoT conformance at `40fd93b` | none |
| M8.2A Task Intake and Planner Contracts | in_progress | SG1-SG6 complete locally: code-owned schemas, bounded SourceLedger lineage, canonical flat/multi-stage graph reconstruction with typed evidence, deterministic source-to-terminal coverage, proposal normalization, veto-only audit, bounded repair, and held-out non-BrowserGym conformance. SG7 targeted protected-family confirmation passed cleanly at `3d44a9d`: `enter-date` and `text-transform`, seeds 0 and 1, 4/4 observed and passed, no provider/runtime failure, `official_score_claimed=false`. PR breadth diagnostic at `d66760f` completed 12/12 observed with 0/12 passed; after V-PRB-1, V-PRB-3, V-PRB-2, V-PRB-5A, V-PRB-5B, three V-PRB-5C repairs, and V-PRB-6B progress accounting through clean `407133d`, the current matrix is 12/12 observed, 11/12 official reward passed, and 3 Runtime failures. V-PRB-6B closes `enter-text:seed-1`; `form-sequence` exposed the broader dual-authority problem now governed by ODG-0/ODG-2. `click-button:seed-1` JSON-invalid is monitored after a targeted clean recheck passed. | continue ODG-2/ODG-3 obligation progress authority foundation; no breadth acceptance, fresh diagnostic, or promotion claim |
| M8.2B Public Benchmark Audit | in_progress | clean `df5b820` 30 x 2 diagnostic completed 60/60 at 24/60 success with zero provider failure/retry and 36 attributed residuals; SG1-SG7 later closed the targeted protected-family intake/planning failure for `enter-date` and `text-transform` seeds 0 and 1; latest PR breadth evidence at `407133d` remains promotion-held with 11/12 official reward and 3 Runtime failures after V-PRB-6B closed `enter-text:seed-1`; targeted click-button recheck at `47932a2` did not reproduce the JSON-invalid case. | hold PR/nightly/release; next production candidate must follow ODG role/projection/attribution contracts rather than pre-action TaskPlan subgoal attribution |
| M8.3 Recovery-Cascade Components | in_progress | incident/loop detection, lower-half online recovery, typed dispatch, configured provider-switch owner, planner-context compaction owner, and target-bound planner-schema repair owner wired in BrowserGym and `GeneralistTaskPipeline` normal entrypoints | level-4 empirical effectiveness remains open; do not claim full-phase recovery |
| M8.4 Adaptive Shallow Task Planning | in_progress | TaskPlan contracts, criteria-bound progress, obligation outcomes/evidence, deterministic cross-scenario controls, and stateless decision admission | prove held-out behavior |
| M8.5 Unified Adaptive Routing and Skill Internalization | in_progress | unified candidates, routes, gestures, safe fallback, active perception, trace mining, accepted profile loading, fallthrough, and rollback | preserve generic main path while planner/recovery operational gaps close |
| M8.6 Planner, Active Perception, and Recovery Governance | in_progress | `c939051` closes the scoped internal gate/rollout; concrete context/schema recovery owners plus neutral Planner/approval contracts remain green through the latest implementation-bearing local-equivalent baseline `66747420c4d319d26a10a7c6fb6006871cf3310a` | level-4 recovery effectiveness, planner generalization, immutable Planner input, semantic ownership review, and Coordinator responsibility reduction remain open |
| M9 Durable Single Run | pending | in-memory state only | conditional on a measured restart/waiting failure |

## M0: Design Freeze and Status Alignment

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Authoritative current plan and two-horizon rule | done | `current-implementation-plan.md`, `complete-architecture-blueprint.md` |
| Three Web/SaaS scenario specifications with oracles | done | `scenarios/pricing-extraction.md`, `scenarios/settings-update.md`, `scenarios/approval-gated-report-export.md` |
| System invariants and recovery matrix | done | `design-freeze.md` |
| One task-level state machine in code | done | `coordinator.py`, transition validation in `state_kernel.py`, coordinator tests |
| Action Contract schema v1 with snapshot and target validity | done | canonical hash and snapshot/page/target/TTL fields plus preflight tests |
| Approval binding contract | done | single-use token binds run/hash/revision/capability/approver/expiry |
| Minimum trace event schema | done | state, versions, causal parents, policy/preflight, receipts, verification, and artifact refs |
| Declarative evolution artifact schema | done | version metadata and direction-aware regression rules |
| README/status claims match implementation | current | `status_alignment.snapshot=current`; this is a continuing governance assertion, not a one-time milestone closure |

## M1: Web Gold Path

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Local pricing fixture with canonical oracle | done | `/pricing`, `/api/pricing`, reset endpoint, and oracle test |
| Playwright-compatible pre/post observer | done | plan, immediate-preflight, and post-action observations |
| DOM affordance builder and executor | done | semantic page revision, target fingerprint, leases, and DOM executor |
| Scripted planner through `PlannerPort` | done | deterministic `PricingPlanner` |
| RunCoordinator and multi-step RunState | done | serial coordinator, transitions, budgets, evidence, and recovery boundaries |
| Post-action structural verifier | done | DOM verifier runs against post-action HTML |
| Artifact store and complete run layout | done | run JSON, JSONL events, observations, screenshots, receipts, verification reports, hashes |
| One-command CLI gold path | done | `affordance-runtime run --target ... --artifacts ...` |
| Direct Playwright baseline | done | `affordance-runtime baseline --target ...` |
| Repeated pricing run and stale perturbation evidence | done | three consecutive Chromium runs passed; deterministic drift test blocks stale execution |

## M2: Runtime Reliability and Cross-Surface Proof

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Settings and export fixtures | done | real settings persistence/API oracle and approved report download/file-hash/audit oracle |
| Drift/modal/delay perturbation controls | done | target replacement, selector drift, async enablement, blocking modal, transient API error, and delayed download are deterministic fixture controls |
| Scoped capabilities and approval gate | done | explicit capability plus single-use bound approval; unapproved Chromium export stops in `WAITING_APPROVAL` |
| Bounded recovery integrated into coordinator | done | execution/preflight/verification failures enter the deterministic recovery policy within budgets |
| Shared DOM/SoM/WoT contract execution path | done | all three surfaces pass the same coordinator, contract, trace, and verifier path in tests |
| Benchmark runner with independent oracles | done | executable local runner uses pricing JSON, settings API, export audit/file hash, and perturbation labels |
| JSON, Markdown, and CSV reports | done | `BenchmarkReportWriter` and format tests |
| Direct/primitive/full baselines and required ablations | done | fixed-seed 3 scenarios × 7 variants execute through the CLI and emit reports |
| Zero unsafe side effects under the suite | done | Full Runtime report: success 1.0, constraint violations 0.0, unsafe side effects 0.0; disabling capability gate produces the expected unsafe export signal |

## M3: Assisted Harness Evolution

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Failure taxonomy classifier | done | typed seven-class classifier maps benchmark/trace evidence and is tested |
| Typed declarative proposals | done | typed artifact types, proposal schema, applicability, source trace, negative examples, and validation plan |
| Quarantine/version/rollback registry | done | atomic JSON registry store, accepted-only loading, version history, runtime unload, persisted rollback proof |
| Direction-aware regression gate | done | higher/lower-is-better thresholds, allowed regression, missing-metric quarantine tests |
| Replay-category accounting | done | decision requires original, family, global-smoke, and safety-smoke evidence |
| Executable artifact applied before fresh replay | done | SHA-bound verifier payload is loaded into a fresh no-verifier candidate before six real Chromium runs |
| One real failure before/after report | done | no-verifier settings false accept is fixed; original/family/global/safety replay passes with no unsafe regression |

## M4: Optional Integrations

| Deliverable / exit criterion | Status | Evidence or next action |
| --- | --- | --- |
| Stable task-level API | done | `TaskRuntimeService` supports submit, execute, status, scoped approval, cancel, result, evidence, and trace |
| Parent agent cannot bypass runtime with public primitive actions | done | `TaskToolAdapter` exports only eight task-level operations; click/type/observe are absent |
| Local working integration | done | `LocalScenarioTaskRunner` connects the task API to real Chromium scenarios |
| Real external parent-agent integration | done | compiled LangGraph calls separate runtime process over `affordance-task-rpc/1.0`; pricing and gated export pass |
| Evidence and trace retrieval | done | adapter returns artifact paths and parsed JSONL events |
| Optional PiP decision gate | done | deferred: no measured observer/takeover need justifies another UI surface |

## M5-M9 Forward Gates

| Milestone | Required evidence |
| --- | --- |
| M5 | done: CI, package build, environment identity, clean-checkout command, and versioned benchmark/evolution summaries at `4528f25` |
| M6 | done: executable payload, fresh candidate runtime, mandatory replay, persisted decision, and rollback at `4cccc96` |
| M7 | done: real LangGraph submission/approval/result/evidence/trace over an external protocol with no primitive GUI bypass at `9a9796e` |
| M8 | done: distinct seeds, unseen layouts, repeated pinned MiniWoB++ subset, and real visual grounding at `e463e16` |
| M9 | only after a failing restart/waiting case; simple durable state/events and uncertain-effect inspection |

### M8 Generalization Evidence

The clean `e463e16` checkout upgraded the fixture to distinct seeded layouts
and passed all M8 gates:

```text
training matrix = 63/63 accepted, 3 distinct layout fingerprints
held-out local scenarios = 6/6
visual screenshot grounding = 5/5, 5 distinct boxes, no DOM coordinates
official MiniWoB++ = 18/18 raw-reward success across 6 task families
```

The official subset is pinned to Farama commit
`eb59fed60fabe8951350275ba8650633b740013b` and owns episode reset, instruction
extraction, termination/reward collection, runtime diagnostics, and report
aggregation. It is a curated compatibility/generalization subset, not a claim
of a full MiniWoB++ score.

## M8.1-M8.3 Forward Work

### M8.1 Container Reproducibility — done

The profile contains the in-memory fixture, test runner, benchmark runner,
health checks, and mounted artifacts. The optional `wot-proof` profile
selectively migrates the old node-wot fixture and a minimal dashboard; it is
not part of the default Web profile.

Clean commit `40fd93b` provides the digest-pinned non-root fixture, test, and
benchmark services. Its 63 stable host/container outcomes agree exactly. The
optional real node-wot profile reaches the same independent oracle through DOM,
real screenshot/SoM, and WoT while retaining Coordinator contracts, verifier
evidence, and traces. See `evidence/m8.1-40fd93b.md`.

### M8.2A Task Intake and Generalist Planner

Contract and local canonical-intake boundaries are done; empirical open-world
behavior remains open. UserRequest, IntentDraft,
immutable TaskSpec, semantic PlannerProposal, ContractBuilder, provider-neutral
ports, clarification revisions, and trace lineage exist. The 2026-07-23 audit
below is historical diagnosis; later SG1-SG6 slices replace provider-authored
authority with Runtime canonical compilation and deterministic coverage. Those
local gates still do not prove open-world planner generality.

At `7edaa97`, Mistral completed controlled intent compilation plus verified
pricing read-only, settings reversible-write, and approval-gated report export
paths. The same planner class is tested across DOM/SoM/WoT affordances and
passed an official BrowserGym `click-button` smoke through typed action binding.
See `evidence/m8.2a-7edaa97.md`.
Clean `bba582c` closes the local correctness defects around bounded intake
repair: malformed provider obligation nodes become typed repair input, graph
fields survive repair, model-call reservations are counted, repair has an
immutable Prompt/checkpoint identity, selected provider profile is preserved,
and failed repair emits a redacted trace event.

The historical `bba582c` snapshot still lacked Runtime-owned canonical graph
construction. That statement is superseded by locally completed SG2-SG6:
`CanonicalObligationCompiler` now reconstructs flat and bounded multi-stage
graphs, typed evidence and deterministic source-to-terminal coverage gate
admission, and the model audit has veto-only authority. Protected-family,
breadth, diagnostic, nightly, and release promotion remain separately gated.

### M8.2B Public Benchmark Audit - diagnostic complete, repair required

The latest clean strict diagnostic at `df5b820` completed all 60 episodes at
24/60 success (`0.4`) with zero provider failure, retry, missing episode,
invalidation, or batch stop. Its 36 envelopes are 12 intent/planning, 11
contract/field binding, 8 verification, 3 execution, and 2 observation/context.
The result is diagnostic and non-promotable. It also contains protected-family
regressions, including `text-transform` 2/2 to 0/2 and `enter-date` 2/2 to 1/2.
The immutable report must be published before any release claim.

The earlier strict-generalist evaluation at implementation SHA `351dbdf` completed
all 60 scheduled cases in seed-major order after fresh smoke and PR breadth
gates. It recorded 19 successes and 41 failures, mean official reward
`0.3166666667`, 251 model calls, and zero provider failures, rate-limit retries,
transient retries, missing cases, invalidations, or batch stops. Seven tasks are
2/2, five are 1/2, and eighteen are 0/2. `official_score_claimed` remains false.

Formal envelopes contain 4 contract/field-binding, 4 execution, 7
intent/planning, and 26 generic recovery results. Because the recovery bucket
mixes unlike precondition, approval, routing-target, and terminal-action facts
across eight families, frozen nightly is held. The next implementation slice is
generic attribution fidelity followed by cross-family contract, context,
subgoal-routing, and execution/verification owners—not task-specific repair.
Evidence: `evidence/runs/m8.2b-diagnostic-351dbdf/`.

The isolated BrowserGym 0.14.3 adapter routes every supported action through
`RunCoordinator`, exposes a typed action whitelist, discovers 125 registered
MiniWoB tasks, checkpoints resumable episodes, and records official reward
separately from runtime diagnostics. The latest GPU-local v101 PR matrix has
18/18 coverage and official success; v102 covers all 30 nightly-manifest tasks
at seed 0 with 0.9667 mean reward and no provider/runtime/429/retry failure.
Structured SVG point families and sortable drag families pass 10/10, while
v103 enforces clean source identity for the pending frozen nightly/release.

Before larger or external matrices, repository claims, dependency constraints,
the BrowserGym module split, and the `miniwob-action-family-v1` 30-task nightly
manifest are complete. A real screenshot-capable visual grounder is implemented,
but official ScreenSpot assets are still required before a result claim.
WebArena-Verified is publicly provisioned rather than authorization
gated; its missing requirement is a running official environment plus agent
response/HAR artifacts. WorkArena remains the only suite in this ladder that
requires gated instance access.

The earlier task-specific `benchmarks.miniwob` compatibility runner remains
available only to reproduce historical M8 evidence. Its generated reports are
explicitly ineligible for M8.2B scoring; current MiniWoB claims must use the
BrowserGym Generalist full-Coordinator track.

Current local external-suite preflight (2026-07-22) remains intentionally
non-runnable where provisioned inputs are absent: the ordinary project Python lacks BrowserGym,
but the existing isolated Python 3.12 runtime has pinned MiniWoB 0.14.3 and
Playwright 1.44, and the launcher-confirmed current-code local smoke passes
6/6 with 18 calls and no runtime/provider failure. This dirty-tree run remains
a runtime confirmation rather than a promoted score. Runtime discovery is now
guarded by dedicated BrowserGym and WorkArena preflight boundaries. WorkArena
v104 selects only its dedicated interpreter and probes it without credentials;
the environment, L1 registration, and authorized ServiceNow instance are still
absent. ScreenSpot assets, a running WebArena-Verified
environment plus upstream agent artifacts, and an isolated WASP VisualWebArena
evaluator are likewise absent from this worktree. These are deployment/asset
gates, not zero-score results; no dependency install, credential lookup, or
remote benchmark request was made.

The v109 clean immutable 30x10 nightly completed 300/300 and exposed one
acceptance error plus two execution failures. The replacement v112 nightly
passed 300/300 for its exact revision and active compiler profile. These are
historical compatibility and diagnostic results, not proof of a
strict-generalist planner. The scoped M8.6 internal gate is closed, and the new strict diagnostic
remains non-promotable while its cross-family residual owners are open;
release and provisioned external suites remain later audit gates.

### M8.3 Recovery-Cascade Components - partial

Clean commit `07e406f` groups attempts under normalized failure signatures,
preserves root failure and symptoms, and detects repeated signatures,
no-progress, A-B oscillation, stale/verifier repetition, exhausted fallback,
and duplicate-effect risk. The benchmark schema reports cascade depth,
repetition, loop abort, effectiveness, and duplicate-effect diagnostics.

Typed `RecoveryPolicyPatch` and `RecoverySkill` payloads are digest-validated,
bounded, risk-scoped, accepted-only loaded, and unloadable. A real Coordinator
cascade was stopped online at depth two; its quarantined policy reduced fresh
original/family replays to depth one, passed global and uncertain-effect safety
smoke with no blind retry, persisted acceptance, and proved rollback. See
`evidence/m8.3-07e406f.md`.

### M8.4 Adaptive Shallow Task Planning - component done

`TaskPlan`/`SubgoalSpec`, `PlanProgress`, deterministic validation, the
rule/LLM planner router, Coordinator sequencing, and controlled
Flat/Always-plan/Adaptive ablation exist.

The shared matcher advances Subgoals and SkillSteps only from fresh, strong,
explicitly linked evidence covering every mandatory criterion and evidence
requirement. `TaskPlanningContext` now carries bounded environment, affordance,
evidence, failure, recovery, assumption, and remaining-budget summaries;
replacement plans form a monotonic supersession chain and preserve verified
subgoals. The optional normal pricing CLI path completes two stages in real
Chromium. See `evidence/runtime-r2-task-planning-context-20260722.md`,
`evidence/runtime-r1-criteria-evidence-20260722.md`,
`evidence/m8.4-task-planning-ablation.md`, and
`current-architecture-audit-20260722.md` for the remaining completion gates.

### M8.5 Unified Adaptive Routing and Skill Internalization - component done

Typed candidates, unified routes, Core dual-target gesture contracts, fresh
fallback contracts, inspect-before-repeat, visual/DOM/WoT component proofs,
source-conflict extension points, and TaskSkill/RecoverySkill models exist.

Runtime-first R3 and R4 now cover generic TaskSpec/SubgoalSpec-to-perception
wiring, ordinary BrowserSession visual candidates and sourced assertions,
target-specific evidence gates, verifier-backed scoped route calibration, and
geometry-aware conservative fusion. Canonical trace mining and accepted-profile
loading exist as components. Milestone completion still requires empirical
main-path evidence and removal of the remaining allowlisted benchmark-package
dependencies from shared modules.

R4 evidence: `evidence/runtime-r4-verifier-calibrated-routing-20260722.md`.

Follow M8.5R in `current-implementation-plan.md` and the normative
`runtime-first-boundary.md`. The prior completion audit is component evidence,
not milestone closure.

### M8.6 Planner, Active Perception, and Full-Phase Recovery Governance - internal gate done

The [M8.6 Closure Audit](current-closure-audit-20260724.md) reopened behavioral
and responsibility-containment exit criteria. The scoped repairs and fresh G5
internal rollout pass for immutable implementation revision `c939051`. M8.2B
has since completed a separately identified strict diagnostic at 24/60; it is
not promotion evidence.

The governing documents are:

- [Runtime-First Architecture Boundary](runtime-first-boundary.md);
- [Responsibility Containment Boundary](responsibility-containment-boundary.md);
- [Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md);
- [Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md);
- [M8.6 Closure Audit](current-closure-audit-20260724.md).

| Gate | Status | Evidence and remaining work |
| --- | --- | --- |
| G0 Freeze and classify | complete | score-bearing and legacy summaries are classified; current identities are explicit |
| G1 Strict-generalist profile | complete | strict default, physical compatibility isolation, typed provenance, shared proposal validation, and anti-specialization controls |
| G2 Intent and TaskPlan integration | obligation chain and decision owner complete | TaskSpec obligations compile to same-id outcomes, every plan source is checked, verified evidence reaches TerminalReadiness, cross-scenario controls pass, and `DecisionConstraintSet` owns typed text, ordinal, terminal, and current-state admission |
| G2.5 Active perception and evidence repair | repaired / locally verified | strict authority intersection, no adapter escalation, current relevant semantic-candidate evidence, typed flow owner, and negative controls pass |
| G3 Full-phase Recovery Coordinator | component owners integrated / empirical gate open | BrowserGym generalist and `GeneralistTaskPipeline` configure concrete context-compaction and planner-schema repair owners; a provider-switch owner is added only for a real multi-profile fallback. Level-4 effectiveness and every-entrypoint coverage remain unproven. |
| G4 Complete-run audit | complete | immutable run identity, ordinary-failure continuation, exact resume, allowlisted batch stops, and post-collection clustering |
| G5 Internal conformance evidence | complete for internal scope | fresh 11-case profile-separated Runtime rollout at `docs/evidence/runs/m8.6-g5-c939051`; expected/safe outcomes 100%, hash index revalidated, external/open-world suites unprovisioned |
| Responsibility containment | Planner/approval contracts extracted / feature freeze remains | ActivePerceptionFlow, RecoveryCommandDispatcher, Runtime evidence projections, stateless TaskPlanFlow, TaskPlanCommitPreparation, RecoveryTraceProjection, TaskObligationCoverage, TaskObligationOutcomeCompiler, immutable PlannerModelRequest, neutral PlannerDecision/PlannerPort contracts, explicit approval-source contracts, and the ODG-5 post-observation diagnostic seam have typed ownership; strict `propose()` remains separately bounded and Coordinator owns task-execution commit sequencing at 3461 lines / 26 methods. Legacy harness, skill/progress mutation, and scoped non-execution trace debt remain explicitly tracked; the reduction target remains open. |

Current verified facts:

- the default planner is strict-generalist and historical task grammar is
  physically isolated;
- proposal provenance and validation are shared across model, deterministic,
  parent, skill, and recovery sources;
- raw requests enter typed intent and TaskPlan routing;
- active perception and lower-half recovery run through normal Coordinator
  paths; BrowserGym generalist and `GeneralistTaskPipeline` configure concrete
  context/schema owners, while configured multi-profile paths can also switch a
  fallback provider through a real owner;
- complete-run accounting continues after ordinary failures;
- immutable historical evidence remains bound to its recorded revisions. The
  latest implementation-bearing baseline
  `66747420c4d319d26a10a7c6fb6006871cf3310a` passed the local equivalent gate:
  957 tests, Ruff, mypy over 116 source files,
  `uv build`, Chromium smoke, BrowserGym bridge smoke, diagnostic benchmark
  smoke, Docker runtime-test, Docker benchmark diagnostic, Docker WoT
  conformance, and diff check. Later documentation-only sync commits must
  record their own focused gates instead of being treated as full runtime
  evidence. Remote CI is disabled for this iteration, so this is locally
  reproducible implementation evidence, not remote-green or immutable
  promotion evidence.

Current blockers for the scoped `c939051` internal gate: none. This does not
close the broader product work. Entrypoints still explicitly own dispatcher
composition, level-4 recovery effectiveness remains unproven, the Coordinator
remains above its reduction target, and strict planner behavior is still
diagnostic. External-suite provisioning is a separate confirmation gap.

Current vertical next action (the horizontal architecture track applies in
parallel and is not an arrow in this sequence):

~~~text
SG1-SG6 canonical intake and local conformance complete
  -> context/schema normal-entrypoint owners complete at component level
  -> targeted SG7 protected-family confirmation complete
  -> protected cross-family / PR breadth and fresh diagnostic confirmation
~~~

The broader product claim may be promoted only when enabled recovery actions
have concrete normal-entry owners and real evidence-backed changes, authority
budgets only narrow downstream, semantic requirements use target-relevant
evidence, Coordinator and Planner pass their reduction gates, and comparisons
come from immutable Runtime runs without protected-family regression. External
suites remain independently provisioned and historical scores remain
unpromoted.

## Verification Commands

Run these from the repository root:

```bash
docker compose build runtime-test
docker compose run --rm runtime-test

# A separately provisioned development environment may run:
python -m pytest -q
python -m ruff check src tests scripts
python -m build

# Current repository-governed static gate:
python -m mypy --ignore-missing-imports src
```

M1 end-to-end commands:

```bash
affordance-runtime serve-fixture --port 3000
affordance-runtime run --target http://127.0.0.1:3000/pricing
affordance-runtime baseline --target http://127.0.0.1:3000/pricing
```

M2 and M3 evidence commands:

```bash
affordance-runtime benchmark --output benchmark-results --seeds 3
affordance-runtime evolve \
  --benchmark-report benchmark-results/benchmark-report.json \
  --output evolution-results
python scripts/generalization_smoke.py \
  --benchmark benchmark-results/benchmark-report.json \
  --output generalization-results
```

Clean-checkout M0-M8 gate:

```bash
./scripts/reproduce_local.sh
```

## Change Ledger

| Date | Workstream / milestone | Change | Files | Verification |
| --- | --- | --- | --- | --- |
| 2026-07-28 | V-PRB-5 review governance refinement | Incorporated the latest review as governance and planning state before any further production repair: split V-PRB-5 into child diagnostic records for 5A button-sequence effect semantics and 5B entry action-family resolution, added V-PRB-6 terminal-completion guard classification, and recorded that V-PRB-3's semantic resolver must be executable-gate protected while deeper immutable output/input typing remains future debt. | `docs/change-admission/v-prb-5a-button-sequence-effect-semantics.yaml`, `docs/change-admission/v-prb-5b-entry-action-family-resolution.yaml`, `docs/change-admission/v-prb-6-terminal-completion-guard.yaml`, current/status/horizontal-governance records, horizontal governance test | documentation/governance slice only; no production behavior, provider run, benchmark episode, remote CI, score, or promotion claim. Focused governance gates must pass before commit. |
| 2026-07-28 | V-PRB-5A requested-effect sequence repair | Added a compiler-local sequence-preservation switch for multi-stage requested-effect fallback. Runtime still owns canonical graph ids and node construction; flat requested-effect defaults remain independent terminal effects. The repair does not modify Coordinator, StateKernel, PlannerPort, Prompt, budget, task grammar, benchmark-specific logic, or verifier authority. | `canonical_obligation_compiler.py`, `intent_compiler.py`, canonical compiler tests, V-PRB-5A admission/status records | non-BrowserGym RED `test_requested_effect_sequence_preserves_dependency_and_terminal_boundary` failed before the repair and passes after it; flat-default regression added. Focused compiler/intake/planning/governance tests passed 152/152; full local pytest passed 975/975; Ruff, mypy over 117 source files, and diff check passed. PR breadth rerun is required on the clean committed revision before judging button-sequence impact. |
| 2026-07-28 | ODG-5.3 post-observation shadow trace hookup | Replaced the inline Coordinator current-state completion block with the `commit_post_observation_progress()` seam and wrote diagnostic-only `ObligationProgressShadowCompared` / `ObligationProgressShadowFailed` events after post-observation progress handling. | `src/affordance_runtime/task_plan_progress_flow.py`, `src/affordance_runtime/coordinator.py`, `tests/test_post_observation_progress_flow.py`, `tests/test_browsergym_adapter.py`, ODG-5 admission/current/status/governance records | RED first failed because `commit_post_observation_progress` did not exist. Focused ODG/governance gates report 77 passed. Full local pytest reports 1049 passed, 1 xfailed. Ruff, mypy over 125 source files, `uv build`, and diff check pass. `coordinator.py` is ratcheted down to 3461 lines, `RunCoordinator.run_sync` to 2034 lines, and RunCoordinator remains at 26 methods. No obligation ledger initialization/mutation, Coordinator obligation satisfaction commit, finish authority change, PlannerContext change, TaskPlan behavior change, BrowserGym rerun, PR breadth claim, or promotion claim. |
| 2026-07-28 | V-PRB-5A clean PR breadth rerun | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `0565e2ef3f5d082cdc13652b8ca399a393ef4074` after the compiler-local V-PRB-5A repair. | `docs/evidence/runs/m8.2a-pr-breadth-0565e2e/`, `/tmp/affordance-pr-breadth-0565e2e-20260728-005603` | Negative evidence: 12 expected, 12 observed, 7 official reward passed, 5 official reward failed, 6 runtime failures, no missing/unrun/invalidated cases, `official_score_claimed=false`. V-PRB-5A is not closed: both `click-button-sequence` seeds still fail with `planner_waiting_clarification`. Trace classification shows dependency/terminal boundaries are now present, but clicked targets remain `predicate / is_available` obligations and weak execution evidence is correctly rejected. `form-sequence` remains V-PRB-5B, `enter-text:seed-1` remains V-PRB-6 terminal guard, and `click-button:seed-1` now requires separate `schema_incompatible` classification. |
| 2026-07-28 | V-PRB-5A clicked navigation relation repair | Added the second V-PRB-5A non-BrowserGym RED/GREEN repair after the clean `0565e2e` rerun showed dependency/terminal semantics were fixed but clicked targets still compiled as availability predicates. Multi-stage NAVIGATION requested effects whose success criteria mark the target as clicked/activated/pressed/selected/submitted now compile to `effect / is_completed` obligations while preserving compiler-owned dependency and terminal boundaries. | `src/affordance_runtime/canonical_obligation_compiler.py`, `src/affordance_runtime/intent_compiler.py`, `tests/test_intent_compiler.py::test_llm_compiler_canonicalizes_clicked_navigation_effects_as_completed_actions`, V-PRB-5A admission/status records | RED failed first on `predicate` versus expected `effect`; after the repair, focused compiler/intake/planning/governance tests passed 143/143, full local pytest passed 976/976, Ruff, mypy over 117 source files, and diff check passed. No Coordinator, StateKernel, PlannerPort, Prompt, budget, task grammar, benchmark-specific branch, or verifier authority change. A clean PR breadth rerun on the committed repair revision is still required before judging button-sequence impact or any breadth completion claim. |
| 2026-07-28 | V-PRB-5A clean PR breadth rerun after clicked relation repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `e4795c1f25aeebeda63c715829e188e052acdab5` after the second V-PRB-5A repair. | `docs/evidence/runs/m8.2a-pr-breadth-e4795c1/`, `/tmp/affordance-pr-breadth-e4795c1-20260728-010712` | Negative evidence: 12 expected, 12 observed, 8 official reward passed, 4 official reward failed, 5 Runtime failures, no missing/unrun/invalidated cases, no provider failures, `official_score_claimed=false`; report sha256 `64f548a72917dd18a5d375040cec88b4bf6d416a1507d130af27d283009bd843`, matrix metadata sha256 `cb93c89becf900d2c8f6d82e9b5604fb263435b4add1f0188bf5afb26a47f80d`. V-PRB-5A is not closed: both `click-button-sequence` seeds still fail with `planner_waiting_clarification`. Trace classification now shows `effect / is_completed` obligations are present, but completed-click progress lacks independent observer/verifier evidence after execution; weak receipt/state-delta evidence is correctly rejected. `form-sequence` remains V-PRB-5B and `enter-text:seed-1` remains V-PRB-6; the prior `click-button:seed-1` schema incompatibility no longer reproduces. |
| 2026-07-28 | V-PRB-5A completed-click progress evidence repair | Added the third V-PRB-5A non-BrowserGym RED/GREEN repair after the clean `e4795c1` rerun showed completed-click obligations were present but progress evidence remained incomplete. Completed click outcomes now add a post-observation `observation_metadata(active_control == bid)` verifier scoped to the active subgoal. Generic `state_delta_or_terminal` remains terminal-only and weak; receipt success remains insufficient for subgoal completion. | `src/affordance_runtime/benchmarks/browsergym_encoder.py`, `tests/test_browsergym_encoder.py::test_browsergym_click_completed_outcome_declares_independent_progress_evidence`, V-PRB-5A admission/status records | RED failed first because the declaration only returned terminal-only `state_delta_or_terminal`; after the repair, focused browsergym/criteria/planning/governance tests passed 99/99, full local pytest passed 977/977, Ruff, mypy over 117 source files, and diff check passed. No Coordinator, StateKernel, PlannerPort, Prompt, budget, task grammar, benchmark-family branch, verifier weakening, or receipt-driven progress change. A clean PR breadth rerun on the committed repair revision is still required before judging button-sequence impact. |
| 2026-07-28 | V-PRB-5A clean PR breadth rerun after progress evidence repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `c75fc3b32b737180a3bf39d948811ad5e7730724` after the first completed-click progress evidence repair. | `docs/evidence/runs/m8.2a-pr-breadth-c75fc3b/`, `/tmp/affordance-pr-breadth-c75fc3b-20260728-011621` | Negative evidence: 12 expected, 12 observed, 8 official reward passed, 4 official reward failed, 5 Runtime failures, no missing/unrun/invalidated cases, no provider failures, `official_score_claimed=false`; report sha256 `5c4dd324482a132d28429fdfaf4c2ce196d0db2eb3317f2737b34520f0d64ee1`, matrix metadata sha256 `3bdc66bd1fc1377f9c2e94c5d4fd82063887339ac22752778cddafc071158650`. Trace classification shows the progress verifier design did not enter real button-sequence contracts: `ContractBuilt` still contains only `evidence:last_action_error` and `state_delta_or_terminal`, while active subgoal action-family is empty. |
| 2026-07-28 | V-PRB-5A refined completed-click progress evidence repair | Refined the completed-click progress declaration after the clean `c75fc3b` rerun proved active action-family metadata is absent in the real button-sequence path. A present action-family still must match, but absent action-family metadata no longer blocks a typed `IS_COMPLETED` click outcome with a matching target from declaring independent post-observation progress evidence. | `src/affordance_runtime/benchmarks/browsergym_encoder.py`, `tests/test_browsergym_encoder.py::test_browsergym_click_completed_outcome_does_not_require_task_plan_action_family`, V-PRB-5A admission/status records | RED failed first because action-family `None` returned terminal-only `state_delta_or_terminal`; after the repair, focused browsergym/criteria/planning/governance tests passed 100/100, full local pytest passed 978/978, Ruff, mypy over 117 source files, and diff check passed. No Coordinator, StateKernel, PlannerPort, Prompt, budget, task grammar, benchmark-family branch, verifier weakening, or receipt-driven progress change. A clean PR breadth rerun on the committed refined repair revision is still required before judging button-sequence impact. |
| 2026-07-28 | V-PRB-5A clean PR breadth rerun after refined progress repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `151fbefc3470b7893eb9f92d4b85c75133bd6750` after the refined completed-click progress evidence repair. | `docs/evidence/runs/m8.2a-pr-breadth-151fbef/`, `/tmp/affordance-pr-breadth-151fbef-20260728-012127` | Negative breadth evidence but positive V-PRB-5A closure: 12 expected, 12 observed, 10 official reward passed, 2 official reward failed, 3 Runtime failures, no missing/unrun/invalidated cases, no provider failures, `official_score_claimed=false`; report sha256 `7a76b65b6be817e4afca73562cd5276470f71a06025b1c84d8075e17a459fca4`, matrix metadata sha256 `adb7d7e978a853c5da35c639c8042e57507ad47dae2c9a38c092c22fe1c2b4c0`. `click-button-sequence` seeds 0 and 1 now pass; V-PRB-5A is closed for this matrix. Remaining failures are V-PRB-5B `form-sequence` seeds 0 and 1 and V-PRB-6 `enter-text:seed-1`. |
| 2026-07-28 | V-PRB-5B clean PR breadth rerun after action-family resolver repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `5c7a2abf17c6e15f497cb613856730ddd9080242` after adding the authority-free task action-family resolver. | `docs/evidence/runs/m8.2a-pr-breadth-5c7a2ab/`, `/tmp/affordance-pr-breadth-5c7a2ab-20260728-013253` | Negative breadth evidence but positive original-failure closure: 12 expected, 12 observed, 8 official reward passed, 4 official reward failed, 4 Runtime failures, no missing/unrun/invalidated cases, no provider failures, `official_score_claimed=false`; report sha256 `bafb6c409351218c9b117f5f55a9438c5148c3a690f9057b530f63075b778a22`, matrix metadata sha256 `4255606fb169ebe17dc4064390c35cbb91224b1847066a1ce372b0676ed28021`. The original `form-sequence` `entry_action_family_unavailable` rejection no longer reproduces: TaskPlan is accepted and `press_key` is permitted. The run exposed a textbox fallback regression: `enter-text` seeds 0 and 1 now also produce empty `ask_user` / `planner_waiting_clarification`. |
| 2026-07-28 | V-PRB-5B textbox fallback repair | Added a second V-PRB-5B non-BrowserGym RED/GREEN repair after the clean `5c7a2ab` rerun exposed over-narrow current-affordance matching for textbox labels such as `tt`. Text field value-change obligations now infer `TYPE_TEXT` from typed current textbox affordance role/support even when subject and label tokens do not overlap. | `src/affordance_runtime/task_action_family_resolution.py`, `tests/test_task_planning.py::test_obligation_compiler_uses_textbox_affordance_for_text_field_change`, V-PRB-5B admission/status records | RED failed first with unresolved `action_family`; after the repair, focused task-planning/governance tests passed 118/118, full local pytest passed 981/981, Ruff, mypy over 118 source files, and diff check passed. `task_planning.py` remains under its frozen line ceiling at 1641/1642. Isolated package build remains environment-blocked by missing `ensurepip/python3.12-venv`; BrowserGym venv build is blocked by missing `setuptools.build_meta`. A clean PR breadth rerun on the committed repair revision is required before closing V-PRB-5B. |
| 2026-07-28 | V-PRB-5B clean PR breadth rerun after textbox fallback repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `3daf779bb8d1b6fb6c4e8a73c31fd00c514668fd` after the V-PRB-5B follow-up repair and evidence/status sync. | `docs/evidence/runs/m8.2a-pr-breadth-3daf779/`, `/tmp/affordance-pr-breadth-3daf779-20260728-013951` | Negative breadth evidence but positive V-PRB-5B closure: 12 expected, 12 observed, 10 official reward passed, 2 official reward failed, 3 Runtime failures, no missing/unrun/invalidated cases, no provider failures, `official_score_claimed=false`; report sha256 `7f037e730828f5c45d02173d6b9221f8b9639f6e22c970e164f5d2a214014d3f`, matrix metadata sha256 `ace05c1e278bdd1987177e7b6cd15b58dd21b04ab92058b0cb54ccc900b8a754`. The original form-sequence `entry_action_family_unavailable` rejection remains closed, `enter-text:seed-0` is restored, and V-PRB-5B is closed for action-family resolution in this matrix. Remaining failures split into V-PRB-5C `form-sequence` strict-planner empty proposal and V-PRB-6 `enter-text:seed-1` terminal-completion guard. |
| 2026-07-28 | V-PRB-5C clean PR breadth rerun after slider press-key clarification repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `a805f0dfd1b58b76951003b9d12b9561b19d40e1` after adding the bounded strict semantic slider `press_key` resolver. | `docs/evidence/runs/m8.2a-pr-breadth-a805f0d/`, `/tmp/affordance-pr-breadth-a805f0d-20260728-014828` | Negative breadth evidence: 12 expected, 12 observed, 10 official reward passed, 2 official reward failed, 3 Runtime failures, no missing/unrun/invalidated cases, no provider failures, `official_score_claimed=false`; report sha256 `c6c7b62ca23933e4123218262dfb09b63cc490521387cea989c12beb03fc5f0d`, matrix metadata sha256 `202a85e7a060ee63295e02ced09ece7348e72cfc25fd77ae110085aa94adcdc9`. The resolver entered the real form path and produced verified slider `press_key` actions, but both `form-sequence` seeds still later fail with empty `ask_user` after replan/progress normalizes the active slider subgoal. V-PRB-5C remains open and narrowed to that post-replan slider value/progress residual; V-PRB-6 `enter-text:seed-1` remains separate. |
| 2026-07-28 | V-PRB-5C verified-form follow-up repair and clean rerun | Added verifier-backed strict-planner follow-up resolution from a verified slider effect to the uniquely requested checkbox, and from a current-state satisfied requested checkbox to a unique terminal submit control. Reran the same PR breadth matrix on clean committed `9c1b58c33f20e2690221516a953ce96f910ef2d3`. | `src/affordance_runtime/semantic_action_resolver.py`, `tests/test_generalist_planner.py`, `docs/evidence/runs/m8.2a-pr-breadth-9c1b58c/`, `/tmp/affordance-pr-breadth-9c1b58c-20260728-020037` | Non-BrowserGym RED/GREEN plus focused generalist/architecture suite, full local pytest 984/984, Ruff, mypy, and diff check passed before commit. Clean rerun remained negative: 12 expected, 12 observed, 10 official reward passed, 2 official reward failed, 3 Runtime failures, no missing/unrun/invalidated/provider failures. Seed 0 reached the requested checkbox, but form terminal-submit and negative-slider stop/direction residuals remained; V-PRB-5C stayed open. |
| 2026-07-28 | V-PRB-5C negative-slider / terminal-submit repair and clean rerun | Stopped slider requested-value extraction from reading checkbox ordinal text and permitted terminal submit after the requested checkbox is current-state satisfied even when active-subgoal projection is stale. Reran the same PR breadth matrix on clean committed `d50a631a2e67b294db4b6273106df85fd941b3b7`. | `src/affordance_runtime/semantic_action_resolver.py`, `tests/test_generalist_planner.py`, `docs/evidence/runs/m8.2a-pr-breadth-d50a631/`, `/tmp/affordance-pr-breadth-d50a631-20260728-020748` | Non-BrowserGym RED/GREEN plus focused generalist/architecture suite, full local pytest 986/986, Ruff, mypy, and diff check passed before commit. Clean rerun is 12 expected, 12 observed, 12 official reward passed, 0 official reward failed, 3 Runtime failures, no missing/unrun/invalidated/provider failures, `official_score_claimed=false`; report sha256 `dc4b4b9d7cf192c3de9aab00544396ea26ab8932c55b75d2212ba09b94ec5518`, matrix metadata sha256 `d68de8f9f0c8ee37cb2b67a7aa3c580c0ea9f46291b6d85bdefcaa7eeaa03872`. V-PRB-5C is closed for the current PR breadth matrix; PR breadth acceptance remains held by V-PRB-6 terminal-completion guard aborts. |
| 2026-07-28 | V-PRB-6 compact trace projection and 6A RED | Archived a compact trace projection for the three d50a631 Runtime guard failures. The form-sequence cases narrow to active-subgoal progress-scope binding for dependent checkbox/submit follow-ups. `enter-text:seed-1` is reclassified before RED: the trace has two subgoals, not one, and the incomplete unit is independent read-only submit-button availability. Added a strict xfail executable RED for V-PRB-6A without production repair. | `docs/evidence/runs/v-prb-6-compact-d50a631/`, `tests/test_browsergym_encoder.py::test_browsergym_checkbox_has_changed_click_declares_active_subgoal_progress`, V-PRB-6A/6B admission/status records | Forced RED with `--runxfail` fails as expected because checkbox `HAS_CHANGED` click evidence remains `task_terminal` rather than `active_subgoal`. Ordinary focused gate remains green with strict xfail: `48 passed, 1 xfailed`. No Coordinator, StateKernel, PlannerPort, Prompt, budget, task grammar, benchmark-family branch, verifier weakening, or production repair was admitted. |
| 2026-07-28 | V-PRB-6B read-only availability RED | Added the reclassified V-PRB-6B non-BrowserGym RED after compact trace projection showed `enter-text:seed-1` is not a single-subgoal failure. The RED models completed text progress followed by an active read-only `submit_button is available` subgoal whose current Submit control is visible/enabled. | `tests/test_task_planning.py::test_validator_repairs_current_submit_button_availability_after_text_progress`, `docs/change-admission/v-prb-6b-single-subgoal-terminal-completion.yaml`, V-PRB-6 compact evidence/status/current plan records | Forced RED with `--runxfail` fails as expected because TaskPlanValidator returns `ACCEPT` instead of `REPAIRABLE / entry_outcome_already_satisfied`. Ordinary focused gate remains green with strict xfails: `135 passed, 2 xfailed`. No production repair, Coordinator finish weakening, BrowserGym reward substitution, Prompt/budget change, StateKernel mutation change, or immutable Planner input work was admitted. |
| 2026-07-28 | V-PRB-6B read-only availability repair | Selected TaskPlan current-state/cardinality handling as the V-PRB-6B child production owner and turned the non-BrowserGym RED green. The repair is generic symbolic subject-to-affordance matching: `submit_button` can match a current `Submit` affordance with role `button`, so already-current read-only availability entries become repairable/resolved before Runtime finish. | `src/affordance_runtime/task_planning.py`, `tests/test_task_planning.py::test_validator_repairs_current_submit_button_availability_after_text_progress`, `docs/change-admission/v-prb-6b-read-only-availability-cardinality.yaml` | RED-to-green: target test passes without xfail. Focused regression passes `147 passed, 1 xfailed`; remaining xfail is V-PRB-6A. Ruff, mypy, and diff check pass. No Coordinator finish guard weakening, BrowserGym reward substitution, Prompt/budget change, StateKernel mutation change, PlannerStateView work, fresh diagnostic, promotion, or official score claim. PR breadth remains held pending a clean committed matrix rerun. |
| 2026-07-28 | V-PRB-6B clean PR breadth rerun after availability repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `17f2e5021bc0c1eab8d1302bc01aa77b82323459` after repairing symbolic read-only availability matching. The local Ollama container initially failed GPU preflight with stale NVML / `size_vram=0`; it was recreated with `--gpus all` while preserving the named `ollama` model volume, then preflight passed with `size_vram_bytes > 0`. | `docs/evidence/runs/m8.2a-pr-breadth-17f2e50/`, `/tmp/affordance-pr-breadth-17f2e50-20260728-122426` | Negative evidence: 12 expected, 12 observed, 11 official reward passed, 1 official reward failed, 4 Runtime failures, no missing/unrun/invalidated/provider failures, `official_score_claimed=false`; report sha256 `73127f5c558539d4e22a9e1723530cdb5bdf0f983fd30016fdc44942980c1fb1`. V-PRB-6B changed shape but is not closed: `enter-text:seed-1` now fails in TaskPlan validation with `entry_outcome_already_satisfied` and then exhausts repair budget. V-PRB-6A remains both form-sequence terminal guard failures. `click-button:seed-1` introduces a separate JSON-invalid/schema robustness cluster. |
| 2026-07-28 | V-PRB-6B current-state discard replacement | Implemented the follow-up V-PRB-6B local repair after the `17f2e50` rerun showed `entry_outcome_already_satisfied` repair loops. TaskPlanFlow now prepares an accepted replacement that preserves verified prior subgoals and discards an already-current read-only availability/visibility subgoal through the existing replacement-plan commit path; TaskPlanValidator still keeps ordinary replacement-without-unfinished-work repairable unless the missing unfinished unit is current-state satisfied. | `src/affordance_runtime/task_plan_flow.py`, `src/affordance_runtime/task_planning.py`, `tests/test_task_plan_flow.py::test_flow_discards_current_state_satisfied_read_only_subgoal_without_replanning`, `docs/change-admission/v-prb-6b-current-state-discard-replacement.yaml` | RED-to-green target test passes; negative control `test_replacement_without_unfinished_work_is_repairable` remains green. Focused regression passes `155 passed, 1 xfailed`; remaining xfail is V-PRB-6A. Ruff, mypy, and diff check pass. No Coordinator growth, finish-guard weakening, BrowserGym reward substitution, Prompt/budget change, StateKernel mutation change, PlannerStateView work, fresh diagnostic, promotion, or official score claim. The clean `9ad1288` PR breadth rerun is negative, so this repair is insufficient for PR breadth closure. |
| 2026-07-28 | V-PRB-6B clean PR breadth rerun after current-state discard replacement | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `9ad128848a070ba1026f3696e2ea5a9edc55a592` after the current-state discard replacement repair. | `docs/evidence/runs/m8.2a-pr-breadth-9ad1288/`, `/tmp/affordance-pr-breadth-9ad1288-20260728-123843` | Negative evidence: 12 expected, 12 observed, 11 official reward passed, 1 official reward failed, 4 Runtime failures, no missing/unrun/invalidated cases, `official_score_claimed=false`; report sha256 `b959f61bcdceaa8035f3e5775f9d3714fd82be1ebc0d254301a6ec005e98f6ce`. The V-PRB-6B follow-up is safe but insufficient: `enter-text:seed-1` still fails Runtime completion. V-PRB-6A remains both form-sequence terminal guard failures. `click-button:seed-1` remains the separate JSON-invalid/schema provider robustness cluster. PR breadth acceptance, fresh diagnostic, promotion, and official score remain held. |
| 2026-07-28 | Post-9ad1288 residual classification | Classified the four residual failures from the clean `9ad1288` rerun without production changes. | `docs/evidence/runs/v-prb-6-post-9ad1288-classification/`, `docs/change-admission/v-prb-6-post-9ad1288-residual-classification.yaml` | Diagnostic only: `click-button:seed-1` is an intent structured-draft JSON-invalid schema/provider robustness cluster before TaskSpec creation; `enter-text:seed-1` now points to verifier-to-subgoal progress binding / task-plan replacement accounting, because strong DOM text evidence passes but is not linked to active mandatory progress before submit terminal evidence backfills the prior subgoal; both `form-sequence` seeds remain V-PRB-6A dependent-subgoal progress-scope / finish-guard failures. No production repair, breadth acceptance, fresh diagnostic, promotion, or official score claim. |
| 2026-07-28 | V-PRB-6B HAS_CHANGED text progress binding | Selected the smallest post-`9ad1288` child production slice for the `enter-text:seed-1` residual. The RED proved BrowserGym exact typed text postconditions for `HAS_CHANGED` remained task-terminal-only even when the concrete filled value equaled the Runtime-owned typed outcome. | `src/affordance_runtime/benchmarks/browsergym_encoder.py`, `tests/test_browsergym_encoder.py::test_browsergym_has_changed_text_value_declares_active_subgoal_evidence`, `docs/change-admission/v-prb-6b-has-changed-text-progress-binding.yaml` | RED failed with `task_terminal` instead of `active_subgoal`; GREEN passes after extending exact typed text progress declaration to `HAS_CHANGED`. Focused regression passes `49 passed, 1 xfailed`; remaining xfail is V-PRB-6A. No Coordinator finish weakening, BrowserGym reward substitution, Prompt/budget change, StateKernel mutation change, PlannerStateView work, fresh diagnostic, promotion, or official score claim. Clean PR breadth rerun is required before judging matrix impact. |
| 2026-07-28 | V-PRB-6B clean PR breadth rerun after HAS_CHANGED text progress binding | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `c382592d6d614e5784730fa2ff0347a9a1b09548` after the HAS_CHANGED text progress binding repair. | `docs/evidence/runs/m8.2a-pr-breadth-c382592/`, `/tmp/affordance-pr-breadth-c382592-20260728-125238` | Negative evidence: 12 expected, 12 observed, 11 official reward passed, 1 official reward failed, 4 Runtime failures, no missing/unrun/invalidated cases, `official_score_claimed=false`; report sha256 `3a4b13bb1f0f003c0823c68c92813f13b5ca339b35cdad04480e684173daf390`. The HAS_CHANGED text progress binding repair is safe but insufficient: `enter-text:seed-1` still fails in task planning with `entry_outcome_already_satisfied`. V-PRB-6A remains both form-sequence terminal guard failures. `click-button:seed-1` remains the separate JSON-invalid/schema provider robustness cluster. PR breadth acceptance, fresh diagnostic, promotion, and official score remain held. |
| 2026-07-28 | V-PRB-6B active-empty ready read-only discard repair | Added a follow-up non-BrowserGym RED/GREEN after the clean `c382592` rerun showed `enter-text:seed-1` still looping on `entry_outcome_already_satisfied`. The trace showed verified text progress clears the active projection while a dependency-ready `submit_button is available` subgoal remains current-state satisfied. | `src/affordance_runtime/task_plan_flow.py`, `tests/test_task_plan_flow.py::test_flow_discards_ready_current_state_satisfied_read_only_subgoal_when_active_projection_empty`, `docs/change-admission/v-prb-6b-ready-read-only-discard-after-progress.yaml` | RED failed with `TaskPlanFlowResult.accepted` false and `entry_outcome_already_satisfied`; GREEN passes after TaskPlanFlow resolves the ready replacement subgoal from the replacement decision when active projection is empty. Adjacent regression passes 11/11 including the ordinary replacement-without-unfinished-work negative control. No Coordinator finish weakening, BrowserGym reward substitution, Prompt/budget change, StateKernel mutation ownership change, PlannerStateView work, fresh diagnostic, promotion, or official score claim. Clean committed PR breadth rerun is required before judging matrix impact. |
| 2026-07-28 | V-PRB-6B clean PR breadth rerun after active-empty discard repair | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `66dae07eb6de259a17c8f9604e30189a74fcc357` after the V-PRB-6B active-empty ready read-only discard repair and revision-binding docs sync. | `docs/evidence/runs/m8.2a-pr-breadth-66dae07/`, `/tmp/affordance-pr-breadth-66dae07-20260728-130459` | Negative but partially positive evidence: 12 expected, 12 observed, 12 official reward passed, 0 official reward failed, 3 Runtime failures, no missing/unrun/invalidated/provider failures, `official_score_claimed=false`; report sha256 `a5c5945d35959aba6a89d5cb079182c3abdffe57593948ea3d8b2da95b566878`. The earlier `click-button:seed-1` JSON-invalid/schema-provider cluster no longer reproduces. `enter-text:seed-1` now fails as `task_planning ... obligation_subgoal_missing`, so V-PRB-6B is still not closed. Both form-sequence seeds remain V-PRB-6A / finish-guard progress-scope failures. PR breadth acceptance, fresh diagnostic, promotion, and official score remain held. |
| 2026-07-28 | V-PRB-6B obligation-subgoal-missing diagnostic | Classified the post-`66dae07` `enter-text:seed-1` residual without production changes. | `docs/change-admission/v-prb-6b-obligation-subgoal-missing-after-discard.yaml`, `/tmp/affordance-pr-breadth-66dae07-20260728-130459/artifacts/runs/browsergym-generalist-enter-text-seed-1/events.jsonl` | Diagnostic only: the previous repair eliminated the `entry_outcome_already_satisfied` loop, but the replacement plan now omits a required `submit_button is available` obligation and TaskPlanValidator correctly rejects it with `obligation_subgoal_missing`. Next V-PRB-6B production work must start from a new non-BrowserGym RED for required read-only obligation completion/accounting; it must not weaken TaskPlanValidator obligation coverage, RunCoordinator finish guard, verifier authority, Prompt/budget constraints, or mix with V-PRB-6A. |
| 2026-07-28 | V-PRB-6B empty-value HAS_CHANGED fill-delta negative rerun and revert | Archived the clean PR breadth rerun for the attempted `f6d053b` / `21f44b0` BrowserGym fill-delta active-subgoal evidence repair, then reverted the production behavior because the clean matrix regressed externally. | `docs/evidence/runs/m8.2a-pr-breadth-21f44b0/`, `docs/change-admission/v-prb-6b-empty-has-changed-fill-delta-binding.yaml`, revert of `src/affordance_runtime/benchmarks/browsergym_encoder.py` and rejected tests | Negative-regression evidence: 12 expected, 12 observed, 11 official reward passed, 1 official reward failed, 3 Runtime failures, no missing/unrun/invalidated/provider failures, `official_score_claimed=false`; report sha256 `09e940792c4faa0d0a8d40aeaa31453b8684d4053dea73585fcd4fb3906ede1c`. The prior clean `66dae07` rerun had 12/12 external reward with the same 3 Runtime failures, so this attempted repair is rejected and reverted. Next V-PRB-6B work returns to required read-only obligation completion/accounting from a non-BrowserGym RED; V-PRB-6A remains separate. |
| 2026-07-28 | V-PRB-6B current-state progress reconciliation negative rerun and revert | Archived the clean PR breadth rerun for the attempted `95fe00b` Core current-state progress reconciliation repair, then reverted the production behavior because the clean matrix regressed externally. | `docs/evidence/runs/m8.2a-pr-breadth-95fe00b/`, `docs/change-admission/v-prb-6b-current-state-progress-reconciliation.yaml`, revert of `src/affordance_runtime/task_plan_progress.py`, related `task_plan_flow.py` / `coordinator.py` integration, and rejected tests | Negative-regression evidence: 12 expected, 12 observed, 11 official reward passed, 1 official reward failed, 2 Runtime failures, no missing/unrun/invalidated/provider failures, `official_score_claimed=false`; report sha256 `a563f1fe452e60178f8b03aabcba94e8e93ee87f8ca5e59c3e4c7069217840b9`. The prior clean `66dae07` rerun had 12/12 external reward with 3 Runtime failures. The attempted repair reduced Runtime failures but regressed external reward, so it is rejected and reverted. Next work must reclassify the form-sequence residuals before another production slice; do not broaden BrowserGym evidence, delete required obligations, weaken finish guard, or claim PR breadth/fresh diagnostic/promotion. |
| 2026-07-28 | Post-95fe00b form-sequence residual classification | Classified the rejected `95fe00b` form-sequence residuals without production changes. | `docs/evidence/runs/v-prb-6-post-95fe00b-classification/`, `docs/change-admission/v-prb-6-post-95fe00b-residual-classification.yaml` | Diagnostic only: `form-sequence:seed-0` shows V-PRB-6A progress-target mismatch. The resolver selected checkbox/submit targets while proposal progress still named the stale slider subgoal, and submit terminal evidence completed the slider subgoal rather than the dependent checkbox/submit obligations; finish guard correctly rejected completion. `form-sequence:seed-1` is treated as a rejected-path regression symptom, not a standalone next owner. Latest review reorders work so V-PRB-6B Core progress accounting is primary; V-PRB-6A remains second-lane work after 6B clean rerun evidence. |
| 2026-07-28 | V-PRB-6B verifier-backed progress accounting RED/GREEN | Added the non-BrowserGym RED/admission and the narrow authority-free Core evaluator for current-state progress accounting, hardened the contract, then connected Coordinator integration at `d17a1f3`. | `src/affordance_runtime/task_plan_progress.py`, `src/affordance_runtime/task_plan_progress_flow.py`, `src/affordance_runtime/coordinator.py`, `src/affordance_runtime/task_plan_flow.py`, `tests/test_task_plan_progress.py`, `tests/test_coordinator.py`, `docs/change-admission/v-prb-6b-verifier-backed-progress-accounting.yaml` | Focused Coordinator GREEN: `tests/test_coordinator.py::test_coordinator_completes_current_state_read_only_subgoal_without_replanning` reports 1 passed. Related regression reports 52 passed across Coordinator / flow / lifecycle / progress tests. Architecture gates report 41 passed with `coordinator.py` at 3466 lines and `RunCoordinator.run_sync` at 2039 lines. Full local pytest reports 1000 passed, 1 xfailed. Ruff, mypy over 121 source files, and diff check pass. The implementation completes ready read-only `IS_AVAILABLE` / `IS_VISIBLE` subgoals from typed current observation through `StateKernel.complete_subgoal()` while retaining required TaskPlan obligation coverage. It does not broaden BrowserGym adapter evidence, delete required obligations, weaken finish guard, use receipt/reward authority, implement V-PRB-6A, run PR breadth, fresh diagnostic, or claim promotion. |
| 2026-07-27 | Remote CI disabled and local equivalent gate | Recorded that GitHub Actions was intentionally closed after the latest remote attempt was blocked by account billing/spending limits. The current tree therefore has no remote-green or remote-fail claim; development validation uses the local equivalent gate while promotion remains held. | status, current plan, horizontal governance, active goal records | clean committed `66747420c4d319d26a10a7c6fb6006871cf3310a`; local equivalent gate passed: 957 tests, Ruff, mypy over 116 source files, `uv build`, Chromium smoke, BrowserGym bridge smoke, diagnostic benchmark smoke, Docker runtime-test, Docker benchmark diagnostic, Docker WoT conformance, and diff check. Diagnostic benchmark acceptance remains failed by design and `official_score_claimed=false`; no remote-CI or promotion claim. |
| 2026-07-27 | Review governance alignment | Applied the latest architecture review as governance state rather than broad implementation permission: preserved SG7 targeted evidence as historical immutable evidence, made semantic ownership review debt visible, kept immutable Planner input `not_started`, and separated implementation-bearing local-equivalent evidence from later documentation-only synchronization commits. | current/status/horizontal governance documents, SG7 admission record, horizontal governance tests | focused governance/document gates must pass for each documentation-sync commit; no production behavior, benchmark/provider episode, remote CI, score, or promotion claim. |
| 2026-07-27 | M8.2A PR breadth diagnostic | Ran the active vertical protected cross-family / PR breadth slice on clean `d66760f76bb4668f610d2ebfac2c8ba0bf83c71a` using `profile=pr`, strict-generalist planning, local Ollama `qwen2.5:7b`, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0, and seeds 0 and 1 across `click-button`, `enter-text`, `choose-list`, `click-dialog`, `click-button-sequence`, and `form-sequence`. | `docs/evidence/runs/m8.2a-pr-breadth-d66760f/`, `/tmp/affordance-pr-breadth-d66760f-20260727-201632` | Negative evidence: 12 expected, 12 observed, 0 passed, 12 failed, 0 provider failures, 0 missing/unrun/invalidated, `official_score_claimed=false`. Runtime-owner clusters: 6 `intent_compilation_rejected` across 4 tasks/families, 5 `planner_waiting_clarification` across 4 tasks/families, and 1 `schema_incompatible` CONTRACT / FIELD_BINDING case. Promotion remains held; next repair owner is INTENT / PLANNING unless deeper trace classification narrows it. |
| 2026-07-27 | V-PRB-0 failure attribution fidelity | Split the broad PR breadth root-layer buckets into exact episode-level mechanisms before admitting production repair. The umbrella repair packet remains diagnostic-only and cannot become a production slice. | `docs/evidence/runs/m8.2a-pr-breadth-d66760f/episode-attribution.yaml`, `docs/change-admission/v-prb-0-failure-attribution-fidelity.yaml` | 12/12 episodes have exact mechanism owner: 2 invalid coverage-audit cases, 4 provider graph proposal-normalization cases, 5 typed semantic action-constraint cases, and 1 structured decoding / attribution-projection case. `click-button:seed-1` created no TaskSpec, so it must not be repaired first as ContractBuilder field binding without further proof. No production change admitted. |
| 2026-07-27 | V-PRB-1 invalid coverage audit handling | Implemented the first child production slice after a non-BrowserGym red test reproduced that an invalid optional coverage audit quote could veto deterministic READY. | `docs/change-admission/v-prb-1-invalid-coverage-audit-handling.yaml`, `tests/test_intent_compiler.py::test_invalid_coverage_audit_quote_cannot_veto_deterministic_ready`, intent coverage admission | The compiler now records `coverage_review_invalid_quote` audit evidence but drops that incoherent audit as an invalid veto, preserving deterministic READY. Valid uncovered-clause and unresolved-dependency audit decisions remain vetoes. No Coordinator, StateKernel, PlannerPort, prompt, budget, task grammar, or benchmark-specific logic change. PR breadth rerun is required on the clean committed revision before judging the matrix impact. |
| 2026-07-27 | V-PRB-1 clean PR breadth rerun | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `d40f8f1792e85f391fe6c94dd88f9b5e0235d481` after V-PRB-1. | `docs/evidence/runs/m8.2a-pr-breadth-d40f8f1/`, `/tmp/affordance-pr-breadth-d40f8f1-20260727-234649` | Negative evidence: 12 expected, 12 observed, 0 passed, 12 failed, no provider failures, no missing/unrun/invalidated cases, `official_score_claimed=false`. V-PRB-1 closed the invalid coverage-audit mechanism: the previous two `coverage_review_invalid_quote` episodes now reach planner clarification. Remaining clusters are 7 `planner_waiting_clarification`, 4 invalid provider graph, and 1 structured decoding / attribution projection. Promotion remains held; next selectable repair is V-PRB-3 or V-PRB-2, one at a time. |
| 2026-07-27 | V-PRB-3 clean PR breadth rerun | Reran the same PR breadth 6-task x 2-seed matrix on clean committed `9b951ed968314aa7a139611d00256adb17b3cbb7` after V-PRB-3 typed semantic action constraints. | `docs/evidence/runs/m8.2a-pr-breadth-9b951ed/`, `/tmp/affordance-pr-breadth-9b951ed-20260727-235739` | Diagnostic evidence: 12 expected, 12 observed, 8 official reward passed, 4 official reward failed, no provider failures, no missing/unrun/invalidated cases, `official_score_claimed=false`. V-PRB-3 closed the typed semantic action constraint cluster for this matrix. Remaining official-failed episodes are four invalid provider graph rejections in `click-button-sequence` and `form-sequence`; `enter-text:seed-1` also has a runtime terminal-completion guard observation with `official_reward=1.0` and is tracked separately. Promotion remains held; next selectable repair is V-PRB-2 provider graph proposal normalization. |
| 2026-07-27 | M8.2A SG7 clean targeted protected-family confirmation | Reran the exact SG7 matrix after committing the generic repair as `3d44a9d222decd1de272d7a4d3eb14b025a8738a`. This clean run preserves the selected scope (`enter-date`, `text-transform`, seeds 0 and 1), strict-generalist planner profile, local Ollama `qwen2.5:7b`, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0, existing 15-call episode budget, and `official_score_claimed=false`. | `docs/evidence/runs/m8.2a-sg7-3d44a9d/`, `/tmp/affordance-sg7-3d44a9d-20260727-184535` | Clean-tree result: expected 4, observed 4, passed 4, failed 0, missing 0, invalidated 0, unrun 0, runtime failures 0, provider failures 0, rate-limit retries 0, transient retries 0, official success rate 1.0, mean official reward 1.0. Run identity digest `sha256:d09d403f6976b246ff614f5f288e8bc7a7bca6719529e934919973ade608309d`; source tree digest `sha256:cb4dd50f8cf2376fce30673d813e1ca895f44b67a2c46860022902c163fa8403`; report sha256 `cea708f3971a85bf231448b5f5cdab182629d54c2449694c8c69cb9f0ff84eed`; matrix metadata sha256 `0ad2bb171b6d8d41aa2c827057e07ba2a8c185fcc6c45cfba10d0ce0936171a1`. This closes SG7 targeted confirmation only; it is not PR breadth, nightly/release, M8.2B promotion, or a formal benchmark score. |
| 2026-07-27 | M8.2A SG7 generic repair candidate | Repaired the clean `fa288af` SG7 protected-family failure without adding task-name, URL, selector, Prompt-only, budget, Coordinator, StateKernel, or PlannerStateView changes. The repair remains generic: unresolved dependency drafts can be boundedly repaired and rechecked before reviewer admission; explicit imperative field entry is canonicalized as reversible write with exact literal value only when the raw request provides that value; page-sourced "text below" is not literalized; reversible generic `HAS_CHANGED` obligations no longer infer text entry unless the subject is a value-entry field; strict planner fallback handles exact value entry, single page-observed text entry, and verifier-backed terminal submit; targeted active perception can preserve requested probes while adding required evidence gaps; the BrowserGym observer exposes targeted capture; opaque DOM/accessibility locators can satisfy executor-local spatial binding without raw coordinates. | intent compiler, canonical compiler, task planning, strict generalist planner, active perception flow, BrowserGym observer, unified grounding, focused regressions, status/goal records | Dirty-tree SG7 diagnostic `/tmp/affordance-sg7-fa288af-submit-fallback-dirty-20260727-182502/browsergym-report.json` passed 4/4 for `enter-date` and `text-transform`, seeds 0 and 1: expected 4, observed 4, failed 0, missing 0, invalidated 0, unrun 0, runtime failures 0, provider failures 0, official success rate 1.0, mean official reward 1.0, `official_score_claimed=false`; report sha256 `0b2313a2356c2411ce5a77db9bd1469227a6d404af5f3be97657cbeec94fc953`, matrix metadata sha256 `26006f8f025e645c3e109615aafa27f127c60bcad20df3f24defc5efd47c63d6`, source tree digest `sha256:cb4dd50f8cf2376fce30673d813e1ca895f44b67a2c46860022902c163fa8403`, `working_tree_clean=false`. The result is a validated repair candidate, not clean SG7 evidence, not PR breadth, not nightly/release, and not a promoted score. Focused repair/gate verification passed: 429 planner/intake/perception/grounding/governance tests, Ruff, mypy over 116 source files, and diff check. |
| 2026-07-27 | M8.2A SG7 targeted protected-family diagnostic | Ran the requested strict-generalist targeted confirmation for `enter-date` and `text-transform`, seeds 0 and 1, after repairing the local Ollama GPU environment by restarting the existing container. The run is bound to clean committed revision `fa288afa7ba047dd3d0ae186f74e948058928436`, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0, local Ollama `qwen2.5:7b`, profile `diagnostic`, and `official_score_claimed=false`. All four scheduled episodes were observed with no missing/unrun/invalidated cases, no provider failures, and no rate-limit/transient retries. Result: SG7 did not pass. Three episodes failed before TaskSpec creation with `unresolved_task_dependency`; `enter-date` seed 0 produced a canonical compiler TaskSpec and accepted TaskPlan, then the strict planner returned `ask_user` / `waiting_clarification`. | `/tmp/affordance-sg7-fa288af-20260727-173720`, preflight artifacts, BrowserGym traces, status/goal records | preflight after restart passed: BrowserGym runtime ready and Ollama model resident on 100% GPU. Pre-run gates passed: 21 horizontal architecture/responsibility tests, 40 SG1-SG6 deterministic intake tests, Ruff, mypy over 116 source files, and diff check. Decision-tree classification: case B for three episodes and case C for one episode; root owner remains INTENT / PLANNING. No production code change, no PlannerStateView migration, no PR breadth/nightly/release, no score or promotion claim. |
| 2026-07-27 | Active-subgoal read/activation boundary | Split the formerly hidden `StateKernel.active_subgoal()` progress mutation into a read-only `active_subgoal()` query and an explicit `activate_next_subgoal()` command. Production activation is Coordinator-owned; planner context construction now remains read-only and no longer advances plan progress while building untrusted planner context. The old planner-context hidden-mutation exception was removed from the architecture gate instead of being kept as an allowlist waiver. | `state_kernel.py`, `coordinator.py`, planner context/task-plan/planning/browsergym tests, horizontal governance test, governance/current/status/goal records | new planner-context no-mutation test and architecture debt-closure test failed before the implementation and pass after it; 189 focused active-subgoal/planner/context/governance tests pass; full dedicated Python 3.12 suite 944 passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. No benchmark/provider/remote CI/promotion claim. |
| 2026-07-27 | Benchmark epoch stabilization and diagnostic CI split | Added bounded BrowserSession recapture for transient affordance-state stabilization during multi-source observation epochs. The retry is allowed only when URL is unchanged and the semantic affordance inventory is unchanged; semantic DOM drift still raises. Split local benchmark CLI semantics so default `benchmark` remains a release acceptance gate, while CI smoke jobs use explicit `--allow-acceptance-fail` to prove the benchmark runs and writes reports without claiming promotion. Container benchmark uses the same explicit diagnostic flag. | `browser_session.py`, CLI benchmark command, CI workflow, compose benchmark command, browser/session/CLI/governance tests, status/goal records | new transient-state-drift test failed before the BrowserSession change and passes after it; semantic DOM drift rejection still passes; CLI diagnostic flag test passes; workflow/compose governance test passes; `affordance-runtime benchmark --seeds 3 --allow-acceptance-fail` completes 63 runs and exits 0 while reporting release acceptance failed; full dedicated Python 3.12 suite 942 passed; 13 focused CLI/browser/governance gates passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. No new remote CI run yet. |
| 2026-07-27 | CI failure classification and harness repair | Converted two classified CI failures into narrow harness repairs: core CI now invokes pytest through the active interpreter so repo-root script imports remain available, and the BrowserGym bridge job uses the documented isolated BrowserGym dependency profile on an Ubuntu runner compatible with Playwright 1.44 dependency names. Added an executable governance test that failed against the old workflow and passes with the repaired workflow. The Chromium/container `coherent observation epoch drifted during multi-source capture` failure is intentionally left open as a benchmark/runtime diagnostic rather than relabeled as environment. | `.github/workflows/ci.yml`, horizontal architecture governance test, status/goal records | focused CI workflow contract test passed; `tests/test_generalization_evidence.py` passed under `python -m pytest`; `scripts/chromium_smoke.py` passed; focused epoch-drift behavior tests passed; full dedicated Python 3.12 suite 940 passed; 10 focused horizontal governance gates passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. The dedicated local interpreter lacks `pip`, so BrowserGym pip dry-run could not be executed there; no new remote CI run yet. |
| 2026-07-27 | Governance baseline self-calibration | Removed duplicated live milestone state from the stable project plan; established the vertical/horizontal `1 + 1` WIP and single-production-writer policy; separated milestone, completed-scope, evidence-maturity, promotion, architecture-admission, and remote-CI axes; bound the current evidence to committed revision `627b5f7`; classified the associated failed push/PR jobs from verified logs; scoped INV-11 to authoritative task-execution commit sequencing with non-expanding compatibility/skill/progress exceptions; and added an executable document-drift gate. | project/current plans, architecture governance/status/intent documents, architecture test, active goal plan | new drift test observed failing before documentation changes and then passed; 19 focused architecture gates; full dedicated Python 3.12 suite 939 passed; Ruff, mypy over 116 source files, `uv build`, and diff check pass. The dedicated interpreter cannot run isolated `python -m build` because its host Python lacks `ensurepip/python3.12-venv`; no production code, benchmark/provider episode, promotion, push, or new remote CI run. |
| 2026-07-27 | Horizontal architecture governance activation | Established an independent always-active change-admission track rather than a new serial milestone. Froze current control-module and long-method growth, classified every public StateKernel method as read/mutation, prohibited neutral/extracted collaborator reverse dependencies and authority reacquisition, recorded the existing hidden mutation debt, normalized absolute/relative import scanning, froze existing non-adapter benchmark import debt, documented prior-waiver/anti-circumvention semantics, and synchronized the current plan, architecture, responsibility boundary, and status axes. Existing debt is baselined but not declared healthy; gate failure blocks the violating change rather than requiring a unified rewrite first. | horizontal governance normative document, four governed documents, executable architecture tests, active goal plan | 18 focused horizontal/existing architecture gates; full dedicated Python 3.12 suite 938 passed; Ruff, mypy over 116 source files, and diff check pass. Local snapshot only; no benchmark/provider/remote CI/score claim. |
| 2026-07-27 | M8.6 neutral approval-source boundary | Moved `ApprovalProvider` and `ConfiguredApprovalProvider` out of Coordinator into a neutral approval-contract module. CLI and local benchmark entrypoints now depend directly on neutral approval and planning contracts; Coordinator consumes the approval protocol and preserves compatibility re-exports. Added executable neutral-ownership/direct-import/compatibility gates plus provider token-binding, TTL, no-match, and first-allowed-capability regressions; lowered the Coordinator line ratchet from 3499 to 3473 without moving state, trace, policy, or capability-gate authority. | approval contracts, Coordinator/entrypoint imports, architecture/behavior/containment tests | 20 focused approval/boundary tests; full dedicated Python 3.12 suite 930 passed; Ruff, mypy over 116 source files, and diff check pass. No benchmark/provider/CI run or score claim. |
| 2026-07-27 | M8.6 neutral Planner contract boundary | Moved `PlannerDecision` and `PlannerPort` definitions out of Coordinator into a neutral planning-contract module. Generalist, parent adapter, and deterministic planners now depend on that module; Coordinator consumes the same contracts and retains compatibility re-exports. Added an AST import-boundary gate and lowered the Coordinator line ratchet from 3520 to 3499 without moving state/trace authority. | planning contracts, Coordinator/planner imports, architecture and containment tests | 106 focused architecture/Coordinator/planner tests; full dedicated Python 3.12 suite 924 passed; Ruff, mypy over 115 source files, and diff check pass. No benchmark/provider/CI run or score claim. |
| 2026-07-27 | M8.3 normal-entrypoint schema recovery owner | Added a one-way `REPAIR_MODEL_SCHEMA` owner at the Generalist planner's provider-neutral model-orchestration boundary. It changes subsequent candidate decoding from the action-bound initial schema to the existing current-target/value-bound repair schema, with before/after schema identity and evidence. Ordinary task-pipeline and BrowserGym paths expose it only for planners implementing the real transition. | planner schema recovery owner, Generalist planner, model recovery dispatcher, normal entrypoints, regressions | 160 focused recovery/planner/pipeline/BrowserGym tests; full dedicated Python 3.12 suite 923 passed; Ruff, mypy over 114 source files, and diff check pass. No provider/benchmark/CI run or score claim. |
| 2026-07-26 | M8.3 normal-entrypoint context recovery owner | Added an owner for `COMPACT_CONTEXT` that changes only Generalist planner optional context windows, emits a validated before/after receipt, and is installed only when the ordinary task pipeline or BrowserGym planner exposes that concrete compaction surface. Provider-switch wiring remains conditional. | planner context recovery owner, model recovery dispatcher, normal entrypoints, regressions | 89 focused recovery/pipeline/BrowserGym tests; full dedicated Python 3.12 suite 922 passed; Ruff, mypy over 113 source files, and diff check pass. No provider/benchmark/CI run or score claim. |
| 2026-07-26 | M8.2A provisioned local quality gate | Re-ran the full repository gate with the dedicated project BrowserGym interpreter rather than the unrelated agent-reach environment. | local quality-gate record | `/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest -q`: 921 passed; Ruff, mypy over 112 source files, and `git diff --check` pass. No benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG6 local held-out intake conformance | Added a non-BrowserGym held-out sequential value-flow request using unrelated agreement/records vocabulary and verified it passes the ordinary model intake, canonical multi-stage compiler, deterministic coverage, and independent audit path. Existing source-clause omission, independent-audit veto, ambiguity, stale-lineage, and unknown-source controls provide adversarial omission boundaries. | non-BrowserGym conformance and coverage/compiler regressions | 16 focused SG6 tests; Ruff; repository-governed mypy over 112 source files; no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG5 canonical graph migration | Extended `CanonicalObligationCompiler` to construct a generic flat graph from source-bound requested effects and to reconstruct bounded multi-stage semantic proposals. Runtime owns all graph node instances, identifiers, dependency/value-flow references, provenance, and typed evidence; model/parent proposals may contribute only validated semantic relations and edges. Both normal entrypoints therefore have no direct candidate graph copy into `TaskSpec`. The independent auditor's `COMPLETE` is advisory-only; typed non-complete findings retain bounded veto authority. | canonical compiler, model/parent intake, coverage boundary, and regressions | 116 focused compiler/intake/multi-stage-planning tests; Ruff; repository-governed mypy over 112 source files; `git diff --check`; full suite 916 passed with four unchanged environment-only failures (two missing Playwright; two subprocess interpreter importability); no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG4 deterministic coverage and veto-only audit | Added a code-owned SourceLedger-to-claim-to-obligation-to-terminal structural coverage validator. It runs before the model audit, rejects missing/unknown/uncovered source-unit lineage, and repeats graph/terminal reachability validation. A coverage `COMPLETE` cannot make an invalid graph READY; optional audit unavailability also cannot reject a deterministically admitted task, while clarification/unsupported responses retain downgrade authority. | obligation coverage and intent compiler; intake/coverage regressions | 126 focused tests; full suite 913/917 in this environment. Four unrelated environment prerequisites remain: missing Playwright (two Chromium tests) and uninstalled editable project in the active interpreter's subprocess (two architecture tests). Ruff and mypy pass 112 source files; no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG3 parent proposal normalization | Added a model-free `ParentSemanticProposalCompiler` for untrusted parent semantic proposals. It requires the same bounded SourceLedger, source binding, Runtime-derived graph identities, deterministic validation, policy, and immutable TaskSpec admission as the model route. A complete typed TaskSpec remains a separate API. | intent compiler and intake regressions | 69 focused intake/pipeline tests; Ruff; repository-governed mypy over 112 source files; no benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG3 provider proposal-identity slice | Provider claim/obligation IDs are now proposal-local references only. Runtime validates source-unit membership, derives bounded semantic IDs for the accepted graph, rewrites edges/value dependencies deterministically, and gives coverage review the normalized graph. A narrow review-reference bridge preserves pre-SG3 replay fixtures without allowing a provider handle into `TaskSpec`. Deterministic source coverage and removal of proposal-shape compatibility remain open. | intent compiler; intake, pipeline, and BrowserGym-adapter regressions | 120 focused tests pass; mypy passes 112 source files; full suite is 909/913 in this environment. The four failures are pre-existing environment prerequisites: Playwright is absent for two Chromium tests and the active interpreter's subprocess cannot import the editable project for two architecture tests. No benchmark/provider/CI run or score claim. |
| 2026-07-26 | M8.2A SG2 canonical graph foundation | Added generic Runtime-owned canonical effect-to-claim/obligation construction, stable ids/provenance, typed evidence contracts, and source-ledger membership rejection. The model-draft normal path remains explicitly un-migrated. | canonical compiler, task-intake contracts, tests, current plan | 913 tests; Ruff; repository-governed mypy over 112 source files; `git diff --check`; no benchmark/provider/GitHub Actions/`.env`/push or score claim |
| 2026-07-26 | M8.2A SG1 source-ledger lineage | Added a deterministic, bounded SourceLedgerBuilder before model intake. It owns whole-request/clause ids, exact request spans, hashes, metadata-only external references, redacted trace projection, and canonicalization of the legacy raw-text alias; over-bound input rejects before a model call. | source ledger, intent compiler, intake/coordinator/BrowserGym identity tests, current plans | 911 tests; Ruff; repository-governed mypy over 111 source files; `git diff --check`; no benchmark/provider/GitHub Actions/`.env`/push or score claim |
| 2026-07-25 | M8.2A repair-failure observability | Added a typed, redacted `IntentDraftRepairFailed` trace event when the bounded repair call cannot decode; it records only the immutable repair Prompt version and error type, while the reservation-based compiler count still accounts for the attempted call. | intent compiler, intake tests, current plan | targeted repair trace test; 907 tests; Ruff; repository-governed mypy over 110 source files; `git diff --check`; no benchmark/provider/GitHub Actions/`.env`/push or score claim |
| 2026-07-26 | M8.2A schema/graph authority audit | Audited clean source revision `bba582c`; froze code-owned SourceLedger, CanonicalObligationCompiler, deterministic coverage, veto-only model audit, and SG1-SG7 ordering without changing Runtime behavior | schema-authority governance, architecture/boundary, task-intake, project/current plans | 907 tests; Ruff; repository-governed mypy over 110 source files; no benchmark/provider/GitHub Actions/.env/push or score claim |
| 2026-07-25 | M8.2B provider-profile launcher boundary | Removed the launcher's unconditional local-profile override. The sole launcher now accepts explicit local/mistral/gemini/zhipu selection, retains Ollama preflight only for local, and leaves the selected provider in immutable run identity. | BrowserGym launcher, current plan | Gemini-profile runtime preflight passed without a remote call; succeeding full local gate passed |
| 2026-07-25 | M8.2B protected intake recheck | Ran only `enter-date` and `text-transform` after fixed Python/BrowserGym/Ollama preflight. The first `f2f689a` wave invalidated on schema incompatibility; `05bd94c` then completed all four 2-task x 2-seed episodes and `58f01ff` reproduced both seed-0 failures. Every observed case failed before action at typed sourced-obligation intake; zero provider/retry failure. | immutable `/tmp/affordance-m8.2b-protected-*` run reports/traces; current plan | negative evidence only; no PR breadth, diagnostic, nightly, release, remote provider, GitHub Actions, `.env`, push, or score claim |
| 2026-07-25 | M8.2A immutable repair identity | Factored the compiler-stage checkpoint identity into one pure construction and directly tested that the initial compiler and repair Prompt versions are distinct and both participate in immutable resume identity | BrowserGym checkpoint identity, adapter test | targeted identity test, full local gate pending this revision; no benchmark or provider run |
| 2026-07-25 | M8.6 containment ratchet | Re-audited active-perception ownership: `ActivePerceptionFlow` already owns gap/probe/capture/resolution while Coordinator commits state and canonical trace; lowered the feature-freeze line ceiling to the measured 3520-line surface | containment test, boundary, implementation status | containment test, full local gate pending this revision; no benchmark or provider run |
| 2026-07-25 | M8.3 normal-entrypoint provider recovery | Attached the existing evidence-backed fallback-provider owner to `GeneralistTaskPipeline` only when its compiler has a real configured multi-profile model; explicit handlers remain authoritative and single-provider/context/schema paths remain unavailable | task pipeline, model recovery, pipeline test | focused recovery/pipeline tests; Ruff; repository-governed mypy over 110 source files; no provider call, browser benchmark, GitHub Actions, `.env`, push, or score claim |
| 2026-07-25 | M8.2A intake repair audit | Replaced inferred BrowserGym intake-call accounting with the compiler's bounded reservation count; bound the repair call to its own Prompt identity in trace/checkpoint metadata; corrected `missing_source_claims`; retained fail-closed policy, ambiguity, stale, and unsafe-repair behavior | intent compiler, BrowserGym runner/checkpoint metadata, intake and runner tests, current plan | 902 tests; Ruff; repository-governed mypy over 110 source files; `git diff --check`; no BrowserGym matrix, remote provider, GitHub Actions, `.env`, push, or score claim |
| 2026-07-24 | M8.6 reclosure | Enforced strict probe authority and semantic evidence, extracted typed active-perception flow, invoked real recovery owning ports, rejected no-op progress, reduced the Coordinator ratchet, and published real four-profile Runtime evidence | active perception/session, recovery dispatcher, Runtime evidence projection, G5 rollout, Coordinator, tests, synchronized plans/status | implementation `c939051`; 680 tests; Ruff; mypy over 100 source files; immutable 11-case rollout passed with 82-file hash index; no remote model, BrowserGym benchmark, GitHub Actions, score claim, `.env`, or push |
| 2026-07-24 | M8.6 closure audit / responsibility containment | Reopened G2.5, G3, and G5 empirical closure; froze Coordinator feature growth; added normative ownership, typed-result, no-op-success, budget-narrowing, and evidence-level gates | closure audit, responsibility boundary, README, plans, status | audited clean `f4c3308`; 666 tests after adding the containment ratchet; Ruff; mypy over 96 source files; no remote model/browser/score run |
| 2026-07-23 | M8.6 G1 / behavioral governance and proposal provenance | Added runtime-authored source identity for model, rule, parent, skill, recovery, external-policy, and runtime-terminal proposals; rejected missing provenance before binding; persisted provenance in trace/state; added generic target-scope and unrequested-effect gates with camelCase/hyphen/morphology normalization and a non-BrowserGym anti-specialization matrix | proposal contracts/validator, Coordinator, all production proposal sources, governance matrix, plans/evidence | 567 tests; Ruff; mypy with optional imports across 90 source files; paraphrase positive control and distractor/extra-control/ambiguity/unrelated-interface/unrequested-terminal/destructive-effect/scope-expansion negatives; G1 complete; `m8.6-g1-behavior-provenance-20260723.md` |
| 2026-07-23 | M8.6 G1 / physical compatibility containment | Moved historical objective parsers, terminal exposure, repair recipes, semantic rewrites, and compiler callback assembly out of the strict Planner module; retained only a lazy explicit replay entrypoint and reverse dependency on shared proposal contracts | `compatibility_planner_algorithms.py`, strict Planner lazy boundary, architecture controls, plans/evidence | 557 tests; 95 focused tests; Ruff; mypy with optional imports across 90 source files; subprocess proof that strict import/construction does not load compatibility while the historical profile does; `m8.6-g1-physical-containment-20260723.md`; G1 remains open for broader behavioral controls and proposal provenance |
| 2026-07-22 | Runtime-first R8 / module containment closure | Audited extracted Core collaborators, typed boundaries, authoritative state/trace ownership, benchmark-vocabulary isolation, and BrowserGym facade compatibility; documented the legacy one-contract conformance harness as non-authoritative | executable R8 architecture boundary test, plans/audit/evidence | 522 tests; Ruff; mypy with optional imports across 89 source files; no Core benchmark vocabulary/adapter import; no collaborator `StateKernel` construction; observer/encoder/runner/protocol/report facade identity checks; `runtime-r8-closure-20260722.md` |
| 2026-07-23 | M8.2B R9 / native labels and explicit form obligations | Kept descriptive native labels out of the action inventory, associated explicit/nested/adjacent labels with controls, and compiled multi-field exact-value obligations with verified-target progress and ambiguity fallthrough | generic DOM observation, semantic compiler/planner, non-BrowserGym controls, clean bounded BrowserGym ladder | clean `b4e596e`: original failures 2/2, form family 20/20, PR 18/18; complete diagnostic 29/30 with one retained planning-budget envelope caused by exact-value versus prefix/suggestion semantics; 528 tests, Ruff, mypy 89 source files; `m8.2b-r9-form-obligations-20260723.md` |
| 2026-07-23 | M8.2B R9 / typed suggestion selection | Separated exact form literals from prefix/suffix suggestion relations; compiled prefix entry, uniquely observed option activation, matching-current progress, and unique terminal exposure with ambiguity fallthrough | default semantic registry, Generalist typed obligations, generic DOM controls, clean immutable BrowserGym ladder | clean `7d0ada0`: original failure 1/1, task family 10/10, PR 18/18, diagnostic 30/30, frozen nightly 300/300 reward 1.0; zero missing/runtime/envelope/provider/retry/circuit failures; 532 tests, Ruff, mypy 89 source files; `m8.2b-r9-suggestion-selection-20260723.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym report and protocol containment | Separated versioned profile metadata and seed-major protocol from FailureEnvelope construction/clustering and aggregate report publication; matrix retains scheduling, circuit state, and atomic checkpoints; unknown release tasks use observed action capability evidence or an explicit unresolved evidence gap without task-name dispatch | `browsergym_protocol.py`, `browsergym_report.py`, matrix compatibility wiring, direct taxonomy/report tests, plans/evidence | 519 tests; Ruff; mypy with optional imports across 89 source files; 66 focused tests; compatibility, declared-family precedence, observed-capability fallback, and no-action evidence-gap controls; `runtime-r8-browsergym-report-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym episode runner containment | Extracted one-episode setup, Coordinator traversal, backend execution, external-policy lifecycle, model/context trace projection, local source serving, and killable process timeout/exit/cleanup while suite scheduling, frozen identity, checkpoints, circuit breaking, and reports remain outside | `browsergym_episode_runner.py`, bridge facade wiring, direct lifecycle/isolation tests, plans/evidence | 515 tests; Ruff; mypy with optional imports across 87 source files; 69 focused tests; facade identity, forced timeout termination/cleanup, and empty-worker-result exit-code controls; `runtime-r8-browsergym-episode-runner-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym encoder containment | Extracted external-policy contract attachment, semantic-action translation, validated gesture and point encoding, native value conversion, and action-specific verifier mapping while Core retains dual-target binding, currentness, route, policy, capability, and preflight authority | `browsergym_encoder.py`, bridge facade wiring, direct encoder/adapter/Core tests, plans/evidence | 512 tests; Ruff; mypy with optional imports across 86 source files; 88 focused tests; invalid geometry/missing binding/value/verifier negative controls; facade compatibility and Core gesture invariants; `runtime-r8-browsergym-encoder-20260722.md` |
| 2026-07-22 | Runtime-first R8 / BrowserGym observer containment | Extracted coherent capture, observation metadata normalization, bounded epoch-drift retry, drag geometry/fingerprint enrichment, DOM grounding refresh, screenshot fallback, visual candidate fusion, and JSON-safe adapter metadata while preserving bridge facade imports and Runtime ownership | `browsergym_observer.py`, shared BrowserGym backend constant, bridge facade wiring, direct observer/adapter tests, plans/evidence | 498 tests; Ruff; mypy with optional imports across 85 source files; 76 focused BrowserGym/observer/boundary tests; retry-cap, unrelated-error, serialization, geometry, visual, and facade compatibility controls; `runtime-r8-browsergym-observer-20260722.md` |
| 2026-07-22 | Runtime-first R8 / planner model orchestration containment | Extracted provider-neutral candidate data/dynamic schemas, structured model invocation, bounded same-context repair, redacted exhaustion, and call-budget reservation hooks while Generalist retains Prompt/configuration, semantic validation/binding, fallback order, and trace assembly | `planner_model_orchestrator.py`, Generalist policy wiring and compatibility wrappers, direct provider-neutral tests, plans/evidence | 494 tests; Ruff; mypy with optional imports across 84 source files; 88 focused tests; first-pass/repair/schema-failure/budget/exhaustion negative controls; public candidate JSON Schema field equivalence; `runtime-r8-planner-model-orchestrator-20260722.md` |
| 2026-07-22 | Runtime-first R8 / default SemanticCompiler registry containment | Moved ordered rule/constraint assembly, applicability declarations, evidence metadata, operation scopes, output kinds, and negative examples behind a typed factory while Generalist retains unchanged semantic algorithms and a compatible public entrypoint | `default_semantic_compilers.py`, Generalist callback wiring, direct generic factory tests, plans/evidence | 488 tests; Ruff; mypy with optional imports across 83 source files; exact precedence/evidence assertions, empty/unsupported-context negative controls, existing non-BrowserGym DOM integration, and benchmark-vocabulary boundary; `runtime-r8-default-semantic-registry-20260722.md` |
| 2026-07-23 | M8.6 G1 / proposal validation and compatibility containment | Added one Coordinator-owned PlannerProposalValidator before completion/binding/approval/execution; preserved clarification in strict mode; renamed the historical registry as compatibility-only; added form/suggestion/disclosure task-shape controls and strict DOM/visual/WoT conformance | `planning.py`, Coordinator trace, `compatibility_semantic_compilers.py`, strict planner, generic behavior and cross-surface tests, plan/evidence | 554 tests; Ruff; mypy across 89 source files; `m8.6-g1-proposal-validation-20260723.md`; G1 remains open for broader controls and physical algorithm extraction |
| 2026-07-22 | Runtime-first R8 / PlannerContextBuilder containment | Extracted bounded task/state/observation context models, semantic inventory projection, action exposure, relevance bounds, current progress, and one-failure summary while preserving Generalist LM Prompt/schema/compiler behavior and compatible imports | `planner_context.py`, Generalist planner wiring, generic context tests, plans/evidence | 485 tests; Ruff; mypy with optional imports across 82 source files; bounded/no-handle/legacy-envelope negative controls; `runtime-r8-planner-context-builder-20260722.md` |
| 2026-07-22 | Runtime-first R8 / RecoveryHandler containment | Separated immutable failure/cascade/context/policy evaluation from Coordinator-owned incident, reroute, budget, diagnostic, and state-transition application | `recovery_handler.py`, Coordinator wiring, generic recovery tests, plans/evidence | 482 tests; Ruff; mypy with optional imports across 81 source files; stale, uncertain-effect, repeated-loop, and no-incident-mutation controls; `runtime-r8-recovery-handler-20260722.md` |
| 2026-07-22 | Runtime-first R8 / ContractExecutionLoop containment | Extracted run/snapshot binding, scoped gate construction, policy/capability/preflight checks, fresh-observation revalidation, one-shot executor delegation, and structural verification while retaining state/trace/budget/approval/recovery authority in Coordinator | `contract_execution_loop.py`, Coordinator wiring, generic contract-stage tests, plans/evidence | 479 tests; Ruff; mypy with optional imports across 80 source files; policy/capability/staleness negative controls; approval/uncertain-effect/fallback integration; `runtime-r8-contract-execution-loop-20260722.md` |
| 2026-07-22 | Runtime-first R8 / PerceptionSession containment | Extracted task/subgoal requirement derivation, failed-route escalation, coherent BrowserSession capture profiles, screenshot artifact handling, and sync/async targeted observation port resolution while retaining observation recording, counters, budgets, and trace transitions in Coordinator/StateKernel | `perception_session.py`, Coordinator wiring, generic perception tests, plans/evidence | 476 tests; Ruff; mypy with optional imports across 79 source files; plain-source/no-mutation, missing-port, invalid-source negative controls; visual-primary/fallback/conflict integration; `runtime-r8-perception-session-20260722.md` |
| 2026-07-22 | Runtime-first R8 / TaskPlanLifecycle containment | Extracted immutable task-plan transition preparation, bounded planning context, async planner resolution, validation, replan eligibility, completion, and active-subgoal lookup from Coordinator while retaining all mutation in Coordinator/StateKernel | `task_plan_lifecycle.py`, Coordinator wiring, generic lifecycle tests, plans/evidence | 473 tests; Ruff; mypy with optional imports across 78 source files; generic invalid-plan negative control; benchmark-vocabulary boundary; `runtime-r8-task-plan-lifecycle-20260722.md` |
| 2026-07-22 | Runtime-first R7 / clean public evaluation | Froze one source/model/Prompt/schema/context/budget identity, ran the three-layer breadth-first protocol through complete nightly and all-supported-task residual release, and retained cross-layer failures without in-run repair | fixed Python 3.12 launcher, BrowserGym matrix/checkpoint/report artifacts, plans/evidence | clean `7e1c7db`: smoke 6/6, PR 18/18, diagnostic 30/30, nightly 300/300 reward 1.0; release 625/625 observed, 402 successes, zero provider/retry/missing/drift/circuit failures, 223 retained envelopes; `runtime-r7-clean-public-evaluation-20260722.md` |
| 2026-07-22 | R7 diagnostic / target-scoped perception and bounded incremental control | Preserved task-level coherent observation acquisition while projecting route hard gates onto the current semantic action/target; after a complete frozen nightly, unified typed incremental-control compilation and constraint selection around verified Page/Arrow steps without task-family dispatch | perception, unified target resolution/grounding, semantic compiler, non-BrowserGym routing controls, tests, plans/evidence | clean `f8001d9`: smoke 6/6, PR 18/18, diagnostic 30/30, frozen nightly 298/300 with only two >50-step control failures; dirty generic repair reproduction 7/7 and family 10/10; 471 tests, Ruff, mypy 77 source files, diff/boundary checks pass; replacement clean ladder is recorded in the R7 row above |
| 2026-07-22 | Runtime-first R6 / complete harness learning | Added causal canonical JSONL validation, backend-neutral semantic extraction, cross-run clustering and parameter/negative/applicability mining, schema 1.1 source/report provenance, digest-bound replay evidence, accepted TaskSkill/RecoverySkill profile loading, and explicit System 1 selection provenance | harness learning, TaskSkill/evolution/profile loader, Coordinator trace, normal CLI, tests, plans/evidence | fixed Python 3.12: 463 tests pass; Ruff passes; mypy passes all 77 source files; three real non-BrowserGym System 2 traces across three layouts auto-quarantine one skill; five-category fresh replay accepts it and a fresh persisted profile completes held-out with zero System 2 calls; rollback and digest-tamper controls pass |
| 2026-07-22 | Runtime-first R5 / planner and observation de-specialization | Moved BrowserGym authored DOM/SVG profiles and backend encoding into its adapter; normalized shared observation to opaque handles; added typed semantic compiler/constraint registry, generic incremental-control compilation, terminal-evidence separation, boundary scans, non-BrowserGym controls, and disabled-profile ablation | DOM/SVG adapters, BrowserSession, grounding, planner/compiler registry, verification, BrowserGym adapter, tests, plans/evidence | fixed Python 3.12: 452 tests pass; Ruff passes; mypy passes all 76 source files; dirty-tree diagnostic family 10/10 and seed-major PR 18/18 with no provider/retry failures; not an official benchmark score |
| 2026-07-22 | Runtime-first R2 / M8.4 | Added bounded TaskPlanningContext, evidence-aware replanning, monotonic plan lineage, verified-progress preservation, forbidden plan-content validation, and optional real Chromium pricing entrypoint | task planning, StateKernel, Coordinator, reference planners/CLI, tests, plans/status | fixed Python 3.12: 423 tests pass; Ruff passes; mypy with optional imports ignored passes all 73 source files; Flat/Always-plan/Adaptive semantic ablation acceptance passes |
| 2026-07-22 | Runtime-first R3 / generic perception | Wired TaskSpec/SubgoalSpec requirements through Coordinator and BrowserSession; added coherent DOM/A11Y/SVG/screenshot/visual candidates, ordinary source assertions, fresh targeted perception, trusted visual binding, and evidence-driven DOM-to-visual escalation | perception, BrowserSession, Coordinator, ContractBuilder, recovery, BrowserGym point-region reuse, tests, plans/status | fixed Python 3.12: 433 tests pass; Ruff passes; mypy with optional imports ignored passes all 73 source files; 59 BrowserGym adapter regressions pass; public BrowserSession.launch Chromium 125 visual route passes an independent DOM-state verifier |
| 2026-07-22 | Runtime-first R4 / verifier-calibrated routing | Made candidate evidence gates target-specific, added geometry-aware conservative sibling fusion, typed post-verification RouteOutcome, strong-evidence-only scoped calibration, origin-level browser environment family, and removed receipt learning from the static backend selector | grounding, unified routing, Coordinator, BrowserSession, routing, tests, plans/status | fixed Python 3.12: 442 tests pass; Ruff passes; mypy passes all 74 source files; shifted-layout candidate ids switch to the verified source without cross-environment leakage; six-profile ablation has zero unsafe effects, false accepts, and duplicate risk |
| 2026-07-22 | Runtime-first R1 | Added shared criteria/evidence matching, explicit verifier evidence identity and obligation links, fresh strong-evidence gates for Subgoal and TaskSkill checkpoints, and structured trace reports | criteria, contracts, verifier, task planning/skills, Coordinator, controlled benchmark fixtures, tests, plans/status | fixed Python 3.12: 412 tests pass; Ruff passes; mypy with optional imports ignored passes all 73 source files; unrelated, partial, stale-revision, stale-snapshot, weak/self-declared receipt, state-delta weakness, mandatory-coverage, multi-criterion, and unbound SkillStep cases covered |
| 2026-07-22 | Architecture audit | Adopted Runtime-first boundary, prohibited benchmark specialization in shared architecture, corrected M8.4/M8.5 status, and added ordered remediation gates | boundary, audit, README, project/current plans, status ledger | reviewed `0272765`; 401 tests pass, Ruff passes, full mypy has four optional-integration errors |
| 2026-07-20 | M0-M4 | Created milestone implementation ledger from the authoritative plan and current source audit | `docs/implementation-status.md` | baseline: 27 tests, Ruff, and mypy passing before implementation changes |
| 2026-07-20 | M0 | Implemented frozen state, contract, approval, trace, and evolution semantics | core runtime modules and tests | 32+ tests, Ruff, mypy |
| 2026-07-20 | M1 | Implemented coordinator, artifacts, pricing fixture/planner, CLI, structural post-verification, immediate revalidation, screenshots, and baseline | coordinator, artifacts, fixture, planner, CLI, tests | 36 tests; Ruff/mypy; real Chromium gold path/baseline; three repeated runs |
| 2026-07-20 | M2 | Added settings and export fixtures, persisted/API and file-hash oracles, explicit CLI approval, download artifacts, cross-surface coordinator proofs, correct metric denominators, benchmark matrix, and JSON/Markdown/CSV writers | fixtures, planners, browser/executor, verification, benchmark modules, tests | 39 tests; Ruff/mypy; real Chromium settings pass, export blocked without approval, approved export and audit pass |
| 2026-07-20 | M2 | Completed deterministic perturbations and executable Direct/Primitive/Full plus four-ablation matrix | benchmark local runner, runtime feature gates, fixture perturbations | 21 real Chromium runs; Full Runtime success 1.0, stale recall 1.0, unsafe rate 0.0, false accept rate 0.0 |
| 2026-07-20 | M3 | Added failure classification, typed proposals, versioned registry/rollback, mandatory replay categories, and before/after reports | evolution and replay modules, CLI, tests | real no-verifier false accept became accepted verifier patch after 1.0/0.0/0.0 regression gate |
| 2026-07-20 | M4 | Added stable task service, bounded tool adapter, local scenario runner, scoped approval, cancellation, result/evidence/trace retrieval | integrations package and tests | real Chromium pricing task succeeded; export waited for approval then succeeded with file-hash receipt |
| 2026-07-20 | Audit | Added task-constraint policy, effect idempotency/compensation enforcement, post-approval state revalidation, async task adapter, and release thresholds | safety, coordinator, integration, benchmark validation, docs, tests | 49 tests; Ruff/mypy; 21-run local gate passed; evolution report and local async API passed |
| 2026-07-20 | M8 precursor | Ran official Farama MiniWoB++ click-button through BrowserSession, DOM Affordance, ActionContract, and DomExecutor | temporary official checkout only | historical compatibility proof later superseded by the integrated M8 suite |
| 2026-07-20 | M5 | Added CI, package build dependency, focused Chromium smoke, environment manifest, versioned report output, and one-command clean-checkout reproduction | workflow, environment module, benchmark writer, scripts, evidence summary | clean clone at `4528f25`: 49 tests, Ruff, mypy, build, smoke, 21-run matrix, and evolution gate passed |
| 2026-07-20 | M6 | Added SHA-bound executable verifier payloads, fresh candidate runtime replay, atomic registry persistence, accepted-only loading, versioned reports, and two-layer rollback proof | evolution modules, explicit benchmark runtime profiles, evidence gate, tests | clean clone at `4cccc96`: 51 tests plus 21 benchmark and 6 fresh replay runs; accepted registry and rolled-back proof verified |
| 2026-07-20 | M7 | Added external task JSON-RPC, a separate runtime server process, and a compiled LangGraph parent for pricing and approval-gated export | integration modules, parent smoke, CI/reproduction, tests, evidence | clean clone at `9a9796e`: 52 tests; pricing success; export waited then succeeded; evidence and trace retrieved; no primitive GUI tools exposed |
| 2026-07-20 | M8 | Added distinct seeded and held-out layouts, real screenshot grounding, and a pinned official MiniWoB++ curated adapter | fixture v2, benchmark/generalization modules, CI/reproduction, tests, evidence | clean clone at `e463e16`: 55 tests; 63 matrix runs, 6 held-out runs, 5 visual runs, and 18 official episodes all passed |
| 2026-07-22 | M8.2B v132 | Added bounded authored item/type/current-quantity observation and fresh-epoch semantic increment selection without admitting every unmarked `bid` | DOM adapter, browser session, generalist planner, tests, evidence | `order-food` 10/10 with zero model calls; same-source PR 18/18 and breadth 60/60; 388 tests, Ruff, focused mypy, diff check |
| 2026-07-22 | M8.2B v148 | Preserved action-family diversity in the bounded planner inventory so a 96-endpoint calendar cannot hide its newly rendered name/create controls | generalist planner, DOM/BrowserGym calendar path, tests, evidence | same-source `daily-calendar` 10/10, PR 18/18, and seed-major breadth 60/60; 395 tests, Ruff, focused mypy, diff check; no provider, 429, retry, runtime, acceptance, or failure cluster |
| 2026-07-22 | M8.2B v149 | Restored local Ollama GPU residency without replacing its model volume, added fail-closed provider preflight to the sole launcher, and restored documented smoke/PR defaults | launcher, provider preflight, fixed-budget evidence | same-source fixed 165/10/15/15 PR 18/18; RTX 3080 and 4.75 GB model residency recorded; no provider, 429, retry, runtime, acceptance, or failure cluster |
| 2026-07-22 | M8.2B v155 | Added bounded owner/position/action/toggle semantics for authored collection controls and a BrowserGym current-bid scroll/DOM-click route without exposing bids to Planner proposals | DOM adapter, generalist compiler, BrowserGym binder/executor, tests, evidence | same-source social families 30/30, PR 18/18, and seed-major breadth 60/60; 401 tests; no provider, 429, retry, runtime, acceptance, or failure cluster |
