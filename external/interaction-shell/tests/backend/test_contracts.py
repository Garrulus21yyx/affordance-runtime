from __future__ import annotations

import pytest
from interaction_shell.contracts import ShellEvent, ViewerState
from pydantic import ValidationError


@pytest.mark.parametrize(
    "field",
    [
        "selector",
        "coordinate",
        "backend_handle",
        "accessibility_node_id",
        "private_binding",
        "credential",
        "viewer_reusable_secret",
        "full_world",
        "hidden_reasoning",
        "benchmark_hidden_state",
    ],
)
def test_public_events_reject_private_fields_recursively(field):
    with pytest.raises(ValidationError):
        ShellEvent(
            session_id="s",
            event_epoch="contract-test-epoch",
            cursor=1,
            type="STEP_FINISHED",
            data={"nested": {field: "x"}},
        )


def test_viewer_requires_secret_free_same_origin_read_only_route():
    viewer = ViewerState(
        status="available",
        provider="steel",
        protected_path="/viewer/session-1",
    )
    assert viewer.read_only is True
    with pytest.raises(ValidationError):
        ViewerState(
            status="available",
            provider="browserbase",
            protected_path="https://provider.test/live?secret=reusable",
        )
    with pytest.raises(ValidationError):
        ViewerState(
            status="available",
            provider="steel",
            protected_path="/viewer/session-1",
            read_only=False,
        )
