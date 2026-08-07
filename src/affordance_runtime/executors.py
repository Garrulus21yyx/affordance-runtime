"""Contract executors adapted from the modular action system.

The implementations operate on injected protocols, so unit tests do not need a
browser or network. Playwright and richer transports remain optional adapters.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from time import monotonic, perf_counter
from typing import Any, Callable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from affordance_runtime.adapters.wot_security import SecurityScheme, build_auth
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.immutable import thaw_json_at_external_boundary


class ContractExecutor(Protocol):
    backend: str

    @property
    def supported_actions(self) -> tuple[str, ...]: ...

    @property
    def provider_capabilities(self) -> tuple[str, ...]: ...

    @property
    def adapter_capabilities(self) -> tuple[str, ...]: ...

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        ...


class DomPage(Protocol):
    def click(self, selector: str) -> Any: ...

    def fill(self, selector: str, value: str) -> Any: ...

    def locator(self, selector: str) -> Any: ...


class VisualPointer(Protocol):
    def click_xy(self, x: int, y: int) -> Any: ...

    def type_text(self, text: str) -> Any: ...


SendFn = Callable[..., tuple[int, Any]]
CredentialProvider = Callable[[str], str | None]


@dataclass(frozen=True)
class PlaywrightDragAction:
    source_selector: str
    destination_selector: str


@dataclass(frozen=True)
class PlaywrightGestureEncoder:
    """Encode a core gesture binding as a Playwright locator-to-locator drag."""

    def encode(self, contract: ActionContract) -> PlaywrightDragAction:
        binding = contract.gesture_binding
        if binding is None:
            raise ValueError("Playwright drag contract requires a gesture binding")
        source = str(binding.source.locator.get("selector") or "")
        destination = str(binding.destination.locator.get("selector") or "")
        if not source or not destination:
            raise ValueError("Playwright drag encoding requires source and destination selectors")
        return PlaywrightDragAction(source, destination)


@dataclass(frozen=True)
class VisualDragAction:
    source_xy: tuple[int, int]
    destination_xy: tuple[int, int]
    steps: int = 10


@dataclass(frozen=True)
class VisualGestureEncoder:
    """Encode fresh visual endpoint geometry as one bounded pointer gesture."""

    steps: int = 10

    def encode(self, contract: ActionContract, observation: Observation) -> VisualDragAction:
        binding = contract.gesture_binding
        if binding is None:
            raise ValueError("visual drag contract requires a gesture binding")
        source = _visual_locator_center(binding.source.locator)
        destination = _visual_locator_center(binding.destination.locator)
        viewport = observation.metadata.get("viewport_size")
        for name, point in (("source", source), ("destination", destination)):
            if not all(math.isfinite(value) for value in point) or min(point) < 0:
                raise ValueError(f"visual drag {name} point is invalid")
            if isinstance(viewport, (list, tuple)) and len(viewport) == 2:
                width, height = (float(value) for value in viewport)
                if width <= 0 or height <= 0 or point[0] > width or point[1] > height:
                    raise ValueError(f"visual drag {name} point is outside the viewport")
        if source == destination:
            raise ValueError("visual drag source and destination points must differ")
        return VisualDragAction(
            (round(source[0]), round(source[1])),
            (round(destination[0]), round(destination[1])),
            max(1, self.steps),
        )


def _visual_locator_center(locator: dict[str, Any]) -> tuple[float, float]:
    for key in ("point", "center"):
        raw = thaw_json_at_external_boundary(locator.get(key))
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            return float(raw[0]), float(raw[1])
    raw = thaw_json_at_external_boundary(locator.get("bbox"))
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        left, top, width, height = (float(value) for value in raw)
        if width > 0 and height > 0:
            return left + width / 2, top + height / 2
    raise ValueError("visual gesture endpoint requires point, center, or positive bbox")


def _receipt(
    contract: ActionContract,
    observation: Observation,
    *,
    backend: str,
    started_at: float,
    success: bool,
    evidence: dict[str, Any] | None = None,
    error_code: RuntimeErrorCode | None = None,
    message: str = "",
) -> ExecutionReceipt:
    return ExecutionReceipt(
        contract_id=contract.id,
        backend=backend,
        success=success,
        started_revision=observation.environment_revision,
        ended_revision=observation.environment_revision,
        latency_ms=round((perf_counter() - started_at) * 1_000.0, 3),
        evidence=evidence or {},
        error_code=error_code,
        message=message,
    )


@dataclass
class DomExecutor:
    supported_actions = ("activate", "click", "download", "drag", "fill", "navigate", "press", "select", "type")
    provider_capabilities = (
        "settings.write",
        "settings.write.reversible",
        "report.export",
        "conformance.shared-state.write",
    )
    adapter_capabilities = provider_capabilities
    page: DomPage
    backend: str = "dom"
    gesture_encoder: PlaywrightGestureEncoder = field(default_factory=PlaywrightGestureEncoder)

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started_at = perf_counter()
        selector = str(contract.locator.get("selector") or "")
        action = contract.action.lower()
        if not selector and action not in {"navigate", "drag"}:
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message="DOM contract requires locator.selector",
            )

        try:
            value = contract.parameters.get("value", "")
            if action in {"click", "activate"}:
                self.page.click(selector)
                evidence = {"action": "click", "selector": selector}
            elif action in {"type", "fill"}:
                self.page.fill(selector, str(value))
                evidence = {"action": "fill", "selector": selector, "value": value}
            elif action == "select":
                select_option = getattr(self.page, "select_option", None)
                if select_option is None:
                    raise RuntimeError("DOM page does not support select_option")
                select_option(selector, str(value))
                evidence = {"action": "select", "selector": selector, "value": value}
            elif action == "press":
                press = getattr(self.page, "press", None)
                if press is None:
                    raise RuntimeError("DOM page does not support press")
                key = str(contract.parameters.get("key") or value)
                press(selector, key)
                evidence = {"action": "press", "selector": selector, "key": key}
            elif action == "navigate":
                goto = getattr(self.page, "goto", None)
                if goto is None:
                    raise RuntimeError("DOM page does not support goto")
                url = str(contract.parameters.get("url") or contract.locator.get("url") or "")
                if not url:
                    raise ValueError("navigate contract requires parameters.url or locator.url")
                goto(url)
                evidence = {"action": "navigate", "url": url}
            elif action == "download":
                download = getattr(self.page, "download", None)
                if download is None:
                    raise RuntimeError("DOM page does not support downloads")
                destination_dir = str(contract.parameters.get("destination_dir") or "")
                if not destination_dir:
                    raise ValueError("download contract requires parameters.destination_dir")
                evidence = {"action": "download", "selector": selector, **download(selector, destination_dir)}
            elif action == "drag":
                encoded = self.gesture_encoder.encode(contract)
                locator = getattr(self.page, "locator", None)
                if locator is None:
                    raise RuntimeError("DOM page does not support Playwright locators")
                source = locator(encoded.source_selector)
                destination = locator(encoded.destination_selector)
                drag_to = getattr(source, "drag_to", None)
                if drag_to is None:
                    raise RuntimeError("Playwright source locator does not support drag_to")
                drag_to(destination)
                evidence = {
                    "action": "playwright_drag_to",
                    "source_selector": encoded.source_selector,
                    "destination_selector": encoded.destination_selector,
                }
            else:
                raise ValueError(f"unsupported DOM action: {contract.action}")
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=True,
                evidence=evidence,
            )
        except TimeoutError as exc:
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
                message=str(exc),
            )
        except Exception as exc:
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message=f"{type(exc).__name__}: {exc}",
            )


@dataclass
class VisualExecutor:
    supported_actions = ("drag", "point_activate", "type_text")
    provider_capabilities = (
        "settings.write",
        "spatial.point.current_geometry",
        "conformance.shared-state.write",
    )
    adapter_capabilities = provider_capabilities
    pointer: VisualPointer
    backend: str = "visual"
    gesture_encoder: VisualGestureEncoder = field(default_factory=VisualGestureEncoder)

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started_at = perf_counter()
        try:
            action = contract.action.lower()
            if action == "drag":
                encoded = self.gesture_encoder.encode(contract, observation)
                move_xy = getattr(self.pointer, "move_xy", None)
                button_down = getattr(self.pointer, "button_down", None)
                button_up = getattr(self.pointer, "button_up", None)
                if move_xy is None or button_down is None or button_up is None:
                    raise RuntimeError("visual pointer does not support bounded drag gestures")
                move_xy(*encoded.source_xy, steps=1)
                button_down("left")
                pressed = True
                try:
                    move_xy(*encoded.destination_xy, steps=encoded.steps)
                finally:
                    if pressed:
                        button_up("left")
                return _receipt(
                    contract,
                    observation,
                    backend=self.backend,
                    started_at=started_at,
                    success=True,
                    evidence={
                        "action": "visual_drag",
                        "source_center": list(encoded.source_xy),
                        "destination_center": list(encoded.destination_xy),
                        "steps": encoded.steps,
                    },
                )
            center = thaw_json_at_external_boundary(contract.locator.get("point") or contract.locator.get("center"))
            if center is None:
                bbox = thaw_json_at_external_boundary(contract.locator.get("bbox"))
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    raise ValueError("visual contract requires center or [x, y, w, h] bbox")
                x, y, width, height = (int(value) for value in bbox)
                center = [x + width // 2, y + height // 2]
            x, y = (int(value) for value in center)
            self.pointer.click_xy(x, y)
            evidence: dict[str, Any] = {
                "action": "visual_click",
                "center": [x, y],
                "mark_id": contract.locator.get("mark_id", ""),
                "screenshot_ref": contract.locator.get("screenshot_ref", ""),
            }
            if action in {"type", "fill"}:
                value = str(contract.parameters.get("value", ""))
                self.pointer.type_text(value)
                evidence["typed"] = value
            elif action not in {"click", "activate", "point_activate"}:
                raise ValueError(f"unsupported visual action: {contract.action}")
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=True,
                evidence=evidence,
            )
        except Exception as exc:
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message=f"{type(exc).__name__}: {exc}",
            )


class RateLimitExceeded(RuntimeError):
    pass


@dataclass
class MinIntervalGate:
    last_call_s: dict[str, float] = field(default_factory=dict)

    def check(self, key: str, min_interval_ms: float) -> None:
        now = monotonic()
        previous = self.last_call_s.get(key)
        if previous is not None and (now - previous) * 1_000.0 < min_interval_ms:
            raise RateLimitExceeded(f"rate limit for {key}: minimum interval is {min_interval_ms:g} ms")
        self.last_call_s[key] = now


def _stdlib_send(method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
    payload = kwargs.get("json")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = dict(kwargs.get("headers") or {})
    if body is not None:
        headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=headers, method=method)
    timeout_s = float(kwargs.get("timeout_s", 5.0))
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - URL is constrained by runtime policy
        raw = response.read()
        content_type = response.headers.get("content-type", "")
        parsed: Any = json.loads(raw) if raw and "json" in content_type else raw.decode("utf-8")
        return response.status, parsed


@dataclass
class WotExecutor:
    supported_actions = ("invoke", "write_property")
    provider_capabilities = (
        "device.actuate",
        "device.write",
        "conformance.shared-state.write",
    )
    adapter_capabilities = provider_capabilities
    send: SendFn = _stdlib_send
    gate: MinIntervalGate = field(default_factory=MinIntervalGate)
    security_schemes: Mapping[str, SecurityScheme] = field(default_factory=dict)
    credential_provider: CredentialProvider | None = None
    backend: str = "wot"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started_at = perf_counter()
        credential: str | None = None
        try:
            href = str(contract.locator.get("href") or "")
            if not href:
                raise ValueError("WoT contract requires locator.href")
            method = str(contract.locator.get("method") or "GET").upper()
            thing_id = str(contract.locator.get("thing_id") or contract.affordance_id)
            declared_interval_ms = float(contract.locator.get("min_interval_ms", 0.0))
            requested_interval_ms = float(contract.parameters.get("min_interval_ms", 0.0))
            min_interval_ms = max(declared_interval_ms, requested_interval_ms)
            self.gate.check(thing_id, min_interval_ms)

            payload = thaw_json_at_external_boundary(
                contract.parameters.get("payload", contract.parameters.get("value"))
            )
            headers = dict(thaw_json_at_external_boundary(contract.parameters.get("headers") or {}))
            security_ref = str(contract.locator.get("security_scheme_ref") or "")
            request_href = href
            if security_ref:
                scheme = self.security_schemes.get(security_ref)
                if scheme is None:
                    raise ValueError(f"unknown WoT security scheme ref {security_ref!r}")
                credential = self.credential_provider(security_ref) if self.credential_provider is not None else None
                if scheme.requires_credential and not credential:
                    raise ValueError(f"credential unavailable for WoT security scheme ref {security_ref!r}")
                auth_headers, auth_query = build_auth(scheme, credential)
                headers.update(auth_headers)
                request_href = _append_query(href, auth_query)
            status, response = self.send(
                method,
                request_href,
                json=None if method == "GET" else payload,
                headers=headers,
                timeout_s=contract.timeout_ms / 1_000.0,
            )
            if status >= 400:
                raise RuntimeError(f"WoT {method} {href} returned HTTP {status}")
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=True,
                evidence={
                    "method": method,
                    "href": href,
                    "status": status,
                    "response": _redact_credential(response, credential),
                },
            )
        except TimeoutError as exc:
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
                message=str(_redact_credential(str(exc), credential)),
            )
        except Exception as exc:
            return _receipt(
                contract,
                observation,
                backend=self.backend,
                started_at=started_at,
                success=False,
                error_code=RuntimeErrorCode.EXECUTION_FAILED,
                message=f"{type(exc).__name__}: {_redact_credential(str(exc), credential)}",
            )


def _append_query(url: str, values: Mapping[str, str]) -> str:
    if not values:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend(values.items())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _redact_credential(value: Any, credential: str | None) -> Any:
    if not credential:
        return value
    if isinstance(value, str):
        return value.replace(credential, "[REDACTED]")
    if isinstance(value, Mapping):
        return {key: _redact_credential(item, credential) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_credential(item, credential) for item in value]
    return value


@dataclass
class ExecutorRouter:
    """Dispatch an already validated contract to its bound backend.

    Fallback is deliberately not automatic. A failed effectful execution must
    return to recovery for post-state inspection before another backend acts.
    """

    executors: dict[str, ContractExecutor] = field(default_factory=dict)
    backend: str = "executor_router"

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return tuple(sorted({action for executor in self.executors.values() for action in executor.supported_actions}))

    @property
    def provider_capabilities(self) -> tuple[str, ...]:
        return tuple(
            sorted({capability for executor in self.executors.values() for capability in executor.provider_capabilities})
        )

    @property
    def adapter_capabilities(self) -> tuple[str, ...]:
        return tuple(
            sorted({capability for executor in self.executors.values() for capability in executor.adapter_capabilities})
        )

    def register(self, executor: ContractExecutor, *aliases: str) -> None:
        self.executors[executor.backend] = executor
        for alias in aliases:
            self.executors[alias] = executor

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        executor = self.executors.get(contract.backend)
        if executor is None:
            return ExecutionReceipt(
                contract_id=contract.id,
                backend=contract.backend,
                success=False,
                started_revision=observation.environment_revision,
                ended_revision=observation.environment_revision,
                latency_ms=0.0,
                error_code=RuntimeErrorCode.BACKEND_UNAVAILABLE,
                message=f"backend is not registered: {contract.backend}",
            )
        return executor.execute(contract, observation)
