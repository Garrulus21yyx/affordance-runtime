import pytest
from pydantic import ValidationError

from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.task_intake import (
    AmbiguityRisk,
    CompilationPolicy,
    CompilationStatus,
    FieldProvenance,
    IntentAmbiguity,
    IntentDraft,
    IntentDraftValidator,
    IntentEntity,
    OperationClass,
    RequestedEffect,
    UserRequest,
)


def _request() -> UserRequest:
    return UserRequest(request_id="request-1", raw_text="Update the theme to dark")


def _draft(**changes: object) -> IntentDraft:
    values = {
        "objective": "Set the theme to dark",
        "requested_effects": (
            RequestedEffect(
                operation_class=OperationClass.REVERSIBLE_WRITE,
                target="theme",
                capability="settings.write",
                source_ref="request-1:0-24",
            ),
        ),
        "candidate_success_criteria": ("theme is dark",),
        "candidate_evidence_requirements": ("settings API confirms dark",),
        "source_map": (FieldProvenance(field="objective", source_ref="request-1:0-24"),),
    }
    values.update(changes)
    return IntentDraft(**values)


def test_ready_compilation_creates_immutable_versioned_task_spec_without_granting_capability() -> None:
    entity = IntentEntity(name="theme", value="dark", source_ref="request-1:20-24")
    result = IntentDraftValidator().compile(
        _request(),
        _draft(entities=(entity,)),
        revision=2,
    )

    assert result.status == CompilationStatus.READY
    assert result.task_spec is not None
    assert result.task_spec.revision == 2
    assert result.task_spec.operation_class == OperationClass.REVERSIBLE_WRITE
    assert result.task_spec.requested_capabilities == ("settings.write",)
    assert result.task_spec.entities == (entity,)
    assert result.task_spec.evidence_requirements == ("settings API confirms dark",)
    assert "granted" not in result.task_spec.model_dump()
    with pytest.raises(ValidationError):
        result.task_spec.revision = 3  # type: ignore[misc]


def test_blocking_or_high_risk_ambiguity_stops_before_task_spec() -> None:
    draft = _draft(
        ambiguities=(
            IntentAmbiguity(
                field="recipient",
                reason="two recipients are referenced",
                blocking=False,
                risk=AmbiguityRisk.HIGH,
            ),
        )
    )

    result = IntentDraftValidator().compile(_request(), draft)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None
    assert result.issues[0].code == "blocking_ambiguity"


def test_blocking_ambiguity_takes_precedence_over_missing_derived_success_criterion() -> None:
    draft = _draft(
        candidate_success_criteria=(),
        ambiguities=(
            IntentAmbiguity(
                field="recipient",
                reason="recipient is missing",
                blocking=True,
                risk=AmbiguityRisk.HIGH,
            ),
        ),
    )

    result = IntentDraftValidator().compile(_request(), draft)

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.task_spec is None


def test_policy_intersection_rejects_denied_capability_and_forbidden_effect() -> None:
    draft = _draft(candidate_forbidden_effects=("theme",))
    validator = IntentDraftValidator(
        CompilationPolicy(
            allowed_requested_capabilities=frozenset({"settings.read"}),
            denied_capabilities=frozenset({"settings.write"}),
        )
    )

    result = validator.compile(_request(), draft)

    assert result.status == CompilationStatus.POLICY_CONFLICT
    assert {issue.code for issue in result.issues} == {
        "capability_denied",
        "capability_not_allowed",
        "forbidden_effect",
    }


def test_missing_required_semantics_are_unsupported() -> None:
    result = IntentDraftValidator().compile(_request(), IntentDraft())

    assert result.status == CompilationStatus.UNSUPPORTED
    assert {item.code for item in result.issues} == {
        "missing_objective",
        "missing_effect",
        "missing_success_criteria",
    }


def test_taskspec_envelope_compatibility_and_revision_identity() -> None:
    first = IntentDraftValidator().compile(_request(), _draft(), revision=1).task_spec
    second = IntentDraftValidator().compile(_request(), _draft(), revision=2).task_spec
    assert first is not None and second is not None

    envelope = TaskEnvelope(task_spec=second)

    assert envelope.task_id == "request-1"
    assert envelope.goal == "Set the theme to dark"
    assert envelope.target == "theme"
    assert first.identity != second.identity
    with pytest.raises(ValueError, match="does not match"):
        TaskEnvelope(task_id="other", task_spec=second)
