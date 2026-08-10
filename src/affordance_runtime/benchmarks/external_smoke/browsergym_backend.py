"""Own BrowserGym's synchronous Playwright lifecycle on one private thread."""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future

_PROBE_SCRIPT = """bid => {
const el = document.querySelector(`[bid="${CSS.escape(bid)}"]`);
if (!el) return {exists: false};
const tag = el.tagName.toLowerCase();
const type = (el.getAttribute('type') || '').toLowerCase();
const role = el.getAttribute('role') || (tag === 'button' ? 'button' :
  tag === 'a' ? 'link' : tag === 'select' ? 'combobox' :
  (tag === 'textarea' || (tag === 'input' && !['button','submit'].includes(type))) ? 'textbox' : '');
const labelled = el.getAttribute('aria-label') || (el.labels && el.labels[0] ? el.labels[0].innerText.trim() : '');
const label = labelled || ((role === 'button' || role === 'link') ? (el.innerText || el.value || '').trim() : '');
const options = tag === 'select' ? Array.from(el.options).map(o => o.text.trim()) : [];
return {exists: true, url: location.href, episode: String(window.WOB_EPISODE_ID),
  ready: window.WOB_TASK_READY === true, done: window.WOB_DONE_GLOBAL === true,
  role, label, state: {value: 'value' in el ? String(el.value) : '', checked: !!el.checked,
    disabled: !!el.disabled, expanded: el.getAttribute('aria-expanded') === 'true',
    required: !!el.required, selected: !!el.selected, option_count: options.length}, options};
}"""

_VERIFIER_PROBE_SCRIPT = """() => ({
  ready: window.WOB_TASK_READY === true,
  done: window.WOB_DONE_GLOBAL === true,
  episode: String(window.WOB_EPISODE_ID),
  url: location.href
})"""


class ThreadBoundBrowserGym:
    """Small synchronous facade; no page or element handle crosses the thread."""

    def __init__(self, task_id: str, *, headless: bool = True) -> None:
        self._commands: queue.Queue[
            tuple[str, tuple[object, ...], dict[str, object], Future[object]] | None
        ] = queue.Queue()
        self._ready: Future[object] = Future()
        self._thread = threading.Thread(target=self._run, args=(task_id, headless), daemon=True)
        self.owner_thread_ident: int | None = None
        self.last_capture_thread_ident: int | None = None
        self._thread.start()
        ready = self._ready.result(timeout=60)
        self.supports_capture_current = bool(ready)
        self.browser = object()
        self.context = object()
        self.unwrapped = self
        self._closed = False

    def _run(self, task_id: str, headless: bool) -> None:
        try:
            self.owner_thread_ident = threading.get_ident()
            import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
            import gymnasium as gym  # type: ignore[import-not-found]

            environment = gym.make(task_id, headless=headless)
            unwrapped = getattr(environment, "unwrapped", environment)
            getter = getattr(unwrapped, "_get_obs", None)
            # BrowserGym creates its page during reset. Capability inventory happens
            # before that preparation reset, so the pinned read-only API itself is
            # the stable capability signal; capture still executes only after reset.
            self._ready.set_result(callable(getter))
        except BaseException as exc:
            self._ready.set_exception(exc)
            return
        while (command := self._commands.get()) is not None:
            name, args, kwargs, outcome = command
            try:
                if name == "probe_element":
                    unwrapped = getattr(environment, "unwrapped", environment)
                    value = unwrapped.page.evaluate(_PROBE_SCRIPT, *args)
                elif name == "capture_current":
                    self.last_capture_thread_ident = threading.get_ident()
                    unwrapped = getattr(environment, "unwrapped", environment)
                    getter = getattr(unwrapped, "_get_obs", None)
                    if not callable(getter):
                        raise RuntimeError("pinned BrowserGym has no read-only observation API")
                    raw = getter()
                    verifier = unwrapped.page.evaluate(_VERIFIER_PROBE_SCRIPT)
                    value = (raw, verifier)
                else:
                    value = getattr(environment, name)(*args, **kwargs)
                    if name == "close":
                        import browsergym.core as browsergym_core  # type: ignore[import-not-found]

                        playwright = browsergym_core._get_global_playwright()
                        playwright.stop()
                        browsergym_core._set_global_playwright(None)
                outcome.set_result(value)
            except BaseException as exc:
                outcome.set_exception(exc)

    def _call(self, name: str, *args: object, **kwargs: object) -> object:
        if self._closed:
            raise RuntimeError("BrowserGym owner thread is closed")
        outcome: Future[object] = Future()
        self._commands.put((name, args, kwargs, outcome))
        return outcome.result(timeout=180)

    def reset(self, *, seed: int):
        return self._call("reset", seed=seed)

    def step(self, action: str):
        return self._call("step", action)

    def probe_element(self, bid: str):
        return self._call("probe_element", bid)

    def capture_current(self):
        if not self.supports_capture_current:
            raise RuntimeError("pinned BrowserGym read-only capture is unavailable")
        return self._call("capture_current")

    def close(self) -> None:
        if self._closed:
            return
        outcome: Future[object] = Future()
        self._commands.put(("close", (), {}, outcome))
        try:
            outcome.result(timeout=60)
        finally:
            self._commands.put(None)
            self._thread.join(timeout=60)
            self._closed = True
            self.browser = None
            self.context = None
        if self._thread.is_alive():
            raise RuntimeError("BrowserGym owner thread remained alive after cleanup")
