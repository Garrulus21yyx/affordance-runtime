from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "affordance_runtime"
GOVERNANCE_DOC = REPOSITORY_ROOT / "docs" / "architecture-governance-track.md"
CHANGE_ADMISSION_DIR = REPOSITORY_ROOT / "docs" / "change-admission"
PROJECT_PLAN = REPOSITORY_ROOT / "docs" / "project-plan.md"
CURRENT_PLAN = REPOSITORY_ROOT / "docs" / "current-implementation-plan.md"
IMPLEMENTATION_STATUS = REPOSITORY_ROOT / "docs" / "implementation-status.md"
ARCHITECTURE_DOC = REPOSITORY_ROOT / "docs" / "architecture.md"
INTENT_GOVERNANCE = (
    REPOSITORY_ROOT / "docs" / "intent-schema-authority-governance-20260726.md"
)
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE_FILE = REPOSITORY_ROOT / "compose.yaml"
GOVERNED_DOCUMENTS = (
    REPOSITORY_ROOT / "docs" / "architecture.md",
    REPOSITORY_ROOT / "docs" / "current-implementation-plan.md",
    REPOSITORY_ROOT / "docs" / "implementation-status.md",
    REPOSITORY_ROOT / "docs" / "responsibility-containment-boundary.md",
)

# Horizontal ratchets freeze current control hotspots. Ceilings may decrease as
# ownership is extracted; increases require an explicit, time-bounded exception.
CONTROL_MODULE_LINE_CEILINGS = {
    "coordinator.py": 3_461,
    "compatibility_planner_algorithms.py": 2_042,
    "task_planning.py": 1_642,
}

CONTROL_METHOD_LINE_CEILINGS = {
    ("coordinator.py", "RunCoordinator", "run_sync"): 2_034,
    ("generalist_planner.py", "GeneralistLMPlanner", "propose"): 222,
    ("intent_compiler.py", "LLMIntentCompiler", "compile"): 253,
    ("task_planning.py", "TaskPlanValidator", "validate"): 239,
}

RUN_COORDINATOR_METHOD_CEILING = 26

NEUTRAL_CONTRACT_MODULES = (
    "approval_contracts.py",
    "planning_contracts.py",
    "simplified_runtime_contracts.py",
)

EXTRACTED_AUTHORITY_FREE_COLLABORATORS = (
    "active_perception_flow.py",
    "approval_contracts.py",
    "contract_execution_loop.py",
    "perception_session.py",
    "planner_context.py",
    "planner_model_orchestrator.py",
    "planning_contracts.py",
    "recovery_command_dispatcher.py",
    "recovery_handler.py",
    "recovery_trace_projection.py",
    "semantic_action_resolver.py",
    "task_action_family_resolution.py",
    "obligation_attribution_flow.py",
    "obligation_progress_shadow_flow.py",
    "task_plan_flow.py",
    "task_plan_lifecycle.py",
)

FORBIDDEN_NEUTRAL_DEPENDENCIES = (
    "affordance_runtime.adapters",
    "affordance_runtime.benchmarks",
    "affordance_runtime.cli",
    "affordance_runtime.coordinator",
)

STRICT_AUTHORITY_FREE_COLLABORATORS = (
    "semantic_action_resolver.py",
    "task_action_family_resolution.py",
)

FORBIDDEN_STRICT_COLLABORATOR_DEPENDENCIES = (
    "affordance_runtime.benchmarks",
    "affordance_runtime.coordinator",
    "affordance_runtime.state_kernel",
    "affordance_runtime.trace",
)

STATE_KERNEL_MUTATIONS = {
    "activate_task_skill",
    "activate_next_subgoal",
    "add_obligation",
    "checkpoint_task_skill_step",
    "complete_grounding_recovery",
    "complete_subgoal",
    "expose_task_skill_step",
    "fall_through_task_skill",
    "initialize_obligation_progress",
    "install_task_plan",
    "remember_observation",
    "record_action_progress",
    "record_disproved_assumption",
    "record_grounding_reroute",
    "record_planner_proposal",
    "record_progress_guard",
    "record_receipt",
    "record_subgoal_action",
    "replace_task_plan",
    "satisfy_obligation",
    "transition",
    "update_task_skill_bindings",
}

STATE_KERNEL_READS = {
    "active_subgoal",
    "check_progress_guard",
    "constraint_summary",
    "current_page_revision",
    "current_revision",
    "excluded_candidates_for",
    "fallback_lineage_for",
    "obligation_progress_view",
}

EXECUTION_COMMIT_MUTATIONS = {
    "install_task_plan",
    "remember_observation",
    "replace_task_plan",
    "transition",
}

ALLOWED_STATE_MUTATION_MODULES = {
    "coordinator.py",
    "runtime.py",
}

LEGACY_NON_ADAPTER_BENCHMARK_IMPORTERS = {
    "cli.py",
    "conformance.py",
    "evolution.py",
    "evolution_replay.py",
}

OBLIGATION_PROGRESS_CONTRACT_MODULES = {
    "obligation_attribution.py",
    "obligation_current_state.py",
    "obligation_progress.py",
    "obligation_progress_shadow.py",
}

FORBIDDEN_OBLIGATION_PROGRESS_DEPENDENCIES = (
    "affordance_runtime.adapters",
    "affordance_runtime.benchmarks",
    "affordance_runtime.cli",
    "affordance_runtime.coordinator",
    "affordance_runtime.planner_context",
    "affordance_runtime.planners",
    "affordance_runtime.state_kernel",
    "affordance_runtime.task_plan_progress",
    "affordance_runtime.task_planning",
    "affordance_runtime.trace",
)

EXTRACTED_MUTATION_DEBT: set[tuple[str, str]] = set()


def _import_dependencies(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return ()
    if node.level:
        base = "affordance_runtime"
        module = f"{base}.{node.module}" if node.module else base
    else:
        module = node.module or ""
    dependencies = [module] if module else []
    if module == "affordance_runtime":
        dependencies.extend(f"{module}.{alias.name}" for alias in node.names)
    return tuple(dependencies)


def _matches_module(dependency: str, prefix: str) -> bool:
    return dependency == prefix or dependency.startswith(f"{prefix}.")


def _class_method(
    path: Path,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    module = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    )


def test_horizontal_governance_document_is_active_and_non_blocking() -> None:
    assert GOVERNANCE_DOC.exists()
    text = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()

    assert "independent horizontal governance track" in text
    assert "not a unified-rewrite prerequisite" in text
    assert "synchronous change-admission gate" in text
    for path in GOVERNED_DOCUMENTS:
        assert "architecture-governance-track.md" in path.read_text(encoding="utf-8"), path
    for ceiling in CONTROL_MODULE_LINE_CEILINGS.values():
        assert f"{ceiling:,}" in text
    for ceiling in CONTROL_METHOD_LINE_CEILINGS.values():
        assert f"{ceiling:,}" in text
    assert f"{RUN_COORDINATOR_METHOD_CEILING} `runcoordinator` methods" in text


def test_governance_status_and_dual_lane_policy_have_one_current_source() -> None:
    project_plan = " ".join(PROJECT_PLAN.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    governance = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()
    architecture = " ".join(ARCHITECTURE_DOC.read_text(encoding="utf-8").split()).casefold()
    intent = " ".join(INTENT_GOVERNANCE.read_text(encoding="utf-8").split()).casefold()

    assert "current milestone status is maintained exclusively" in project_plan
    assert "one active vertical slice" in current_plan
    assert "one active horizontal slice" in current_plan
    assert "milestone status" in status
    assert "evidence maturity" in status
    assert "promotion status" in status
    assert "architecture admission" in status
    assert "remote ci" in status
    assert "double-track, one-gate" in governance
    assert "single production writer" in governance
    assert "sole authoritative task-execution commit sequencer" in architecture
    assert "sg1-sg7 targeted confirmation is locally complete" in intent
    assert "protected cross-family / pr breadth is the active vertical slice" in intent
    assert "historical sg7 targeted result alone" in intent
    assert "remains incomplete" in intent


def test_reviewed_architecture_debt_and_sg7_admission_record_are_visible() -> None:
    governance = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    sg7_record = CHANGE_ADMISSION_DIR / "v-sg7-targeted-protected-family.yaml"

    assert "standard `plannerport` still receives mutable `statekernel`" in governance
    assert "generalist planner semantic fallback ownership review" in governance
    assert "semantic_ownership_review: pending_review" in status
    assert sg7_record.exists()

    record = sg7_record.read_text(encoding="utf-8").casefold()
    assert "slice_id: v-sg7-targeted-protected-family" in record
    assert "change_type: vertical_evidence_and_generic_repair" in record
    assert "production_change_initially_allowed: false" in record
    assert "architecture_admission: pass" in record
    assert "semantic_ownership_review:" in record
    assert "status: pending_review" in record
    assert "official_score_claimed: false" in record


def test_reviewed_status_alignment_and_immutable_planner_input_axes_are_explicit() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()

    assert "status_alignment:" in status
    assert "snapshot: current" in status
    assert "not a one-time milestone closure" in status
    assert "immutable_planner_input:" in status
    assert "implementation: not_started" in status
    assert "standard_path_migrated: false" in status
    assert "latest implementation-bearing baseline" in status
    assert "later documentation-only sync commits" in status
    assert "inherit no broader runtime evidence" in status
    assert "standard planner contract no longer receives mutable `statekernel`" in current_plan
    assert "review-driven remediation sequence" in current_plan
    assert "v-prb-5a button-sequence effect semantics" in current_plan
    assert "v-prb-5b entry action-family resolution" in current_plan
    assert "v-prb-6 terminal completion guard classification" in current_plan
    assert "h2 immutable planner input" in current_plan
    assert "p2 semantic fallback owner extraction" in current_plan
    assert "p3 intent semantic normalizer" in current_plan


def test_obligation_driven_progress_decision_is_current_and_non_promotional() -> None:
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    governance = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()
    odg_record = CHANGE_ADMISSION_DIR / "odg-0-obligation-driven-progress-architecture.yaml"
    odg_2_record = CHANGE_ADMISSION_DIR / "odg-2-obligation-progress-contracts.yaml"
    odg_3_record = (
        CHANGE_ADMISSION_DIR / "odg-3-statekernel-obligation-ledger-foundation.yaml"
    )
    odg_4_record = CHANGE_ADMISSION_DIR / "odg-4-role-decisions-ready-projection.yaml"
    odg_5_record = CHANGE_ADMISSION_DIR / "odg-5-obligation-progress-shadow-comparison.yaml"
    odg_6_record = (
        CHANGE_ADMISSION_DIR
        / "odg-6-current-observation-obligation-satisfaction.yaml"
    )
    odg_6_1_record = (
        CHANGE_ADMISSION_DIR
        / "odg-6-1-shared-attribution-contract-hardening.yaml"
    )
    odg_7_record = CHANGE_ADMISSION_DIR / "odg-7-attribution-ticket-resolver.yaml"
    odg_8_record = CHANGE_ADMISSION_DIR / "odg-8-post-action-evidence-normalization.yaml"
    odg_8_1_record = CHANGE_ADMISSION_DIR / "odg-8-1-causality-strength-hardening.yaml"
    odg_8b_record = CHANGE_ADMISSION_DIR / "odg-8b-verifier-evidence-fidelity.yaml"
    odg_9_record = (
        CHANGE_ADMISSION_DIR / "odg-9-post-verification-obligation-attribution.yaml"
    )
    odg_9_runtime_record = (
        CHANGE_ADMISSION_DIR / "odg-9-runtime-ticket-carry-shadow-diagnostic.yaml"
    )
    s0_record = CHANGE_ADMISSION_DIR / "s0-simplified-architecture-freeze.yaml"
    s1_record = CHANGE_ADMISSION_DIR / "s1-simplified-core-contracts.yaml"
    s2_record = CHANGE_ADMISSION_DIR / "s2-legacy-step-compatibility-projection.yaml"
    s2_1_record = CHANGE_ADMISSION_DIR / "s2-1-step-projection-hardening.yaml"
    simplified_architecture = (
        REPOSITORY_ROOT
        / "docs/superpowers/specs/2026-07-29-affordance-runtime-simplified-target-architecture.md"
    )
    simplification_plan = (
        REPOSITORY_ROOT
        / "docs/superpowers/plans/2026-07-29-affordance-runtime-simplification-execution-plan.md"
    )
    role_audit = REPOSITORY_ROOT / "docs" / "audits" / "obligation-execution-role-audit.md"

    assert odg_record.exists()
    assert odg_2_record.exists()
    assert odg_3_record.exists()
    assert odg_4_record.exists()
    assert odg_5_record.exists()
    assert odg_6_record.exists()
    assert odg_6_1_record.exists()
    assert odg_7_record.exists()
    assert odg_8_record.exists()
    assert odg_8_1_record.exists()
    assert odg_8b_record.exists()
    assert odg_9_record.exists()
    assert odg_9_runtime_record.exists()
    assert s0_record.exists()
    assert s1_record.exists()
    assert s2_record.exists()
    assert s2_1_record.exists()
    assert simplified_architecture.exists()
    assert simplification_plan.exists()
    assert role_audit.exists()
    record = " ".join(odg_record.read_text(encoding="utf-8").split()).casefold()
    odg_2 = " ".join(odg_2_record.read_text(encoding="utf-8").split()).casefold()
    odg_3 = " ".join(odg_3_record.read_text(encoding="utf-8").split()).casefold()
    odg_4 = " ".join(odg_4_record.read_text(encoding="utf-8").split()).casefold()
    odg_5 = " ".join(odg_5_record.read_text(encoding="utf-8").split()).casefold()
    odg_6 = " ".join(odg_6_record.read_text(encoding="utf-8").split()).casefold()
    odg_6_1 = " ".join(odg_6_1_record.read_text(encoding="utf-8").split()).casefold()
    odg_7 = " ".join(odg_7_record.read_text(encoding="utf-8").split()).casefold()
    odg_8 = " ".join(odg_8_record.read_text(encoding="utf-8").split()).casefold()
    odg_8_1 = " ".join(odg_8_1_record.read_text(encoding="utf-8").split()).casefold()
    odg_8b = " ".join(odg_8b_record.read_text(encoding="utf-8").split()).casefold()
    odg_9 = " ".join(odg_9_record.read_text(encoding="utf-8").split()).casefold()
    odg_9_runtime = " ".join(
        odg_9_runtime_record.read_text(encoding="utf-8").split()
    ).casefold()
    s0 = " ".join(s0_record.read_text(encoding="utf-8").split()).casefold()
    s1 = " ".join(s1_record.read_text(encoding="utf-8").split()).casefold()
    s2 = " ".join(s2_record.read_text(encoding="utf-8").split()).casefold()
    s2_1 = " ".join(s2_1_record.read_text(encoding="utf-8").split()).casefold()
    simplified_architecture_text = " ".join(
        simplified_architecture.read_text(encoding="utf-8").split()
    ).casefold()
    simplification_plan_text = " ".join(
        simplification_plan.read_text(encoding="utf-8").split()
    ).casefold()
    audit = " ".join(role_audit.read_text(encoding="utf-8").split()).casefold()

    assert "canonical obligation graph is the sole authoritative progress model" in record
    assert "production_change_allowed: false" in record
    assert "production_behavior_change: false" in odg_2
    assert "statekernel mutation" in odg_2
    assert "closure_status: foundation_only" in odg_2
    assert "production_behavior_change: false" in odg_3
    assert "coordinator satisfaction commit" in odg_3
    assert "finish gate change" in odg_3
    assert "plannercontext ready-obligation projection" in odg_3
    assert "closure_status: foundation_storage_only" in odg_3
    assert "production_behavior_change: false" in odg_4
    assert "blocking_availability_predicate: role_pending" in odg_4
    assert "task name" in odg_4
    assert "benchmark family" in odg_4
    assert "planner state" in odg_4
    assert "taskplan state" in odg_4
    assert "closure_status: foundation_projection_only" in odg_4
    assert "production_behavior_change: false" in odg_5
    assert "trace identity envelope" in odg_5
    assert "legacy_verified_projection" in odg_5
    assert "obligationprogressshadowcompared trace event" in odg_5
    assert "obligationprogressshadowfailed diagnostic event" in odg_5
    assert "statekernel initialization" in odg_5
    assert "exact-id mapping" in odg_5
    assert "completed_without_evidence_is_satisfied: false" in odg_5
    assert "writes_state: false" in odg_5
    assert "writes_trace: diagnostic_only" in odg_5
    assert "closure_status: post_observation_trace_hookup" in odg_5
    assert "production_behavior_change: false" in odg_6
    assert "currentobservationobligationsatisfactionevaluator" in odg_6
    assert "is_available" in odg_6
    assert "is_visible" in odg_6
    assert "executionreceipt" in odg_6
    assert "browsergym official reward" in odg_6
    assert "writes_state: false" in odg_6
    assert "writes_trace: false" in odg_6
    assert "closure_status: foundation_evaluator_only_hardened" in odg_6
    assert "synthetic_contract_id_for_current_observation: prohibited" in odg_6_1
    assert "progressattributionticket.task_spec_identity" in odg_6_1
    assert "obligationsatisfactionpreparation.task_spec_identity" in odg_6_1
    assert "currentobservationsatisfactionresult" in odg_6_1
    assert "closure_status: shared_contract_hardening" in odg_6_1
    assert "production_behavior_change: false" in odg_7
    assert "attributionactionview" in odg_7
    assert "progressattributionticketresolver" in odg_7
    assert "attributiontargetview" in odg_7
    assert "canonical-json ticket_id generation" in odg_7
    assert "stale_progress and invalid_progress projection classification split" in odg_7
    assert "ready-view canonical consistency validation" in odg_7
    assert "runtime supplied target-to-canonical-subject binding" in odg_7
    assert "multiple_candidates_allowed: true" in odg_7
    assert "ticket_completion_authority: none" in odg_7
    assert "actioncontract schema changes" in odg_7
    assert "closure_status: ticket_resolver_foundation_only" in odg_7
    assert "production_behavior_change: false" in odg_8
    assert "verificationevidenceview" in odg_8
    assert "verificationreportview" in odg_8
    assert "verifiersemanticevidencedeclaration" in odg_8
    assert "postactionevidencenormalizer" in odg_8
    assert "fact_obligation_id: prohibited" in odg_8
    assert "receipt_success_completion: prohibited" in odg_8
    assert "external_reward_completion: prohibited" in odg_8
    assert "source_strength_policy:" in odg_8
    assert "effective_strength: min(reported_strength, source_cap)" in odg_8
    assert "stable_semantic_evidence_key: required" in odg_8
    assert "closure_status: evidence_normalization_foundation_hardened_with_verifier_fidelity" in odg_8
    assert "postverificationcontext" in odg_8_1
    assert "effective strength equals the minimum" in odg_8_1
    assert "unknown reported strength fail-closed as invalid" in odg_8_1
    assert "closure_status: causality_strength_contract_hardening" in odg_8_1
    assert "verifierevaluation" in odg_8b
    assert "verificationevidence.semantic_evidence_key" in odg_8b
    assert "verify_result_equals_evaluate_passed" in odg_8b
    assert "state_delta_or_terminal_concrete_progress_fact: prohibited" in odg_8b
    assert "closure_status: verifier_fidelity_foundation_only" in odg_8b
    assert "production_behavior_change: false" in odg_9
    assert "postverificationobligationattributor" in odg_9
    assert "weak_evidence_completion: prohibited" in odg_9
    assert "taskplan_required: false" in odg_9
    assert "closure_status: attribution_foundation_only" in odg_9
    assert "boundactionexecution" in odg_9_runtime
    assert "contractexecutionloop.bind_action_execution" in odg_9_runtime
    assert "action_contract_schema_change: false" in odg_9_runtime
    assert "executor_ticket_visibility: prohibited" in odg_9_runtime
    assert "verifier_ticket_visibility: prohibited" in odg_9_runtime
    assert "closure_status: runtime_ticket_carry_shadow_foundation_only" in odg_9_runtime
    assert "slice_id: s0-simplified-architecture-freeze" in s0
    assert "default_production_progress_authority: runtime_owned_active_step" in s0
    assert "advanced_attribution: experimental_only" in s0
    assert "odg_10_progress_commit: not_authorized" in s0
    assert "odg_11_finish_authority_migration: not_authorized" in s0
    assert "closure_status: architecture_freeze_only" in s0
    assert "slice_id: s1-simplified-core-contracts" in s1
    assert "production_behavior_change: false" in s1
    assert "standard_path_authority_change: none" in s1
    assert "sourcereference" in s1
    assert "step_spec" not in s1
    assert "stepspec" in s1
    assert "executionattempt" in s1
    assert "verificationresult" in s1
    assert "actionoutcome" in s1
    assert "source_refs_for_completion_criteria: required" in s1
    assert "precondition_as_completion_criterion: prohibited" in s1
    assert "receipt_success_completion: prohibited" in s1
    assert "closure_status: contract_foundation_only" in s1
    assert "next_slice: s2-legacy-step-compatibility-projection" in s1
    assert "slice_id: s2-legacy-step-compatibility-projection" in s2
    assert "production_behavior_change: false" in s2
    assert "projected_view_authority: none" in s2
    assert "exact_id_mapping_only: true" in s2
    assert "lexical_mapping: prohibited" in s2
    assert "no_state_mutation: required" in s2
    assert "closure_status: compatibility_projection_foundation_only" in s2
    assert "hardening_record: docs/change-admission/s2-1-step-projection-hardening.yaml" in s2
    assert "next_slice: s2-1-step-projection-hardening-before-s3" in s2
    assert "slice_id: s2-1-step-projection-hardening" in s2_1
    assert "production_behavior_change: false" in s2_1
    assert "completed_plan_active_step_id: null" in s2_1
    assert "claim_id_is_not_source_unit_id: true" in s2_1
    assert "criterion_policy_source: typed_evidence_requirements" in s2_1
    assert "completed_without_evidence: projection_invalid" in s2_1
    assert "unknown_progress_ids: projection_invalid" in s2_1
    assert "closure_status: compatibility_projection_hardened" in s2_1
    assert "next_slice: s3-immutable-planning-request" in s2_1
    assert "approved_with_guardrails" in simplified_architecture_text
    assert "高级 attribution" in simplified_architecture_text
    assert "experimental_only" in simplified_architecture_text
    assert "odg-10 obligation ledger commit 与 odg-11 finish-authority migration 停止" in simplified_architecture_text
    assert "proposed_for_execution" in simplification_plan_text
    assert "s1 simplified core contracts" in simplification_plan_text
    assert "advanced attribution 进入默认 completion" in simplification_plan_text
    assert "taskplanprogresstarget:" in record
    assert "status: compatibility_foundation" in record
    assert "subgoalevidencebinder_progress_target:" in record
    assert "coordinator_integration: status: not_authorized" in record
    assert "promotion_status: held" in record

    assert "odg-2 adds the typed progress/attribution contracts" in current_plan
    assert "odg-3 adds statekernel obligation ledger foundation" in current_plan
    assert "odg-4a/4b: executable role decisions" in current_plan
    assert "odg-5 adds typed divergence classification" in current_plan
    assert "taskplan becomes an optional execution strategy view" in current_plan
    assert "obligation_driven_progress:" in status
    assert "contracts: foundation_only" in status
    assert "ledger: foundation_storage_only" in status
    assert "ready_projection: authority_free_foundation" in status
    assert "shadow_comparison: post_observation_trace_hookup" in status
    assert "current_observation_satisfaction: foundation_evaluator_only_hardened" in status
    assert "shared_attribution_contract_hardening: complete" in status
    assert "attribution_ticket_resolver: foundation_only_hardened" in status
    assert "post_action_evidence_normalization: foundation_hardened_with_verifier_fidelity" in status
    assert "post_action_causality_strength: complete" in status
    assert "verifier_evidence_fidelity: foundation_only" in status
    assert "post_verification_attribution: foundation_only" in status
    assert "runtime_ticket_carry_shadow: foundation_only" in status
    assert "next_odg_slice: stopped_for_default_path" in status
    assert "simplified_runtime_architecture:" in status
    assert "core_contracts_record: docs/change-admission/s1-simplified-core-contracts.yaml" in status
    assert "core_contracts: foundation_only" in status
    assert "step_projection_record: docs/change-admission/s2-legacy-step-compatibility-projection.yaml" in status
    assert "step_projection_hardening_record: docs/change-admission/s2-1-step-projection-hardening.yaml" in status
    assert "step_projection: foundation_hardened" in status
    assert "next_slice: s3-immutable-planning-request" in status
    assert "odg_advanced_attribution: experimental_only" in status
    assert "coordinator_commit: not_authorized" in status
    assert "taskplan_authority: compatibility_only_target" in status
    assert "future standard-path completion must be attributed to obligation ids" in governance
    assert "must not import coordinator, statekernel, taskplan" in governance
    assert "statekernel to the obligation progress contracts" in governance
    assert "odg-4 may add executable role decisions" in governance
    assert "odg-5 may add authority-free shadow comparison" in governance
    assert "odg-6 may add a typed, authority-free current-observation" in governance
    assert "odg-6.1 hardens shared attribution contracts" in governance
    assert "odg-7 may add an authority-free attribution action view" in governance
    assert "multiple candidate obligations in one ticket are allowed" in governance
    assert "odg-8 may add authority-free post-action evidence normalization" in governance
    assert "must not persist tickets" in governance
    assert "receipt and external-evaluator sources remain weak" in governance
    assert "odg-8.1 hardens odg-8 before attribution" in governance
    assert "effective strength is the minimum" in governance
    assert "odg-8b may improve verifier evidence fidelity" in governance
    assert "verify()` a compatibility wrapper" in governance
    assert "odg-9 may add a pure" in governance
    assert "weak receipt, weak state-delta, and weak external-evaluator" in governance
    assert "odg-9 runtime carry may add" in governance
    assert "must not be added to the `actioncontract` schema" in governance
    assert "s0 simplified architecture freeze supersedes odg-0" in governance
    assert "advanced attribution is `experimental_only`" in governance
    assert "no change may create three simultaneous completion authorities" in governance
    assert "s1 simplified core contracts may add a neutral contract module" in governance
    assert "foundation-only boundary" in governance
    assert "next default-path slice after s1 is exact-id legacy-to-step compatibility projection" in governance
    assert "s2 legacy-step compatibility projection may read taskplan" in governance
    assert "exact subgoal id to canonical obligation id" in governance
    assert "s2.1 hardens this projection before s3" in governance
    assert "completed plans must project with no active step" in governance
    assert "criterion evidence policy must come from typed evidence requirements" in governance
    assert "immutable_planner_input: planned under simplified active-step architecture" in status
    assert "taskspec, step projection, unifiedobservation, recent actionoutcome summaries, and budgets" in status
    assert "completed_plan_active_step_id: null" in s2_1
    assert "claim_id_is_not_source_unit_id: true" in s2_1
    assert "criterion_policy_source: typed_evidence_requirements" in s2_1
    assert "completed_without_evidence: projection_invalid" in s2_1
    assert "unknown_progress_ids: projection_invalid" in s2_1
    assert "synthetic contract id" in governance
    assert "coordinator commit remains odg-10" in governance
    assert "submit_button_is_available:" in audit
    assert "fail_closed_pending_rule" in audit
    assert "module-level semantic owner gate" in governance
    assert "strict planner module may not add new task-language parser logic" in governance
    assert "typed resolver or constraint owner" in governance
    assert "canonical obligation graph is the sole target progress authority" in governance
    assert "current vertical lane is sg7 targeted protected-family confirmation" not in governance


def test_pr_breadth_negative_evidence_is_recorded_without_promotion_claim() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    evidence = REPOSITORY_ROOT / "docs/evidence/runs/m8.2a-pr-breadth-d66760f/README.md"
    repair_record = CHANGE_ADMISSION_DIR / "v-pr-breadth-intent-planning-repair.yaml"

    assert evidence.exists()
    assert (evidence.parent / "browsergym-report.json").exists()
    assert (evidence.parent / "matrix-metadata.json").exists()
    assert repair_record.exists()
    evidence_text = " ".join(evidence.read_text(encoding="utf-8").split()).casefold()
    repair_text = " ".join(repair_record.read_text(encoding="utf-8").split()).casefold()

    assert "pr_breadth_initial_negative:" in status
    assert "status: failed" in status
    assert "expected: 12" in status
    assert "observed: 12" in status
    assert "passed: 0" in status
    assert "official_score_claimed: false" in status
    assert "root_owner_next: intent / planning" in status
    assert "historical initial p4 diagnostic at `d66760f`" in current_plan
    assert "current pr breadth evidence at `407133d`" in current_plan
    assert "11/12 official reward passed" in current_plan
    assert "3 runtime failures" in current_plan
    assert "m8.2a-pr-breadth-d66760f" in status
    assert "official_score_claimed=false" in evidence_text
    assert "promotion eligible: no" in evidence_text
    assert "intent_compilation_rejected" in evidence_text
    assert "planner_waiting_clarification" in evidence_text
    assert "architecture_admission: not_evaluated" in repair_text
    assert "non-browsergym reproduction" in repair_text
    assert "do not add task-name" in repair_text
    assert "rerun pr breadth 6-task x 2-seed matrix" in repair_text
    assert "packet_role: umbrella_diagnostic" in repair_text
    assert "may_become_production_slice: false" in repair_text
    assert "child_slices_required: true" in repair_text


def test_v_prb_6b_407133d_rerun_is_recorded_without_promotion_claim() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    evidence = REPOSITORY_ROOT / "docs/evidence/runs/m8.2a-pr-breadth-407133d/README.md"

    assert evidence.exists()
    assert (evidence.parent / "browsergym-report.json").exists()
    assert (evidence.parent / "matrix-metadata.json").exists()

    evidence_text = " ".join(evidence.read_text(encoding="utf-8").split()).casefold()
    assert "pr_breadth_latest:" in status
    assert "revision: 407133d1a1c902436ae2576175f834a7a74b1367" in status
    assert "passed: 11" in status
    assert "runtime_failed: 3" in status
    assert "v_prb_6b_enter_text_closed: true" in status
    assert "monitored_nonreproduced_episode:" in status
    assert "click-button:seed-1" in status
    assert "form-sequence:seed-0" in status
    assert "form-sequence:seed-1" in status
    assert "v-prb-6a progress-target foundation is retained as compatibility-only" in current_plan
    assert "json-invalid cluster remains monitored" in current_plan
    assert "obligation-driven progress architecture" in current_plan
    assert "official_score_claimed=false" in evidence_text
    assert "promotion_status: held" in evidence_text
    assert "pr_breadth_acceptance: failed" in evidence_text


def test_post_407133d_click_button_recheck_prevents_premature_repair_claim() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    evidence = REPOSITORY_ROOT / "docs/evidence/runs/v-prb-6-post-407133d-click-button-recheck/README.md"

    assert evidence.exists()
    evidence_text = " ".join(evidence.read_text(encoding="utf-8").split()).casefold()
    assert "click_button_recheck:" in status
    assert "revision: 47932a2d84266983c632258afdfacae9b1cdcd94" in status
    assert "json_invalid did not reproduce" in status
    assert "historical_next_change_before_odg_0: v-prb-6a form-sequence" in status
    assert "current_next_change_admission: s3 immutable planningrequest" in status
    assert "official_score_claimed=false" in evidence_text
    assert "passed: 2" in evidence_text
    assert "too weak to authorize a production repair" in evidence_text
    assert "no longer to extend pre-action taskplan subgoal attribution" in current_plan
    assert "odg-1 records the initial obligation execution-role audit" in current_plan


def test_pr_breadth_child_packet_lifecycle_matches_review_approval() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    governance = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()

    record_5a = CHANGE_ADMISSION_DIR / "v-prb-5a-button-sequence-effect-semantics.yaml"
    record_5b = CHANGE_ADMISSION_DIR / "v-prb-5b-entry-action-family-resolution.yaml"
    record_5c = CHANGE_ADMISSION_DIR / "v-prb-5c-form-sequence-strict-planner-proposal.yaml"
    record_6 = CHANGE_ADMISSION_DIR / "v-prb-6-terminal-completion-guard.yaml"
    record_6a = CHANGE_ADMISSION_DIR / "v-prb-6a-dependent-subgoal-evidence-binding.yaml"
    record_6b = CHANGE_ADMISSION_DIR / "v-prb-6b-single-subgoal-terminal-completion.yaml"

    for path in (record_5a, record_5b, record_5c, record_6, record_6a, record_6b):
        assert path.exists(), path

    text_5a = " ".join(record_5a.read_text(encoding="utf-8").split()).casefold()
    text_5b = " ".join(record_5b.read_text(encoding="utf-8").split()).casefold()
    text_5c = " ".join(record_5c.read_text(encoding="utf-8").split()).casefold()
    text_6 = " ".join(record_6.read_text(encoding="utf-8").split()).casefold()
    text_6a = " ".join(record_6a.read_text(encoding="utf-8").split()).casefold()
    text_6b = " ".join(record_6b.read_text(encoding="utf-8").split()).casefold()

    assert "packet_role: child_production_slice" in text_5a
    assert "do not modify production code in this diagnostic packet" not in text_5a
    assert "next_requirement:" in text_5a
    assert "close v-prb-5a" not in text_5a

    assert "packet_role: child_production_slice" in text_5b
    assert "task_action_family_resolution.py" in text_5b
    assert "executable_authority_free_manifest: task_action_family_resolution.py" in text_5b
    assert "architecture_admission: pass" in text_5b

    assert "packet_role: child_production_slice" in text_5c
    assert "closure_status: closed_for_current_pr_breadth_matrix" in text_5c

    assert "packet_role: child_diagnostic" in text_6
    assert "production_change_allowed: false" in text_6
    assert "architecture_admission: not_evaluated" in text_6
    assert "child_diagnostics:" in text_6
    assert "v-prb-6a-dependent-subgoal-evidence-binding.yaml" in text_6
    assert "v-prb-6b-single-subgoal-terminal-completion.yaml" in text_6

    assert "packet_role: child_diagnostic" in text_6a
    assert "production_change_allowed: false" in text_6a
    assert "form-sequence:seed-0" in text_6a
    assert "form-sequence:seed-1" in text_6a
    assert "receipt success alone must not complete any subgoal" in text_6a

    assert "packet_role: child_diagnostic" in text_6b
    assert "production_change_allowed: false" in text_6b
    assert "enter-text:seed-1" in text_6b
    assert "single-subgoal" in text_6b

    assert "v-prb-5c is closed for the current pr breadth matrix" in current_plan
    assert "v-prb-6a" in current_plan
    assert "v-prb-6b" in current_plan
    assert "v-prb-5b" in governance
    assert "task_action_family_resolution.py" in governance
    assert "executable_authority_free_manifest: incomplete" not in status


def test_pr_breadth_failure_attribution_child_slice_is_recorded() -> None:
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    attribution = REPOSITORY_ROOT / "docs/evidence/runs/m8.2a-pr-breadth-d66760f/episode-attribution.yaml"
    child_record = CHANGE_ADMISSION_DIR / "v-prb-0-failure-attribution-fidelity.yaml"

    assert attribution.exists()
    assert child_record.exists()

    attribution_text = " ".join(attribution.read_text(encoding="utf-8").split()).casefold()
    child_text = " ".join(child_record.read_text(encoding="utf-8").split()).casefold()

    assert "v-prb-0" in current_plan
    assert "attribution_classification:" in status
    assert "episodes_classified: 12" in status
    assert "unclassified: 0" in status
    assert "actual_owner: intent structured decoding" in attribution_text
    assert "click-button:seed-1" in attribution_text
    assert "task_spec_created: false" in attribution_text
    assert "reported_layer_correction: contract / field_binding -> intent structured decoding" in attribution_text
    assert "coverage audit validator" in attribution_text
    assert "semantic action resolver" in attribution_text
    assert "packet_role: child_diagnostic" in child_text
    assert "production_change_allowed: false" in child_text
    assert "12/12 episodes have exact mechanism owner" in child_text


def test_pr_breadth_invalid_coverage_audit_child_slice_is_scoped() -> None:
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    child_record = CHANGE_ADMISSION_DIR / "v-prb-1-invalid-coverage-audit-handling.yaml"

    assert child_record.exists()

    child_text = " ".join(child_record.read_text(encoding="utf-8").split()).casefold()
    assert "v-prb-1 invalid coverage audit handling" in current_plan
    assert "v_prb_1_invalid_coverage_audit_handling:" in status
    assert "single_primary_owner: intent coverage audit admission" in child_text
    assert "production_change_allowed: true" in child_text
    assert "non_browsergym_red_test:" in child_text
    assert "coverage_review_invalid_quote" in child_text
    assert "do not modify coordinator" in child_text
    assert "do not modify statekernel" in child_text
    assert "do not add task-name" in child_text


def test_v_prb_1_clean_pr_breadth_rerun_is_recorded() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    evidence = REPOSITORY_ROOT / "docs/evidence/runs/m8.2a-pr-breadth-d40f8f1/README.md"

    assert evidence.exists()
    assert (evidence.parent / "browsergym-report.json").exists()
    assert (evidence.parent / "matrix-metadata.json").exists()

    evidence_text = " ".join(evidence.read_text(encoding="utf-8").split()).casefold()
    assert "v_prb_1_clean_rerun:" in status
    assert "revision: d40f8f1792e85f391fe6c94dd88f9b5e0235d481" in status
    assert "passed: 0" in status
    assert "waiting_clarification: 7" in status
    assert "invalid_coverage_audit_handling_closed: true" in status
    assert "m8.2a-pr-breadth-d40f8f1" in current_plan
    assert "official_score_claimed=false" in evidence_text
    assert "promotion eligible: no" in evidence_text
    assert "next selectable repair: v-prb-3" in evidence_text


def test_pr_breadth_typed_semantic_action_child_slice_is_scoped() -> None:
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    child_record = CHANGE_ADMISSION_DIR / "v-prb-3-typed-semantic-action-constraints.yaml"

    assert child_record.exists()

    child_text = " ".join(child_record.read_text(encoding="utf-8").split()).casefold()
    assert "v-prb-3 typed semantic action constraints" in current_plan
    assert "v_prb_3_typed_semantic_action_constraints:" in status
    assert "single_primary_owner: strict semantic action resolver" in child_text
    assert "production_change_allowed: true" in child_text
    assert "non_browsergym_red_tests:" in child_text
    assert "strict-semantic-action-resolver" in child_text
    assert "do not modify coordinator" in child_text
    assert "do not modify statekernel" in child_text
    assert "do not add task-name" in child_text
    assert "do not modify prompt" in child_text


def test_v_prb_3_clean_pr_breadth_rerun_is_recorded() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    evidence = REPOSITORY_ROOT / "docs/evidence/runs/m8.2a-pr-breadth-9b951ed/README.md"

    assert evidence.exists()
    assert (evidence.parent / "browsergym-report.json").exists()
    assert (evidence.parent / "matrix-metadata.json").exists()

    evidence_text = " ".join(evidence.read_text(encoding="utf-8").split()).casefold()
    assert "v_prb_3_clean_rerun:" in status
    assert "revision: 9b951ed968314aa7a139611d00256adb17b3cbb7" in status
    assert "passed: 8" in status
    assert "failed: 4" in status
    assert "typed_semantic_action_constraints_closed: true" in status
    assert "remaining_mechanisms:" in status
    assert "invalid_provider_graph: 4" in status
    assert "planner_terminal_completion_guard: 1" in status
    assert "next_selectable_child_slice: v-prb-2 provider graph proposal normalization" in status
    assert "m8.2a-pr-breadth-9b951ed" in current_plan
    assert "official_score_claimed=false" in evidence_text
    assert "promotion eligible: no" in evidence_text
    assert "passed: 8" in evidence_text
    assert "next selectable repair: v-prb-2" in evidence_text


def test_pr_breadth_provider_graph_normalization_child_slice_is_scoped() -> None:
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    child_record = CHANGE_ADMISSION_DIR / "v-prb-2-provider-graph-proposal-normalization.yaml"

    assert child_record.exists()

    child_text = " ".join(child_record.read_text(encoding="utf-8").split()).casefold()
    assert "v-prb-2 provider graph proposal normalization" in current_plan
    assert "v_prb_2_provider_graph_proposal_normalization:" in status
    assert "single_primary_owner: canonical obligation compiler boundary" in child_text
    assert "production_change_allowed: true" in child_text
    assert "non_browsergym_red_tests:" in child_text
    assert "compile_requested_effects" in child_text
    assert "do not modify coordinator" in child_text
    assert "do not modify statekernel" in child_text
    assert "do not add task-name" in child_text
    assert "do not modify prompt" in child_text


def test_v_prb_2_clean_pr_breadth_rerun_is_recorded() -> None:
    status = " ".join(IMPLEMENTATION_STATUS.read_text(encoding="utf-8").split()).casefold()
    current_plan = " ".join(CURRENT_PLAN.read_text(encoding="utf-8").split()).casefold()
    evidence = REPOSITORY_ROOT / "docs/evidence/runs/m8.2a-pr-breadth-c24b277/README.md"

    assert evidence.exists()
    assert (evidence.parent / "browsergym-report.json").exists()
    assert (evidence.parent / "matrix-metadata.json").exists()

    evidence_text = " ".join(evidence.read_text(encoding="utf-8").split()).casefold()
    assert "v_prb_2_clean_rerun:" in status
    assert "revision: c24b277a93712191c626a1db87cc1f3fc1c166bd" in status
    assert "passed: 8" in status
    assert "failed: 4" in status
    assert "invalid_provider_graph_closed: true" in status
    assert "waiting_clarification: 2" in status
    assert "entry_action_family_unavailable: 2" in status
    assert "m8.2a-pr-breadth-c24b277" in current_plan
    assert "official_score_claimed=false" in evidence_text
    assert "promotion eligible: no" in evidence_text
    assert "invalid_provider_graph closed: yes" in evidence_text
    assert "next selectable repair: v-prb-5" in evidence_text


def test_ci_keeps_reproducible_python_and_browsergym_profiles() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "- run: python -m pytest -q" in workflow
    assert "- run: pytest -q" not in workflow
    assert "python -m pip install -e '.[dev,web,parent]'" in workflow
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "browsergym-bridge:\n    runs-on: ubuntu-22.04" in workflow
    assert "python -m pip install -e . -r requirements/constraints-browsergym.txt" in workflow
    assert "affordance-runtime benchmark --output evidence/benchmark --seeds 3 --allow-acceptance-fail" in workflow
    assert (
        "python scripts/generalization_smoke.py --benchmark evidence/benchmark/benchmark-report.json "
        "--output evidence/generalization --allow-acceptance-fail"
    ) in workflow
    assert "--allow-acceptance-fail" in compose


def test_active_subgoal_is_read_only_and_no_longer_a_planner_context_debt() -> None:
    assert "active_subgoal" not in STATE_KERNEL_MUTATIONS
    assert "active_subgoal" in STATE_KERNEL_READS
    assert ("planner_context.py", "active_subgoal") not in EXTRACTED_MUTATION_DEBT


def test_control_module_growth_ratchets_cannot_expand() -> None:
    for filename, ceiling in CONTROL_MODULE_LINE_CEILINGS.items():
        source = (SOURCE_ROOT / filename).read_text(encoding="utf-8")
        assert len(source.splitlines()) <= ceiling, filename


def test_control_method_growth_ratchets_cannot_expand() -> None:
    for (filename, class_name, method_name), ceiling in CONTROL_METHOD_LINE_CEILINGS.items():
        method = _class_method(SOURCE_ROOT / filename, class_name, method_name)
        assert method.end_lineno is not None
        assert method.end_lineno - method.lineno + 1 <= ceiling, (
            filename,
            class_name,
            method_name,
        )

    coordinator = ast.parse((SOURCE_ROOT / "coordinator.py").read_text(encoding="utf-8"))
    run_coordinator = next(
        node
        for node in coordinator.body
        if isinstance(node, ast.ClassDef) and node.name == "RunCoordinator"
    )
    coordinator_methods = [
        node
        for node in run_coordinator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert len(coordinator_methods) <= RUN_COORDINATOR_METHOD_CEILING
    oversized_new_methods = [
        node.name
        for node in run_coordinator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name != "run_sync"
        and node.end_lineno is not None
        and node.end_lineno - node.lineno + 1 > 250
    ]
    assert oversized_new_methods == []


def test_neutral_contracts_do_not_depend_on_orchestration_or_adapters() -> None:
    violations: list[tuple[str, str]] = []
    for filename in NEUTRAL_CONTRACT_MODULES:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for dependency in _import_dependencies(node):
                if any(
                    _matches_module(dependency, prefix)
                    for prefix in FORBIDDEN_NEUTRAL_DEPENDENCIES
                ):
                    violations.append((filename, dependency))
    assert violations == []


def test_obligation_progress_contracts_do_not_import_taskplan_or_runtime_authority() -> None:
    violations: list[tuple[str, int, str]] = []
    for filename in OBLIGATION_PROGRESS_CONTRACT_MODULES:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for dependency in _import_dependencies(node):
                if any(
                    _matches_module(dependency, prefix)
                    for prefix in FORBIDDEN_OBLIGATION_PROGRESS_DEPENDENCIES
                ):
                    violations.append((filename, getattr(node, "lineno", 0), dependency))
    assert violations == []


def test_obligation_shadow_flow_is_read_only_runtime_projection() -> None:
    filename = "obligation_progress_shadow_flow.py"
    tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
    violations: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        for dependency in _import_dependencies(node):
            if any(
                _matches_module(dependency, prefix)
                for prefix in (
                    "affordance_runtime.adapters",
                    "affordance_runtime.benchmarks",
                    "affordance_runtime.coordinator",
                    "affordance_runtime.trace",
                )
            ):
                violations.append((filename, getattr(node, "lineno", 0), dependency))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in STATE_KERNEL_MUTATIONS
        ):
            violations.append((filename, node.lineno, node.func.attr))
    assert violations == []


def test_simplified_step_projection_is_read_only_compatibility_projection() -> None:
    filename = "simplified_step_projection.py"
    tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
    violations: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        for dependency in _import_dependencies(node):
            if any(
                _matches_module(dependency, prefix)
                for prefix in (
                    "affordance_runtime.adapters",
                    "affordance_runtime.benchmarks",
                    "affordance_runtime.coordinator",
                    "affordance_runtime.planner_context",
                    "affordance_runtime.trace",
                )
            ):
                violations.append((filename, getattr(node, "lineno", 0), dependency))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in STATE_KERNEL_MUTATIONS
        ):
            violations.append((filename, node.lineno, node.func.attr))
    assert violations == []


def test_obligation_attribution_flow_is_diagnostic_only_runtime_projection() -> None:
    filename = "obligation_attribution_flow.py"
    tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
    violations: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        for dependency in _import_dependencies(node):
            if any(
                _matches_module(dependency, prefix)
                for prefix in (
                    "affordance_runtime.adapters",
                    "affordance_runtime.benchmarks",
                    "affordance_runtime.coordinator",
                    "affordance_runtime.state_kernel",
                    "affordance_runtime.trace",
                )
            ):
                violations.append((filename, getattr(node, "lineno", 0), dependency))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in STATE_KERNEL_MUTATIONS
        ):
            violations.append((filename, node.lineno, node.func.attr))
    assert violations == []


def test_extracted_collaborators_cannot_reacquire_state_or_trace_authority() -> None:
    violations: list[tuple[str, int, str]] = []
    mutation_debt: set[tuple[str, str]] = set()
    for filename in EXTRACTED_AUTHORITY_FREE_COLLABORATORS:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for dependency in _import_dependencies(node):
                if any(
                    _matches_module(dependency, prefix)
                    for prefix in (
                        "affordance_runtime.coordinator",
                        "affordance_runtime.trace",
                    )
                ):
                    violations.append((filename, getattr(node, "lineno", 0), dependency))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in STATE_KERNEL_MUTATIONS
            ):
                identity = (filename, node.func.attr)
                if identity in EXTRACTED_MUTATION_DEBT:
                    mutation_debt.add(identity)
                else:
                    violations.append((filename, node.lineno, node.func.attr))
    assert violations == []
    assert mutation_debt == EXTRACTED_MUTATION_DEBT


def test_strict_authority_free_collaborators_do_not_import_state_or_benchmarks() -> None:
    violations: list[tuple[str, int, str]] = []
    for filename in STRICT_AUTHORITY_FREE_COLLABORATORS:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for dependency in _import_dependencies(node):
                if any(
                    _matches_module(dependency, prefix)
                    for prefix in FORBIDDEN_STRICT_COLLABORATOR_DEPENDENCIES
                ):
                    violations.append((filename, getattr(node, "lineno", 0), dependency))
    assert violations == []


def test_every_state_kernel_method_is_classified_as_read_or_mutation() -> None:
    tree = ast.parse((SOURCE_ROOT / "state_kernel.py").read_text(encoding="utf-8"))
    state_kernel = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StateKernel"
    )
    public_methods = {
        node.name
        for node in state_kernel.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods == STATE_KERNEL_MUTATIONS | STATE_KERNEL_READS


def test_execution_commit_calls_remain_in_runtime_committers() -> None:
    violations: list[tuple[str, int, str]] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        if relative in ALLOWED_STATE_MUTATION_MODULES or relative == "state_kernel.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in EXECUTION_COMMIT_MUTATIONS
            ):
                violations.append((relative, node.lineno, node.func.attr))
    assert violations == []


def test_non_adapter_benchmark_dependency_debt_cannot_spread() -> None:
    importers: set[str] = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        if relative.startswith("benchmarks/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            _matches_module(dependency, "affordance_runtime.benchmarks")
            for node in ast.walk(tree)
            for dependency in _import_dependencies(node)
        ):
            importers.add(relative)
    assert importers == LEGACY_NON_ADAPTER_BENCHMARK_IMPORTERS
