from affordance_runtime.actions import ActionBinding
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
from affordance_runtime.mission.environment_projection import project_mission_environment
from affordance_runtime.world import SemanticTarget
from tests.support.world import fused_world


def test_mission_environment_is_bounded_semantic_scope_without_world_identity() -> None:
    observation_id = "observation:manager-environment"
    revision = f"revision:{observation_id}"
    heading = SemanticTarget(
        "page-heading",
        "heading",
        "Ordered Products Report / Reports / Magento Admin",
    )
    viewport = SemanticTarget(
        "viewport",
        "viewport",
        "Current page viewport",
        {"page.route": "http://localhost:7780/admin/reports/report_product/sold/?secret=no"},
    )
    report = SemanticTarget("reports-link", "link", "REPORTS")
    binding = ActionBinding(
        "binding:reports",
        observation_id,
        observation_id,
        revision,
        "fingerprint:reports",
        report.target_id,
        report.target_id,
        "browsergym",
        "browsergym",
        "activate",
        "click",
        "external_ui_interaction",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {},
    )
    world = fused_world(
        observation_id,
        (heading, viewport, report),
        bindings=(binding,),
        surface="browsergym",
    )
    recent = (
        AgentTurnView(
            "selectaction",
            "activate",
            AgentHistoricalTargetView("link", "REPORTS"),
            dispatch_status="sent_confirmed",
            local_postcondition="satisfied",
        ),
    )

    view = project_mission_environment(world, recent)

    assert view.surface == "browser"
    assert view.application == "Magento Admin"
    assert view.page_title == "Ordered Products Report"
    assert view.route_family == "/admin/reports/"
    assert view.available_capabilities == (
        "read_current_world",
        "search_current_world",
        "activate",
        "navigate_current_ui",
    )
    assert view.unavailable_capabilities == ("public_web_search",)
    assert view.last_successful_transitions == ("activate REPORTS",)
    serialized = repr(view)
    assert "observation:manager-environment" not in serialized
    assert "localhost" not in serialized
    assert "secret" not in serialized
    assert "E19" not in serialized


def test_mission_environment_strips_refs_from_public_labels_and_history() -> None:
    world = fused_world(
        "observation:ref-free-manager",
        (SemanticTarget("heading", "heading", "Report E19 / Magento Admin"),),
        surface="browsergym",
    )
    recent = (
        AgentTurnView(
            "selectaction",
            "activate",
            AgentHistoricalTargetView("link", "REPORTS R14 <expired-ref-1>"),
            dispatch_status="sent_confirmed",
            local_postcondition="satisfied",
        ),
    )

    serialized = repr(project_mission_environment(world, recent))

    assert "E19" not in serialized
    assert "R14" not in serialized
    assert "expired-ref" not in serialized
