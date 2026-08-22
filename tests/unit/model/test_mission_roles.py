import asyncio
from types import SimpleNamespace

import pytest

from affordance_runtime.mission import MissionState, PlannerRequestMode, PlannerRoleRequest
from affordance_runtime.mission.environment_projection import project_mission_environment
from affordance_runtime.model.mission_roles import (
    MilestoneRoadmapModel,
    ModelBackedMilestonePlanner,
    PlannerDecisionModel,
)
from affordance_runtime.model.providers.port import ModelConfig, ModelMessage
from affordance_runtime.model.pydantic_ai_role_invoker import PydanticAIRoleInvoker
from affordance_runtime.task import TaskGoal
from tests.support.world import fused_world


class Invoker:
    supports_thinking_control = True
    provider = "fixture"
    model_name = "fixture-model"
    endpoint_class = "fixture"

    def __init__(self, output):
        self.output = output
        self.calls = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output=self.output, failure=None, attempts=())


def _request():
    task = TaskGoal("task:planner", "Obtain the requested report")
    world = fused_world("planner-world")
    return PlannerRoleRequest(
        PlannerRequestMode.START,
        task,
        MissionState.empty(),
        remaining_mission_budget=8,
        environment=project_mission_environment(world),
    )


def test_model_backed_planner_lowers_one_closed_roadmap_and_records_physical_mode() -> None:
    output = PlannerDecisionModel.model_validate(
        {
            "route": "roadmap",
            "roadmap": {
                "version": 1,
                "milestones": [
                    {
                        "id": "report",
                        "outcome": "Requested report result is available",
                        "done_when": "The fresh filtered report is observable",
                        "required_evidence": [],
                        "depends_on": [],
                        "final": True,
                    }
                ],
            },
        }
    )
    invoker = Invoker(output)
    result = asyncio.run(ModelBackedMilestonePlanner(invoker).plan(_request()))
    assert result.output is not None and result.output.roadmap is not None
    assert result.output.roadmap.milestones[0].id == "report"
    call = invoker.calls[0]
    assert call["role"] == "planner"
    assert call["mode"] == "start"
    assert call["config"].max_tokens == 2048
    assert call["config"].thinking_mode == "enabled"


@pytest.mark.parametrize(
    "value",
    [
        "geographic coordinates are included in the report",
        "the product selector contains the requested category",
        "the selected product is shown",
        "the press release is available",
        "the click-through rate is reported",
        "the requested type of account is active",
        "the navigation coordinates are documented",
        "Selector #result is visible",
        "E7 contains the answer",
    ],
)
def test_planner_business_vocabulary_is_never_interpreted_as_gui_authority(value) -> None:
    milestone = {
        "id": "result",
        "outcome": value,
        "done_when": value,
        "required_evidence": [],
        "depends_on": [],
        "final": False,
    }
    model = MilestoneRoadmapModel.model_validate({"version": 1, "milestones": [milestone]})
    assert model.milestones[0].outcome == value


def test_planner_allows_submit_as_a_business_state_term() -> None:
    model = MilestoneRoadmapModel.model_validate(
        {
            "version": 1,
            "milestones": [
                {
                    "id": "application",
                    "outcome": "Submit application is accepted",
                    "done_when": "The application has accepted status",
                    "required_evidence": [],
                    "depends_on": [],
                    "final": False,
                }
            ],
        }
    )
    assert model.milestones[0].outcome == "Submit application is accepted"


@pytest.mark.parametrize(
    ("role", "expected_calls", "succeeds"),
    (("planner", 2, True), ("auditor", 2, True), ("action_policy", 1, False)),
)
def test_only_side_effect_free_roles_retry_transport_and_persist_before_retry(
    role: str,
    expected_calls: int,
    succeeds: bool,
) -> None:
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    async def scenario() -> None:
        calls = 0
        persisted = []

        async def respond(_messages, _info):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("provider timeout")
            assert len(persisted) == 1
            assert persisted[0].status == "failed"
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "planner_start_output",
                        {
                            "route": "roadmap",
                            "roadmap": {
                                "version": 1,
                                "milestones": [
                                    {
                                        "id": "result",
                                        "outcome": "result is available",
                                        "done_when": "fresh result is observable",
                                        "required_evidence": [],
                                        "depends_on": [],
                                        "final": True,
                                    }
                                ],
                            },
                        },
                    )
                ]
            )

        invocation = await PydanticAIRoleInvoker(
            FunctionModel(respond, model_name="scripted"),
            "fixture",
            "scripted",
            "fixture.invalid",
            provider_retry_backoff_s=0,
            attempt_sink=persisted.append,
        ).invoke(
            messages=(ModelMessage(role="user", content="return a roadmap"),),
            schema=PlannerDecisionModel,
            output_tool_name="planner_start_output",
            config=ModelConfig(max_tokens=128, timeout_s=5.0),
            role=role,
            mode="start",
            schema_version="mission.planner.v1",
            trigger="task_start",
        )

        assert calls == expected_calls
        assert (invocation.output is not None) is succeeds
        assert len(invocation.attempts) == expected_calls
        assert len(persisted) == expected_calls
        assert [item.attempt for item in persisted] == list(range(1, expected_calls + 1))

    asyncio.run(scenario())


def test_first_physical_role_attempt_is_persisted_before_cancelled_schema_repair() -> None:
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    async def scenario() -> None:
        repair_started = asyncio.Event()
        calls = 0

        async def respond(_messages, _info):
            nonlocal calls
            calls += 1
            if calls == 1:
                return ModelResponse(parts=[TextPart("invalid structured output")])
            repair_started.set()
            await asyncio.Event().wait()

        persisted = []
        invoker = PydanticAIRoleInvoker(
            FunctionModel(respond, model_name="scripted"),
            "fixture",
            "scripted",
            "fixture.invalid",
            attempt_sink=persisted.append,
        )
        invocation = asyncio.create_task(
            invoker.invoke(
                messages=(ModelMessage(role="user", content="return a roadmap"),),
                schema=PlannerDecisionModel,
                output_tool_name="planner_start_output",
                config=ModelConfig(max_tokens=128, timeout_s=5.0),
                role="planner",
                mode="start",
                schema_version="mission.planner.v1",
                trigger="task_start",
            )
        )
        await asyncio.wait_for(repair_started.wait(), timeout=2.0)
        invocation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invocation

        assert calls == 2
        assert [item.attempt for item in persisted] == [1, 2]
        assert persisted[1].status == "failed"
        assert persisted[1].exception_class == "CancelledError"
        assert persisted[0].transcript["llm.output_messages"]
        assert persisted[1].transcript["llm.input_messages"]

    asyncio.run(scenario())


def test_planner_schema_failure_reports_only_bounded_field_path_code_attempt_and_phase() -> None:
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    calls = 0

    async def respond(_messages, _info):
        nonlocal calls
        calls += 1
        invalid_field = "done_when" if calls == 1 else "outcome"
        milestone = {
            "id": "report",
            "outcome": "result",
            "done_when": "fresh result",
            "required_evidence": [],
            "depends_on": [],
            "final": True,
        }
        milestone[invalid_field] = "x" * 501
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "planner_start_output",
                    {
                        "route": "roadmap",
                        "roadmap": {
                            "version": 1,
                            "milestones": [milestone],
                        },
                    },
                )
            ]
        )

    planner = ModelBackedMilestonePlanner(
        PydanticAIRoleInvoker(FunctionModel(respond), "fixture", "scripted", "fixture.invalid")
    )
    result = asyncio.run(planner.plan(_request()))

    assert result.failure is not None
    assert result.diagnostics["structured_output_violations"] == (
        {
            "field_path": "roadmap.milestones.0.outcome",
            "code": "string_too_long",
            "attempt": 2,
            "phase": "output_retry",
        },
    )
    assert "x" * 32 not in repr(result.diagnostics)
