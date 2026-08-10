"""Pure BrowserGym acquisition identity and typed outcome mechanics."""

from __future__ import annotations

import hashlib

from affordance_runtime.execution import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ExecutionOutcome,
    ObservationAcquisition,
)


def not_sent_outcome(request: BoundActionRequest, error: ActionError) -> ExecutionOutcome:
    result = ActionResult(
        request.request_id, DispatchStatus.NOT_SENT, "browsergym", False, error,
        {"currentness_probe_count": 1, "effectful_dispatch_count": 0},
    )
    post = ObservationAcquisition(
        AcquisitionStatus.CAPABILITY_UNAVAILABLE,
        AcquisitionOrigin.POST_ACTION,
        None,
        "action_not_dispatched",
    )
    return ExecutionOutcome(result, post)


def failed_acquisition(origin: AcquisitionOrigin, code: str) -> ObservationAcquisition:
    return ObservationAcquisition(AcquisitionStatus.FAILED, origin, None, code)


def task_info(info: object) -> dict[str, object]:
    value = info.get("task_info") if isinstance(info, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError("BrowserGym omitted environment-native task status")
    return value


def page_identity(raw: object) -> str:
    url = raw.get("url") if isinstance(raw, dict) else None
    if not isinstance(url, str) or not url:
        raise RuntimeError("BrowserGym observation omitted current page identity")
    return digest_text(url)


def episode_identity(info: dict[str, object]) -> str:
    episode = info.get("EPISODE_ID")
    if not isinstance(episode, int | str) or isinstance(episode, bool):
        raise RuntimeError("BrowserGym task status omitted episode identity")
    return str(episode)


def probe_episode(probe: object, fallback: str) -> str:
    value = probe.get("episode") if isinstance(probe, dict) else None
    return str(value) if isinstance(value, int | str) and not isinstance(value, bool) else fallback


def source_revision(page: str, episode: str, serial: int) -> str:
    return digest_text(f"{page}\0{episode}\0{serial}")


def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
