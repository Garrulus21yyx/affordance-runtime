from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interaction_shell.contracts import (
    COMMAND_ADMISSION_ADAPTER,
    SHELL_COMMAND_ADAPTER,
    SHELL_EVENT_ADAPTER,
    InteractiveSurface,
    ReadOnlySurface,
    RuntimeSessionSnapshot,
    UnavailableSurface,
)
from pydantic import ValidationError


def snapshot_payload() -> dict[str, object]:
    return {
        "schema_version": "interaction-shell.v3",
        "session_id": "session-1",
        "event_epoch": "event-epoch-00000001",
        "expires_at": datetime.now(UTC).isoformat(),
        "surface": {"status": "unavailable", "reason_code": "surface_not_configured"},
    }


@pytest.mark.parametrize(
    "adapter,payload",
    [
        (SHELL_COMMAND_ADAPTER, {"command_id": "c", "expected_task_revision": 0, "expected_run_status": "idle"}),
        (COMMAND_ADMISSION_ADAPTER, {"command_id": "c", "snapshot": snapshot_payload()}),
        (SHELL_EVENT_ADAPTER, {"schema_version": "interaction-shell.v3", "session_id": "session-1", "event_epoch": "event-epoch-00000001", "cursor": 1, "snapshot": snapshot_payload()}),
    ],
)
def test_closed_unions_require_discriminators(adapter, payload):
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_snapshot_rejects_duplicate_offer_kinds_and_private_extensions():
    with pytest.raises(ValidationError, match="unique by kind"):
        RuntimeSessionSnapshot.model_validate({
            **snapshot_payload(),
            "command_offers": [{"kind": "start_task"}, {"kind": "start_task"}],
        })
    with pytest.raises(ValidationError):
        RuntimeSessionSnapshot.model_validate({**snapshot_payload(), "checkpoint_currentness": "fresh"})


def test_surface_contract_is_provider_neutral_same_origin_and_closed():
    unavailable = UnavailableSurface(status="unavailable", reason_code="provider_unavailable")
    assert unavailable.model_dump() == {"status": "unavailable", "reason_code": "provider_unavailable"}
    read_only = ReadOnlySurface(status="read_only", surface_kind="web", presentation="snapshot", protected_path="/viewer/session-1")
    assert read_only.protected_path == "/viewer/session-1"
    InteractiveSurface(status="interactive", surface_kind="web", presentation="live_media", protected_path="/viewer/session-1", input_mode="native")
    with pytest.raises(ValidationError):
        ReadOnlySurface(status="read_only", surface_kind="web", presentation="live_media", protected_path="https://provider.test/live?secret=x")
    with pytest.raises(ValidationError):
        ReadOnlySurface.model_validate({"status": "read_only", "surface_kind": "web", "presentation": "live_media", "protected_path": "/viewer/session-1", "provider": "steel"})


def test_user_control_and_interactive_surface_invariants_are_coupled_once():
    with pytest.raises(ValidationError, match="user control requires"):
        RuntimeSessionSnapshot.model_validate({**snapshot_payload(), "control_owner": "user"})
    with pytest.raises(ValidationError, match="Agent control"):
        RuntimeSessionSnapshot.model_validate({
            **snapshot_payload(),
            "surface": {"status": "interactive", "surface_kind": "web", "presentation": "live_media", "protected_path": "/viewer/session-1", "input_mode": "native"},
        })
