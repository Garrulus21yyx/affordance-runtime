"""Own BrowserGym's synchronous Playwright lifecycle on one private thread."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future
from typing import cast

from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)

_PHYSICAL_PROPERTIES_SCRIPT = """el => ({
  readonly: ('readOnly' in el) ? Boolean(el.readOnly) : false,
  ariaHiddenByAncestor: Boolean(el.closest('[aria-hidden="true"]')),
  labelHint: (() => {
    const explicit = String(el.getAttribute('aria-label') || '').trim();
    if (explicit) return explicit;
    if ('labels' in el && el.labels && el.labels.length) {
      const value = Array.from(el.labels).map(label => label.textContent || '').join(' ').trim();
      if (value) return value;
    }
    const group = el.parentElement;
    if (group && group.querySelectorAll('input,textarea,select').length === 1) {
      const label = group.querySelector('label');
      if (label) return String(label.textContent || '').trim();
    }
    return '';
  })(),
  bbox: (() => {
    const rect = el.getBoundingClientRect();
    return [rect.x, rect.y, rect.width, rect.height];
  })(),
  options: (el instanceof HTMLSelectElement) ? Array.from(el.options).map(option => ({
    label: String(option.label || option.textContent || '').trim(),
    value: String(option.value),
    selected: Boolean(option.selected)
  })) : []
})"""

_VERIFIER_PROBE_SCRIPT = """() => {
  const facts = {
    episode: String(window.WOB_EPISODE_ID),
    url: location.href
  };
  if ('WOB_TASK_READY' in window) facts.ready = window.WOB_TASK_READY;
  if ('WOB_DONE_GLOBAL' in window) facts.done = window.WOB_DONE_GLOBAL;
  if ('WOB_RAW_REWARD_GLOBAL' in window) facts.raw_reward = window.WOB_RAW_REWARD_GLOBAL;
  return facts;
}"""


class ThreadBoundBrowserGym:
    """Small synchronous facade; no page, locator, or element handle crosses the thread."""

    def __init__(self, task_id: str, *, headless: bool = True) -> None:
        self._commands: queue.Queue[
            tuple[str, tuple[object, ...], dict[str, object], Future[object]] | None
        ] = queue.Queue()
        self._ready: Future[object] = Future()
        self._thread = threading.Thread(target=self._run, args=(task_id, headless), daemon=True)
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

    def _run(self, task_id: str, headless: bool) -> None:
        try:
            self.owner_thread_ident = threading.get_ident()
            import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
            import gymnasium as gym  # type: ignore[import-not-found]

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
                elif name == "capture_current":
                    self.last_capture_thread_ident = threading.get_ident()
                    getter = getattr(unwrapped, "_get_obs", None)
                    if not callable(getter):
                        raise RuntimeError("pinned BrowserGym has no read-only observation API")
                    raw = _with_private_control_properties(unwrapped.page, getter())
                    verifier = unwrapped.page.evaluate(_VERIFIER_PROBE_SCRIPT)
                    value = (raw, verifier)
                else:
                    value = getattr(environment, name)(*args, **kwargs)
                    if name == "reset":
                        reset_raw, info = cast(tuple[object, object], value)
                        value = (_with_private_control_properties(unwrapped.page, reset_raw), info)
                    elif name == "step":
                        step_raw, reward, terminated, truncated, info = cast(
                            tuple[object, object, object, object, object], value,
                        )
                        value = (
                            _with_private_control_properties(unwrapped.page, step_raw),
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

    def currentness_probe(self, bid: str):
        return self._call("currentness_probe", bid)

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
        properties[bid] = {
            "attached": attached,
            "visible": _effective_visibility(visible, physical),
            "enabled": enabled,
            "readonly": readonly if isinstance(readonly, bool) else None,
            "editable": editable,
            "options": options if isinstance(options, list) else [],
            "bbox": bbox if isinstance(bbox, list) else [],
            "label_hint": label_hint if isinstance(label_hint, str) else "",
        }
    enriched = dict(raw)
    enriched[PRIVATE_CONTROL_PROPERTIES_KEY] = properties
    return enriched


def _effective_visibility(visible: bool | None, physical: dict[str, object]) -> bool | None:
    """Fail closed when an otherwise laid-out control is inside aria-hidden content."""

    return False if physical.get("ariaHiddenByAncestor") is True else visible
