from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from affordance_runtime.actions import ActionBinder, ActionSpaceBuilder
from affordance_runtime.evaluation import (
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    ProductionActionOutcomeProjector,
)
from affordance_runtime.evaluation.action_applicability import apply_action_evidence_profile
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import CoverageState, WorldFusion
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


class NavigationPage:
    def __init__(self) -> None:
        self.url = "https://start.example.test/"

    def content(self) -> str:
        return "<html><head><title>Start</title></head><body><h1>Start</h1></body></html>"

    def goto(self, url: str, **_kwargs: Any) -> None:
        self.url = url

    def click(self, selector: str) -> None:
        raise AssertionError(selector)

    def fill(self, selector: str, value: str) -> None:
        raise AssertionError((selector, value))

    def screenshot(self, **_kwargs: Any) -> bytes:
        return b"png"


def _task() -> TaskGoal:
    return TaskGoal(
        "task:open-browser",
        "Open the documentation",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def test_dom_surface_projects_and_executes_unrestricted_browser_navigation() -> None:
    async def scenario() -> None:
        page = NavigationPage()
        environment = UnifiedWorldEnvironment(
            (DomSurfaceAdapter(BrowserSession(page)),)  # type: ignore[arg-type]
        )
        acquired = await environment.reset(_task())
        assert acquired.observation is not None
        before = acquired.observation
        browser = next(item for item in before.targets if item.role == "browser_context")
        assert browser.state["navigation_scope"] == "unrestricted"
        assert browser.state["open_tabs"][0]["route"] == "https://start.example.test/"
        space = ActionSpaceBuilder().build(_task(), before)
        goto = next(item for item in space.options if item.semantic_action == "goto")
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(
                goto,
                {"url": "https://docs.example.test/guide?private=query"},
            ),
            before,
            "context:goto",
        )

        execution = await environment.execute(request)

        assert execution.result.dispatch_status is DispatchStatus.SENT
        assert execution.post_acquisition is not None
        assert execution.post_acquisition.observation is not None
        after_browser = next(
            item for item in execution.post_acquisition.observation.targets if item.role == "browser_context"
        )
        assert after_browser.state["open_tabs"][0]["route"] == "https://docs.example.test/guide"
        assert page.url == "https://docs.example.test/guide?private=query"

    asyncio.run(scenario())


def test_sent_unknown_navigation_uses_current_browser_context_on_truncated_page() -> None:
    async def scenario() -> None:
        page = NavigationPage()
        environment = UnifiedWorldEnvironment(
            (DomSurfaceAdapter(BrowserSession(page)),)  # type: ignore[arg-type]
        )
        acquired = await environment.reset(_task())
        assert acquired.observation is not None
        before = acquired.observation
        goto = next(
            item
            for item in ActionSpaceBuilder().build(_task(), before).options
            if item.semantic_action == "goto"
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(
                goto,
                {"url": "https://docs.example.test/guide"},
            ),
            before,
            "context:goto-truncated",
        )
        execution = await environment.execute(request)
        assert execution.post_acquisition is not None
        assert execution.post_acquisition.observation is not None
        captured = execution.post_acquisition.observation
        fused = WorldFusion().fuse(
            tuple(
                replace(source, coverage=CoverageState.TRUNCATED)
                for source in captured.sources
            )
        )
        assert fused.observation is not None
        after = fused.observation
        assert all(source.coverage is CoverageState.TRUNCATED for source in after.sources)

        outcome = await ProductionActionOutcomeProjector().evaluate(
            _task(),
            before,
            request,
            ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                "dom",
                False,
                ActionError.EXECUTION_FAILED,
            ),
            after,
        )

        assert outcome.observed_change is ObservedChange.CHANGED
        assert outcome.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE
        assert outcome.evidence_method is EvidenceMethod.STRUCTURAL
        assert outcome.evidence["verification_profile"] == "structural_target_diff_v1"
        assert outcome.evidence_refs
        assert all(WorldEvidenceIndex.from_observation(after).resolve(ref) for ref in outcome.evidence_refs)
        applicable = apply_action_evidence_profile(
            outcome,
            request,
            before,
            after,
            WorldEvidenceIndex.from_observation(after),
        )
        assert applicable.observed_change is ObservedChange.CHANGED
        assert applicable.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE

    asyncio.run(scenario())


def test_dom_browser_navigation_fails_closed_when_live_tab_identity_changed() -> None:
    async def scenario() -> None:
        page = NavigationPage()
        environment = UnifiedWorldEnvironment(
            (DomSurfaceAdapter(BrowserSession(page)),)  # type: ignore[arg-type]
        )
        acquired = await environment.reset(_task())
        assert acquired.observation is not None
        before = acquired.observation
        space = ActionSpaceBuilder().build(_task(), before)
        goto = next(item for item in space.options if item.semantic_action == "goto")
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(goto, {"url": "https://docs.example.test/"}),
            before,
            "context:stale",
        )
        page.url = "https://changed.example.test/"

        execution = await environment.execute(request)

        assert execution.result.dispatch_status is DispatchStatus.NOT_SENT
        assert execution.result.error is ActionError.STALE_BINDING
        assert page.url == "https://changed.example.test/"

    asyncio.run(scenario())
