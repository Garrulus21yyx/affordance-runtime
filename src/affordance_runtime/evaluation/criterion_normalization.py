"""Normalize legacy criterion mappings once at the Runtime boundary."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.evaluation.criterion_contracts import CriterionAdjudicator, NormalizedCriterionSpec
from affordance_runtime.task.contracts import TaskGoal, criterion_id

_COMMON = {
    "id", "criterion_id", "adjudicator", "kind", "subject_id", "target_id",
    "predicate", "value", "expected_value", "state", "state_key", "rubric",
    "evidence_scope_target_ids", "required_assurance", "output_id",
}
_KINDS = {"fact_equals", "target_state_equals", "artifact_exists", "user_acceptance", "semantic_rubric", "hybrid"}


def normalize_task_criteria(task: TaskGoal) -> tuple[NormalizedCriterionSpec, ...]:
    normalized = tuple(normalize_criterion(item) for item in task.success_criteria)
    identities = tuple(item.criterion_id for item in normalized)
    if any(not item.strip() for item in identities) or len(set(identities)) != len(identities):
        raise ValueError("normalized criterion IDs must be nonblank and unique")
    return normalized


def normalize_criterion(raw: Mapping[str, object]) -> NormalizedCriterionSpec:
    legacy_state_keys = set(raw) - _COMMON if isinstance(raw, Mapping) else set()
    if not isinstance(raw, Mapping) or (legacy_state_keys and not ("target_id" in raw and len(legacy_state_keys) == 1)):
        raise ValueError("criterion shape is unsupported")
    kind = _kind(raw)
    adjudicator = _adjudicator(raw, kind)
    subject_id = _optional_string(raw.get("subject_id") or raw.get("target_id"), "criterion subject")
    predicate = _optional_string(raw.get("predicate"), "criterion predicate")
    expected, state_key = _mechanical_fields(raw, kind, legacy_state_keys)
    rubric = _optional_string(raw.get("rubric"), "criterion rubric", max_length=2_000)
    scope = _string_tuple(raw.get("evidence_scope_target_ids", ()))
    required_assurance = _optional_string(raw.get("required_assurance"), "required assurance", max_length=80)
    output_id = _optional_string(raw.get("output_id"), "criterion output")
    _validate_shape(kind, adjudicator, subject_id, predicate, state_key, rubric, scope, output_id)
    return NormalizedCriterionSpec(
        criterion_id(raw), adjudicator, kind, subject_id, predicate, expected,
        state_key, rubric, scope, required_assurance, output_id,
    )


def _kind(raw: Mapping[str, object]) -> str:
    explicit = raw.get("kind")
    if explicit is not None:
        if not isinstance(explicit, str) or explicit not in _KINDS:
            raise ValueError("criterion kind is unsupported")
        return explicit
    if "state" in raw:
        return "target_state_equals"
    if "target_id" in raw and set(raw) - _COMMON:
        return "target_state_equals"
    if "predicate" in raw:
        return "fact_equals"
    raise ValueError("criterion kind cannot be inferred")


def _adjudicator(raw: Mapping[str, object], kind: str) -> CriterionAdjudicator:
    explicit = raw.get("adjudicator")
    if explicit is None:
        if "rubric" in raw or kind in {"semantic_rubric", "user_acceptance", "hybrid"}:
            raise ValueError("semantic, hybrid, and user criteria require an explicit adjudicator")
        return CriterionAdjudicator.MECHANICAL
    try:
        return CriterionAdjudicator(str(explicit))
    except ValueError as exc:
        raise ValueError("criterion adjudicator is unsupported") from exc


def _mechanical_fields(raw: Mapping[str, object], kind: str, legacy_state_keys: set[str]) -> tuple[object, str]:
    if kind == "target_state_equals" and legacy_state_keys:
        state_key = next(iter(legacy_state_keys))
        return raw[state_key], state_key
    if kind == "target_state_equals" and "state" in raw:
        state = raw["state"]
        if not isinstance(state, Mapping) or len(state) != 1:
            raise ValueError("target state criterion requires exactly one state field")
        state_key, expected = next(iter(state.items()))
        if not isinstance(state_key, str) or not state_key.strip():
            raise ValueError("target state key is invalid")
        return expected, state_key
    state_key = _optional_string(raw.get("state_key"), "target state key")
    if kind in {"fact_equals", "target_state_equals", "hybrid"}:
        if "expected_value" in raw:
            return raw["expected_value"], state_key
        if "value" in raw:
            return raw["value"], state_key
        raise ValueError("mechanical criterion requires an expected value")
    return None, state_key


def _validate_shape(kind, adjudicator, subject, predicate, state_key, rubric, scope, output_id) -> None:
    if kind == "fact_equals" and (not predicate or adjudicator != CriterionAdjudicator.MECHANICAL):
        raise ValueError("fact_equals requires a mechanical predicate")
    if kind == "target_state_equals" and (not subject or not state_key or adjudicator != CriterionAdjudicator.MECHANICAL):
        raise ValueError("target_state_equals requires mechanical target and state key")
    if kind == "artifact_exists" and (not output_id or adjudicator != CriterionAdjudicator.MECHANICAL):
        raise ValueError("artifact_exists requires a mechanical output ID")
    if kind == "semantic_rubric" and (adjudicator != CriterionAdjudicator.SEMANTIC or not rubric or not scope):
        raise ValueError("semantic rubric requires explicit semantic scope")
    if kind == "user_acceptance" and adjudicator != CriterionAdjudicator.USER_ACCEPTANCE:
        raise ValueError("user acceptance requires its explicit adjudicator")
    if kind == "hybrid" and (adjudicator != CriterionAdjudicator.HYBRID or not rubric or not scope or not predicate):
        raise ValueError("hybrid criterion requires mechanical and semantic components")


def _optional_string(value: object, label: str, *, max_length: int = 240) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{label} is invalid")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple | list) or any(not isinstance(item, str) for item in value):
        raise ValueError("criterion evidence scope must be a string list")
    return tuple(value)
