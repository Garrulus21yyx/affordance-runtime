from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.mission import (
    AcceptedFact,
    AuditorRoleRequest,
    EvidenceBundle,
    EvidenceRequirement,
    ManagerRecoveryView,
    ManagerRequestMode,
    ManagerRoleRequest,
    MissionState,
    RecoveryKind,
    RecoverySignal,
    SubtaskContract,
    SubtaskOutcomeKind,
)
from affordance_runtime.mission.environment_projection import project_mission_environment
from affordance_runtime.model.mission_roles import (
    INITIAL_MANAGER_SCHEMA_VERSION,
    REVIEW_MANAGER_SCHEMA_VERSION,
    InitialManagerDecisionModel,
    ModelBackedMissionAuditor,
    ModelBackedMissionManager,
    ReviewManagerDecisionModel,
    _auditor_messages,
    _lower_manager_decision,
    _manager_messages,
)
from affordance_runtime.model.pydantic_ai_role_invoker import PydanticAIRoleInvoker
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import SemanticTarget, StateFact
from tests.support.world import fused_world


def _request() -> ManagerRoleRequest:
    return ManagerRoleRequest(
        ManagerRequestMode.INITIAL_PLAN,
        TaskGoal("task:manager-role", "Obtain one observable record."),
        MissionState.empty(),
        remaining_rounds=3,
    )


def _review_request() -> ManagerRoleRequest:
    task = TaskGoal("task:manager-review-schema", "Review one bounded result.")
    world = fused_world(
        "source:review-schema",
        (SemanticTarget("target:review-schema", "text", "Result"),),
    )
    subtask = SubtaskContract(
        "Obtain one result", "One result is visible", "Provides the requested result"
    )
    return ManagerRoleRequest(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        task,
        MissionState.empty(),
        last_typed_exit="outcome_proposed",
        recovery=ManagerRecoveryView(
            "outcome_proposed",
            True,
            subtask,
            outcome_proposal="Measured result is 17 units.",
        ),
        active_subtask=subtask,
        review_world=world,
        evidence_bundle=EvidenceBundle.from_world(world),
    )


def _decision() -> dict[str, object]:
    return {
        "route": "execute_subtask",
        "subtask": {
            "objective": "Obtain the requested record",
            "done_when": "One fresh result panel contains the requested record",
            "task_link": "Provides the user's requested observable record",
            "episode_turn_budget": 6,
        },
    }


@dataclass
class _RoleModel:
    responses: list[dict[str, object] | Exception]
    calls: int = 0
    settings: list[object] = field(default_factory=list)
    output_tools: list[tuple[str, ...]] = field(default_factory=list)

    def invoker(self, *, thinking: bool = True) -> PydanticAIRoleInvoker:
        async def respond(_messages, info: AgentInfo) -> ModelResponse:
            self.calls += 1
            self.settings.append(info.model_settings)
            self.output_tools.append(tuple(tool.name for tool in info.output_tools))
            scripted = self.responses.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            return ModelResponse(parts=[ToolCallPart(
                info.output_tools[0].name,
                scripted,
                tool_call_id=f"role-call:{self.calls}",
            )], provider_response_id=f"role-response:{self.calls}")

        return PydanticAIRoleInvoker(
            FunctionModel(respond, model_name="role-fixture"),
            "fixture",
            "role-fixture",
            "fixture.invalid",
            thinking,
            0,
        )


def test_compact_manager_decision_is_accepted_without_truncation() -> None:
    model = _RoleModel([_decision()])
    manager = ModelBackedMissionManager(model.invoker())

    result = asyncio.run(manager.decide(_request()))

    assert result.failure is None
    assert result.output is not None
    assert result.output.assessment.value == "not_applicable"
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "accepted"
    assert result.attempts[0].max_output_tokens == 2048
    assert result.attempts[0].schema_name == "InitialManagerDecisionModel"
    assert result.attempts[0].schema_version == INITIAL_MANAGER_SCHEMA_VERSION
    assert result.attempts[0].role == "manager"
    assert result.attempts[0].mode == "initial_plan"
    assert result.attempts[0].thinking_requested == "disabled"
    assert result.attempts[0].thinking_effective == "disabled"
    assert model.output_tools == [("manager_initial_plan_output",)]
    assert model.settings[0]["temperature"] == 0.0
    assert model.settings[0]["max_tokens"] == 2048


def test_manager_invalid_tool_arguments_receive_one_pydantic_output_retry() -> None:
    model = _RoleModel([{"route": "execute_subtask"}, _decision()])
    manager = ModelBackedMissionManager(model.invoker())

    result = asyncio.run(manager.decide(_request()))

    assert result.failure is None
    assert result.output is not None
    assert tuple(item.phase for item in result.attempts) == (
        "manager_initial",
        "manager_output_retry",
    )
    first, repair = result.attempts
    assert first.max_output_tokens == 2048
    assert first.transcript is not None
    assert repair.status == "accepted"
    assert repair.schema_name == "InitialManagerDecisionModel"
    assert repair.schema_version == INITIAL_MANAGER_SCHEMA_VERSION
    assert repair.mode == "initial_plan"
    assert repair.transcript is not None
    assert model.calls == 2
    assert model.output_tools == [
        ("manager_initial_plan_output",),
        ("manager_initial_plan_output",),
    ]
    assert result.repair_diagnostics == ({
        "kind": "structured_output_repair",
        "phase": "manager_output_retry",
        "repair_of_attempt": 1,
        "attempt": 2,
        "role": "manager",
        "mode": "initial_plan",
        "schema_version": INITIAL_MANAGER_SCHEMA_VERSION,
    },)


def test_provider_without_thinking_control_receives_no_invented_manager_parameter() -> None:
    model = _RoleModel([_decision()])

    result = asyncio.run(ModelBackedMissionManager(model.invoker(thinking=False)).decide(_request()))

    assert result.failure is None
    assert "thinking" not in model.settings[0]
    assert result.attempts[0].thinking_requested == "provider_default"
    assert result.attempts[0].thinking_effective == "provider_default"


def test_manager_thinking_override_does_not_change_auditor_configuration() -> None:
    review = _review_request()
    assert review.active_subtask is not None
    assert review.review_world is not None
    assert review.evidence_bundle is not None
    audit_request = AuditorRoleRequest.from_authorities(
        review.original_task,
        review.active_subtask,
        review.mission_state,
        review.review_world,
        (),
        "outcome_proposed",
        (),
        review.evidence_bundle,
    )
    model = _RoleModel([{
        "assessment": "unknown",
        "reason": "No cited evidence.",
    }])

    result = asyncio.run(ModelBackedMissionAuditor(model.invoker()).audit(audit_request))

    assert result.failure is None
    assert "thinking" not in model.settings[0]
    assert result.attempts[0].thinking_requested == "provider_default"


def test_initial_rejects_review_only_fields_before_lowering() -> None:
    for field_name, value in (
        ("assessment", "not_applicable"),
        ("evidence_refs", ("F1",)),
        ("working_outcomes", ()),
        ("working_facts", ()),
        ("invalidate_fact_keys", ("old_fact",)),
        ("final_response", {"answer": "42"}),
        ("final_response_evidence_refs", ("F1",)),
    ):
        payload = _decision() | {field_name: value}
        try:
            InitialManagerDecisionModel.model_validate(payload)
        except Exception:
            continue
        raise AssertionError(f"initial schema accepted review-only field {field_name}")


def test_review_schema_forbids_not_applicable() -> None:
    try:
        ReviewManagerDecisionModel.model_validate({
            "assessment": "not_applicable",
            "route": "blocked",
        })
    except Exception:
        return
    raise AssertionError("review schema accepted not_applicable")


def test_review_initial_and_retry_keep_review_schema_and_mode() -> None:
    model = _RoleModel([
        {"assessment": "invalid", "route": "blocked"},
        {"assessment": "unknown", "route": "blocked"},
    ])

    result = asyncio.run(ModelBackedMissionManager(model.invoker()).decide(_review_request()))

    assert result.failure is None
    assert tuple(item.schema_name for item in result.attempts) == (
        "ReviewManagerDecisionModel",
        "ReviewManagerDecisionModel",
    )
    assert all(
        item.schema_version == REVIEW_MANAGER_SCHEMA_VERSION
        for item in result.attempts
    )
    assert all(item.mode == "review_and_route" for item in result.attempts)


def test_deliberate_subtask_replan_has_one_distinct_bounded_role_trigger() -> None:
    request = _review_request()
    assert request.recovery is not None
    recovery = replace(
        request.recovery,
        recovery_signal=RecoverySignal(
            RecoveryKind.SUBTASK_MISALIGNED,
            "subtask:rejected",
            {"reason": "The advisory subtask does not advance TaskGoal."},
            prohibited_immediate_repeat="subtask:rejected",
            recovery_attempt=2,
        ),
    )
    model = _RoleModel([{"assessment": "unsatisfied", "route": "blocked"}])

    result = asyncio.run(
        ModelBackedMissionManager(model.invoker()).decide(
            replace(request, recovery=recovery)
        )
    )

    assert result.failure is None
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.trigger == "subtask_misaligned_deliberate_replan"
    assert attempt.max_output_tokens == 2048


def test_two_invalid_manager_outputs_return_typed_schema_failure() -> None:
    model = _RoleModel([
        {"route": "execute_subtask"},
        {"route": "execute_subtask"},
    ])

    result = asyncio.run(ModelBackedMissionManager(model.invoker()).decide(_request()))

    assert result.output is None
    assert result.failure is not None
    assert result.failure.kind.value == "schema_error"
    assert model.calls == 2
    assert tuple(item.status for item in result.attempts) == (
        "schema_error",
        "schema_error",
    )


def test_retryable_provider_failure_and_recovery_are_both_retained() -> None:
    model = _RoleModel([ModelHTTPError(503, "role-fixture"), _decision()])

    result = asyncio.run(ModelBackedMissionManager(model.invoker()).decide(_request()))

    assert result.failure is None
    assert tuple(item.phase for item in result.attempts) == (
        "manager_initial",
        "manager_provider_retry",
    )
    assert tuple(item.status for item in result.attempts) == ("failed", "accepted")
    assert result.attempts[0].exception_class == "ModelHTTPError"
    assert result.attempts[1].trigger == "provider_retry"
    assert result.attempts[0].transcript["llm.input_messages"]
    assert result.attempts[0].transcript["llm.output_messages"] == []
    assert result.attempts[1].transcript["llm.output_messages"]
    assert result.metadata.transient_retry_count == 1
    assert result.metadata.rate_limit_retry_count == 0


def test_initial_json_schema_has_no_review_or_final_fields() -> None:
    properties = InitialManagerDecisionModel.model_json_schema()["properties"]

    assert set(properties) == {"route", "subtask", "question", "reason"}


def test_manager_review_receives_pinned_fact_as_fresh_review_evidence_ref() -> None:
    task = TaskGoal("task:manager-review", "Compare one measured value.")
    old_target = SemanticTarget("target:old", "text", "Measured", {"value": "33 units"})
    old_world = fused_world(
        "source:old",
        (old_target,),
        (StateFact("fact:old:value", old_target.target_id, "value", "33 units", "source:old"),),
    )
    record = next(item for item in EvidenceBundle.from_world(old_world).evidence_records if item.value == "33 units")
    pinned = WorkingFact("measured_value", record, 3, "compare after navigation")
    new_world = fused_world(
        "source:new",
        (SemanticTarget("target:new", "text", "Comparison page"),),
    )
    bundle = EvidenceBundle.from_world(new_world, (pinned,))
    subtask = SubtaskContract(
        "Measure one value",
        "One evidence packet is available",
        "Provides the requested measured value",
        SubtaskOutcomeKind.EVIDENCE_PACKET,
        required_evidence=(EvidenceRequirement("measured_value", "exact measured value"),),
    )
    request = ManagerRoleRequest(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        task,
        MissionState.empty(),
        last_typed_exit="outcome_proposed",
        recovery=ManagerRecoveryView(
            "outcome_proposed",
            True,
            subtask,
            outcome_proposal="Measured result is 17 units.",
        ),
        active_subtask=subtask,
        review_world=new_world,
        evidence_bundle=bundle,
        allowed_evidence_refs=(record.evidence_ref,),
        episode_working_facts=(pinned,),
    )

    prompt = _manager_messages(request)
    payload = prompt.messages[1].content

    assert isinstance(payload, str)
    decoded = json.loads(payload)
    review_bundle = decoded["mission_review_bundle"]
    assert review_bundle["priority_1_admitted_episode_working_facts"][0]["key"] == "measured_value"
    assert review_bundle["required_evidence_status"] == [{
        "key": "measured_value",
        "description": "exact measured value",
        "status": "retained",
    }]
    assert decoded["episode_working_facts"][0]["key"] == "measured_value"
    assert decoded["episode_working_facts"][0]["value"] == "33 units"
    assert decoded["episode_working_facts"][0]["observation_lineage"] == {
        "origin": "pinned_episode_fact"
    }
    assert record.evidence_ref not in payload
    assert record.observation_id not in payload
    assert record.source_observation_id not in payload
    assert tuple(prompt.public_evidence_refs.values()) == (record.evidence_ref,)


def test_manager_review_prioritizes_changed_required_result_before_conflicting_title() -> None:
    task = TaskGoal("task:changed-review", "Retain one current result.")
    world = fused_world(
        "source:changed-review",
        (
            SemanticTarget("document", "document", "Not Found"),
            SemanticTarget("heading", "heading", "Current result"),
            SemanticTarget("viewport", "viewport", "Viewport", {"page.route": "https://example.test/results"}),
            SemanticTarget("result", "status", "Measured result", {"value": "17 units"}),
        ),
        (StateFact("measured_result", "result", "value", "17 units", "source:changed-review"),),
        surface="browsergym",
    )
    bundle = EvidenceBundle.from_world(world)
    record = next(item for item in bundle.evidence_records if item.value == "17 units")
    subtask = SubtaskContract(
        "Retain one measured result",
        "One evidence packet is reviewable",
        "Preserves the requested measured result",
        SubtaskOutcomeKind.EVIDENCE_PACKET,
        required_evidence=(EvidenceRequirement("measured_value", "17 units measured result"),),
    )
    request = ManagerRoleRequest(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        task,
        MissionState.empty(),
        recovery=ManagerRecoveryView(
            "outcome_proposed",
            True,
            subtask,
            outcome_proposal="Measured result is 17 units.",
        ),
        environment=project_mission_environment(world),
        active_subtask=subtask,
        review_world=world,
        evidence_bundle=bundle,
        allowed_evidence_refs=(record.evidence_ref,),
        changed_evidence_refs=(record.evidence_ref,),
    )
    prompt = _manager_messages(request)
    decoded = json.loads(prompt.messages[1].content)
    review = decoded["mission_review_bundle"]
    assert review["required_evidence_status"] == [{
        "key": "measured_value",
        "description": "17 units measured result",
        "status": "currently_visible",
    }]
    assert review["priority_4_typed_recovery_or_failure"]["outcome_proposal"] == (
        "Measured result is 17 units."
    )
    assert review["priority_2_fresh_relevant_result_evidence"][0]["value"] == "17 units"
    assert review["priority_3_current_page_identity"] == {
        "current_route": "/results",
        "visible_primary_heading": "Current result",
        "document_title": "Not Found",
        "identity_conflict": True,
    }


def test_model_backed_manager_rejects_guessed_canonical_evidence_ref() -> None:
    task = TaskGoal("task:canonical-reject", "Read one current value.")
    target = SemanticTarget("target:current", "text", "Current value")
    world = fused_world(
        "source:current",
        (target,),
        (StateFact(
            "fact:current:value",
            target.target_id,
            "value",
            "33 units",
            "source:current",
        ),),
    )
    bundle = EvidenceBundle.from_world(world)
    canonical = next(item.evidence_ref for item in bundle.evidence_records if item.value == "33 units")
    subtask = SubtaskContract(
        "Read one value", "One evidence packet is visible", "Provides the requested value"
    )
    request = ManagerRoleRequest(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        task,
        MissionState.empty(),
        recovery=ManagerRecoveryView("outcome_proposed", True, subtask),
        active_subtask=subtask,
        review_world=world,
        evidence_bundle=bundle,
        allowed_evidence_refs=(canonical,),
    )
    model = _RoleModel([{
        "assessment": "unknown",
        "route": "blocked",
        "evidence_refs": (canonical,),
        "reason": "Guessed a private canonical ref.",
    }])

    result = asyncio.run(ModelBackedMissionManager(model.invoker()).decide(request))

    assert result.output is None
    assert result.failure is not None
    assert result.failure.kind.value == "schema_error"


def test_manager_non_authoritative_reason_is_mechanically_bounded_without_repair() -> None:
    response = ReviewManagerDecisionModel.model_validate({
        "assessment": "unknown",
        "route": "blocked",
        "reason": "r" * 700,
    })

    decision = _lower_manager_decision(
        ManagerRequestMode.REVIEW_AND_ROUTE,
        response,
        {},
    )

    assert decision.reason == "r" * 500


def test_accepted_mission_state_never_exposes_canonical_evidence_identifiers() -> None:
    task = TaskGoal("task:accepted-state", "Use one accepted value.")
    world = fused_world(
        "source:accepted",
        (SemanticTarget("target:accepted", "text", "Accepted value"),),
        (StateFact(
            "fact:accepted:value",
            "target:accepted",
            "value",
            "33 units",
            "source:accepted",
        ),),
    )
    record = next(
        item
        for item in EvidenceBundle.from_world(world).evidence_records
        if item.value == "33 units"
    )
    mission = MissionState(
        1,
        accepted_facts=(AcceptedFact(
            "accepted_value",
            record,
            "use in the next outcome",
            1,
        ),),
    )
    manager_prompt = _manager_messages(ManagerRoleRequest(
        ManagerRequestMode.INITIAL_PLAN,
        task,
        mission,
        remaining_rounds=2,
    ))
    manager_payload = manager_prompt.messages[1].content
    assert isinstance(manager_payload, str)
    manager_state = json.loads(manager_payload)["mission_state"]
    assert record.evidence_ref not in json.dumps(manager_state)
    assert record.source_observation_id not in json.dumps(manager_state)
    assert "accepted_value" in manager_payload and "33 units" in manager_payload

    pinned = WorkingFact("accepted_value", record, 2, "strict review input")
    audit_world = fused_world(
        "source:audit-review",
        (SemanticTarget("target:audit", "text", "Fresh audit page"),),
    )
    audit_bundle = EvidenceBundle.from_world(audit_world, (pinned,))
    subtask = SubtaskContract(
        "Review one durable claim",
        "One independently cited result is visible",
        "Verifies the requested durable claim",
        relevant_fact_keys=("accepted_value",),
        related_audit_ids=("claim:durable",),
    )
    audit_request = AuditorRoleRequest.from_authorities(
        task,
        subtask,
        mission,
        audit_world,
        (pinned,),
        "outcome_proposed",
        (),
        audit_bundle,
        subtask.related_audit_ids,
    )
    audit_prompt = _auditor_messages(audit_request)
    audit_payload = audit_prompt.messages[1].content
    assert isinstance(audit_payload, str)
    assert record.evidence_ref not in audit_payload
    audit_state = json.loads(audit_payload)["pre_mission_state"]
    assert record.source_observation_id not in json.dumps(audit_state)
    assert "accepted_value" in audit_payload and "33 units" in audit_payload
    public_fact = json.loads(audit_payload)["working_facts"][0]["evidence_ref"]
    assert public_fact.startswith("F")
    assert audit_prompt.public_evidence_refs[public_fact] == record.evidence_ref
