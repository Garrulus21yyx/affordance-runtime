# Target Runtime test-topology closure inventory

Status: `IMPLEMENTED / T5_COMPLETE / STATIC_AND_OFFLINE_VERIFIED`

This closure classifies every executable test formerly at the test root by test kind and exercised owner. The 229 `test_*.py` modules move below `unit/`, `integration/`, `conformance/`, or `benchmarks/`; the four former root helpers move separately under `tests/support/*`.

## Ownership counts

| Category | Owner | Files |
|---|---|---:|
| `benchmarks` | `agent` | 3 |
| `benchmarks` | `evaluation` | 1 |
| `benchmarks` | `model` | 21 |
| `benchmarks` | `runtime` | 52 |
| `benchmarks` | `surfaces/browsergym` | 12 |
| `benchmarks` | `surfaces/dom` | 3 |
| `benchmarks` | `world` | 1 |
| `conformance` | `actions` | 4 |
| `conformance` | `agent` | 5 |
| `conformance` | `evaluation` | 3 |
| `conformance` | `model` | 6 |
| `conformance` | `runtime` | 7 |
| `conformance` | `surfaces/browsergym` | 2 |
| `conformance` | `surfaces/dom` | 2 |
| `conformance` | `surfaces/http_json` | 1 |
| `conformance` | `surfaces/visual` | 4 |
| `conformance` | `surfaces/wot` | 4 |
| `conformance` | `task` | 2 |
| `conformance` | `world` | 9 |
| `integration` | `agent` | 11 |
| `integration` | `evaluation` | 1 |
| `integration` | `model` | 4 |
| `integration` | `runtime` | 5 |
| `integration` | `surfaces/dom` | 1 |
| `integration` | `surfaces/visual` | 2 |
| `integration` | `surfaces/wot` | 2 |
| `integration` | `task` | 1 |
| `integration` | `world` | 2 |
| `unit` | `actions` | 3 |
| `unit` | `agent` | 11 |
| `unit` | `evaluation` | 3 |
| `unit` | `model` | 13 |
| `unit` | `risk` | 2 |
| `unit` | `runtime` | 13 |
| `unit` | `surfaces/browsergym` | 6 |
| `unit` | `surfaces/dom` | 1 |
| `unit` | `surfaces/visual` | 3 |
| `unit` | `task` | 2 |
| `unit` | `world` | 1 |

## Test-support disposition

- `StaticEnvironment`: independent benchmark-owned copy at `affordance_runtime.benchmarks.support`; test-owned copy at `tests.support.agent`.
- `failure_injection`: `tests.support.world` only.
- BrowserGym, model-policy, DOM reference-site, and agent-loop helpers: corresponding `tests.support.*` owners.
- `affordance_runtime.testing`: deleted; no compatibility import remains.

## Complete physical move map

| Old path | New path |
|---|---|
| `tests/test_control_feedback_targeted.py` | `tests/benchmarks/agent/test_control_feedback_targeted.py` |
| `tests/test_control_state_machine_properties.py` | `tests/benchmarks/agent/test_control_state_machine_properties.py` |
| `tests/test_two_stage_progress.py` | `tests/benchmarks/agent/test_two_stage_progress.py` |
| `tests/test_target_loop_internal_evaluation.py` | `tests/benchmarks/evaluation/test_target_loop_internal_evaluation.py` |
| `tests/test_compact_grounding_cutover.py` | `tests/benchmarks/model/test_compact_grounding_cutover.py` |
| `tests/test_compact_grounding_decision_matrix.py` | `tests/benchmarks/model/test_compact_grounding_decision_matrix.py` |
| `tests/test_compact_grounding_matrix_runner.py` | `tests/benchmarks/model/test_compact_grounding_matrix_runner.py` |
| `tests/test_grounded_tools_v2.py` | `tests/benchmarks/model/test_grounded_tools_v2.py` |
| `tests/test_model_conformance_attestation.py` | `tests/benchmarks/model/test_model_conformance_attestation.py` |
| `tests/test_model_conformance_classification.py` | `tests/benchmarks/model/test_model_conformance_classification.py` |
| `tests/test_model_conformance_complexity.py` | `tests/benchmarks/model/test_model_conformance_complexity.py` |
| `tests/test_model_conformance_contracts.py` | `tests/benchmarks/model/test_model_conformance_contracts.py` |
| `tests/test_model_conformance_destination_ladder.py` | `tests/benchmarks/model/test_model_conformance_destination_ladder.py` |
| `tests/test_model_conformance_failure_stages.py` | `tests/benchmarks/model/test_model_conformance_failure_stages.py` |
| `tests/test_model_conformance_levels.py` | `tests/benchmarks/model/test_model_conformance_levels.py` |
| `tests/test_model_conformance_live_context.py` | `tests/benchmarks/model/test_model_conformance_live_context.py` |
| `tests/test_model_conformance_profile_identity.py` | `tests/benchmarks/model/test_model_conformance_profile_identity.py` |
| `tests/test_model_conformance_reporting.py` | `tests/benchmarks/model/test_model_conformance_reporting.py` |
| `tests/test_model_conformance_runner.py` | `tests/benchmarks/model/test_model_conformance_runner.py` |
| `tests/test_model_policy_compact_grounding.py` | `tests/benchmarks/model/test_model_policy_compact_grounding.py` |
| `tests/test_model_policy_compact_grounding_v2.py` | `tests/benchmarks/model/test_model_policy_compact_grounding_v2.py` |
| `tests/test_model_policy_grounding_adoption.py` | `tests/benchmarks/model/test_model_policy_grounding_adoption.py` |
| `tests/test_model_policy_grounding_bridge.py` | `tests/benchmarks/model/test_model_policy_grounding_bridge.py` |
| `tests/test_model_policy_grounding_variants.py` | `tests/benchmarks/model/test_model_policy_grounding_variants.py` |
| `tests/test_model_protocol_capabilities.py` | `tests/benchmarks/model/test_model_protocol_capabilities.py` |
| `tests/test_benchmark_failure_facts_properties.py` | `tests/benchmarks/runtime/test_benchmark_failure_facts_properties.py` |
| `tests/test_cli.py` | `tests/benchmarks/runtime/test_cli.py` |
| `tests/test_external_smoke_admission.py` | `tests/benchmarks/runtime/test_external_smoke_admission.py` |
| `tests/test_external_smoke_boundaries.py` | `tests/benchmarks/runtime/test_external_smoke_boundaries.py` |
| `tests/test_external_smoke_execution_gate.py` | `tests/benchmarks/runtime/test_external_smoke_execution_gate.py` |
| `tests/test_external_smoke_manifest.py` | `tests/benchmarks/runtime/test_external_smoke_manifest.py` |
| `tests/test_external_smoke_mechanical_verifier.py` | `tests/benchmarks/runtime/test_external_smoke_mechanical_verifier.py` |
| `tests/test_external_smoke_oracle_isolation.py` | `tests/benchmarks/runtime/test_external_smoke_oracle_isolation.py` |
| `tests/test_external_smoke_preflight.py` | `tests/benchmarks/runtime/test_external_smoke_preflight.py` |
| `tests/test_external_smoke_reporting.py` | `tests/benchmarks/runtime/test_external_smoke_reporting.py` |
| `tests/test_live_target_loop_policy_attestation.py` | `tests/benchmarks/runtime/test_live_target_loop_policy_attestation.py` |
| `tests/test_live_target_loop_policy_workflow.py` | `tests/benchmarks/runtime/test_live_target_loop_policy_workflow.py` |
| `tests/test_m35_runtime_decision_matrix.py` | `tests/benchmarks/runtime/test_m35_runtime_decision_matrix.py` |
| `tests/test_m35_support_scope.py` | `tests/benchmarks/runtime/test_m35_support_scope.py` |
| `tests/test_miniwob_breadth_classification.py` | `tests/benchmarks/runtime/test_miniwob_breadth_classification.py` |
| `tests/test_miniwob_breadth_manifest.py` | `tests/benchmarks/runtime/test_miniwob_breadth_manifest.py` |
| `tests/test_miniwob_breadth_oracle_isolation.py` | `tests/benchmarks/runtime/test_miniwob_breadth_oracle_isolation.py` |
| `tests/test_miniwob_breadth_reporting.py` | `tests/benchmarks/runtime/test_miniwob_breadth_reporting.py` |
| `tests/test_miniwob_breadth_runner.py` | `tests/benchmarks/runtime/test_miniwob_breadth_runner.py` |
| `tests/test_miniwob_capability_inventory_v2.py` | `tests/benchmarks/runtime/test_miniwob_capability_inventory_v2.py` |
| `tests/test_miniwob_failure_attribution_v2.py` | `tests/benchmarks/runtime/test_miniwob_failure_attribution_v2.py` |
| `tests/test_miniwob_perception_ab.py` | `tests/benchmarks/runtime/test_miniwob_perception_ab.py` |
| `tests/test_miniwob_rerun_readiness.py` | `tests/benchmarks/runtime/test_miniwob_rerun_readiness.py` |
| `tests/test_miniwob_short_loop_diagnostics.py` | `tests/benchmarks/runtime/test_miniwob_short_loop_diagnostics.py` |
| `tests/test_recurrent_qualification.py` | `tests/benchmarks/runtime/test_recurrent_qualification.py` |
| `tests/test_screenspot_benchmark.py` | `tests/benchmarks/runtime/test_screenspot_benchmark.py` |
| `tests/test_target_loop_attestation.py` | `tests/benchmarks/runtime/test_target_loop_attestation.py` |
| `tests/test_target_loop_benchmark_acceptance.py` | `tests/benchmarks/runtime/test_target_loop_benchmark_acceptance.py` |
| `tests/test_target_loop_benchmark_contracts.py` | `tests/benchmarks/runtime/test_target_loop_benchmark_contracts.py` |
| `tests/test_target_loop_benchmark_runner.py` | `tests/benchmarks/runtime/test_target_loop_benchmark_runner.py` |
| `tests/test_target_loop_case_projection.py` | `tests/benchmarks/runtime/test_target_loop_case_projection.py` |
| `tests/test_target_loop_cleanup_ownership.py` | `tests/benchmarks/runtime/test_target_loop_cleanup_ownership.py` |
| `tests/test_target_loop_exact_head_workflow.py` | `tests/benchmarks/runtime/test_target_loop_exact_head_workflow.py` |
| `tests/test_target_loop_full_validation_attestation.py` | `tests/benchmarks/runtime/test_target_loop_full_validation_attestation.py` |
| `tests/test_target_loop_internal_core.py` | `tests/benchmarks/runtime/test_target_loop_internal_core.py` |
| `tests/test_target_loop_internal_safety.py` | `tests/benchmarks/runtime/test_target_loop_internal_safety.py` |
| `tests/test_target_loop_lifecycle_failures.py` | `tests/benchmarks/runtime/test_target_loop_lifecycle_failures.py` |
| `tests/test_target_loop_manifest_identity.py` | `tests/benchmarks/runtime/test_target_loop_manifest_identity.py` |
| `tests/test_target_loop_metric_measurements.py` | `tests/benchmarks/runtime/test_target_loop_metric_measurements.py` |
| `tests/test_target_loop_real_adapters.py` | `tests/benchmarks/runtime/test_target_loop_real_adapters.py` |
| `tests/test_target_loop_report_privacy.py` | `tests/benchmarks/runtime/test_target_loop_report_privacy.py` |
| `tests/test_target_loop_result_consistency.py` | `tests/benchmarks/runtime/test_target_loop_result_consistency.py` |
| `tests/test_target_loop_terminal_reasons.py` | `tests/benchmarks/runtime/test_target_loop_terminal_reasons.py` |
| `tests/test_two_stage_candidate_reporting.py` | `tests/benchmarks/runtime/test_two_stage_candidate_reporting.py` |
| `tests/test_two_stage_contracts.py` | `tests/benchmarks/runtime/test_two_stage_contracts.py` |
| `tests/test_two_stage_http_transports.py` | `tests/benchmarks/runtime/test_two_stage_http_transports.py` |
| `tests/test_two_stage_qualification.py` | `tests/benchmarks/runtime/test_two_stage_qualification.py` |
| `tests/test_two_stage_runner.py` | `tests/benchmarks/runtime/test_two_stage_runner.py` |
| `tests/test_two_stage_schemas.py` | `tests/benchmarks/runtime/test_two_stage_schemas.py` |
| `tests/test_wasp_benchmark.py` | `tests/benchmarks/runtime/test_wasp_benchmark.py` |
| `tests/test_webarena_verified_benchmark.py` | `tests/benchmarks/runtime/test_webarena_verified_benchmark.py` |
| `tests/test_workarena_preflight.py` | `tests/benchmarks/runtime/test_workarena_preflight.py` |
| `tests/test_browsergym_active_capture_conformance.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_active_capture_conformance.py` |
| `tests/test_browsergym_adapter_conformance.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_adapter_conformance.py` |
| `tests/test_browsergym_adapter_readiness.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_adapter_readiness.py` |
| `tests/test_browsergym_dependency_inventory.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_dependency_inventory.py` |
| `tests/test_browsergym_live_runner_gate.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_live_runner_gate.py` |
| `tests/test_browsergym_local_progress_regression.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_local_progress_regression.py` |
| `tests/test_browsergym_m46b_verifier_conformance.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_m46b_verifier_conformance.py` |
| `tests/test_browsergym_oracle_isolation.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_oracle_isolation.py` |
| `tests/test_browsergym_policy_pacing.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_policy_pacing.py` |
| `tests/test_browsergym_report_privacy.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_report_privacy.py` |
| `tests/test_browsergym_runtime.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_runtime.py` |
| `tests/test_browsergym_verifier.py` | `tests/benchmarks/surfaces/browsergym/test_browsergym_verifier.py` |
| `tests/test_reference_target_pricing.py` | `tests/benchmarks/surfaces/dom/test_reference_target_pricing.py` |
| `tests/test_reference_target_readiness.py` | `tests/benchmarks/surfaces/dom/test_reference_target_readiness.py` |
| `tests/test_reference_target_settings.py` | `tests/benchmarks/surfaces/dom/test_reference_target_settings.py` |
| `tests/test_semantic_inventory_targeted.py` | `tests/benchmarks/world/test_semantic_inventory_targeted.py` |
| `tests/test_action_evidence_applicability.py` | `tests/conformance/actions/test_action_evidence_applicability.py` |
| `tests/test_action_verification_scope.py` | `tests/conformance/actions/test_action_verification_scope.py` |
| `tests/test_destination_contract.py` | `tests/conformance/actions/test_destination_contract.py` |
| `tests/test_interaction_capability_onboarding.py` | `tests/conformance/actions/test_interaction_capability_onboarding.py` |
| `tests/test_confirmation_contracts.py` | `tests/conformance/agent/test_confirmation_contracts.py` |
| `tests/test_confirmation_subject_properties.py` | `tests/conformance/agent/test_confirmation_subject_properties.py` |
| `tests/test_control_feedback_contract.py` | `tests/conformance/agent/test_control_feedback_contract.py` |
| `tests/test_control_feedback_state_machine_properties.py` | `tests/conformance/agent/test_control_feedback_state_machine_properties.py` |
| `tests/test_control_outcome_contract.py` | `tests/conformance/agent/test_control_outcome_contract.py` |
| `tests/test_evaluation_contract_closed_algebra.py` | `tests/conformance/evaluation/test_evaluation_contract_closed_algebra.py` |
| `tests/test_verification_evidence_fidelity.py` | `tests/conformance/evaluation/test_verification_evidence_fidelity.py` |
| `tests/test_verification_package_boundaries.py` | `tests/conformance/evaluation/test_verification_package_boundaries.py` |
| `tests/test_future_model_contracts.py` | `tests/conformance/model/test_future_model_contracts.py` |
| `tests/test_m2_model_boundary_closure.py` | `tests/conformance/model/test_m2_model_boundary_closure.py` |
| `tests/test_model_policy_admission.py` | `tests/conformance/model/test_model_policy_admission.py` |
| `tests/test_model_tool_transport.py` | `tests/conformance/model/test_model_tool_transport.py` |
| `tests/test_native_tool_transport.py` | `tests/conformance/model/test_native_tool_transport.py` |
| `tests/test_provider_preflight.py` | `tests/conformance/model/test_provider_preflight.py` |
| `tests/test_architecture_modification_audit.py` | `tests/conformance/runtime/test_architecture_modification_audit.py` |
| `tests/test_documentation_governance.py` | `tests/conformance/runtime/test_documentation_governance.py` |
| `tests/test_migration_architecture_boundary.py` | `tests/conformance/runtime/test_migration_architecture_boundary.py` |
| `tests/test_run_accounting_properties.py` | `tests/conformance/runtime/test_run_accounting_properties.py` |
| `tests/test_runtime_boundaries.py` | `tests/conformance/runtime/test_runtime_boundaries.py` |
| `tests/test_semantic_evidence_catalog.py` | `tests/conformance/runtime/test_semantic_evidence_catalog.py` |
| `tests/test_target_core_boundaries.py` | `tests/conformance/runtime/test_target_core_boundaries.py` |
| `tests/test_browsergym_currentness.py` | `tests/conformance/surfaces/browsergym/test_browsergym_currentness.py` |
| `tests/test_browsergym_m46a_currentness_conformance.py` | `tests/conformance/surfaces/browsergym/test_browsergym_m46a_currentness_conformance.py` |
| `tests/test_dom_adapter.py` | `tests/conformance/surfaces/dom/test_dom_adapter.py` |
| `tests/test_dom_surface_adapter.py` | `tests/conformance/surfaces/dom/test_dom_surface_adapter.py` |
| `tests/test_http_json_surface_adapter.py` | `tests/conformance/surfaces/http_json/test_http_json_surface_adapter.py` |
| `tests/test_som_adapter.py` | `tests/conformance/surfaces/visual/test_som_adapter.py` |
| `tests/test_visual_provider_adapters.py` | `tests/conformance/surfaces/visual/test_visual_provider_adapters.py` |
| `tests/test_visual_surface_adapter.py` | `tests/conformance/surfaces/visual/test_visual_surface_adapter.py` |
| `tests/test_visual_surface_contracts.py` | `tests/conformance/surfaces/visual/test_visual_surface_contracts.py` |
| `tests/test_wot_adapter.py` | `tests/conformance/surfaces/wot/test_wot_adapter.py` |
| `tests/test_wot_surface_adapter.py` | `tests/conformance/surfaces/wot/test_wot_surface_adapter.py` |
| `tests/test_wot_surface_contracts.py` | `tests/conformance/surfaces/wot/test_wot_surface_contracts.py` |
| `tests/test_wot_transport.py` | `tests/conformance/surfaces/wot/test_wot_transport.py` |
| `tests/test_target_result_invariants.py` | `tests/conformance/task/test_target_result_invariants.py` |
| `tests/test_target_task_contracts.py` | `tests/conformance/task/test_target_task_contracts.py` |
| `tests/test_observation_action_legality.py` | `tests/conformance/world/test_observation_action_legality.py` |
| `tests/test_orphan_evidence.py` | `tests/conformance/world/test_orphan_evidence.py` |
| `tests/test_semantic_inventory_architecture.py` | `tests/conformance/world/test_semantic_inventory_architecture.py` |
| `tests/test_semantic_inventory_contract.py` | `tests/conformance/world/test_semantic_inventory_contract.py` |
| `tests/test_source_assertions.py` | `tests/conformance/world/test_source_assertions.py` |
| `tests/test_source_assurance.py` | `tests/conformance/world/test_source_assurance.py` |
| `tests/test_target_world_contracts.py` | `tests/conformance/world/test_target_world_contracts.py` |
| `tests/test_world_evidence_validation.py` | `tests/conformance/world/test_world_evidence_validation.py` |
| `tests/test_world_orchestrator_currentness.py` | `tests/conformance/world/test_world_orchestrator_currentness.py` |
| `tests/test_agent_loop.py` | `tests/integration/agent/test_agent_loop.py` |
| `tests/test_agent_progress_loop.py` | `tests/integration/agent/test_agent_progress_loop.py` |
| `tests/test_confirmation_continuation.py` | `tests/integration/agent/test_confirmation_continuation.py` |
| `tests/test_confirmation_reselection.py` | `tests/integration/agent/test_confirmation_reselection.py` |
| `tests/test_control_feedback_runtime_integration.py` | `tests/integration/agent/test_control_feedback_runtime_integration.py` |
| `tests/test_control_transition.py` | `tests/integration/agent/test_control_transition.py` |
| `tests/test_control_transition_failures.py` | `tests/integration/agent/test_control_transition_failures.py` |
| `tests/test_session_snapshot_authority.py` | `tests/integration/agent/test_session_snapshot_authority.py` |
| `tests/test_target_cli.py` | `tests/integration/agent/test_target_cli.py` |
| `tests/test_terminal_session_immutability.py` | `tests/integration/agent/test_terminal_session_immutability.py` |
| `tests/test_user_input_continuation.py` | `tests/integration/agent/test_user_input_continuation.py` |
| `tests/test_task_evaluation_loop_policy.py` | `tests/integration/evaluation/test_task_evaluation_loop_policy.py` |
| `tests/test_live_model_policy_smoke.py` | `tests/integration/model/test_live_model_policy_smoke.py` |
| `tests/test_model_policy_http_bridge.py` | `tests/integration/model/test_model_policy_http_bridge.py` |
| `tests/test_model_policy_ollama_bridge.py` | `tests/integration/model/test_model_policy_ollama_bridge.py` |
| `tests/test_model_policy_runtime_integration.py` | `tests/integration/model/test_model_policy_runtime_integration.py` |
| `tests/test_dynamic_tool_runtime_integration.py` | `tests/integration/runtime/test_dynamic_tool_runtime_integration.py` |
| `tests/test_live_semantic_evaluator_smoke.py` | `tests/integration/runtime/test_live_semantic_evaluator_smoke.py` |
| `tests/test_migrated_environments.py` | `tests/integration/runtime/test_migrated_environments.py` |
| `tests/test_production_evaluator_surface_proofs.py` | `tests/integration/runtime/test_production_evaluator_surface_proofs.py` |
| `tests/test_surface_symmetry_matrix.py` | `tests/integration/runtime/test_surface_symmetry_matrix.py` |
| `tests/test_dom_agent_loop_e2e.py` | `tests/integration/surfaces/dom/test_dom_agent_loop_e2e.py` |
| `tests/test_visual_agent_loop_e2e.py` | `tests/integration/surfaces/visual/test_visual_agent_loop_e2e.py` |
| `tests/test_visual_agent_loop_negatives.py` | `tests/integration/surfaces/visual/test_visual_agent_loop_negatives.py` |
| `tests/test_wot_agent_loop_e2e.py` | `tests/integration/surfaces/wot/test_wot_agent_loop_e2e.py` |
| `tests/test_wot_agent_loop_negatives.py` | `tests/integration/surfaces/wot/test_wot_agent_loop_negatives.py` |
| `tests/test_dynamic_semantic_task_progression.py` | `tests/integration/task/test_dynamic_semantic_task_progression.py` |
| `tests/test_observation_acquisition_lifecycle.py` | `tests/integration/world/test_observation_acquisition_lifecycle.py` |
| `tests/test_unified_source_orchestration.py` | `tests/integration/world/test_unified_source_orchestration.py` |
| `tests/test_action_evaluation_lineage.py` | `tests/unit/actions/test_action_evaluation_lineage.py` |
| `tests/test_action_paging.py` | `tests/unit/actions/test_action_paging.py` |
| `tests/test_action_relevance.py` | `tests/unit/actions/test_action_relevance.py` |
| `tests/test_agent_decision_context.py` | `tests/unit/agent/test_agent_decision_context.py` |
| `tests/test_agent_progress_control.py` | `tests/unit/agent/test_agent_progress_control.py` |
| `tests/test_agent_progress_projection.py` | `tests/unit/agent/test_agent_progress_projection.py` |
| `tests/test_agent_state_mutation.py` | `tests/unit/agent/test_agent_state_mutation.py` |
| `tests/test_browser_session.py` | `tests/unit/agent/test_browser_session.py` |
| `tests/test_confirmation_presentation.py` | `tests/unit/agent/test_confirmation_presentation.py` |
| `tests/test_context_identity.py` | `tests/unit/agent/test_context_identity.py` |
| `tests/test_control_feedback_policy.py` | `tests/unit/agent/test_control_feedback_policy.py` |
| `tests/test_control_feedback_public_digests.py` | `tests/unit/agent/test_control_feedback_public_digests.py` |
| `tests/test_target_runtime_composition_factory.py` | `tests/unit/agent/test_target_runtime_composition_factory.py` |
| `tests/test_target_runtime_facade.py` | `tests/unit/agent/test_target_runtime_facade.py` |
| `tests/test_criterion_adjudication.py` | `tests/unit/evaluation/test_criterion_adjudication.py` |
| `tests/test_target_evaluation_certainty.py` | `tests/unit/evaluation/test_target_evaluation_certainty.py` |
| `tests/test_task_evaluation_validation.py` | `tests/unit/evaluation/test_task_evaluation_validation.py` |
| `tests/test_control_feedback_model_projection.py` | `tests/unit/model/test_control_feedback_model_projection.py` |
| `tests/test_grounding.py` | `tests/unit/model/test_grounding.py` |
| `tests/test_model_backed_agent_policy.py` | `tests/unit/model/test_model_backed_agent_policy.py` |
| `tests/test_model_decision_spec.py` | `tests/unit/model/test_model_decision_spec.py` |
| `tests/test_model_policy_parser.py` | `tests/unit/model/test_model_policy_parser.py` |
| `tests/test_model_policy_production_grounding.py` | `tests/unit/model/test_model_policy_production_grounding.py` |
| `tests/test_model_policy_views.py` | `tests/unit/model/test_model_policy_views.py` |
| `tests/test_model_port.py` | `tests/unit/model/test_model_port.py` |
| `tests/test_model_port_decision_bridge.py` | `tests/unit/model/test_model_port_decision_bridge.py` |
| `tests/test_model_world_projection.py` | `tests/unit/model/test_model_world_projection.py` |
| `tests/test_provider_call_orchestrator.py` | `tests/unit/model/test_provider_call_orchestrator.py` |
| `tests/test_strict_model_json.py` | `tests/unit/model/test_strict_model_json.py` |
| `tests/test_unified_grounding.py` | `tests/unit/model/test_unified_grounding.py` |
| `tests/test_low_risk_inconclusive_policy.py` | `tests/unit/risk/test_low_risk_inconclusive_policy.py` |
| `tests/test_risk_policy.py` | `tests/unit/risk/test_risk_policy.py` |
| `tests/test_dynamic_tool_bridge.py` | `tests/unit/runtime/test_dynamic_tool_bridge.py` |
| `tests/test_dynamic_tool_catalog.py` | `tests/unit/runtime/test_dynamic_tool_catalog.py` |
| `tests/test_flat_semantic_tool_compiler.py` | `tests/unit/runtime/test_flat_semantic_tool_compiler.py` |
| `tests/test_import_order_regression.py` | `tests/unit/runtime/test_import_order_regression.py` |
| `tests/test_intent_context.py` | `tests/unit/runtime/test_intent_context.py` |
| `tests/test_negative_claim_coverage_gate.py` | `tests/unit/runtime/test_negative_claim_coverage_gate.py` |
| `tests/test_regular_lattice_semantics.py` | `tests/unit/runtime/test_regular_lattice_semantics.py` |
| `tests/test_route_calibration.py` | `tests/unit/runtime/test_route_calibration.py` |
| `tests/test_routing_policy_and_binding_cache.py` | `tests/unit/runtime/test_routing_policy_and_binding_cache.py` |
| `tests/test_semantic_judge_bridge.py` | `tests/unit/runtime/test_semantic_judge_bridge.py` |
| `tests/test_semantic_judge_http_proof.py` | `tests/unit/runtime/test_semantic_judge_http_proof.py` |
| `tests/test_target_output_validation.py` | `tests/unit/runtime/test_target_output_validation.py` |
| `tests/test_transition_digest_projection.py` | `tests/unit/runtime/test_transition_digest_projection.py` |
| `tests/test_browsergym_action_evaluator.py` | `tests/unit/surfaces/browsergym/test_browsergym_action_evaluator.py` |
| `tests/test_browsergym_canonical_semantics.py` | `tests/unit/surfaces/browsergym/test_browsergym_canonical_semantics.py` |
| `tests/test_browsergym_execution.py` | `tests/unit/surfaces/browsergym/test_browsergym_execution.py` |
| `tests/test_browsergym_visual_binding.py` | `tests/unit/surfaces/browsergym/test_browsergym_visual_binding.py` |
| `tests/test_browsergym_workflows.py` | `tests/unit/surfaces/browsergym/test_browsergym_workflows.py` |
| `tests/test_browsergym_world_projection.py` | `tests/unit/surfaces/browsergym/test_browsergym_world_projection.py` |
| `tests/test_dom_document_projection.py` | `tests/unit/surfaces/dom/test_dom_document_projection.py` |
| `tests/test_svg_geometry.py` | `tests/unit/surfaces/visual/test_svg_geometry.py` |
| `tests/test_visual_capture.py` | `tests/unit/surfaces/visual/test_visual_capture.py` |
| `tests/test_visual_integer_point.py` | `tests/unit/surfaces/visual/test_visual_integer_point.py` |
| `tests/test_production_task_evaluator.py` | `tests/unit/task/test_production_task_evaluator.py` |
| `tests/test_target_task_intake.py` | `tests/unit/task/test_target_task_intake.py` |
| `tests/test_context_projection_budget.py` | `tests/unit/world/test_context_projection_budget.py` |
