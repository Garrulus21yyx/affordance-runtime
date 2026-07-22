from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, TypeVar, cast

import pytest
from pydantic import BaseModel

from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage, StructuredModelError
from affordance_runtime.planner_context import AffordanceSummary, PlannerContext
from affordance_runtime.planner_model_orchestrator import (
    PlannerCandidateModel,
    PlannerCandidateRepairPolicy,
    PlannerModelOrchestrator,
    build_initial_candidate_schema,
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

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del output_schema, config
        self.messages.append(tuple(messages))
        payload = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return cast(T, PlannerCandidateModel.model_validate(payload))


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
