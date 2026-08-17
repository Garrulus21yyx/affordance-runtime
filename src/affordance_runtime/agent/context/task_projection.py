"""Truthful bounded projection of Runtime-owned task authority."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
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
    _bounded_string,
    _model_private_key,
    project_public_value,
)
from affordance_runtime.agent.context.world_projection import PublicFactView
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.task.contracts import TaskGoal, criterion_id

_MAX_ITEMS = 12
_MAX_DEPTH = 3
_MAX_STRING = 240
_MAX_INSTRUCTION = 1_024
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
    for item in task.material_bindings[:_MAX_ITEMS]:
        reference = item.public_reference or (item.digest if _SHA256_REFERENCE.fullmatch(item.digest) else "")
        if reference and _safe_public_reference(reference):
            materials.append(AgentMaterialBindingView(item.name[:_MAX_STRING], item.media_type[:_MAX_STRING], reference))
    criteria = tuple(
        AgentSuccessCriterionView(criterion_id(item), _project_task_value(item))
        for item in task.success_criteria[:_MAX_ITEMS]
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
            fact_ref=fact_refs[item.fact_ref],
            subject_id=target_refs.get(item.subject_id, "task"),
        )
        for item in facts
        if item.fact_ref in evidence_refs and item.fact_ref in fact_refs
    )
    return AgentTaskView(
        task.task_id,
        _bounded_string(task.instruction, _MAX_INSTRUCTION),
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
    items = tuple(_bounded_string(item, _MAX_STRING) for item in values[:_MAX_ITEMS])
    return _section(items, len(values))


def _section(items: tuple[Any, ...], total_count: int) -> BoundedSection[Any]:
    return BoundedSection(items, total_count, total_count > len(items))


def _project_task_value(value: Any, depth: int = 0) -> Any:
    if isinstance(value, Mapping):
        if depth >= _MAX_DEPTH:
            return "[TRUNCATED]"
        return {
            str(key): _project_task_value(item, depth + 1)
            for key, item in list(value.items())[:_MAX_ITEMS]
            if not _model_private_key(str(key))
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if depth >= _MAX_DEPTH:
            return "[TRUNCATED]"
        return [_project_task_value(item, depth + 1) for item in list(value)[:_MAX_ITEMS]]
    return project_public_value(value, depth)


def _project_public_inputs(value: Mapping[str, object]) -> tuple[dict[str, object], int]:
    safe_items = tuple((str(key), item) for key, item in value.items() if not _model_private_key(str(key)))
    projected = {
        key: _project_task_value(item, 1)
        for key, item in safe_items[:_MAX_ITEMS]
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
