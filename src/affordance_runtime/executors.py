"""Contract executors adapted from the modular action system.

The implementations operate on injected protocols, so unit tests do not need a
browser or network. Playwright and richer transports remain optional adapters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import monotonic, perf_counter
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode


class ContractExecutor(Protocol):
    backend: str

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        ...


class DomPage(Protocol):
    def click(self, selector: str) -> Any: ...

    def fill(self, selector: str, value: str) -> Any: ...


class VisualPointer(Protocol):
    def click_xy(self, x: int, y: int) -> Any: ...

    def type_text(self, text: str) -> Any: ...


SendFn = Callable[..., tuple[int, Any]]


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
    page: DomPage
    backend: str = "dom"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started_at = perf_counter()
        selector = str(contract.locator.get("selector") or "")
        if not selector and contract.action != "navigate":
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
            action = contract.action.lower()
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
    pointer: VisualPointer
    backend: str = "visual"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started_at = perf_counter()
        try:
            center = contract.locator.get("center")
            if center is None:
                bbox = contract.locator.get("bbox")
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
            if contract.action.lower() in {"type", "fill"}:
                value = str(contract.parameters.get("value", ""))
                self.pointer.type_text(value)
                evidence["typed"] = value
            elif contract.action.lower() not in {"click", "activate"}:
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
    send: SendFn = _stdlib_send
    gate: MinIntervalGate = field(default_factory=MinIntervalGate)
    backend: str = "wot"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        started_at = perf_counter()
        try:
            href = str(contract.locator.get("href") or "")
            if not href:
                raise ValueError("WoT contract requires locator.href")
            method = str(contract.locator.get("method") or "GET").upper()
            thing_id = str(contract.locator.get("thing_id") or contract.affordance_id)
            min_interval_ms = float(contract.parameters.get("min_interval_ms", 0.0))
            self.gate.check(thing_id, min_interval_ms)

            payload = contract.parameters.get("payload", contract.parameters.get("value"))
            headers = dict(contract.parameters.get("headers") or {})
            status, response = self.send(
                method,
                href,
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
                evidence={"method": method, "href": href, "status": status, "response": response},
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
class ExecutorRouter:
    """Dispatch an already validated contract to its bound backend.

    Fallback is deliberately not automatic. A failed effectful execution must
    return to recovery for post-state inspection before another backend acts.
    """

    executors: dict[str, ContractExecutor] = field(default_factory=dict)
    backend: str = "executor_router"

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
