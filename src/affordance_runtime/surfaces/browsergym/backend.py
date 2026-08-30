"""Own BrowserGym's synchronous Playwright lifecycle on one private thread."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Protocol, cast

from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.surfaces.browsergym.transition import (
    BrowserGymStabilityStatus,
    BrowserGymStepTransition,
    BrowserGymTransitionTrace,
)

_BROWSERGYM_PLAYWRIGHT_LOCAL = threading.local()
_BROWSERGYM_PLAYWRIGHT_PATCH_LOCK = threading.Lock()
_browsergym_playwright_patch_installed = False


def _get_thread_owned_browsergym_playwright() -> object:
    playwright = getattr(_BROWSERGYM_PLAYWRIGHT_LOCAL, "playwright", None)
    if playwright is None:
        sync_api = import_module("playwright.sync_api")
        playwright = sync_api.sync_playwright().start()
        _BROWSERGYM_PLAYWRIGHT_LOCAL.playwright = playwright
    return playwright


def _set_thread_owned_browsergym_playwright(playwright: object | None) -> None:
    _BROWSERGYM_PLAYWRIGHT_LOCAL.playwright = playwright


def _get_thread_owned_browsergym_environment_playwright() -> object:
    """Return the environment-specific driver while keeping BrowserGym chat local."""

    override = getattr(_BROWSERGYM_PLAYWRIGHT_LOCAL, "environment_playwright", None)
    return override if override is not None else _get_thread_owned_browsergym_playwright()


def _set_thread_owned_browsergym_environment_playwright(playwright: object | None) -> None:
    _BROWSERGYM_PLAYWRIGHT_LOCAL.environment_playwright = playwright


def _install_thread_owned_browsergym_playwright() -> None:
    """Replace BrowserGym 0.14's process-global sync driver with owner-thread state.

    BrowserGym caches one synchronous Playwright instance at module scope.  A
    second ``ThreadBoundBrowserGym`` would otherwise reuse the first owner's
    greenlet and fail, while closing either environment could stop the other's
    driver.  BrowserGym's environment and chat modules cache the getter at
    import time, so all three authoritative import sites must be migrated
    together before an environment is reset.
    """

    global _browsergym_playwright_patch_installed
    with _BROWSERGYM_PLAYWRIGHT_PATCH_LOCK:
        if _browsergym_playwright_patch_installed:
            return
        core = import_module("browsergym.core")
        environment_module = import_module("browsergym.core.env")
        chat_module = import_module("browsergym.core.chat")
        setattr(core, "_get_global_playwright", _get_thread_owned_browsergym_playwright)
        setattr(core, "_set_global_playwright", _set_thread_owned_browsergym_playwright)
        setattr(
            environment_module,
            "_get_global_playwright",
            _get_thread_owned_browsergym_environment_playwright,
        )
        setattr(chat_module, "_get_global_playwright", _get_thread_owned_browsergym_playwright)
        _browsergym_playwright_patch_installed = True


_PHYSICAL_PROPERTIES_SCRIPT = r"""el => {
  const classifyColor = raw => {
    const match = String(raw || '').match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const values = match[1].split(',').map(value => Number.parseFloat(value.trim()));
    if (values.length < 3 || values.slice(0, 3).some(value => !Number.isFinite(value))) return null;
    if (values.length > 3 && values[3] === 0) return null;
    const [r, g, b] = values.slice(0, 3).map(value => value / 255);
    const high = Math.max(r, g, b), low = Math.min(r, g, b), delta = high - low;
    let family = 'gray';
    if (delta >= 0.04) {
      let hue = high === r
        ? 60 * (((g - b) / delta) % 6)
        : high === g
          ? 60 * (((b - r) / delta) + 2)
          : 60 * (((r - g) / delta) + 4);
      if (hue < 0) hue += 360;
      family = ['red', 'yellow', 'green', 'cyan', 'blue', 'magenta'][Math.round(hue / 60) % 6];
    }
    const linear = value => value <= 0.04045
      ? value / 12.92
      : Math.pow((value + 0.055) / 1.055, 2.4);
    const luminance = 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
    const tone = luminance < 0.2 ? 'dark' : luminance > 0.65 ? 'light' : 'mid';
    return {family, tone};
  };
  const style = getComputedStyle(el);
  const backgroundAppearance = classifyColor(style.backgroundColor);
  const svgFill = el.namespaceURI === 'http://www.w3.org/2000/svg'
    ? classifyColor(style.fill)
    : null;
  const foregroundAppearance = svgFill || classifyColor(style.color);
  const legacyAppearance = (
    el.namespaceURI === 'http://www.w3.org/2000/svg' && !backgroundAppearance
      ? svgFill
      : backgroundAppearance
  );
  return ({
  readonly: ('readOnly' in el) ? Boolean(el.readOnly) : false,
  selected: (() => {
    if (el.classList.contains('selected')) return true;
    for (const name of ['aria-selected', 'aria-checked', 'aria-pressed']) {
      const value = el.getAttribute(name);
      if (value === 'true') return true;
      if (value === 'false') return false;
    }
    if ('checked' in el && ['checkbox', 'radio'].includes(String(el.type || '').toLowerCase())) {
      return Boolean(el.checked);
    }
    if (el.tagName.toLowerCase() === 'option') return Boolean(el.selected);
    return null;
  })(),
  // `classList.contains` is a closed boolean fact. Preserve false as well as
  // true so the Actor can distinguish an inactive control from an omitted
  // state field and can avoid toggling already-active controls.
  active: el.classList.contains('active'),
  colorFamily: legacyAppearance ? legacyAppearance.family : '',
  appearance: {
    foregroundFamily: foregroundAppearance ? foregroundAppearance.family : '',
    foregroundTone: foregroundAppearance ? foregroundAppearance.tone : '',
    backgroundFamily: backgroundAppearance ? backgroundAppearance.family : '',
    backgroundTone: backgroundAppearance ? backgroundAppearance.tone : '',
  },
  ariaHiddenByAncestor: Boolean(el.closest('[aria-hidden="true"]')),
  labelHint: (() => {
    const explicit = String(el.getAttribute('aria-label') || '').trim();
    if (explicit) return explicit;
    const title = String(el.getAttribute('title') || '').trim();
    if (title) return title;
    if ('labels' in el && el.labels && el.labels.length) {
      const value = Array.from(el.labels).map(label => label.textContent || '').join(' ').trim();
      if (value) return value;
    }
    const group = el.parentElement;
    if (group && group.querySelectorAll('input,textarea,select').length === 1) {
      const label = group.querySelector('label');
      if (label) return String(label.textContent || '').trim();
    }
    const tag = el.tagName.toLowerCase();
    const classes = el.classList;
    const explicitHtmlDrag = el.getAttribute('draggable') === 'true';
    const gestureCandidate = (
      explicitHtmlDrag ||
      el.getAttribute('aria-grabbed') === 'true' ||
      classes.contains('ui-draggable') ||
      classes.contains('ui-sortable-handle') ||
      classes.contains('ui-resizable-handle') ||
      Object.keys(el).some(key => key.endsWith('.drag'))
    );
    const svgCandidate = (
      el.namespaceURI === 'http://www.w3.org/2000/svg' &&
      ['circle', 'rect', 'polygon'].includes(tag)
    );
    if (!gestureCandidate && !svgCandidate) return '';
    const text = String(el.textContent || '').trim().replace(/\s+/g, ' ');
    if (text && text.length <= 120) return text;
    if (svgCandidate) {
      const fill = String(el.getAttribute('fill') || '').trim();
      const shape = tag === 'polygon' ? 'triangle' : tag === 'rect' ? 'rectangle' : tag;
      return [!fill || fill === 'none' ? '' : fill, shape].filter(Boolean).join(' ');
    }
    return '';
  })(),
  gesture: (() => {
    const classes = el.classList;
    const ownKeys = Object.keys(el);
    const d3Drag = ownKeys.some(key => key.endsWith('.drag'));
    const sortable = classes.contains('ui-sortable-handle');
    const resizable = classes.contains('ui-resizable-handle');
    const explicitHtmlDrag = el.getAttribute('draggable') === 'true';
    const movable = (
      explicitHtmlDrag ||
      el.getAttribute('aria-grabbed') === 'true' ||
      classes.contains('ui-draggable') ||
      sortable ||
      resizable ||
      d3Drag
    );
    const explicitDrop = (
      Boolean(el.getAttribute('aria-dropeffect')) ||
      classes.contains('ui-droppable')
    );
    const svgRect = (
      el.namespaceURI === 'http://www.w3.org/2000/svg' &&
      el.tagName.toLowerCase() === 'rect' &&
      !movable
    );
    const group = sortable
      ? el.closest('.ui-sortable')
      : el.namespaceURI === 'http://www.w3.org/2000/svg'
        ? el.ownerSVGElement
        : el.parentElement;
    return {
      role: movable ? 'draggable' : explicitDrop ? 'drop_target' : '',
      potentialSvgDrop: svgRect,
      groupBid: group ? String(group.getAttribute('bid') || '') : '',
      kind: sortable ? 'sort' : resizable ? 'resize' : d3Drag ? 'svg' : movable ? 'move' : '',
    };
  })(),
  bbox: (() => {
    const rect = el.getBoundingClientRect();
    return [rect.x, rect.y, rect.width, rect.height];
  })(),
  spatialHint: (() => {
    const rect = el.getBoundingClientRect();
    const group = el.classList.contains('ui-sortable-handle')
      ? el.closest('.ui-sortable')
      : el.namespaceURI === 'http://www.w3.org/2000/svg'
        ? el.ownerSVGElement
        : el.parentElement;
    const frame = group ? group.getBoundingClientRect() : {x: 0, y: 0, width: innerWidth, height: innerHeight};
    const centerX = rect.x + rect.width / 2;
    const centerY = rect.y + rect.height / 2;
    return {
      horizontal: centerX < frame.x + frame.width * 0.4 ? 'left' : centerX > frame.x + frame.width * 0.6 ? 'right' : 'center',
      vertical: centerY < frame.y + frame.height * 0.4 ? 'top' : centerY > frame.y + frame.height * 0.6 ? 'bottom' : 'middle',
    };
  })(),
  options: (el instanceof HTMLSelectElement) ? Array.from(el.options).map(option => ({
    label: String(option.label || option.textContent || '').trim(),
    value: String(option.value),
    selected: Boolean(option.selected)
  })) : [],
  focused: document.activeElement === el,
  focusable: (() => {
    if (el.disabled) return false;
    const tag = el.tagName.toLowerCase();
    const nativeFocusable = (
      ['input', 'select', 'textarea', 'button'].includes(tag) ||
      (tag === 'a' && Boolean(el.getAttribute('href'))) ||
      el.isContentEditable
    );
    if (nativeFocusable) return true;
    const tabindex = el.getAttribute('tabindex');
    if (tabindex === null || tabindex === '') return false;
    const parsed = Number.parseInt(tabindex, 10);
    return Number.isFinite(parsed) && parsed >= 0;
  })(),
  navigationPotential: (() => {
    const target = el.closest('a[href],area[href]');
    if (target) return true;
    const tag = el.tagName.toLowerCase();
    const type = String(el.getAttribute('type') || '').toLowerCase();
    if ((tag === 'button' && (!type || type === 'submit')) ||
        (tag === 'input' && ['submit', 'image'].includes(type))) {
      if (el.form || el.hasAttribute('formaction')) return true;
    }
    if (tag === 'input' && el.form && ![
      'button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit'
    ].includes(type)) return true;
    return false;
  })()
  })
}"""

# BrowserGym already captures the page in one DOM/AX transaction.  Enrich the
# BIDs from that transaction in one browser-side pass per frame; one Playwright
# locator round trip per AX node makes large document pages effectively
# unbounded and prevents the surrounding asyncio watchdog from running.
_BULK_PHYSICAL_PROPERTIES_SCRIPT = r"""bids => {
  const inspect = (""" + _PHYSICAL_PROPERTIES_SCRIPT + r""");
  const wanted = new Set(bids);
  const result = {};
  for (const el of document.querySelectorAll('[bid]')) {
    const bid = String(el.getAttribute('bid') || '');
    if (!wanted.has(bid)) continue;
    const physical = inspect(el);
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const disabled = Boolean(
      ('disabled' in el && el.disabled) || el.getAttribute('aria-disabled') === 'true'
    );
    const readonly = Boolean(
      physical.readonly || el.getAttribute('aria-readonly') === 'true'
    );
    const tag = el.tagName.toLowerCase();
    const type = String(el.getAttribute('type') || '').toLowerCase();
    const textEditable = (
      tag === 'textarea' ||
      (tag === 'input' && ![
        'button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio',
        'range', 'reset', 'submit'
      ].includes(type)) ||
      el.isContentEditable
    );
    const visible = typeof el.checkVisibility === 'function'
      ? el.checkVisibility({checkOpacity: false, checkVisibilityCSS: true})
      : style.display !== 'none' && style.visibility !== 'hidden' &&
        (rect.width > 0 || rect.height > 0 || el.getClientRects().length > 0);
    result[bid] = {
      ...physical,
      attached: el.isConnected,
      visible: Boolean(visible),
      enabled: !disabled,
      readonly,
      editable: !disabled && !readonly && textEditable
    };
  }
  return result;
}"""

_VERIFIER_PROBE_SCRIPT = """() => {
  const facts = {
    url: location.href
  };
  if ('WOB_EPISODE_ID' in window) facts.episode = window.WOB_EPISODE_ID;
  if ('WOB_TASK_READY' in window) facts.ready = window.WOB_TASK_READY;
  if ('WOB_DONE_GLOBAL' in window) facts.done = window.WOB_DONE_GLOBAL;
  if ('WOB_RAW_REWARD_GLOBAL' in window) facts.raw_reward = window.WOB_RAW_REWARD_GLOBAL;
  return facts;
}"""

_STABLE_OBSERVATION_ATTEMPTS = 2
_STABLE_OBSERVATION_WAIT_MS = 120
_NAVIGATION_START_GRACE_MS = 450
_NAVIGATION_COMPLETION_TIMEOUT_MS = 5_000
_DOM_QUIET_WINDOW_MS = 80
_DOM_QUIET_TIMEOUT_MS = 1_500

_INSTALL_DOM_QUIET_TRACKER = r"""() => {
  const key = '__affordanceRuntimeLastMutation';
  window[key] = performance.now();
  const observer = new MutationObserver(() => { window[key] = performance.now(); });
  observer.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
}"""

_DOM_IS_QUIET = r"""quietMs => {
  const value = window.__affordanceRuntimeLastMutation;
  return typeof value === 'number' && performance.now() - value >= quietMs;
}"""


class _NavigationRequestPort(Protocol):
    frame: object

    def is_navigation_request(self) -> bool: ...


class _PagePort(Protocol):
    url: str
    main_frame: object

    def on(self, event: str, handler: Callable[..., object]) -> None: ...
    def remove_listener(self, event: str, handler: Callable[..., object]) -> None: ...
    def evaluate(self, expression: str, arg: object = ...) -> object: ...
    def wait_for_event(self, event: str, **kwargs: object) -> object: ...
    def wait_for_load_state(self, state: str, **kwargs: object) -> None: ...
    def wait_for_function(self, expression: str, **kwargs: object) -> object: ...


class _StepEnvironmentPort(Protocol):
    def step(self, action: str) -> object: ...


class _UnwrappedPort(Protocol):
    page: _PagePort

    def _get_obs(self) -> object: ...


@dataclass
class _NavigationWatcher:
    page: _PagePort
    started_at: float
    before_url: str
    before_document_epoch: int
    navigation_started: float | None = None
    navigation_committed: float | None = None
    dom_content_loaded: float | None = None
    commit_count: int = 0

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.started_at) * 1000, 3)

    def on_request(self, request: object) -> None:
        try:
            request = cast(_NavigationRequestPort, request)
            if request.is_navigation_request() and request.frame == self.page.main_frame:
                self.navigation_started = self.navigation_started or self.elapsed_ms()
        except BaseException:
            return

    def on_commit(self, frame: object) -> None:
        try:
            if frame == self.page.main_frame:
                self.navigation_started = self.navigation_started or self.elapsed_ms()
                self.navigation_committed = self.navigation_committed or self.elapsed_ms()
                self.commit_count += 1
        except BaseException:
            return

    def on_dom_content_loaded(self) -> None:
        if self.navigation_committed is not None:
            self.dom_content_loaded = self.dom_content_loaded or self.elapsed_ms()

    def install(self) -> None:
        self.page.on("request", self.on_request)
        self.page.on("framenavigated", self.on_commit)
        self.page.on("domcontentloaded", self.on_dom_content_loaded)
        try:
            self.page.evaluate(_INSTALL_DOM_QUIET_TRACKER)
        except BaseException:
            pass

    def remove(self) -> None:
        for event, handler in (
            ("request", self.on_request),
            ("framenavigated", self.on_commit),
            ("domcontentloaded", self.on_dom_content_loaded),
        ):
            try:
                self.page.remove_listener(event, handler)
            except BaseException:
                pass


class ThreadBoundBrowserGym:
    """Small synchronous facade; no page, locator, or element handle crosses the thread."""

    def __init__(
        self,
        task_id: str,
        *,
        headless: bool = True,
        registration_modules: tuple[str, ...] = ("browsergym.miniwob",),
        environment_playwright_factory: Callable[[object], object] | None = None,
    ) -> None:
        self._commands: queue.Queue[
            tuple[str, tuple[object, ...], dict[str, object], Future[object]] | None
        ] = queue.Queue()
        self._command_timed_out = threading.Event()
        self._ready: Future[object] = Future()
        self._thread = threading.Thread(
            target=self._run,
            args=(task_id, headless, registration_modules, environment_playwright_factory),
            daemon=True,
        )
        self.owner_thread_ident: int | None = None
        self.last_capture_thread_ident: int | None = None
        self.last_currentness_probe_thread_ident: int | None = None
        self.currentness_probe_calls = 0
        self._thread.start()
        ready = self._ready.result(timeout=60)
        self.supports_capture_current = bool(ready)
        self.browser = object()
        self.context = object()
        self.unwrapped = self
        self._closed = False

    def _run(
        self,
        task_id: str,
        headless: bool,
        registration_modules: tuple[str, ...],
        environment_playwright_factory: Callable[[object], object] | None,
    ) -> None:
        try:
            self.owner_thread_ident = threading.get_ident()
            import gymnasium as gym  # type: ignore[import-not-found]

            for module in registration_modules:
                import_module(module)
            _install_thread_owned_browsergym_playwright()
            if environment_playwright_factory is not None:
                owner = _get_thread_owned_browsergym_playwright()
                _set_thread_owned_browsergym_environment_playwright(
                    environment_playwright_factory(owner)
                )
            # BrowserGym's default ``standard_html`` marking omits SVG child
            # elements.  Those elements still appear as clickable in the CDP
            # DOM snapshot, but without a BrowserGym ID they cannot participate
            # in the identity-based control plane.  Mark every DOM element so
            # clickable SVG/path/circle/text nodes receive private BIDs and can
            # be executed through BrowserGym/Playwright rather than coordinates.
            environment = gym.make(task_id, headless=headless, tags_to_mark="all")
            unwrapped = getattr(environment, "unwrapped", environment)
            getter = getattr(unwrapped, "_get_obs", None)
            # BrowserGym creates its page during reset. The pinned read-only API
            # itself is the capability signal; it is called only after reset.
            self._ready.set_result(callable(getter))
        except BaseException as exc:
            _set_thread_owned_browsergym_environment_playwright(None)
            playwright = getattr(_BROWSERGYM_PLAYWRIGHT_LOCAL, "playwright", None)
            if playwright is not None:
                try:
                    playwright.stop()
                except BaseException:
                    pass
                _set_thread_owned_browsergym_playwright(None)
            self._ready.set_exception(exc)
            return
        document_epoch = 0
        while (command := self._commands.get()) is not None:
            name, args, kwargs, outcome = command
            try:
                unwrapped = getattr(environment, "unwrapped", environment)
                value: object
                if name == "currentness_probe":
                    self.currentness_probe_calls += 1
                    self.last_currentness_probe_thread_ident = threading.get_ident()
                    getter = getattr(unwrapped, "_get_obs", None)
                    if not callable(getter):
                        raise RuntimeError("pinned BrowserGym has no read-only observation API")
                    started = time.perf_counter()
                    raw = _with_private_control_properties(unwrapped.page, getter())
                    verifier = unwrapped.page.evaluate(_VERIFIER_PROBE_SCRIPT)
                    value = {
                        "raw": raw,
                        "task": verifier,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                elif name == "session_health":
                    page = getattr(unwrapped, "page", None)
                    context = getattr(page, "context", None)
                    browser = getattr(context, "browser", None)
                    value = {
                        "page_closed": page.is_closed() if page is not None else None,
                        "browser_connected": (
                            browser.is_connected()
                            if browser is not None and callable(getattr(browser, "is_connected", None))
                            else None
                        ),
                    }
                elif name == "capture_current":
                    self.last_capture_thread_ident = threading.get_ident()
                    getter = getattr(unwrapped, "_get_obs", None)
                    if not callable(getter):
                        raise RuntimeError("pinned BrowserGym has no read-only observation API")
                    raw = _with_stable_private_control_properties(unwrapped.page, getter, getter())
                    verifier = unwrapped.page.evaluate(_VERIFIER_PROBE_SCRIPT)
                    value = (raw, verifier)
                elif name == "causal_step":
                    action, may_navigate = cast(tuple[str, bool], args)
                    value, document_epoch = _causal_step(
                        environment,
                        unwrapped,
                        action,
                        may_navigate=may_navigate,
                        document_epoch=document_epoch,
                    )
                else:
                    value = getattr(environment, name)(*args, **kwargs)
                    getter = getattr(unwrapped, "_get_obs", None)
                    if name == "reset":
                        reset_raw, info = cast(tuple[object, object], value)
                        document_epoch += 1
                        value = (
                            _with_stable_private_control_properties(unwrapped.page, getter, reset_raw),
                            info,
                        )
                    elif name == "close":
                        import browsergym.core as browsergym_core  # type: ignore[import-not-found]

                        _set_thread_owned_browsergym_environment_playwright(None)
                        playwright = browsergym_core._get_global_playwright()
                        playwright.stop()
                        browsergym_core._set_global_playwright(None)
                outcome.set_result(value)
            except BaseException as exc:
                outcome.set_exception(exc)

    def _call(
        self,
        name: str,
        *args: object,
        wait_timeout_s: float = 180.0,
        **kwargs: object,
    ) -> object:
        if self._closed:
            raise RuntimeError("BrowserGym owner thread is closed")
        if self._command_timed_out.is_set():
            raise RuntimeError("BrowserGym owner is unavailable after a command timeout")
        outcome: Future[object] = Future()
        self._commands.put((name, args, kwargs, outcome))
        try:
            return outcome.result(timeout=wait_timeout_s)
        except FutureTimeoutError as exc:
            # ``Future.result`` also propagates a TimeoutError raised by a
            # completed command.  Only an unfinished Future proves that the
            # owner itself exceeded this call's service deadline.
            if outcome.done():
                raise
            self._command_timed_out.set()
            raise TimeoutError(
                f"BrowserGym owner command {name!r} exceeded {wait_timeout_s:.3f}s"
            ) from exc

    def reset(self, *, seed: int):
        return self._call("reset", seed=seed)

    def step(self, action: str, *, may_navigate: bool):
        return self._call("causal_step", action, may_navigate)

    def send_msg_to_user(self, content: str):
        import json

        return self._call("step", f"send_msg_to_user({json.dumps(content, ensure_ascii=False)})")

    def currentness_probe(self, bid: str):
        return self._call("currentness_probe", bid)

    def session_health(self):
        return self._call("session_health", wait_timeout_s=5.0)

    def capture_current(self):
        if not self.supports_capture_current:
            raise RuntimeError("pinned BrowserGym read-only capture is unavailable")
        return self._call("capture_current")

    def close(self) -> None:
        if self._closed:
            return
        if self._command_timed_out.is_set():
            # Python cannot safely cancel synchronous Playwright work running
            # in another thread.  Do not queue cleanup behind that work for
            # another full command timeout; arrange for the daemon owner to
            # exit if it ever returns and fail cleanup promptly.
            self._commands.put(None)
            self._thread.join(timeout=1)
            self._closed = True
            self.browser = None
            self.context = None
            if self._thread.is_alive():
                raise RuntimeError("BrowserGym owner remained busy after a command timeout")
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


def _causal_step(
    environment: object,
    unwrapped: object,
    action: str,
    *,
    may_navigate: bool,
    document_epoch: int,
) -> tuple[BrowserGymStepTransition, int]:
    """Dispatch once and return only a causally stable post-state or typed instability."""

    environment = cast(_StepEnvironmentPort, environment)
    unwrapped = cast(_UnwrappedPort, unwrapped)
    before_page = unwrapped.page
    getter = getattr(unwrapped, "_get_obs", None)
    if not callable(getter):
        raise RuntimeError("pinned BrowserGym has no read-only observation API")
    started_at = time.perf_counter()
    watcher = _NavigationWatcher(
        before_page,
        started_at,
        str(getattr(before_page, "url", "")),
        document_epoch,
    )
    watcher.install()
    try:
        value = environment.step(action)
        _step_raw, reward, terminated, truncated, info = cast(
            tuple[object, object, object, object, object], value,
        )
        dispatch_returned = watcher.elapsed_ms()
        after_page = unwrapped.page

        if may_navigate and watcher.navigation_started is None:
            try:
                before_page.wait_for_event(
                    "request",
                    predicate=lambda request: (
                        request.is_navigation_request()
                        and request.frame == before_page.main_frame
                    ),
                    timeout=_NAVIGATION_START_GRACE_MS,
                )
            except BaseException:
                pass

        if watcher.navigation_started is not None and watcher.navigation_committed is None:
            try:
                before_page.wait_for_event(
                    "framenavigated",
                    predicate=lambda frame: frame == before_page.main_frame,
                    timeout=_NAVIGATION_COMPLETION_TIMEOUT_MS,
                )
            except BaseException:
                pass

        if watcher.navigation_committed is not None and watcher.dom_content_loaded is None:
            try:
                before_page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=_NAVIGATION_COMPLETION_TIMEOUT_MS,
                )
                watcher.dom_content_loaded = watcher.elapsed_ms()
            except BaseException:
                pass

        epoch_after_navigation = document_epoch + watcher.commit_count
        if watcher.navigation_started is not None and (
            watcher.navigation_committed is None or watcher.dom_content_loaded is None
        ):
            trace = _transition_trace(
                watcher,
                dispatch_returned,
                BrowserGymStabilityStatus.NAVIGATION_PENDING,
                epoch_after_navigation,
                after_page=after_page,
            )
            return BrowserGymStepTransition(
                None,
                reward,
                terminated,
                truncated,
                _step_info(info),
                trace,
            ), epoch_after_navigation

        # A navigation replaces the document and its MutationObserver, while a
        # tab action changes the active page entirely. In both cases install the
        # quiet predicate on BrowserGym's authoritative post-action page.
        if watcher.navigation_committed is not None or after_page is not before_page:
            try:
                after_page.evaluate(_INSTALL_DOM_QUIET_TRACKER)
            except BaseException:
                trace = _transition_trace(
                    watcher,
                    dispatch_returned,
                    BrowserGymStabilityStatus.ACQUISITION_UNSTABLE,
                    epoch_after_navigation,
                    after_page=after_page,
                )
                return BrowserGymStepTransition(
                    None,
                    reward,
                    terminated,
                    truncated,
                    _step_info(info),
                    trace,
                ), epoch_after_navigation
        try:
            after_page.wait_for_function(
                _DOM_IS_QUIET,
                arg=_DOM_QUIET_WINDOW_MS,
                timeout=_DOM_QUIET_TIMEOUT_MS,
            )
        except BaseException:
            trace = _transition_trace(
                watcher,
                dispatch_returned,
                BrowserGymStabilityStatus.ACQUISITION_UNSTABLE,
                epoch_after_navigation,
                after_page=after_page,
            )
            return BrowserGymStepTransition(
                None,
                reward,
                terminated,
                truncated,
                _step_info(info),
                trace,
            ), epoch_after_navigation

        post_capture_started = watcher.elapsed_ms()
        raw = _with_private_control_properties(after_page, getter())
        post_capture_completed = watcher.elapsed_ms()
        status = (
            BrowserGymStabilityStatus.STABLE_NAVIGATION
            if watcher.navigation_committed is not None
            else BrowserGymStabilityStatus.STABLE_NO_NAVIGATION
        )
        trace = _transition_trace(
            watcher,
            dispatch_returned,
            status,
            epoch_after_navigation,
            after_page=after_page,
            post_capture_started=post_capture_started,
            post_capture_completed=post_capture_completed,
        )
        return BrowserGymStepTransition(
            raw,
            reward,
            terminated,
            truncated,
            _step_info(info),
            trace,
        ), epoch_after_navigation
    finally:
        watcher.remove()


def _transition_trace(
    watcher: _NavigationWatcher,
    dispatch_returned: float,
    status: BrowserGymStabilityStatus,
    after_document_epoch: int,
    *,
    after_page: _PagePort,
    post_capture_started: float | None = None,
    post_capture_completed: float | None = None,
) -> BrowserGymTransitionTrace:
    return BrowserGymTransitionTrace(
        0.0,
        dispatch_returned,
        watcher.navigation_started,
        watcher.navigation_committed,
        post_capture_started,
        post_capture_completed,
        watcher.before_url,
        str(getattr(after_page, "url", "")),
        watcher.before_document_epoch,
        after_document_epoch,
        status,
    )


def _step_info(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("BrowserGym step info is not a mapping")
    return value


def _with_private_control_properties(page: object, raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise RuntimeError("BrowserGym observation is not a mapping")
    tree = raw.get("axtree_object")
    nodes = tree.get("nodes") if isinstance(tree, dict) else None
    if not isinstance(nodes, list):
        raise RuntimeError("BrowserGym observation omitted AX nodes")
    bids = tuple(dict.fromkeys(
        bid for node in nodes if isinstance(node, dict)
        for bid in (node.get("browsergym_id"),)
        if isinstance(bid, str) and bid
    ))
    dom_extra = raw.get("extra_element_properties")
    dom_extra = dom_extra if isinstance(dom_extra, dict) else {}
    captured = _bulk_physical_properties(page, bids)
    properties: dict[str, object] = {}
    for bid in bids:
        physical = captured.get(bid)
        physical = physical if isinstance(physical, dict) else {}
        attached = physical.get("attached")
        visible = physical.get("visible")
        enabled = physical.get("enabled")
        editable = physical.get("editable")
        readonly = physical.get("readonly")
        options = physical.get("options")
        bbox = physical.get("bbox")
        snapshot_properties = dom_extra.get(bid)
        if isinstance(snapshot_properties, dict):
            # BrowserGym scales DOMSnapshot geometry to the screenshot.  Keep
            # that geometry for E-ref/SoM projection; locator geometry is in
            # CSS pixels and would misalign marks when bgym_scale_factor != 1.
            snapshot_bbox = snapshot_properties.get("bbox")
            if isinstance(snapshot_bbox, list):
                bbox = snapshot_bbox
        label_hint = physical.get("labelHint")
        gesture = physical.get("gesture")
        gesture = gesture if isinstance(gesture, dict) else {}
        spatial = physical.get("spatialHint")
        spatial = spatial if isinstance(spatial, dict) else {}
        appearance = physical.get("appearance")
        appearance = appearance if isinstance(appearance, dict) else {}
        properties[bid] = {
            "attached": attached if isinstance(attached, bool) else False,
            "visible": _effective_visibility(
                visible if isinstance(visible, bool) else None,
                physical,
            ),
            "enabled": enabled if isinstance(enabled, bool) else None,
            "readonly": readonly if isinstance(readonly, bool) else None,
            "selected": (
                physical.get("selected")
                if isinstance(physical.get("selected"), bool)
                else None
            ),
            "active": (
                physical["active"]
                if isinstance(physical.get("active"), bool)
                else None
            ),
            "color_family": (
                physical.get("colorFamily")
                if isinstance(physical.get("colorFamily"), str)
                else ""
            ),
            "foreground_color_family": (
                appearance.get("foregroundFamily")
                if isinstance(appearance.get("foregroundFamily"), str)
                else ""
            ),
            "foreground_tone": (
                appearance.get("foregroundTone")
                if isinstance(appearance.get("foregroundTone"), str)
                else ""
            ),
            "background_color_family": (
                appearance.get("backgroundFamily")
                if isinstance(appearance.get("backgroundFamily"), str)
                else ""
            ),
            "background_tone": (
                appearance.get("backgroundTone")
                if isinstance(appearance.get("backgroundTone"), str)
                else ""
            ),
            "editable": editable if isinstance(editable, bool) else None,
            "focusable": (
                physical["focusable"]
                if isinstance(physical.get("focusable"), bool)
                else None
            ),
            "focused": (
                physical["focused"]
                if isinstance(physical.get("focused"), bool)
                else None
            ),
            "options": options if isinstance(options, list) else [],
            "bbox": bbox if isinstance(bbox, list) else [],
            "label_hint": label_hint if isinstance(label_hint, str) else "",
            "gesture_role": (
                gesture.get("role") if gesture.get("role") in {"draggable", "drop_target"} else ""
            ),
            "gesture_group": (
                gesture.get("groupBid") if isinstance(gesture.get("groupBid"), str) else ""
            ),
            "gesture_kind": (
                gesture.get("kind") if isinstance(gesture.get("kind"), str) else ""
            ),
            "potential_svg_drop": gesture.get("potentialSvgDrop") is True,
            "navigation_potential": physical.get("navigationPotential") is True,
            "spatial_horizontal": (
                spatial.get("horizontal") if spatial.get("horizontal") in {"left", "center", "right"} else ""
            ),
            "spatial_vertical": (
                spatial.get("vertical") if spatial.get("vertical") in {"top", "middle", "bottom"} else ""
            ),
        }
    drag_groups = {
        item.get("gesture_group")
        for item in properties.values()
        if isinstance(item, dict) and item.get("gesture_role") == "draggable"
    }
    for item in properties.values():
        if (
            isinstance(item, dict)
            and item.get("potential_svg_drop") is True
            and item.get("gesture_group") in drag_groups
        ):
            item["gesture_role"] = "drop_target"
    enriched = dict(raw)
    enriched[PRIVATE_CONTROL_PROPERTIES_KEY] = properties
    return enriched


def _bulk_physical_properties(
    page: object,
    bids: tuple[str, ...],
) -> dict[str, object]:
    if not bids:
        return {}
    wanted = frozenset(bids)
    frames = getattr(page, "frames", None)
    owners = tuple(frames) if isinstance(frames, list | tuple) and frames else (page,)
    captured: dict[str, object] = {}
    for owner in owners:
        evaluate = getattr(owner, "evaluate", None)
        if not callable(evaluate):
            continue
        try:
            values = evaluate(_BULK_PHYSICAL_PROPERTIES_SCRIPT, list(bids))
        except BaseException:
            continue
        if not isinstance(values, dict):
            continue
        captured.update(
            (bid, value)
            for bid, value in values.items()
            if isinstance(bid, str) and bid in wanted and isinstance(value, dict)
        )
    return captured


def _with_stable_private_control_properties(page: object, getter: object, raw: object) -> dict[str, object]:
    enriched = _with_private_control_properties(page, raw)
    if not callable(getter):
        return enriched
    signature = _executable_signature(enriched)
    for _attempt in range(_STABLE_OBSERVATION_ATTEMPTS):
        _wait_for_stable_sample(page)
        try:
            candidate = _with_private_control_properties(page, getter())
        except BaseException:
            return enriched
        candidate_signature = _executable_signature(candidate)
        if candidate_signature == signature:
            return candidate
        enriched = candidate
        signature = candidate_signature
    return enriched


def _wait_for_stable_sample(page: object) -> None:
    try:
        page.wait_for_timeout(_STABLE_OBSERVATION_WAIT_MS)
    except BaseException:
        time.sleep(_STABLE_OBSERVATION_WAIT_MS / 1000)


def _executable_signature(raw: dict[str, object]) -> tuple[object, ...]:
    try:
        from affordance_runtime.surfaces.browsergym.semantics import analyze_browsergym_semantics

        analysis = analyze_browsergym_semantics(raw)
    except BaseException:
        return ()
    return tuple(
        (
            item.private_node_id,
            item.private_bid,
            item.role,
            item.accessible_name,
            tuple((offer.semantic_action, offer.primitive_action) for offer in item.executable_offers),
        )
        for item in analysis.controls
    )


def _effective_visibility(visible: bool | None, physical: dict[str, object]) -> bool | None:
    """Fail closed when an otherwise laid-out control is inside aria-hidden content."""

    return False if physical.get("ariaHiddenByAncestor") is True else visible
