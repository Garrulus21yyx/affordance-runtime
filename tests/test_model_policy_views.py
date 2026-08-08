import pytest

from affordance_runtime.agent import SelectAction
from affordance_runtime.agent.state import Turn
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.execution import ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.model_boundary import (
    project_action_space,
    project_parameter_schema_for_model,
    project_plan,
    project_task,
    project_turns,
)
from affordance_runtime.task import MaterialBinding, Milestone, RiskProfile, TaskGoal, TaskPlan
from affordance_runtime.world import ActionOption, ActionRisk, ActionSpace, AgentTargetView, AgentWorldView


def _task() -> TaskGoal:
    return TaskGoal(
        "task-1",
        "Send the report",
        constraints=("only Alice",),
        allowed_effects=("message_sent",),
        forbidden_effects=("account_deleted",),
        inputs={"text": "Quarterly report", "api_token": "raw-secret", "local_path": "/private/report"},
        success_criteria=({"id": "sent", "predicate": "message_sent"},),
        requested_outputs=("receipt",),
        risk_profile=RiskProfile.HIGH,
        material_bindings=(
            MaterialBinding("report", "internal-digest", "application/pdf", public_reference="report-input"),
        ),
    )


def _world() -> AgentWorldView:
    return AgentWorldView(
        "world-internal",
        (
            AgentTargetView("message", "button", "Send message"),
            AgentTargetView("alice", "person", "Alice"),
        ),
        (),
        {"dom": "complete"},
    )


def _space() -> ActionSpace:
    return ActionSpace(
        "world-internal",
        (
            ActionOption(
                "action:opaque",
                "world-internal",
                "send",
                "message",
                "external",
                {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "selector": {"type": "string", "default": "#private"},
                    },
                },
                "private-schema-digest",
                ("binding:private",),
                "send message",
                ("message_sent",),
                ActionRisk.HIGH,
                True,
                ("alice",),
            ),
        ),
    )


def test_task_projection_is_bounded_and_secret_safe() -> None:
    view = project_task(_task())

    assert view.task_id == "task-1"
    assert view.public_inputs["text"] == "Quarterly report"
    assert "api_token" not in view.public_inputs
    assert "local_path" not in view.public_inputs
    assert view.success_criteria[0].criterion_id == "sent"
    assert view.requested_output_ids == ("receipt",)
    assert view.material_bindings[0].public_reference == "report-input"
    assert "raw-secret" not in repr(view)
    assert "/private/report" not in repr(view)


def test_action_space_projection_excludes_runtime_route_identity() -> None:
    view = project_action_space(_space(), _world())
    option = view.options[0]

    assert option.action_id == "action:opaque"
    assert option.target_label == "Send message"
    assert option.destinations.items[0].destination_id == "alice"
    assert option.destinations.items[0].label == "Alice"
    assert option.destinations.total_count == 1
    assert not option.destinations.truncated
    assert option.parameter_schema["properties"]["text"]["type"] == "string"
    representation = repr(view)
    for private in (
        "eligible_binding_ids",
        "binding:private",
        "schema_digest",
        "private-schema-digest",
        "world-internal",
        "backend",
        "surface",
        "executor",
        "selector",
        "#private",
    ):
        assert private not in representation


def test_task_criteria_projection_retains_semantics_but_excludes_private_fields() -> None:
    task = TaskGoal(
        "inspect",
        "x" * 2_000,
        constraints=tuple(f"constraint-{index}-" + "y" * 500 for index in range(30)),
        success_criteria=(
            {
                "id": "safe",
                "predicate": "api-token-enabled",
                "value": True,
                "selector": "#private",
                "credential": "raw-secret",
                "local_path": "/private/path",
            },
        ),
        material_bindings=(
            MaterialBinding("hidden", "arbitrary-internal-digest"),
            MaterialBinding("sha", "sha256:" + "a" * 64),
        ),
    )

    view = project_task(task)

    assert len(view.instruction) <= 1_024
    assert len(view.constraints) == 12
    assert all(len(item) <= 240 for item in view.constraints)
    definition = view.success_criteria[0].definition
    assert definition["predicate"] == "api-token-enabled"
    assert definition["value"] is True
    assert "selector" not in definition
    assert "credential" not in definition
    assert "local_path" not in definition
    assert tuple(item.name for item in view.material_bindings) == ("sha",)
    assert view.material_bindings[0].public_reference == "sha256:" + "a" * 64


def test_parameter_schema_projection_is_consistent_after_private_fields_are_removed() -> None:
    schema = {
        "type": "object",
        "description": "public " + "z" * 500,
        "properties": {
            "text": {"type": "string", "description": "message"},
            "selector": {"type": "string"},
        },
        "required": ["text", "selector"],
        "additionalProperties": False,
    }

    projected = project_parameter_schema_for_model(schema)

    assert tuple(projected["properties"]) == ("text",)
    assert projected["required"] == ["text"]
    assert len(projected["description"]) <= 240


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": [], "additionalProperties": False},
        {"type": "object", "properties": {}, "additionalProperties": {"type": "string"}},
        {"type": "object", "properties": {"value": {"oneOf": [{"type": "string"}]}}},
    ],
)
def test_parameter_schema_projection_rejects_unsupported_or_malformed_shapes(schema) -> None:
    with pytest.raises(ValueError, match="parameter schema"):
        project_parameter_schema_for_model(schema)


def test_recent_turn_projection_is_semantic_and_private_payload_free() -> None:
    result = ActionResult(
        "request:private",
        DispatchStatus.SENT,
        "dom-private-backend",
        True,
        adapter_evidence={"selector": "#send", "credential": "private"},
    )
    evaluation = ActionEvaluation(
        "request:private",
        "before-private",
        "after-private",
        ActionEvaluationStatus.EFFECT_CONFIRMED,
        "backend=/private/path selector=#send credential=raw-secret",
        ("fact:sent",),
    )
    turn = Turn(
        "before-private",
        SelectAction("context:test", "action:opaque", {"text": "hello", "password": "private"}, "alice"),
        ActionIntent("send", "message", {"text": "hello", "password": "private"}, "alice"),
        "request:private",
        result,
        "after-private",
        evaluation,
    )

    view = project_turns((turn,))[0]

    assert view.semantic_action == "send"
    assert view.target_id == "message"
    assert view.destination_id == "alice"
    assert view.public_parameters["password"] == "[REDACTED]"
    assert view.dispatch_status == DispatchStatus.SENT
    representation = repr(view)
    for private in (
        "request:private",
        "before-private",
        "after-private",
        "dom-private-backend",
        "#send",
        "adapter_evidence",
        "/private/path",
        "raw-secret",
    ):
        assert private not in representation


def test_plan_projection_contains_only_semantic_milestones() -> None:
    plan = TaskPlan("plan:private", (Milestone("m1", {"message_sent": True}, "Send message"),), "private")

    view = project_plan(plan)

    assert view is not None
    assert view.milestones[0].milestone_id == "m1"
    assert view.milestones[0].objective == "Send message"
    assert view.milestones[0].completion_criteria["message_sent"] is True
    assert "plan:private" not in repr(view)
