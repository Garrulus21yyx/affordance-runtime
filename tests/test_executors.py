from typing import Any

from affordance_runtime.contracts import ActionContract, Observation, RuntimeErrorCode
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


class FakePointer:
    def __init__(self) -> None:
        self.actions: list[tuple[Any, ...]] = []

    def click_xy(self, x: int, y: int) -> None:
        self.actions.append(("click_xy", x, y))

    def type_text(self, text: str) -> None:
        self.actions.append(("type_text", text))


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


def test_executor_router_does_not_implicitly_fallback() -> None:
    router = ExecutorRouter()
    receipt = router.execute(
        _contract(backend="missing", action="click", locator={"selector": "#save"}),
        Observation(environment_revision="rev-1"),
    )

    assert not receipt.success
    assert receipt.error_code == RuntimeErrorCode.BACKEND_UNAVAILABLE
