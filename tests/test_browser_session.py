from typing import Any

from affordance_runtime.browser_session import BrowserSession


class FakePage:
    url = "http://fixture/settings"

    def __init__(self) -> None:
        self.visits: list[str] = []

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self.visits.append(url)

    def content(self) -> str:
        return "<main><button id='save'>Save</button></main>"

    def click(self, selector: str) -> None:
        pass

    def fill(self, selector: str, value: str) -> None:
        pass

    def screenshot(self, **kwargs: Any) -> bytes:
        return b"png"


def test_browser_session_captures_observation_and_affordances() -> None:
    snapshot = BrowserSession(FakePage()).capture(page_id="settings")

    assert snapshot.observation.url == "http://fixture/settings"
    assert snapshot.observation.dom_hash
    assert snapshot.affordance_model.environment_revision == snapshot.observation.environment_revision
    assert snapshot.affordance_model.affordances[0].label == "Save"


def test_browser_session_reset_uses_initial_url() -> None:
    page = FakePage()
    session = BrowserSession(page, initial_url="http://fixture/start")
    session.open("http://fixture/other")
    session.reset()

    assert page.visits == ["http://fixture/other", "http://fixture/start"]
