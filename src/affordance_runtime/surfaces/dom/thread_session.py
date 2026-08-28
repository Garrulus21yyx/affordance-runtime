"""Thread-affine proxy for the synchronous Playwright BrowserSession."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field

from affordance_runtime.surfaces.dom.browser_session import BrowserSession

_Command = tuple[str, tuple[object, ...], dict[str, object], Future]


@dataclass
class ThreadBoundBrowserSession:
    """Own BrowserSession on one worker while async Runtime runs elsewhere."""

    url: str
    headless: bool = True
    action_timeout_ms: int = 8_000
    lease_ttl_ms: int = 2_000
    command_timeout_s: float = 30.0
    environment_playwright_factory: Callable[[object], object] | None = None
    rendered_dom_only: bool = False
    _commands: queue.Queue[_Command | None] = field(init=False, repr=False)
    _ready: Future = field(init=False, repr=False)
    _thread: threading.Thread = field(init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("thread-bound browser requires a URL")
        if self.command_timeout_s <= 0:
            raise ValueError("thread-bound browser command timeout must be positive")
        self._commands = queue.Queue()
        self._ready = Future()
        self._thread = threading.Thread(
            target=self._run,
            name="affordance-browser-session",
            daemon=True,
        )
        self._thread.start()
        self._ready.result(timeout=self.command_timeout_s)

    @classmethod
    def launch(
        cls,
        url: str,
        *,
        headless: bool = True,
        action_timeout_ms: int = 8_000,
        lease_ttl_ms: int = 2_000,
        environment_playwright_factory: Callable[[object], object] | None = None,
        rendered_dom_only: bool = False,
    ) -> ThreadBoundBrowserSession:
        return cls(
            url,
            headless,
            action_timeout_ms,
            lease_ttl_ms,
            environment_playwright_factory=environment_playwright_factory,
            rendered_dom_only=rendered_dom_only,
        )

    def _run(self) -> None:
        try:
            session = BrowserSession.launch(
                self.url,
                headless=self.headless,
                action_timeout_ms=self.action_timeout_ms,
                lease_ttl_ms=self.lease_ttl_ms,
                environment_playwright_factory=self.environment_playwright_factory,
                rendered_dom_only=self.rendered_dom_only,
            )
            self._ready.set_result(True)
        except BaseException as exc:
            self._ready.set_exception(exc)
            return
        try:
            while (command := self._commands.get()) is not None:
                name, args, kwargs, outcome = command
                try:
                    outcome.set_result(getattr(session, name)(*args, **kwargs))
                except BaseException as exc:
                    outcome.set_exception(exc)
        finally:
            session.close()

    def _call(self, name: str, *args: object, **kwargs: object):
        if self._closed:
            raise RuntimeError("thread-bound browser session is closed")
        outcome: Future = Future()
        self._commands.put((name, args, kwargs, outcome))
        return outcome.result(timeout=self.command_timeout_s)

    def reset(self):
        return self._call("reset")

    def capture(self, **kwargs: object):
        return self._call("capture", **kwargs)

    def probe_dom_target(self, target_id: str):
        return self._call("probe_dom_target", target_id)

    def click(self, selector: str):
        return self._call("click", selector)

    def fill(self, selector: str, text: str):
        return self._call("fill", selector, text)

    def select_option(self, selector: str, value: str):
        return self._call("select_option", selector, value)

    def open(self, url: str):
        return self._call("open", url)

    def go_back(self):
        return self._call("go_back")

    def go_forward(self):
        return self._call("go_forward")

    def new_tab(self):
        return self._call("new_tab")

    def focus_tab(self, index: int):
        return self._call("focus_tab", index)

    def close_tab(self):
        return self._call("close_tab")

    def browser_context_state(self):
        return self._call("browser_context_state")

    def capture_visual_frame(self, observation_id: str):
        return self._call("capture_visual_frame", observation_id)

    def click_xy(self, x: float, y: float):
        return self._call("click_xy", x, y)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._commands.put(None)
        self._thread.join(timeout=self.command_timeout_s)
        if self._thread.is_alive():
            raise RuntimeError("thread-bound browser owner did not stop")

    def __enter__(self) -> ThreadBoundBrowserSession:
        return self

    def __exit__(self, *exc: object) -> None:
        del exc
        self.close()
