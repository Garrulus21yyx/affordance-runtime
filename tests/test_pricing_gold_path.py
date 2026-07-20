import asyncio
import json
import threading
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.coordinator import RunCoordinator
from affordance_runtime.executors import DomExecutor, ExecutorRouter
from affordance_runtime.fixtures import PRICING_DATA, create_fixture_server, pricing_html
from affordance_runtime.planners import PricingPlanner
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope


class InteractivePricingPage:
    url = "http://fixture/pricing"

    def __init__(self) -> None:
        self.html = pricing_html()

    def content(self) -> str:
        return self.html

    def click(self, selector: str) -> None:
        plan = selector.removeprefix("#show-")
        self.html = self.html.replace(f'data-plan="{plan}" data-visible="false"', f'data-plan="{plan}" data-visible="true"')

    def fill(self, selector: str, value: str) -> None:
        del selector, value

    def goto(self, url: str, **kwargs: Any) -> None:
        del kwargs
        self.url = url

    def screenshot(self, **kwargs: Any) -> bytes:
        del kwargs
        return b"fixture"


def test_pricing_gold_path_uses_shared_runtime_and_structural_verification(tmp_path: Path) -> None:
    session = BrowserSession(InteractivePricingPage())
    router = ExecutorRouter()
    router.register(DomExecutor(session))
    result = asyncio.run(
        RunCoordinator(
            observer=session,
            planner=PricingPlanner(),
            executor=router,
            artifacts=ArtifactStore(tmp_path / "artifacts"),
        ).run(
            TaskEnvelope(
                "pricing-test",
                "extract pricing",
                constraints={"read_only": True, "must_return_evidence": True},
            )
        )
    )

    assert result.status == RuntimeStep.DONE
    assert result.result["plans"] == PRICING_DATA
    assert result.state.step_count == 2
    assert [receipt.evidence["selector"] for receipt in result.state.receipts] == ["#show-pro", "#show-enterprise"]
    assert len(list((tmp_path / "artifacts/pricing-test/observations").glob("*.json"))) == 7


def test_local_fixture_exposes_pricing_oracle() -> None:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urlopen(f"http://{host}:{port}/api/pricing", timeout=2) as response:  # noqa: S310 - local fixture
            value = json.loads(response.read())
        assert value == PRICING_DATA
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
