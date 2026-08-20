"""Own BrowserGym's synchronous Playwright lifecycle on one private thread."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from importlib import import_module
from typing import cast

from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)

_PHYSICAL_PROPERTIES_SCRIPT = r"""el => ({
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
  colorFamily: (() => {
    const style = getComputedStyle(el);
    const background = style.backgroundColor;
    const raw = (
      el.namespaceURI === 'http://www.w3.org/2000/svg' &&
      (!background || background === 'transparent' || background === 'rgba(0, 0, 0, 0)')
        ? style.fill
        : background
    );
    const match = raw.match(/rgba?\(([^)]+)\)/);
    if (!match) return '';
    const values = match[1].split(',').map(value => Number.parseFloat(value.trim()));
    if (values.length < 3 || values.slice(0, 3).some(value => !Number.isFinite(value))) return '';
    if (values.length > 3 && values[3] === 0) return '';
    const [r, g, b] = values.slice(0, 3).map(value => value / 255);
    const high = Math.max(r, g, b), low = Math.min(r, g, b), delta = high - low;
    if (delta < 0.04) return 'gray';
    let hue = high === r
      ? 60 * (((g - b) / delta) % 6)
      : high === g
        ? 60 * (((b - r) / delta) + 2)
        : 60 * (((r - g) / delta) + 4);
    if (hue < 0) hue += 360;
    return ['red', 'yellow', 'green', 'cyan', 'blue', 'magenta'][Math.round(hue / 60) % 6];
  })(),
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
  })()
})"""

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


class ThreadBoundBrowserGym:
    """Small synchronous facade; no page, locator, or element handle crosses the thread."""

    def __init__(
        self,
        task_id: str,
        *,
        headless: bool = True,
        registration_modules: tuple[str, ...] = ("browsergym.miniwob",),
    ) -> None:
        self._commands: queue.Queue[
            tuple[str, tuple[object, ...], dict[str, object], Future[object]] | None
        ] = queue.Queue()
        self._ready: Future[object] = Future()
        self._thread = threading.Thread(
            target=self._run,
            args=(task_id, headless, registration_modules),
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

    def _run(self, task_id: str, headless: bool, registration_modules: tuple[str, ...]) -> None:
        try:
            self.owner_thread_ident = threading.get_ident()
            import gymnasium as gym  # type: ignore[import-not-found]

            for module in registration_modules:
                import_module(module)
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
            self._ready.set_exception(exc)
            return
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
                else:
                    value = getattr(environment, name)(*args, **kwargs)
                    getter = getattr(unwrapped, "_get_obs", None)
                    if name == "reset":
                        reset_raw, info = cast(tuple[object, object], value)
                        value = (
                            _with_stable_private_control_properties(unwrapped.page, getter, reset_raw),
                            info,
                        )
                    elif name == "step":
                        step_raw, reward, terminated, truncated, info = cast(
                            tuple[object, object, object, object, object], value,
                        )
                        value = (
                            _with_stable_private_control_properties(unwrapped.page, getter, step_raw),
                            reward, terminated, truncated, info,
                        )
                    elif name == "close":
                        import browsergym.core as browsergym_core  # type: ignore[import-not-found]

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
        outcome: Future[object] = Future()
        self._commands.put((name, args, kwargs, outcome))
        return outcome.result(timeout=wait_timeout_s)

    def reset(self, *, seed: int):
        return self._call("reset", seed=seed)

    def step(self, action: str):
        return self._call("step", action)

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


def _with_private_control_properties(page: object, raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise RuntimeError("BrowserGym observation is not a mapping")
    tree = raw.get("axtree_object")
    nodes = tree.get("nodes") if isinstance(tree, dict) else None
    if not isinstance(nodes, list):
        raise RuntimeError("BrowserGym observation omitted AX nodes")
    from browsergym.core.action.utils import get_elem_by_bid  # type: ignore[import-not-found]

    bids = tuple(dict.fromkeys(
        bid for node in nodes if isinstance(node, dict)
        for bid in (node.get("browsergym_id"),)
        if isinstance(bid, str) and bid
    ))
    dom_extra = raw.get("extra_element_properties")
    dom_extra = dom_extra if isinstance(dom_extra, dict) else {}
    properties: dict[str, object] = {}
    for bid in bids:
        try:
            locator = get_elem_by_bid(page, bid)
            attached = locator.count() > 0
        except BaseException:
            properties[bid] = {
                "attached": False,
                "visible": False,
                "enabled": None,
                "readonly": None,
                "editable": None,
                "options": [],
            }
            continue
        try:
            visible: bool | None = locator.is_visible(timeout=500)
        except BaseException:
            visible = None
        try:
            enabled: bool | None = locator.is_enabled(timeout=500)
        except BaseException:
            enabled = None
        try:
            editable: bool | None = locator.is_editable(timeout=500)
        except BaseException:
            editable = None
        try:
            physical = locator.evaluate(_PHYSICAL_PROPERTIES_SCRIPT)
        except BaseException:
            physical = {}
        physical = physical if isinstance(physical, dict) else {}
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
        properties[bid] = {
            "attached": attached,
            "visible": _effective_visibility(visible, physical),
            "enabled": enabled,
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
            "editable": editable,
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
