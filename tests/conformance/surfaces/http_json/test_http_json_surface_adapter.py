from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.surfaces.http_json import (
    HttpJsonAuthority,
    HttpJsonFactProjection,
    HttpJsonProjectionError,
    HttpJsonProjectionErrorCode,
    HttpJsonSourceRegistration,
    HttpJsonSurfaceAdapter,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    AcquisitionStatus,
    CoverageState,
    ObservationOffer,
    ObservationRequestKind,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservationRequest,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


def _task() -> TaskGoal:
    return TaskGoal(
        "task:http-json",
        "Enable notifications",
        allowed_effects=("notifications_enabled",),
        risk_profile=RiskProfile.LOW,
    )


def _registration(endpoint: str = "https://state.example.test/api/state") -> HttpJsonSourceRegistration:
    return HttpJsonSourceRegistration(
        "settings-state",
        endpoint,
        (
            HttpJsonFactProjection(
                "settings",
                "resource",
                "Notification settings",
                "notifications",
                ("settings", "notifications"),
            ),
        ),
        HttpJsonAuthority.REGISTERED_STATE_API,
    )


@dataclass
class FakeTransport:
    payload: object
    calls: int = 0

    async def fetch_json(self, endpoint: str):
        assert endpoint.endswith("/api/state")
        self.calls += 1
        return self.payload


def test_registered_http_json_projects_only_allowlisted_authoritative_facts() -> None:
    async def scenario() -> None:
        transport = FakeTransport({
            "settings": {"notifications": "enabled", "private_token": "secret"},
            "unrelated": {"account": "private"},
        })
        adapter = HttpJsonSurfaceAdapter(_registration(), transport)
        await adapter.reset(_task())

        observation = await adapter.observe("verify persisted setting")

        assert observation.source_profile == ObservationSourceProfile.http_json()
        assert observation.coverage is CoverageState.COMPLETE
        assert observation.targets == (
            SemanticTarget(
                "settings",
                "resource",
                "Notification settings",
                {"notifications": "enabled"},
            ),
        )
        assert len(observation.facts) == 1
        assert observation.facts[0].subject_id == "settings"
        assert observation.facts[0].predicate == "notifications"
        assert observation.facts[0].value == "enabled"
        assert observation.bindings == ()
        assert observation.artifacts == {}
        assert "private_token" not in repr(observation)
        assert "state.example.test" not in repr(adapter)
        assert transport.calls == 1

    asyncio.run(scenario())


def test_projection_failure_is_typed_and_does_not_publish_partial_authority() -> None:
    async def scenario() -> None:
        adapter = HttpJsonSurfaceAdapter(
            _registration(),
            FakeTransport({"settings": {}}),
        )
        await adapter.reset(_task())

        with pytest.raises(HttpJsonProjectionError) as caught:
            await adapter.observe("missing fact")

        assert caught.value.code is HttpJsonProjectionErrorCode.MISSING_KEY

    asyncio.run(scenario())


def test_registration_requires_explicit_authority_and_stable_projection_identity() -> None:
    with pytest.raises(TypeError, match="typed source authority"):
        HttpJsonSourceRegistration(
            "settings-state",
            "https://state.example.test/api/state",
            _registration().projections,
            "authoritative",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="embedded credentials"):
        _registration("https://user:password@state.example.test/api/state")
    with pytest.raises(ValueError, match="unique subject predicates"):
        HttpJsonSourceRegistration(
            "settings-state",
            "https://state.example.test/api/state",
            _registration().projections * 2,
            HttpJsonAuthority.REGISTERED_STATE_API,
        )


@dataclass
class StructuralAdapter:
    surface: str = "dom"
    observe_calls: int = 0

    @property
    def observation_offers(self):
        return (ObservationOffer("dom", "structural", "structural", "low"),)

    def prepare(self, task):
        del task

    async def reset(self, task):
        del task

    async def observe(self, reason):
        del reason
        self.observe_calls += 1
        observation_id = f"dom:{self.observe_calls}"
        return SurfaceObservation(
            observation_id,
            "dom",
            f"revision:{self.observe_calls}",
            ObservationSourceProfile.dom(),
            (SemanticTarget("settings-button", "button", "Enable notifications"),),
            (StateFact(
                f"{observation_id}:visible",
                "settings-button",
                "visible",
                True,
                observation_id,
            ),),
            (),
            CoverageState.COMPLETE,
        )

    async def execute(self, request):
        return ActionResult(request.request_id, DispatchStatus.SENT, self.surface, True)


def test_authoritative_capture_fuses_http_facts_and_dom_into_one_world() -> None:
    async def scenario() -> None:
        dom = StructuralAdapter()
        http = HttpJsonSurfaceAdapter(
            _registration(),
            FakeTransport({"settings": {"notifications": "enabled"}}),
        )
        environment = UnifiedWorldEnvironment((dom, http))

        initial = await environment.reset(_task())
        assert initial.observation is not None
        assert tuple(source.surface for source in initial.observation.sources) == ("dom",)

        acquired = await environment.capture(WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST,
            "verify persisted setting",
            "settings",
            "environment_state",
            "authoritative",
        ))

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert acquired.observation is not None
        assert {source.surface for source in acquired.observation.sources} == {"dom", "http_json"}
        assert {target.target_id for target in acquired.observation.targets} == {
            "settings",
            "settings-button",
        }
        authoritative = next(
            fact for fact in acquired.observation.facts
            if fact.subject_id == "settings" and fact.predicate == "notifications"
        )
        assert authoritative.value == "enabled"
        assert {
            item.surface: item.coverage for item in acquired.observation.source_manifest
        } == {"dom": CoverageState.COMPLETE, "http_json": CoverageState.COMPLETE}

    asyncio.run(scenario())
