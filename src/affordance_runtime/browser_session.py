"""Isolated, injectable browser session for observation and execution.

This is adapted from the earlier repository without importing a package named
``src``. Playwright is loaded lazily through the ``web`` optional extra.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.contracts import Observation


class PageDriver(Protocol):
    def goto(self, url: str, **kwargs: Any) -> Any: ...

    def content(self) -> str: ...

    def click(self, selector: str) -> Any: ...

    def fill(self, selector: str, value: str) -> Any: ...

    def screenshot(self, **kwargs: Any) -> bytes: ...

    def wait_for_load_state(self, state: str = "load", **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class BrowserSnapshot:
    observation: Observation
    affordance_model: PageAffordanceModel


class BrowserSession:
    """One browser context owned by one runtime run."""

    def __init__(
        self,
        page: PageDriver,
        *,
        initial_url: str = "",
        owner: Any = None,
        lease_ttl_ms: int = 2_000,
    ) -> None:
        self._page = page
        self._initial_url = initial_url
        self._owner = owner
        self._lease_ttl_ms = lease_ttl_ms
        self._dom = DomAdapter()

    @classmethod
    def launch(
        cls,
        url: str,
        *,
        headless: bool = True,
        action_timeout_ms: int = 8_000,
        navigation_attempts: int = 3,
        lease_ttl_ms: int = 2_000,
    ) -> "BrowserSession":
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed; install affordance-runtime[web]") from exc

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(action_timeout_ms)
        last_error: Exception | None = None
        for attempt in range(max(1, navigation_attempts)):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < navigation_attempts:
                    time.sleep(0.5)
        if last_error is not None:
            context.close()
            browser.close()
            playwright.stop()
            raise last_error
        return cls(
            cast(PageDriver, page),
            initial_url=url,
            owner=(playwright, browser, context),
            lease_ttl_ms=lease_ttl_ms,
        )

    def open(self, url: str) -> None:
        self._page.goto(url)

    def reset(self) -> None:
        if self._initial_url:
            self._page.goto(self._initial_url)

    def close(self) -> None:
        if self._owner is None:
            return
        playwright, browser, context = self._owner
        context.close()
        browser.close()
        playwright.stop()
        self._owner = None

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def url(self) -> str:
        return str(getattr(self._page, "url", "") or self._initial_url)

    @property
    def browser_version(self) -> str:
        if self._owner is None:
            return ""
        browser = self._owner[1]
        return str(getattr(browser, "version", ""))

    def capture(
        self,
        *,
        page_id: str = "page",
        ttl_ms: int | None = None,
        screenshot_path: str | None = None,
    ) -> BrowserSnapshot:
        """Capture one coherent HTML observation and derive its affordances."""

        html = self._page.content()
        url = self.url
        snapshot_id = f"snap_{uuid.uuid4().hex}"
        dom_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        environment_revision = hashlib.sha256(f"{url}\0{dom_hash}".encode()).hexdigest()
        screenshot_ref = ""
        if screenshot_path is not None:
            screenshot_bytes = self._page.screenshot(path=screenshot_path)
            screenshot_ref = screenshot_path or f"sha256:{hashlib.sha256(screenshot_bytes).hexdigest()}"
        effective_ttl_ms = self._lease_ttl_ms if ttl_ms is None else ttl_ms
        model = self._dom.transduce(
            html,
            environment_revision=environment_revision,
            page_id=page_id,
            url=url,
            ttl_ms=effective_ttl_ms,
            snapshot_id=snapshot_id,
        )
        observation = Observation(
            environment_revision=environment_revision,
            url=url,
            dom_hash=dom_hash,
            screenshot_ref=screenshot_ref,
            metadata={"html": html},
            snapshot_id=snapshot_id,
            page_revision=model.page_revision,
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            artifact_refs=[screenshot_ref] if screenshot_ref else [],
        )
        return BrowserSnapshot(observation=observation, affordance_model=model)

    def screenshot(self, path: str | None = None) -> bytes:
        return self._page.screenshot(path=path) if path else self._page.screenshot()

    def wait_for_load_state(self, state: str = "domcontentloaded") -> None:
        waiter = getattr(self._page, "wait_for_load_state", None)
        if waiter is not None:
            waiter(state)

    def click(self, selector: str) -> None:
        self._page.click(selector)

    def fill(self, selector: str, value: str) -> None:
        self._page.fill(selector, value)

    def select_option(self, selector: str, value: str) -> Any:
        selector_method = getattr(self._page, "select_option", None)
        if selector_method is None:
            raise RuntimeError("page does not support select_option")
        return selector_method(selector, value)

    def press(self, selector: str, key: str) -> Any:
        press_method = getattr(self._page, "press", None)
        if press_method is None:
            raise RuntimeError("page does not support press")
        return press_method(selector, key)

    def text_content(self, selector: str) -> str | None:
        getter = getattr(self._page, "text_content", None)
        return getter(selector) if getter else None

    def evaluate(self, expression: str) -> Any:
        evaluator = getattr(self._page, "evaluate", None)
        if evaluator is None:
            raise RuntimeError("page does not support JavaScript evaluation")
        return evaluator(expression)

    def download(self, selector: str, destination_dir: str) -> dict[str, str]:
        expect_download = getattr(self._page, "expect_download", None)
        if expect_download is None:
            raise RuntimeError("page does not support download events")
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        with expect_download() as download_info:
            self._page.click(selector)
        download = download_info.value
        filename = str(getattr(download, "suggested_filename", "download.bin"))
        path = destination / filename
        download.save_as(str(path))
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"path": str(path), "sha256": content_hash, "filename": filename}

    def click_xy(self, x: int, y: int) -> None:
        mouse = getattr(self._page, "mouse", None)
        if mouse is not None:
            mouse.click(x, y)
            return
        click_xy = getattr(self._page, "click_xy", None)
        if click_xy is None:
            raise RuntimeError("page does not support pointer clicks")
        click_xy(x, y)

    def type_text(self, text: str) -> None:
        keyboard = getattr(self._page, "keyboard", None)
        if keyboard is not None:
            keyboard.type(text)
            return
        type_text = getattr(self._page, "type_text", None)
        if type_text is None:
            raise RuntimeError("page does not support keyboard typing")
        type_text(text)
