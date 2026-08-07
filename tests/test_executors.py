from dataclasses import replace
from typing import Any

from affordance_runtime.adapters.wot_security import SecurityScheme
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    GestureContractBinder,
    Observation,
    RuntimeErrorCode,
    Surface,
)
from affordance_runtime.executors import DomExecutor, ExecutorRouter, VisualExecutor, WotExecutor


def _contract(
    *,
    backend: str,
    action: str,
    locator: dict[str, Any],
    parameters: dict[str, Any] | None = None,
) -> ActionContract:
    return ActionContract(
        id=f"contract_{backend}_{action}",
        intent=action,
        affordance_id=f"aff_{backend}",
        action=action,
        backend=backend,
        environment_revision="rev-1",
        locator=locator,
        parameters=parameters or {},
    )


class FakePage:
    def __init__(self) -> None:
        self.actions: list[tuple[Any, ...]] = []

    def click(self, selector: str) -> None:
        self.actions.append(("click", selector))

    def fill(self, selector: str, value: str) -> None:
        self.actions.append(("fill", selector, value))

    def select_option(self, selector: str, value: str) -> None:
        self.actions.append(("select", selector, value))

    def locator(self, selector: str) -> "FakeLocator":
        return FakeLocator(self, selector)


class FakeLocator:
    def __init__(self, page: FakePage, selector: str) -> None:
        self.page = page
        self.selector = selector

    def drag_to(self, destination: "FakeLocator") -> None:
        self.page.actions.append(("drag_to", self.selector, destination.selector))


class FakePointer:
    def __init__(self) -> None:
        self.actions: list[tuple[Any, ...]] = []

    def click_xy(self, x: int, y: int) -> None:
        self.actions.append(("click_xy", x, y))

    def type_text(self, text: str) -> None:
        self.actions.append(("type_text", text))

    def move_xy(self, x: int, y: int, *, steps: int = 1) -> None:
        self.actions.append(("move_xy", x, y, steps))

    def button_down(self, button: str = "left") -> None:
        self.actions.append(("button_down", button))

    def button_up(self, button: str = "left") -> None:
        self.actions.append(("button_up", button))


def _drag_contract(
    *, backend: str, source_locator: dict[str, Any], destination_locator: dict[str, Any]
) -> ActionContract:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    source = Affordance(
        "source",
        Surface.VISUAL if backend == "visual" else Surface.DOM,
        "item",
        "Source",
        "drag",
        source_locator,
        lease,
        backend_candidates=[backend],
    )
    destination = Affordance(
        "destination",
        Surface.VISUAL if backend == "visual" else Surface.DOM,
        "region",
        "Destination",
        "drop",
        destination_locator,
        lease,
        backend_candidates=[backend],
    )
    observation = Observation(environment_revision="rev-1")
    binding = GestureContractBinder().bind(
        source,
        destination,
        selected_route=backend,
        observation=observation,
    )
    return replace(
        ActionContract.from_affordance(source, intent="move source", backend=backend),
        gesture_binding=binding,
        contract_hash="",
    )


def test_dom_executor_runs_contract_actions() -> None:
    page = FakePage()
    receipt = DomExecutor(page).execute(
        _contract(backend="dom", action="type", locator={"selector": "#name"}, parameters={"value": "Ada"}),
        Observation(environment_revision="rev-1"),
    )

    assert receipt.success
    assert page.actions == [("fill", "#name", "Ada")]
    assert receipt.evidence["selector"] == "#name"


def test_dom_executor_returns_structured_failure() -> None:
    receipt = DomExecutor(FakePage()).execute(
        _contract(backend="dom", action="click", locator={}),
        Observation(environment_revision="rev-1"),
    )

    assert not receipt.success
    assert receipt.error_code == RuntimeErrorCode.EXECUTION_FAILED


def test_dom_executor_encodes_gesture_with_playwright_locator_drag_to() -> None:
    page = FakePage()
    receipt = DomExecutor(page).execute(
        _drag_contract(
            backend="dom",
            source_locator={"selector": "#source"},
            destination_locator={"selector": "#destination"},
        ),
        Observation(environment_revision="rev-1"),
    )

    assert receipt.success
    assert page.actions == [("drag_to", "#source", "#destination")]
    assert receipt.evidence["action"] == "playwright_drag_to"


def test_visual_executor_uses_bbox_center_and_types() -> None:
    pointer = FakePointer()
    receipt = VisualExecutor(pointer).execute(
        _contract(
            backend="visual",
            action="type",
            locator={"bbox": [10, 20, 40, 20], "mark_id": "M3"},
            parameters={"value": "hello"},
        ),
        Observation(environment_revision="rev-1"),
    )

    assert receipt.success
    assert pointer.actions == [("click_xy", 30, 30), ("type_text", "hello")]
    assert receipt.evidence["mark_id"] == "M3"


def test_visual_executor_encodes_bounded_mouse_down_move_up_drag() -> None:
    pointer = FakePointer()
    receipt = VisualExecutor(pointer).execute(
        _drag_contract(
            backend="visual",
            source_locator={"bbox": [10, 20, 20, 20]},
            destination_locator={"bbox": [100, 120, 40, 40]},
        ),
        Observation(environment_revision="rev-1", metadata={"viewport_size": [800, 600]}),
    )

    assert receipt.success
    assert pointer.actions == [
        ("move_xy", 20, 30, 1),
        ("button_down", "left"),
        ("move_xy", 120, 140, 10),
        ("button_up", "left"),
    ]
    assert receipt.evidence["action"] == "visual_drag"


def test_visual_executor_releases_pointer_when_drag_move_fails() -> None:
    class FailingPointer(FakePointer):
        def move_xy(self, x: int, y: int, *, steps: int = 1) -> None:
            super().move_xy(x, y, steps=steps)
            if steps > 1:
                raise RuntimeError("pointer move failed")

    pointer = FailingPointer()
    receipt = VisualExecutor(pointer).execute(
        _drag_contract(
            backend="visual",
            source_locator={"center": [20, 30]},
            destination_locator={"center": [120, 140]},
        ),
        Observation(environment_revision="rev-1", metadata={"viewport_size": [800, 600]}),
    )

    assert not receipt.success
    assert pointer.actions[-1] == ("button_up", "left")


def test_wot_executor_uses_contract_form_without_hardcoding() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def send(method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        calls.append((method, url, kwargs))
        return 200, {"ok": True}

    receipt = WotExecutor(send=send).execute(
        _contract(
            backend="wot",
            action="invoke",
            locator={"thing_id": "lamp", "href": "http://fixture/lamp/on", "method": "POST"},
            parameters={"payload": {"power": "on"}},
        ),
        Observation(environment_revision="rev-1"),
    )

    assert receipt.success
    assert calls[0][0:2] == ("POST", "http://fixture/lamp/on")
    assert calls[0][2]["json"] == {"power": "on"}


def test_wot_executor_late_binds_header_credential_without_recording_it() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def send(method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        calls.append((method, url, kwargs))
        return 200, {"echo": "runtime-only-secret"}

    receipt = WotExecutor(
        send=send,
        security_schemes={"api": SecurityScheme("api", "apikey", "header", "X-API-Key")},
        credential_provider=lambda scheme_ref: "runtime-only-secret" if scheme_ref == "api" else None,
    ).execute(
        _contract(
            backend="wot",
            action="invoke",
            locator={
                "thing_id": "lamp",
                "href": "http://fixture/lamp/on",
                "method": "POST",
                "security_scheme_ref": "api",
            },
        ),
        Observation(environment_revision="rev-1"),
    )

    assert receipt.success
    assert calls[0][2]["headers"] == {"X-API-Key": "runtime-only-secret"}
    assert receipt.evidence["response"] == {"echo": "[REDACTED]"}
    assert "runtime-only-secret" not in repr(receipt)


def test_wot_executor_late_binds_query_credential_but_redacts_evidence() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def send(method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        calls.append((method, url, kwargs))
        return 200, {}

    receipt = WotExecutor(
        send=send,
        security_schemes={"api": SecurityScheme("api", "apikey", "query", "key")},
        credential_provider=lambda _scheme_ref: "runtime-only-secret",
    ).execute(
        _contract(
            backend="wot",
            action="invoke",
            locator={
                "thing_id": "lamp",
                "href": "http://fixture/lamp/on?mode=fast",
                "method": "POST",
                "security_scheme_ref": "api",
            },
        ),
        Observation(environment_revision="rev-1"),
    )

    assert receipt.success
    assert calls[0][1] == "http://fixture/lamp/on?mode=fast&key=runtime-only-secret"
    assert receipt.evidence["href"] == "http://fixture/lamp/on?mode=fast"
    assert "runtime-only-secret" not in repr(receipt)


def test_wot_executor_redacts_query_credential_from_transport_errors() -> None:
    def send(_method: str, url: str, **_kwargs: Any) -> tuple[int, Any]:
        raise RuntimeError(f"request failed for {url}")

    receipt = WotExecutor(
        send=send,
        security_schemes={"api": SecurityScheme("api", "apikey", "query", "key")},
        credential_provider=lambda _scheme_ref: "runtime-only-secret",
    ).execute(
        _contract(
            backend="wot",
            action="invoke",
            locator={
                "thing_id": "lamp",
                "href": "http://fixture/lamp/on",
                "method": "POST",
                "security_scheme_ref": "api",
            },
        ),
        Observation(environment_revision="rev-1"),
    )

    assert not receipt.success
    assert "runtime-only-secret" not in receipt.message
    assert "[REDACTED]" in receipt.message


def test_executor_router_does_not_implicitly_fallback() -> None:
    router = ExecutorRouter()
    receipt = router.execute(
        _contract(backend="missing", action="click", locator={"selector": "#save"}),
        Observation(environment_revision="rev-1"),
    )

    assert not receipt.success
    assert receipt.error_code == RuntimeErrorCode.BACKEND_UNAVAILABLE
