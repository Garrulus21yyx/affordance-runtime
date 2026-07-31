import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import ActivePerceptionRequest, GroundingSource
from affordance_runtime.perception_session import PerceptionCaptureRequest, PerceptionSession
from affordance_runtime.runtime import RunRequest
from affordance_runtime.state_kernel import StateKernel


def _snapshot(sequence: int) -> BrowserSnapshot:
    revision = f"environment-{sequence}"
    snapshot_id = f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        "<main><button id='inspect'>Inspect</button></main>",
        environment_revision=revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
    )
    observation = Observation(
        environment_revision=revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    return BrowserSnapshot(observation, model)


class PlainObserver:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self) -> BrowserSnapshot:
        self.calls += 1
        return _snapshot(self.calls)


def test_plain_capture_returns_observation_without_mutating_authoritative_state() -> None:
    observer = PlainObserver()
    session = PerceptionSession(observer)
    state = StateKernel(task_id="perception-task", goal="Inspect the current state")
    initial_version = state.version

    snapshot = session.capture(
        PerceptionCaptureRequest(RunRequest("perception-task", state.goal), 1)
    )

    assert snapshot.observation.snapshot_id == "snapshot-1"
    assert observer.calls == 1
    assert state.version == initial_version
    assert state.observation_count == 0


class AsyncTargetedObserver(PlainObserver):
    async def capture_targeted(
        self,
        requests: object,
    ) -> BrowserSnapshot:
        assert requests
        return _snapshot(2)


def test_targeted_capture_resolves_async_port_but_does_not_record_progress() -> None:
    session = PerceptionSession(AsyncTargetedObserver())
    state = StateKernel(task_id="perception-task", goal="Inspect the current state")
    request = ActivePerceptionRequest(
        entity_key="semantic:inspect",
        property_key="visible",
        requested_sources=(GroundingSource.ACCESSIBILITY,),
        reason="resolve a material source conflict",
    )

    snapshot = session.capture_targeted((request,))

    assert session.supports_targeted_capture
    assert snapshot.observation.snapshot_id == "snapshot-2"
    assert state.active_perception_count == 0
    assert state.observation_count == 0


def test_missing_targeted_port_fails_closed_and_invalid_lineage_is_ignored() -> None:
    session = PerceptionSession(PlainObserver())
    state = StateKernel(task_id="perception-task", goal="Inspect the current state")
    state.current_grounding_fallback = {
        "valid": {"failed_source": GroundingSource.DOM.value},
        "invalid": {"failed_source": "untrusted-source"},
    }

    escalation = session.perception_escalation(frozenset({GroundingSource.DOM}))

    assert not session.supports_targeted_capture
    assert escalation is not None
    assert escalation.failed_sources == frozenset({GroundingSource.DOM})
    with pytest.raises(TypeError, match="no capture_targeted port"):
        session.capture_targeted(())
