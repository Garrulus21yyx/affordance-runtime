"""Local BrowserGym lifecycle, projection, ActionSpace, and verifier diagnostics."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum

from affordance_runtime.benchmarks.external_breadth.diagnostic_selection import DiagnosticSelection
from affordance_runtime.benchmarks.external_breadth.requirements import TaskReadiness


class BreadthDiagnosticDisposition(StrEnum):
    ENVIRONMENT_LIFECYCLE_GAP = "environment_lifecycle_gap"
    PROJECTION_GAP = "projection_gap"
    OBSERVATION_SEMANTICS_GAP = "observation_semantics_gap"
    ACTION_SPACE_GAP = "action_space_gap"
    EVALUATION_GAP = "evaluation_gap"
    POLICY_OR_REASONING_CANDIDATE = "policy_or_reasoning_candidate"
    PROVIDER_CAPACITY = "provider_capacity"
    REQUIREMENT_UNSUPPORTED = "requirement_unsupported"
    REQUIREMENT_UNASSESSED = "requirement_unassessed"
    UNRESOLVED = "unresolved"


def diagnostic_disposition(
    readiness: TaskReadiness,
    lifecycle_success: bool,
    projection_success: bool,
    recognized_target_count: int,
    action_option_count: int,
) -> BreadthDiagnosticDisposition:
    if readiness is TaskReadiness.DECLARED_UNSUPPORTED:
        return BreadthDiagnosticDisposition.REQUIREMENT_UNSUPPORTED
    if readiness is TaskReadiness.UNASSESSED:
        return BreadthDiagnosticDisposition.REQUIREMENT_UNASSESSED
    if not lifecycle_success:
        return BreadthDiagnosticDisposition.ENVIRONMENT_LIFECYCLE_GAP
    if not projection_success:
        return BreadthDiagnosticDisposition.PROJECTION_GAP
    if recognized_target_count and not action_option_count:
        return BreadthDiagnosticDisposition.ACTION_SPACE_GAP
    return BreadthDiagnosticDisposition.POLICY_OR_REASONING_CANDIDATE


async def probe_case(
    selection: DiagnosticSelection,
    readiness: TaskReadiness,
    seed: int,
    admitted_task_ids: frozenset[str],
) -> dict[str, object]:
    from affordance_runtime.actions import ActionSpaceBuilder
    from affordance_runtime.benchmarks.external_smoke.case_environment import open_browsergym_case

    task_id = f"browsergym/miniwob.{selection.task_family_label}"
    environment = None
    stage = "environment_reset"
    try:
        environment, task = open_browsergym_case(
            task_id, seed, max_turns=10, admitted_task_ids=admitted_task_ids,
        )
        stage = "initial_observation"
        acquisition = await environment.reset(task)
        if acquisition.observation is None:
            raise RuntimeError("initial typed acquisition failed")
        world = acquisition.observation
        raw_metrics = environment.diagnostic_snapshot().as_metrics()
        stage = "action_space"
        action_space = ActionSpaceBuilder().build(task, world)
        stage = "task_evaluation"
        verifier = environment.current_result(task_id)
        metrics = _projected_metrics(world, action_space)
        recognized = raw_metrics["recognized_target_count"]
        assert type(recognized) is int
        disposition = diagnostic_disposition(
            readiness, True, True, recognized, len(action_space.options),
        )
        stage = "cleanup"
        await environment.close()
        environment = None
        return _success_payload(selection, readiness, raw_metrics, metrics, verifier, disposition)
    except Exception as exc:
        return {
            "case_id": selection.case_id,
            "task_family_label": selection.task_family_label,
            "original_outcome": selection.original_outcome,
            "readiness": readiness.value,
            "lifecycle_success": False,
            "projection_success": stage not in {"environment_reset", "observation_projection"},
            "failure_stage": stage,
            "exception_class": type(exc).__name__,
            "disposition": (
                BreadthDiagnosticDisposition.PROJECTION_GAP.value
                if stage == "observation_projection"
                else BreadthDiagnosticDisposition.EVALUATION_GAP.value
                if stage == "task_evaluation"
                else BreadthDiagnosticDisposition.ENVIRONMENT_LIFECYCLE_GAP.value
            ),
        }
    finally:
        if environment is not None:
            try:
                await environment.close()
            except Exception:
                pass


def _projected_metrics(world, action_space) -> dict[str, object]:
    labels = [item.label for item in world.targets]
    actions = Counter(item.semantic_action for item in action_space.options)
    roles = Counter(item.role for item in world.targets)
    select_domains = []
    for option in action_space.options:
        value = option.parameter_schema.get("properties", {}).get("value", {})
        if option.semantic_action == "select" and isinstance(value, dict):
            select_domains.append(len(value.get("enum", ())))
    return {
        "projected_target_count": len(world.targets),
        "projected_fact_count": len(world.facts),
        "action_binding_count": len(world.bindings),
        "action_option_count": len(action_space.options),
        "semantic_action_counts": dict(sorted(actions.items())),
        "projected_role_distribution": dict(sorted(roles.items())),
        "blank_label_count": sum(not value.strip() for value in labels),
        "duplicate_label_count": len(labels) - len(set(labels)),
        "select_option_counts": select_domains,
        "projection_coverage": {key: str(value) for key, value in world.coverage.items()},
    }


def _success_payload(selection, readiness, raw, projected, verifier, disposition):
    return {
        "case_id": selection.case_id,
        "task_family_label": selection.task_family_label,
        "original_outcome": selection.original_outcome,
        "readiness": readiness.value,
        "lifecycle_success": True,
        "projection_success": True,
        "failure_stage": "",
        "exception_class": "",
        **raw,
        **projected,
        "verifier_initial_status": str(verifier.status),
        "disposition": disposition.value,
    }


def _typed(value: object) -> str:
    return str(value.get("value", "")) if isinstance(value, dict) else ""
