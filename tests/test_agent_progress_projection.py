from types import SimpleNamespace

from affordance_runtime.agent.progress_control import ProgressEvent
from affordance_runtime.agent.progress_projection import project_progress_events


def _event(index: int) -> ProgressEvent:
    return ProgressEvent(
        "already_satisfied_selection",
        "fill",
        f"target:{index}",
        f"sha256:{index:064x}",
        "already_satisfied",
        "incomplete",
        True,
    )


def test_progress_projection_is_bounded_truthfully_and_route_free() -> None:
    state = SimpleNamespace(
        recent_progress_events=tuple(_event(index) for index in range(2, 5)),
        progress_event_total_count=5,
    )
    projected = project_progress_events(state)

    assert len(projected.items) == 3
    assert projected.total_count == 5
    assert projected.truncated is True
    representation = repr(projected)
    assert "selector" not in representation
    assert "binding" not in representation
    assert "private" not in representation
