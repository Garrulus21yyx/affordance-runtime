import pytest

from affordance_runtime.surfaces.dom.browser_session import BrowserSession


def _png(width: int = 100, height: int = 80) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + width.to_bytes(4, "big") + height.to_bytes(4, "big")


def _facts(width: int) -> dict[str, object]:
    return {
        "width": width,
        "height": 80,
        "scrollX": 0,
        "scrollY": 0,
        "dpr": 1,
        "zoom": 1,
        "orientation": "landscape",
    }


class CapturePage:
    def __init__(self, facts: list[dict[str, object]]) -> None:
        self.facts = iter(facts)
        self.screenshots = 0

    def evaluate(self, expression: str):
        del expression
        return next(self.facts)

    def screenshot(self, **kwargs) -> bytes:
        del kwargs
        self.screenshots += 1
        return _png()


def test_visual_capture_accepts_stable_before_and_after_viewport() -> None:
    page = CapturePage([_facts(100), _facts(100)])
    frame = BrowserSession(page).capture_visual_frame("visual:stable")  # type: ignore[arg-type]
    assert frame.viewport.width == 100
    assert page.screenshots == 1


def test_visual_capture_retries_once_then_accepts_stable_viewport() -> None:
    page = CapturePage([_facts(100), _facts(99), _facts(100), _facts(100)])
    frame = BrowserSession(page).capture_visual_frame("visual:retry")  # type: ignore[arg-type]
    assert frame.viewport.width == 100
    assert page.screenshots == 2


def test_visual_capture_rejects_two_incoherent_attempts() -> None:
    page = CapturePage([_facts(100), _facts(99), _facts(100), _facts(99)])
    with pytest.raises(RuntimeError, match="changed during screenshot"):
        BrowserSession(page).capture_visual_frame("visual:unstable")  # type: ignore[arg-type]
    assert page.screenshots == 2
