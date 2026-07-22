from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import affordance_runtime.benchmarks.browsergym as browsergym_facade
from affordance_runtime.benchmarks.browsergym_observer import (
    BrowserGymObserver,
    fuse_visual_candidates,
    json_safe,
    refresh_dom_grounding_candidates,
    visual_fallback_affordance,
)
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeState


@dataclass
class FailingCaptureSession:
    message: str
    calls: int = 0

    def capture(self, **kwargs: Any) -> Any:
        del kwargs
        self.calls += 1
        raise RuntimeError(self.message)

    def bounding_boxes_for_selectors(
        self,
        bindings: dict[str, str],
    ) -> dict[str, tuple[float, float, float, float]]:
        del bindings
        return {}


def _observer(session: Any, screenshot_dir: Path) -> BrowserGymObserver:
    return BrowserGymObserver(
        session,
        BrowserGymEpisodeState("portable-observation", 0, "Inspect the current control", {}, {}),
        screenshot_dir,
    )


def test_browsergym_facade_preserves_observer_compatibility_exports() -> None:
    assert browsergym_facade.BrowserGymObserver is BrowserGymObserver
    assert browsergym_facade._fuse_visual_candidates is fuse_visual_candidates
    assert browsergym_facade._refresh_dom_grounding_candidates is refresh_dom_grounding_candidates
    assert browsergym_facade._visual_fallback_affordance is visual_fallback_affordance
    assert browsergym_facade._json_safe is json_safe


def test_observer_does_not_retry_an_unrelated_capture_failure(tmp_path: Path) -> None:
    session = FailingCaptureSession("page is closed")

    with pytest.raises(RuntimeError, match="page is closed"):
        _observer(session, tmp_path).capture()

    assert session.calls == 1


def test_observer_caps_coherent_epoch_drift_retries(tmp_path: Path) -> None:
    session = FailingCaptureSession("coherent observation epoch drifted during capture")

    with pytest.raises(RuntimeError, match="coherent observation epoch drifted"):
        _observer(session, tmp_path).capture()

    assert session.calls == 2


def test_observer_metadata_serialization_is_recursive_and_non_executing() -> None:
    marker = object()
    payload = {1: ("plain", marker), "nested": {"marker": marker}}

    safe = json_safe(payload)

    assert safe == {
        "1": ["plain", str(marker)],
        "nested": {"marker": str(marker)},
    }
