import pytest

from affordance_runtime.agent import (
    Abort,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
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
from affordance_runtime.simplified_runtime_contracts import (
    CriterionEvidencePolicy,
    ElementIntent,
    EvidenceStrength,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
)
from affordance_runtime.task import MaterialBinding, RiskProfile, TaskGoal
from affordance_runtime.task_plan_contracts import TaskPlan, TaskPlanGeneratorSource
from affordance_runtime.world import (
    ActionBinding,
    ActionOption,
    ActionRisk,
    ActionSpace,
    AgentTargetView,
    AgentWorldView,
)
from runtime_test_support import legacy_step_spec


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
    assert view.success_criteria.items[0].criterion_id == "sent"
    assert view.requested_output_ids.items == ("receipt",)
    assert view.material_bindings.items[0].public_reference == "report-input"
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
    assert len(view.constraints.items) == 12
    assert view.constraints.total_count == 30 and view.constraints.truncated
    assert all(len(item) <= 240 for item in view.constraints.items)
    definition = view.success_criteria.items[0].definition
    assert definition["predicate"] == "api-token-enabled"
    assert definition["value"] is True
    assert "selector" not in definition
    assert "credential" not in definition
    assert "local_path" not in definition
    assert tuple(item.name for item in view.material_bindings.items) == ("sha",)
    assert view.material_bindings.total_count == 2 and view.material_bindings.truncated
    assert view.material_bindings.items[0].public_reference == "sha256:" + "a" * 64


def test_all_task_collections_have_truthful_truncation_metadata() -> None:
    task = TaskGoal(
        "many",
        "Project bounded task sections",
        constraints=tuple(f"constraint-{index}" for index in range(15)),
        allowed_effects=tuple(f"allowed-{index}" for index in range(15)),
        forbidden_effects=tuple(f"forbidden-{index}" for index in range(15)),
        success_criteria=tuple({"id": f"criterion-{index}", "value": index} for index in range(15)),
        requested_outputs=tuple(f"output-{index}" for index in range(15)),
    )

    view = project_task(task)

    for section in (
        view.constraints,
        view.allowed_effects,
        view.forbidden_effects,
        view.success_criteria,
        view.requested_output_ids,
    ):
        assert len(section.items) == 12
        assert section.total_count == 15 and section.truncated


def test_material_public_reference_rejects_private_path_or_url() -> None:
    task = TaskGoal(
        "private-material",
        "Do not expose private material routes",
        material_bindings=(
            MaterialBinding("path", "internal", public_reference="/private/report.pdf"),
            MaterialBinding("url", "internal", public_reference="https://private.invalid/report"),
        ),
    )

    materials = project_task(task).material_bindings

    assert materials.items == ()
    assert materials.total_count == 2 and materials.truncated


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


@pytest.mark.parametrize("contract", ("option", "binding"))
def test_internal_action_contract_rejects_private_parameter_names(contract: str) -> None:
    schema = {
        "type": "object",
        "properties": {"selector": {"type": "string"}},
        "required": ["selector"],
        "additionalProperties": False,
    }
    with pytest.raises(ValueError, match="private parameter"):
        if contract == "option":
            ActionOption(
                "action:private-schema",
                "obs:1",
                "activate",
                "target:1",
                "local_reversible",
                schema,
                "schema:1",
                ("binding:1",),
                "invalid private schema",
            )
        else:
            ActionBinding(
                "binding:1",
                "obs:1",
                "obs:1",
                "revision:1",
                "fingerprint:1",
                "target:1",
                "target:1",
                "dom",
                "dom",
                "activate",
                "click",
                "local_reversible",
                (),
                schema,
                {"selector": "#private-route"},
            )


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


@pytest.mark.parametrize(
    ("decision", "expected"),
    (
        (RequestObservation("context:1", "target:1", "visual", "weak", "inspect"), "subject_id"),
        (RequestActionPage("context:1", query="find"), "query"),
        (AskUser("context:1", "Which account?", ("account",)), "question"),
        (ProposeDone("context:1", ("criterion:1",), ("fact:1",), "done", ()), "claimed_criteria"),
        (Wait("context:1", "settle", 25), "max_wait_ms"),
        (Abort("context:1", "stop", "policy"), "category"),
    ),
)
def test_non_action_turn_projection_has_bounded_semantic_summary(decision, expected: str) -> None:
    view = project_turns((Turn("before", decision, decision_result="page_changed"),))[0]

    assert expected in view.semantic_summary
    representation = repr(view)
    assert "context:1" not in representation
    assert "selector" not in representation


def test_plan_projection_contains_only_semantic_milestones() -> None:
    refs = (SourceReference("request", "request:message"),)
    step = legacy_step_spec(
        step_id="m1",
        objective="Send message",
        interaction=ElementIntent("message", refs),
        completion_criteria=(
            StateCriterion(
                "criterion:m1",
                refs,
                subject="message",
                relation=StateCriterionRelation.IS_COMPLETED,
                evidence_policy=CriterionEvidencePolicy(
                    EvidenceStrength.INDEPENDENT,
                    ("dom_state",),
                ),
            ),
        ),
        source_refs=refs,
    )
    plan = TaskPlan(
        plan_id="plan:private",
        task_id="task:message",
        task_revision=1,
        plan_version=1,
        based_on_state_version=0,
        based_on_observation_ref="observation:1",
        generated_by=TaskPlanGeneratorSource.RULE,
        steps=(step,),
    )

    view = project_plan(plan)

    assert view is not None
    assert view.milestones[0].milestone_id == "m1"
    assert view.milestones[0].objective == "Send message"
    assert view.milestones[0].completion_criteria
    assert "plan:private" not in repr(view)
