import asyncio
import inspect
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
    "field,value",
    [
        ("outcome", "Click submit"),
        ("done_when", "Selector #result is visible"),
        ("outcome", "Use read_region to obtain the result"),
        ("done_when", "E7 contains the answer"),
    ],
)
def test_planner_rejects_gui_operations_and_private_implementation_identity(field, value) -> None:
    milestone = {
        "id": "result",
        "outcome": "Requested result is available",
        "done_when": "Fresh result is observable",
        "required_evidence": [],
        "depends_on": [],
        "final": False,
    }
    milestone[field] = value
    with pytest.raises(ValueError):
        MilestoneRoadmapModel.model_validate({"version": 1, "milestones": [milestone]})


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


def test_side_effect_free_planner_and_auditor_are_the_only_roles_with_transport_retry() -> None:
    source = inspect.getsource(PydanticAIRoleInvoker.invoke)
    assert 'role in {"planner", "auditor"}' in source


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
