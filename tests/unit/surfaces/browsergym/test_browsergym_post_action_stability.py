from __future__ import annotations

import inspect
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from hypothesis import given
from hypothesis import strategies as st
from playwright.sync_api import sync_playwright

from affordance_runtime.surfaces.browsergym import backend
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.surfaces.browsergym.transition import (
    BrowserGymStabilityStatus,
    BrowserGymStepTransition,
    BrowserGymTransitionTrace,
)


class _Pages(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback contract
        if self.path == "/start":
            body = b"""<!doctype html><a id='delayed' href='/not-found'
              onclick='event.preventDefault(); setTimeout(() => location.href = this.href, 300)'>
              Open result</a>"""
            status = 200
        elif self.path == "/not-found":
            body = b"<!doctype html><title>Not Found</title><h1>Not Found</h1>"
            status = 404
        elif self.path == "/never":
            body = b"<!doctype html><title>Never</title>"
            status = 200
        else:
            body = b"missing"
            status = 404
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.fixture
def page_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Pages)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _Unwrapped:
    def __init__(self, page) -> None:
        self.page = page

    def _get_obs(self):
        return {"url": self.page.url, "title": self.page.title()}


class _ClickEnvironment:
    def __init__(self, page, selector: str) -> None:
        self.page = page
        self.selector = selector

    def step(self, _action: str):
        self.page.locator(self.selector).click(no_wait_after=True)
        return ({"url": self.page.url}, 0.0, False, False, {"task_info": {}})


def _identity_private_projection(_page, raw):
    return raw


def test_causal_step_uses_event_and_predicate_waits_not_fixed_sleep() -> None:
    source = inspect.getsource(backend._causal_step)  # noqa: SLF001
    assert "wait_for_event" in source
    assert "wait_for_load_state" in source
    assert "wait_for_function" in source
    assert "time.sleep(" not in source
    assert "wait_for_timeout(" not in source


def test_bulk_physical_projection_uses_one_page_evaluation() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """<a bid='link' href='/next'>Next</a>
            <input bid='field' value='hello'>
            <button bid='disabled' disabled>Disabled</button>"""
        )
        raw = {
            "axtree_object": {
                "nodes": [
                    {"browsergym_id": "link"},
                    {"browsergym_id": "field"},
                    {"browsergym_id": "disabled"},
                ]
            },
            "extra_element_properties": {},
        }

        enriched = backend._with_private_control_properties(page, raw)  # noqa: SLF001

        physical = enriched[PRIVATE_CONTROL_PROPERTIES_KEY]
        assert physical["link"]["attached"] is True
        assert physical["link"]["visible"] is True
        assert physical["link"]["enabled"] is True
        assert physical["link"]["focusable"] is True
        assert physical["link"]["navigation_potential"] is True
        assert physical["field"]["editable"] is True
        assert physical["disabled"]["enabled"] is False
        browser.close()


@given(
    status=st.sampled_from(tuple(BrowserGymStabilityStatus)),
    carries_raw=st.booleans(),
)
def test_transition_algebra_admits_observation_exactly_for_stable_states(
    status,
    carries_raw,
) -> None:
    navigated = status in {
        BrowserGymStabilityStatus.STABLE_NAVIGATION,
        BrowserGymStabilityStatus.NAVIGATION_PENDING,
    }
    committed = status is BrowserGymStabilityStatus.STABLE_NAVIGATION
    stable = status in {
        BrowserGymStabilityStatus.STABLE_NO_NAVIGATION,
        BrowserGymStabilityStatus.STABLE_NAVIGATION,
    }
    trace = BrowserGymTransitionTrace(
        0.0,
        1.0,
        0.2 if navigated else None,
        0.4 if committed else None,
        0.5 if stable else None,
        0.6 if stable else None,
        "https://example.test/before",
        "https://example.test/after" if committed else "https://example.test/before",
        3,
        4 if committed else 3,
        status,
    )
    raw = {"url": trace.after_url} if carries_raw else None

    if carries_raw is stable:
        transition = BrowserGymStepTransition(raw, 0.0, False, False, {}, trace)
        assert transition.stable is stable
    else:
        with pytest.raises(ValueError, match="only a stable"):
            BrowserGymStepTransition(raw, 0.0, False, False, {}, trace)


def test_delayed_link_navigation_is_one_causal_step(monkeypatch, page_server) -> None:
    monkeypatch.setattr(backend, "_with_private_control_properties", _identity_private_projection)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{page_server}/start")

        transition, epoch = backend._causal_step(  # noqa: SLF001 - owner contract gate
            _ClickEnvironment(page, "#delayed"),
            _Unwrapped(page),
            "click('delayed')",
            may_navigate=True,
            document_epoch=7,
        )

        assert transition.trace.stability_status is BrowserGymStabilityStatus.STABLE_NAVIGATION
        assert transition.raw == {"url": f"{page_server}/not-found", "title": "Not Found"}
        assert transition.trace.before_url == f"{page_server}/start"
        assert transition.trace.after_url == f"{page_server}/not-found"
        assert transition.trace.navigation_started is not None
        assert transition.trace.navigation_committed is not None
        assert transition.trace.post_capture_started >= transition.trace.navigation_committed
        assert transition.trace.post_capture_completed >= transition.trace.post_capture_started
        assert (transition.trace.before_document_epoch, epoch) == (7, 8)
        browser.close()


def test_navigation_timeout_returns_typed_pending(monkeypatch, page_server) -> None:
    monkeypatch.setattr(backend, "_with_private_control_properties", _identity_private_projection)
    monkeypatch.setattr(backend, "_NAVIGATION_COMPLETION_TIMEOUT_MS", 100)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{page_server}/start")
        page.eval_on_selector(
            "#delayed",
            "el => { el.href = '/never'; el.onclick = event => { event.preventDefault(); setTimeout(() => location.href = el.href, 1); }; }",
        )
        page.route(f"{page_server}/never", lambda _route: None)

        transition, _epoch = backend._causal_step(  # noqa: SLF001
            _ClickEnvironment(page, "#delayed"),
            _Unwrapped(page),
            "click('delayed')",
            may_navigate=True,
            document_epoch=1,
        )

        assert transition.raw is None
        assert transition.trace.navigation_started is not None
        assert transition.trace.navigation_committed is None
        assert transition.trace.stability_status is BrowserGymStabilityStatus.NAVIGATION_PENDING
        browser.close()


def test_non_navigation_button_skips_navigation_grace(monkeypatch, page_server) -> None:
    monkeypatch.setattr(backend, "_with_private_control_properties", _identity_private_projection)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<button id='plain' onclick='this.textContent = `done`'>plain</button>")

        transition, _epoch = backend._causal_step(  # noqa: SLF001
            _ClickEnvironment(page, "#plain"),
            _Unwrapped(page),
            "click('plain')",
            may_navigate=False,
            document_epoch=1,
        )

        assert transition.trace.stability_status is BrowserGymStabilityStatus.STABLE_NO_NAVIGATION
        assert transition.trace.navigation_started is None
        assert transition.trace.dispatch_returned < backend._NAVIGATION_START_GRACE_MS
        browser.close()


def test_continuously_mutating_post_state_is_typed_unstable(monkeypatch) -> None:
    monkeypatch.setattr(backend, "_with_private_control_properties", _identity_private_projection)
    monkeypatch.setattr(backend, "_DOM_QUIET_TIMEOUT_MS", 120)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """<button id='plain'>plain</button><div id='ticker'></div>
            <script>setInterval(() => ticker.setAttribute('data-tick', String(Date.now())), 5)</script>"""
        )

        transition, _epoch = backend._causal_step(  # noqa: SLF001
            _ClickEnvironment(page, "#plain"),
            _Unwrapped(page),
            "click('plain')",
            may_navigate=False,
            document_epoch=1,
        )

        assert transition.raw is None
        assert transition.trace.post_capture_started is None
        assert transition.trace.stability_status is BrowserGymStabilityStatus.ACQUISITION_UNSTABLE
        browser.close()
