from __future__ import annotations

from dataclasses import replace

import pytest
from test_destination_contract import _option

from affordance_runtime.agent.control_feedback import (
    ContractViolationSnapshot,
    ControlFeedback,
    ControlFeedbackKind,
    ControlFeedbackSource,
    NextDecisionDisposition,
    RecoveryConstraints,
    RelatedDecisionSnapshot,
)
from affordance_runtime.world import ActionSpace, ActionSpaceBuilder
from affordance_runtime.world.admission_issue import AdmissionIssueCode

DIGEST = "a" * 64


def _value_option(schema, *, semantic_action: str = "set_value"):
    return replace(
        _option(),
        semantic_action=semantic_action,
        parameter_schema=schema,
        schema_digest="schema:value",
        destination_required=False,
        eligible_destination_ids=(),
        verification_contract_digest="",
    )


def _feedback(**changes) -> ControlFeedback:
    values = {
        "kind": ControlFeedbackKind.REPAIRABLE_REJECTION,
        "code": "invalid_action_parameters",
        "source": ControlFeedbackSource.ACTION_ADMISSION,
        "next_decision_disposition": NextDecisionDisposition.CORRECT_OR_REPLAN,
        "strategy_transition_required": False,
        "public_subject_id": "target:public",
        "public_field_paths": ("parameters",),
        "scope_digest": DIGEST,
        "issue_digest": "b" * 64,
        "related_decision": RelatedDecisionSnapshot("select_action", "action:1"),
        "violation": ContractViolationSnapshot(
            "current_action_space",
            "invalid_action_parameters",
            ("parameters",),
            {"type": "object"},
            {"type": "object"},
        ),
        "recovery": RecoveryConstraints(
            must_change_fields=("parameters",), retry_allowed=True,
        ),
    }
    values.update(changes)
    return ControlFeedback(**values)


def test_control_feedback_closed_matrix_and_canonical_paths() -> None:
    feedback = _feedback(public_field_paths=("parameters", "action_id", "parameters"))

    assert feedback.public_field_paths == ("action_id", "parameters")
    with pytest.raises(ValueError, match="matrix"):
        _feedback(source=ControlFeedbackSource.ACTION_PAGE)
    with pytest.raises(ValueError, match="matrix"):
        _feedback(strategy_transition_required=True)
    with pytest.raises(ValueError, match="matrix"):
        _feedback(
            kind=ControlFeedbackKind.NO_INFORMATION_GAIN,
            source=ControlFeedbackSource.ACTION_PAGE,
            next_decision_disposition=NextDecisionDisposition.CHANGE_STRATEGY,
            strategy_transition_required=True,
            related_decision=None,
            violation=None,
            recovery=RecoveryConstraints(strategy_change_required=True),
        )


@pytest.mark.parametrize(
    "path",
    ("selector", "parameters[0]", "native_value", "route", "credential"),
)
def test_control_feedback_rejects_private_or_indexed_paths(path: str) -> None:
    with pytest.raises(ValueError, match="public"):
        _feedback(public_field_paths=(path,))


def test_strategy_feedback_does_not_require_request_or_result_digest() -> None:
    feedback = _feedback(
        kind=ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED,
        code="already_satisfied_change_strategy",
        source=ControlFeedbackSource.PROGRESS_EVENT,
        next_decision_disposition=NextDecisionDisposition.CHANGE_STRATEGY,
        strategy_transition_required=True,
        public_field_paths=(),
    )

    assert not feedback.consumes_issue_budget


@pytest.mark.parametrize(
    "parameters",
    (
        {},
        {"value": True},
        {"value": "outside-enum"},
        {"value": -1},
        {"value": 101},
        {"unknown": "x"},
        {"selector": "#private"},
    ),
)
def test_typed_action_admission_rejects_parameter_shapes_without_values(parameters) -> None:
    schema = {
        "type": "object",
        "properties": {
            "value": {"type": "number", "minimum": 0, "maximum": 100},
        },
        "required": ["value"],
        "additionalProperties": False,
    }
    option = _value_option(schema)

    result = ActionSpaceBuilder().try_admit(option, parameters)

    assert result.admitted is None
    assert result.issue is not None
    assert result.issue.code is AdmissionIssueCode.INVALID_ACTION_PARAMETERS
    assert result.issue.public_field_paths in {
        ("parameters",),
        ("parameters.value",),
        ("parameters.unknown",),
    }
    assert "outside-enum" not in repr(result.issue)
    assert "#private" not in repr(result.issue)


def test_typed_action_admission_preserves_valid_values_and_raising_compatibility() -> None:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "number", "minimum": 0, "maximum": 100}},
        "required": ["value"],
        "additionalProperties": False,
    }
    option = _value_option(schema)
    builder = ActionSpaceBuilder()

    assert builder.try_admit(option, {"value": 50}).admitted is not None
    with pytest.raises(ValueError):
        builder.admit(option, {"value": 101})


def test_action_space_owner_produces_typed_unknown_action_issue() -> None:
    result = ActionSpaceBuilder().try_admit_selection(
        ActionSpace("observation:public", ()),
        "not-offered",
        {},
    )

    assert result.issue is not None
    assert result.issue.code is AdmissionIssueCode.ACTION_OUTSIDE_ACTION_SPACE
    assert result.issue.public_field_paths == ("action_id",)


def test_typed_action_admission_enum_mismatch_is_one_public_issue() -> None:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "enum": ["public-a", "public-b"]}},
        "required": ["value"],
        "additionalProperties": False,
    }
    option = _value_option(schema, semantic_action="select_option")

    result = ActionSpaceBuilder().try_admit(
        option, {"value": "not-offered"},
    )

    assert result.issue is not None
    assert result.issue.code is AdmissionIssueCode.INVALID_ACTION_PARAMETERS
    assert "not-offered" not in repr(result.issue)
