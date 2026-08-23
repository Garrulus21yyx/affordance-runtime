"""Truthful bounded projection of Runtime-owned task authority."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.contracts import (
    AgentCriterionEvaluationView,
    AgentEvaluatedOutputView,
    AgentMaterialBindingView,
    AgentSuccessCriterionView,
    AgentTaskEvaluationView,
    AgentTaskView,
)
from affordance_runtime.agent.context.projection import (
    project_public_value,
)
from affordance_runtime.agent.context.world_projection import PublicFactView
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.contracts import TaskGoal, criterion_id

_MAX_STRING = 240
_SHA256_REFERENCE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


def project_task(
    task: TaskGoal,
    evaluation: TaskEvaluation | None = None,
    facts: tuple[PublicFactView, ...] = (),
    fact_refs: Mapping[str, str] | None = None,
    target_refs: Mapping[str, str] | None = None,
) -> AgentTaskView:
    if evaluation is not None and evaluation.task_id != task.task_id:
        raise ValueError("task projection evaluation belongs to another task")
    materials = []
    for item in task.material_bindings:
        reference = item.public_reference or (item.digest if _SHA256_REFERENCE.fullmatch(item.digest) else "")
        if reference and _safe_public_reference(reference):
            materials.append(AgentMaterialBindingView(item.name, item.media_type, reference))
    criteria = tuple(
        AgentSuccessCriterionView(criterion_id(item), _project_task_value(item))
        for item in task.success_criteria
    )
    public_inputs, public_input_count = _project_public_inputs(task.inputs)
    fact_refs = fact_refs or {}
    target_refs = target_refs or {}
    evidence_refs = (
        {
            *evaluation.completion_evidence_refs,
            *(ref for item in evaluation.criteria for ref in item.evidence_refs),
            *(ref for item in evaluation.outputs for ref in item.evidence_refs),
        }
        if evaluation is not None
        else set()
    )
    verified_facts = tuple(
        replace(
            item,
            subject_id=target_refs.get(item.subject_id, "task"),
        )
        for item in facts
        if item.fact_ref in fact_refs and fact_refs[item.fact_ref] in evidence_refs
    )
    return AgentTaskView(
        task.task_id,
        task.instruction,
        _strings(task.constraints),
        _strings(task.allowed_effects),
        _strings(task.forbidden_effects),
        _section(criteria, len(task.success_criteria)),
        _strings(task.requested_outputs),
        task.risk_profile,
        public_inputs,
        _section(tuple(materials), len(task.material_bindings)),
        public_input_count,
        public_input_count > len(public_inputs),
        _evaluation_view(evaluation, verified_facts),
    )


def _evaluation_view(
    evaluation: TaskEvaluation | None,
    verified_facts: tuple[PublicFactView, ...],
) -> AgentTaskEvaluationView:
    if evaluation is None:
        return AgentTaskEvaluationView("unknown")
    return AgentTaskEvaluationView(
        str(evaluation.status),
        tuple(
            AgentCriterionEvaluationView(item.criterion_id, str(item.status))
            for item in evaluation.criteria
        ),
        tuple(
            AgentEvaluatedOutputView(item.output_id, project_public_value(item.value))
            for item in evaluation.outputs
        ),
        verified_facts,
    )


def _strings(values: tuple[str, ...]) -> BoundedSection[str]:
    return _section(tuple(values), len(values))


def _section(items: tuple[Any, ...], total_count: int) -> BoundedSection[Any]:
    return BoundedSection(items, total_count, total_count > len(items))


def _project_task_value(value: Any) -> Any:
    return to_json_compatible(value)


def _project_public_inputs(
    value: Mapping[str, object],
) -> tuple[dict[str, object], int]:
    safe_items = tuple(
        (str(key), item)
        for key, item in value.items()
    )
    projected = {
        key: _project_task_value(item)
        for key, item in safe_items
    }
    return projected, len(safe_items)

def _safe_public_reference(value: str) -> bool:
    if len(value) > _MAX_STRING or _SHA256_REFERENCE.fullmatch(value):
        return len(value) <= _MAX_STRING
    normalized = value.casefold()
    return not (
        "://" in normalized
        or normalized.startswith(("/", "~", "file:"))
        or "credential" in normalized
        or "password" in normalized
        or "secret" in normalized
    )
