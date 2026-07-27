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
    "coordinator.py": 3_473,
    "compatibility_planner_algorithms.py": 2_042,
    "task_planning.py": 1_642,
}

CONTROL_METHOD_LINE_CEILINGS = {
    ("coordinator.py", "RunCoordinator", "run_sync"): 2_039,
    ("generalist_planner.py", "GeneralistLMPlanner", "propose"): 222,
    ("intent_compiler.py", "LLMIntentCompiler", "compile"): 253,
    ("task_planning.py", "TaskPlanValidator", "validate"): 239,
}

RUN_COORDINATOR_METHOD_CEILING = 26

NEUTRAL_CONTRACT_MODULES = (
    "approval_contracts.py",
    "planning_contracts.py",
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
    "task_plan_flow.py",
    "task_plan_lifecycle.py",
)

FORBIDDEN_NEUTRAL_DEPENDENCIES = (
    "affordance_runtime.adapters",
    "affordance_runtime.benchmarks",
    "affordance_runtime.cli",
    "affordance_runtime.coordinator",
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
    governance = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()

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
    assert "p1 immutable planner input" in current_plan
    assert "p2 semantic fallback owner extraction" in current_plan
    assert "p3 intent semantic normalizer" in current_plan
    assert "p4 protected breadth continuation" in current_plan
    assert "module-level semantic owner gate" in governance
    assert "strict planner module may not add new task-language parser logic" in governance
    assert "typed resolver or constraint owner" in governance
    assert "current vertical lane is protected cross-family / pr breadth confirmation" in governance
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

    assert "pr_breadth_latest:" in status
    assert "status: failed" in status
    assert "expected: 12" in status
    assert "observed: 12" in status
    assert "passed: 0" in status
    assert "official_score_claimed: false" in status
    assert "root_owner_next: intent / planning" in status
    assert "protected cross-family / pr breadth failed at `d66760f`" in current_plan
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
