from __future__ import annotations

import asyncio
from typing import Any

import pytest

from affordance_runtime.actions import (
    ActionBinder,
    ActionSpaceBuilder,
)
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_action_outcome
from affordance_runtime.surfaces.dom import DomSurfaceAdapter, project_structured_document
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
from affordance_runtime.task import TaskGoal
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.surfaces.dom.reference_site_support import pricing_html


class PricingPage:
    url = "http://fixture/pricing"

    def __init__(self) -> None:
        self.pro_visible = False
        self.enterprise_visible = False

    def content(self) -> str:
        value = pricing_html()
        if self.pro_visible:
            value = value.replace("<dl hidden>", "<dl>", 1)
        if self.enterprise_visible:
            marker = "<dl hidden>"
            index = value.rfind(marker)
            if index >= 0:
                value = value[:index] + "<dl>" + value[index + len(marker):]
        return value

    def click(self, selector: str) -> None:
        if selector == "#show-pro":
            self.pro_visible = True
        elif selector == "#show-enterprise":
            self.enterprise_visible = True
        else:
            raise AssertionError(selector)

    def fill(self, selector: str, value: str) -> None:
        raise AssertionError((selector, value))

    def screenshot(self, **kwargs: Any) -> bytes:
        return b"png"


def test_document_projection_only_publishes_visible_semantic_records() -> None:
    hidden = project_structured_document(pricing_html(), "http://fixture/pricing")
    assert hidden.targets[0].target_id == "dom_document"
    assert hidden.targets[0].state["visible_record_count"] == 0
    assert hidden.artifact["records"] == ()

    revealed_html = pricing_html(101, "heldout").replace("<dl hidden>", "<dl>")
    revealed = project_structured_document(revealed_html, "http://fixture/pricing")
    records = {item["label"]: item for item in revealed.artifact["records"]}

    assert revealed.targets[0].state["visible_record_count"] == 2
    assert records["Pro"]["fields"] == {
        "users": 25,
        "projects": 100,
        "support": "Business hours",
    }
    assert records["Enterprise"]["fields"] == {
        "users": "Unlimited",
        "projects": "Unlimited",
        "support": "24/7",
    }
    assert "show-pro-heldout-101" not in repr(revealed)
    assert "selector" not in repr(revealed)


def test_read_only_dom_interaction_requires_registered_operation_and_structural_change() -> None:
    async def scenario() -> None:
        page = PricingPage()
        task = TaskGoal(
            "pricing",
            "Reveal pricing records",
            requested_outputs=("structured_document",),
        )
        untrusted = UnifiedWorldEnvironment((DomSurfaceAdapter(BrowserSession(page)),))  # type: ignore[arg-type]
        initial = await untrusted.reset(task)
        assert initial.observation is not None
        assert not ActionSpaceBuilder().build(task, initial.observation).options

        environment = UnifiedWorldEnvironment((
            DomSurfaceAdapter(
                BrowserSession(page),  # type: ignore[arg-type]
                frozenset({"interaction.reveal@v1"}),
            ),
        ))
        acquired = await environment.reset(task)
        assert acquired.observation is not None
        before = acquired.observation
        space = ActionSpaceBuilder().build(task, before)
        assert len(space.options) == 2
        pro = next(
            option for option in space.options
            if next(item for item in before.targets if item.target_id == option.target_id).label
            == "Show Pro limits"
        )
        request = ActionBinder().bind(ActionSpaceBuilder().admit(pro, {}), before, "context:pricing")
        execution = await environment.execute(request)
        after = execution.post_acquisition.observation
        assert after is not None

        proposed = await ProductionActionOutcomeProjector().evaluate(
            task, before, request, execution.result, after,
        )
        validated = validate_action_outcome(
            proposed,
            task,
            request,
            before,
            after,
            WorldEvidenceIndex.from_observation(after),
        )
        assert validated.observed_change.value == "changed"
        assert validated.local_postcondition.value == "not_applicable"
        assert validated.evidence_method.value == "structural"
        assert all("focused" not in ref for ref in validated.evidence_refs)
        document = next(item for item in after.targets if item.target_id == "dom_document")
        assert document.state["visible_record_count"] == 1

    asyncio.run(scenario())


def test_dom_adapter_rejects_non_interaction_operation_registration() -> None:
    with pytest.raises(ValueError, match="local reversible interaction"):
        DomSurfaceAdapter(  # type: ignore[arg-type]
            BrowserSession(PricingPage()),
            frozenset({"resource.update@v1"}),
        )
