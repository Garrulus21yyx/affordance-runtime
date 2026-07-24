from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, TypeVar, cast

import pytest
from pydantic import BaseModel, ValidationError

from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage, StructuredModelError
from affordance_runtime.planner_context import AffordanceSummary, PlannerContext
from affordance_runtime.planner_model_orchestrator import (
    PlannerCandidateModel,
    PlannerCandidateRepairPolicy,
    PlannerModelOrchestrator,
    build_initial_candidate_schema,
    build_repair_candidate_schema,
    compatible_target_ids,
    semantic_text_input_constraint,
)
from affordance_runtime.planning import PlannerActionKind, PlannerProposal

T = TypeVar("T", bound=BaseModel)


@dataclass
class SequenceModel:
    responses: tuple[dict[str, Any], ...]
    provider: str = "fixture"
    model: str = "candidate-sequence"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0
    messages: list[tuple[ModelMessage, ...]] = field(default_factory=list)
    output_schemas: list[type[BaseModel]] = field(default_factory=list)

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del config
        self.messages.append(tuple(messages))
        self.output_schemas.append(output_schema)
        payload = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return cast(T, output_schema.model_validate(payload))


@dataclass
class SchemaFailureModel:
    provider: str = "fixture"
    model: str = "schema-failure"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, output_schema, config
        self.calls += 1
        raise StructuredModelError("structured output validation failed")


def _context() -> PlannerContext:
    return PlannerContext(
        task_spec={"objective": "Enter Ada", "operation_class": "reversible_write"},
        active_subgoal="Enter the supplied name",
        observed_text="",
        affordances=(
            AffordanceSummary(
                id="field-1",
                surface="dom",
                role="textbox",
                label="Name",
                action="fill",
                confidence=1.0,
                state={},
            ),
        ),
        permitted_action_kinds=("type_text", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="coordinator_managed",
        remaining_budgets={"steps": 3},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=2,
        snapshot_id="snapshot-1",
    )


def _policy() -> PlannerCandidateRepairPolicy[PlannerCandidateModel]:
    def prebind(candidate: PlannerCandidateModel, context: PlannerContext) -> str:
        del context
        return "" if candidate.target_affordance_id == "field-1" else "proposal_target_required"

    def bind(candidate: PlannerCandidateModel, context: PlannerContext) -> PlannerProposal:
        return PlannerProposal(
            proposal_id="proposal-1",
            based_on_task_revision=context.task_revision,
            based_on_state_version=context.state_version,
            snapshot_id=context.snapshot_id,
            action_kind=candidate.action_kind,
            target_affordance_id=candidate.target_affordance_id,
            parameters=dict(candidate.parameters),
        )

    def repair_constraints(
        context: PlannerContext,
        candidate: PlannerCandidateModel,
        issue: str,
        permitted: list[str],
        targets: dict[str, list[str]],
    ) -> tuple[list[str], dict[str, list[str]]]:
        del context, candidate, issue
        return list(permitted), {key: list(value) for key, value in targets.items()}

    return PlannerCandidateRepairPolicy(
        prebind_issue=prebind,
        bind_candidate=bind,
        context_issue=lambda proposal, context: "",
        repair_constraints=repair_constraints,
        required_slider_direction=lambda candidate, context: "",
        autocomplete_prefix=lambda context: "",
    )


def _run(
    model: SequenceModel | SchemaFailureModel,
    *,
    max_candidate_repairs: int,
    reserve_model_call: Callable[[], None],
) -> PlannerProposal:
    context = _context()
    return asyncio.run(
        PlannerModelOrchestrator().propose(
            model=model,
            config=ModelConfig(prompt_version="fixture-v1"),
            messages=[ModelMessage(role="system", content="fixed"), ModelMessage(role="user", content="{}")],
            context=context,
            candidate_type=PlannerCandidateModel,
            initial_schema=build_initial_candidate_schema(
                PlannerCandidateModel,
                list(context.permitted_action_kinds),
            ),
            repair_permitted=list(context.permitted_action_kinds),
            repair_targets={"type_text": ["field-1"]},
            max_candidate_repairs=max_candidate_repairs,
            reserve_model_call=reserve_model_call,
            policy=_policy(),
        )
    )


def test_orchestrator_returns_a_provider_neutral_structured_candidate() -> None:
    model = SequenceModel(
        ({"action_kind": "type_text", "target_affordance_id": "field-1", "parameters": {"text": "Ada"}},)
    )
    reservations: list[int] = []

    proposal = _run(
        model,
        max_candidate_repairs=2,
        reserve_model_call=lambda: reservations.append(1),
    )

    assert proposal.action_kind == PlannerActionKind.TYPE_TEXT
    assert proposal.target_affordance_id == "field-1"
    assert proposal.parameters == {"text": "Ada"}
    assert model.calls == 1
    assert len(reservations) == 1


def test_relational_rejection_excludes_only_the_rejected_target() -> None:
    context = _context().model_copy(
        update={
            "affordances": (
                *_context().affordances,
                AffordanceSummary(
                    id="field-2",
                    surface="dom",
                    role="textbox",
                    label="Alternate name",
                    action="fill",
                    confidence=1.0,
                    state={},
                ),
            ),
            "recovery_summary": {
                "proposal_rejection": {
                    "code": "target_out_of_scope",
                    "reason_code": "relational_evidence_not_proven",
                    "semantic_target_id": "field-1",
                }
            },
        }
    )

    assert compatible_target_ids(context)["type_text"] == ["field-2"]


def test_value_rejection_keeps_the_control_available() -> None:
    context = _context().model_copy(
        update={
            "recovery_summary": {
                "proposal_rejection": {
                    "code": "target_out_of_scope",
                    "reason_code": "semantic_value_not_authorized",
                    "semantic_target_id": "field-1",
                }
            }
        }
    )

    assert compatible_target_ids(context)["type_text"] == ["field-1"]


def test_repair_schema_cannot_decode_a_relationally_rejected_target() -> None:
    context = _context().model_copy(
        update={
            "affordances": (
                *_context().affordances,
                AffordanceSummary(
                    id="field-2",
                    surface="dom",
                    role="textbox",
                    label="Alternate name",
                    action="fill",
                    confidence=1.0,
                    state={},
                ),
            ),
            "recovery_summary": {
                "proposal_rejection": {
                    "code": "target_out_of_scope",
                    "reason_code": "relational_evidence_not_proven",
                    "semantic_target_id": "field-1",
                }
            },
        }
    )
    targets = compatible_target_ids(context)
    schema = build_repair_candidate_schema(
        PlannerCandidateModel,
        ["type_text"],
        targets,
    )

    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "action_kind": "type_text",
                "target_affordance_id": "field-1",
                "parameters": {"text": "Ada"},
            }
        )
    accepted = schema.model_validate(
        {
            "action_kind": "type_text",
            "target_affordance_id": "field-2",
            "parameters": {"text": "Ada"},
        }
    )
    assert accepted.target_affordance_id == "field-2"


def test_explicit_prefix_binds_only_one_enabled_text_target() -> None:
    context = _context().model_copy(
        update={
            "task_spec": {
                **_context().task_spec,
                "semantic_value_constraints": [
                    {
                        "relation": "prefix",
                        "value": "Com",
                        "target": "item",
                        "source_ref": "request-1",
                    },
                    {
                        "relation": "suffix",
                        "value": "va",
                        "target": "item",
                        "source_ref": "request-1",
                    },
                ],
            }
        }
    )

    constraint = semantic_text_input_constraint(context, compatible_target_ids(context))

    assert constraint is not None
    assert constraint.relation == "prefix"
    assert constraint.target_id == "field-1"
    assert constraint.allowed_text_values == ("Com",)


@pytest.mark.parametrize(
    ("relation", "required_value", "current_value", "satisfied"),
    (
        ("prefix", "Com", "Comoros", True),
        ("prefix", "Com", "Community", True),
        ("prefix", "Com", "Computer", True),
        ("prefix", "Com", "comoros", False),
        ("exact", "Comoros", "Comoros", True),
        ("exact", "Comoros", "Comoros ", False),
    ),
)
def test_current_control_value_retires_only_the_satisfied_input_obligation(
    relation: str,
    required_value: str,
    current_value: str,
    satisfied: bool,
) -> None:
    base = _context()
    context = base.model_copy(
        update={
            "task_spec": {
                **base.task_spec,
                "semantic_value_constraints": [
                    {
                        "relation": relation,
                        "value": required_value,
                        "source_ref": "request-1",
                    }
                ],
            },
            "affordances": (
                base.affordances[0].model_copy(
                    update={"state": {"enabled": True, "control_value": current_value}}
                ),
            ),
        }
    )

    constraint = semantic_text_input_constraint(context, compatible_target_ids(context))

    assert (constraint is None) is satisfied


def test_suffix_only_multiple_values_or_multiple_controls_do_not_authorize_text() -> None:
    suffix = _context().model_copy(
        update={
            "task_spec": {
                **_context().task_spec,
                "semantic_value_constraints": [
                    {
                        "relation": "suffix",
                        "value": "va",
                        "source_ref": "request-1",
                    }
                ],
            }
        }
    )
    multiple_values = suffix.model_copy(
        update={
            "task_spec": {
                **suffix.task_spec,
                "semantic_value_constraints": [
                    {"relation": "prefix", "value": "A", "source_ref": "request-1"},
                    {"relation": "prefix", "value": "B", "source_ref": "request-1"},
                ],
            }
        }
    )
    multiple_controls = suffix.model_copy(
        update={
            "affordances": (
                *suffix.affordances,
                AffordanceSummary(
                    id="field-2",
                    surface="dom",
                    role="textbox",
                    label="Other",
                    action="fill",
                    confidence=1.0,
                    state={},
                ),
            ),
            "task_spec": multiple_values.task_spec,
        }
    )

    assert semantic_text_input_constraint(suffix, compatible_target_ids(suffix)) is None
    assert (
        semantic_text_input_constraint(
            multiple_values,
            compatible_target_ids(multiple_values),
        )
        is None
    )
    assert (
        semantic_text_input_constraint(
            multiple_controls,
            compatible_target_ids(multiple_controls),
        )
        is None
    )


def test_orchestrator_repairs_once_using_a_narrowed_schema_on_the_same_context() -> None:
    model = SequenceModel(
        (
            {"action_kind": "type_text", "parameters": {"text": "Ada"}},
            {"action_kind": "type_text", "target_affordance_id": "field-1", "parameters": {"text": "Ada"}},
        )
    )
    reservations: list[int] = []

    proposal = _run(
        model,
        max_candidate_repairs=1,
        reserve_model_call=lambda: reservations.append(1),
    )

    assert proposal.target_affordance_id == "field-1"
    assert model.calls == 2
    assert len(reservations) == 2
    assert [message.role for message in model.messages[1]] == ["system", "user", "assistant", "user"]
    assert '"validation_error_types": ["proposal_target_required"]' in model.messages[1][-1].content


def test_orchestrator_keeps_action_and_narrows_parameters_during_parameter_repair() -> None:
    model = SequenceModel(
        (
            {
                "action_kind": "type_text",
                "target_affordance_id": "field-1",
                "parameters": {"value": "Ada"},
            },
            {
                "action_kind": "type_text",
                "target_affordance_id": "field-1",
                "parameters": {"text": "Ada"},
            },
        )
    )

    proposal = _run(model, max_candidate_repairs=1, reserve_model_call=lambda: None)

    assert proposal.parameters == {"text": "Ada"}
    assert model.calls == 2
    repair_schema = model.output_schemas[1].model_json_schema()
    assert repair_schema["properties"]["action_kind"]["const"] == "type_text"
    parameter_ref = repair_schema["properties"]["parameters"]["$ref"].split("/")[-1]
    parameter_schema = repair_schema["$defs"][parameter_ref]
    assert parameter_schema["additionalProperties"] is False
    assert parameter_schema["required"] == ["text"]


def test_drag_repair_schema_requires_destination_and_rejects_parameters() -> None:
    schema = build_repair_candidate_schema(
        PlannerCandidateModel,
        ["drag"],
        {"drag": ["source"]},
        drag_destination_ids=("destination",),
    )

    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "action_kind": "drag",
                "target_affordance_id": "source",
                "destination_affordance_id": "destination",
                "parameters": {"destination": "destination"},
            }
        )
    valid = schema.model_validate(
        {
            "action_kind": "drag",
            "target_affordance_id": "source",
            "destination_affordance_id": "destination",
            "parameters": {},
        }
    )
    assert valid.destination_affordance_id == "destination"


def test_select_option_repair_schema_requires_only_semantic_option() -> None:
    schema = build_repair_candidate_schema(
        PlannerCandidateModel,
        ["select_option"],
        {"select_option": ["select-1"]},
    )

    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "action_kind": "select_option",
                "target_affordance_id": "select-1",
                "parameters": {"value": "Ada"},
            }
        )
    valid = schema.model_validate(
        {
            "action_kind": "select_option",
            "target_affordance_id": "select-1",
            "parameters": {"option": "Ada"},
        }
    )
    assert valid.model_dump()["parameters"]["option"] == "Ada"


def test_orchestrator_exhaustion_is_redacted_and_does_not_return_an_invalid_proposal() -> None:
    model = SequenceModel(
        (
            {"action_kind": "type_text", "parameters": {"text": "private-value"}},
        )
    )

    with pytest.raises(StructuredModelError) as exc_info:
        _run(model, max_candidate_repairs=1, reserve_model_call=lambda: None)

    assert str(exc_info.value) == (
        "planner candidate failed semantic validation: proposal_target_required:type_text"
    )
    assert "private-value" not in str(exc_info.value)
    assert model.calls == 2


def test_orchestrator_reserves_every_attempt_and_stops_before_exceeding_call_budget() -> None:
    model = SequenceModel(
        (
            {"action_kind": "type_text", "parameters": {"text": "Ada"}},
            {"action_kind": "type_text", "target_affordance_id": "field-1", "parameters": {"text": "Ada"}},
        )
    )
    reservations = 0

    def reserve() -> None:
        nonlocal reservations
        if reservations >= 1:
            raise StructuredModelError("model call budget exhausted")
        reservations += 1

    with pytest.raises(StructuredModelError, match="model call budget exhausted"):
        _run(model, max_candidate_repairs=2, reserve_model_call=reserve)

    assert reservations == 1
    assert model.calls == 1


def test_orchestrator_propagates_a_redacted_provider_schema_failure_without_repair() -> None:
    model = SchemaFailureModel()
    reservations: list[int] = []

    with pytest.raises(StructuredModelError, match="^structured output validation failed$"):
        _run(
            model,
            max_candidate_repairs=2,
            reserve_model_call=lambda: reservations.append(1),
        )

    assert model.calls == 1
    assert len(reservations) == 1


def test_generalist_candidate_inheritance_preserves_the_provider_schema_fields() -> None:
    from affordance_runtime.generalist_planner import PlannerProposalCandidate

    base_schema = PlannerCandidateModel.model_json_schema()
    public_schema = PlannerProposalCandidate.model_json_schema()
    for schema in (base_schema, public_schema):
        schema.pop("title", None)
        schema.pop("description", None)

    assert public_schema == base_schema
