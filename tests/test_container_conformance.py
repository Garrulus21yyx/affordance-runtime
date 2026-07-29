import json
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.benchmarks.agreement import compare_benchmark_reports
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.conformance import (
    CONFORMANCE_CAPABILITY,
    CONFORMANCE_GOAL,
    ConformancePlanner,
    ConformanceSurfaceResult,
    _preserves_shared_contract_envelope,
)
from affordance_runtime.contracts import ACTION_CONTRACT_SCHEMA_VERSION, Observation
from affordance_runtime.fixtures import LOCAL_SAAS_FIXTURE_VERSION, create_fixture_server
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


def _request_json(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=2) as response:  # noqa: S310 - ephemeral local fixture
        return json.loads(response.read())


def test_fixture_health_reset_and_local_conformance_state(monkeypatch) -> None:
    monkeypatch.delenv("AFFORDANCE_WOT_CONTROL_URL", raising=False)
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_name}:{server.server_port}"
    try:
        assert _request_json(f"{base_url}/api/health") == {
            "fixture_version": LOCAL_SAAS_FIXTURE_VERSION,
            "ok": True,
        }
        assert _request_json(f"{base_url}/api/conformance") == {
            "enabled": False,
            "oracle": "fixture-memory",
        }
        assert _request_json(f"{base_url}/api/conformance-dom", {})["enabled"] is True
        assert _request_json(f"{base_url}/api/conformance")["enabled"] is True
        _request_json(f"{base_url}/api/reset", {"seed": 2, "profile": "train"})
        assert _request_json(f"{base_url}/api/conformance")["enabled"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_conformance_planner_preserves_shared_contract_envelope() -> None:
    revision = "revision-1"
    snapshot_id = "snapshot-1"
    dom = DomAdapter().transduce(
        '<button id="enable">Enable shared state</button>',
        environment_revision=revision,
        snapshot_id=snapshot_id,
    )
    visual_affordances = SomAdapter().parse(
        [{"bbox": [10, 20, 30, 40], "label": "target", "action": "click"}],
        environment_revision=revision,
        snapshot_id=snapshot_id,
    )
    visual = dom.__class__("visual", "", revision, snapshot_id, revision, visual_affordances, 1, 1)
    thing = WotAdapter().parse(
        {
            "id": "thing",
            "actions": {
                "setEnabled": {
                    "forms": [{"href": "http://thing/actions/setEnabled", "op": "invokeaction"}]
                }
            },
        },
        environment_revision=revision,
        snapshot_id=snapshot_id,
    )
    wot = dom.__class__("wot", "", revision, snapshot_id, revision, thing.affordances, 1, 1)
    envelope = TaskEnvelope("run", "goal", capabilities=[CONFORMANCE_CAPABILITY])

    contracts = []
    for surface, model in (("dom", dom), ("visual", visual), ("wot", wot)):
        observation = Observation(revision, snapshot_id=snapshot_id)
        decision = ConformancePlanner(surface, "http://oracle/state").propose(
            envelope,
            StateKernel("run", "goal"),
            BrowserSnapshot(observation, model),
        )
        assert decision.contract is not None
        contracts.append(decision.contract)

    assert [contract.backend for contract in contracts] == ["dom", "visual", "wot"]
    assert all(contract.required_capabilities == [CONFORMANCE_CAPABILITY] for contract in contracts)
    assert all(contract.schema_version == "1.2" for contract in contracts)
    assert all(contract.verifier_plan[0].kind == "http_json" for contract in contracts)
    assert all(contract.verifier_plan[0].target == "http://oracle/state" for contract in contracts)


def test_conformance_planner_builds_request_when_task_spec_is_available() -> None:
    revision = "revision-1"
    snapshot_id = "snapshot-request-1"
    model = DomAdapter().transduce(
        '<button id="enable">Enable shared state</button>',
        environment_revision=revision,
        snapshot_id=snapshot_id,
    )
    observation = Observation(revision, snapshot_id=snapshot_id, page_revision=model.page_revision)
    state = StateKernel("conformance-request", CONFORMANCE_GOAL)
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    task = TaskSpec(
        task_id="conformance-request",
        revision=1,
        objective=CONFORMANCE_GOAL,
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Enable shared state",),
        success_criteria=("shared state enabled",),
        evidence_requirements=("oracle evidence",),
        requested_capabilities=(CONFORMANCE_CAPABILITY,),
        source_request_ref="conformance-request-source",
    )

    @dataclass
    class RecordingRequestBuilder:
        inner: PlanningRequestBuilder = PlanningRequestBuilder()
        built: PlanningRequest | None = None

        def build(
            self,
            envelope: TaskEnvelope,
            state: StateKernel,
            snapshot: BrowserSnapshot,
        ) -> PlanningRequest:
            self.built = self.inner.build(envelope, state, snapshot)
            return self.built

    request_builder = RecordingRequestBuilder()

    decision = ConformancePlanner(
        "dom",
        "http://oracle/state",
        planning_request_builder=request_builder,
    ).propose(
        TaskEnvelope(task_spec=task, capabilities=[CONFORMANCE_CAPABILITY]),
        state,
        BrowserSnapshot(observation, model),
    )

    assert request_builder.built is not None
    assert decision.contract is not None
    assert decision.contract.required_capabilities == [CONFORMANCE_CAPABILITY]


def test_conformance_acceptance_uses_current_action_contract_schema() -> None:
    item = ConformanceSurfaceResult(
        surface="dom",
        backend="dom",
        status="done",
        oracle_enabled=True,
        oracle_source="node-wot-control",
        verification_status="passed",
        contract_schema=ACTION_CONTRACT_SCHEMA_VERSION,
        contract_capabilities=[CONFORMANCE_CAPABILITY],
        event_types=["PostconditionPassed"],
        trace_path="/evidence/events.jsonl",
        screenshot_refs=[],
    )

    assert _preserves_shared_contract_envelope(item)
    assert not _preserves_shared_contract_envelope(
        item.__class__(**{**item.__dict__, "contract_schema": "1.0"})
    )


def test_conformance_surface_result_sequences_are_immutable_from_source_lists() -> None:
    capabilities = [CONFORMANCE_CAPABILITY]
    events = ["PostconditionPassed"]
    screenshots = ["screen.png"]

    item = ConformanceSurfaceResult(
        surface="dom",
        backend="dom",
        status="done",
        oracle_enabled=True,
        oracle_source="node-wot-control",
        verification_status="passed",
        contract_schema=ACTION_CONTRACT_SCHEMA_VERSION,
        contract_capabilities=capabilities,
        event_types=events,
        trace_path="/evidence/events.jsonl",
        screenshot_refs=screenshots,
    )
    capabilities.append("mutated")
    events.append("extra")
    screenshots.append("other.png")

    assert item.contract_capabilities == (CONFORMANCE_CAPABILITY,)
    assert item.event_types == ("PostconditionPassed",)
    assert item.screenshot_refs == ("screen.png",)
    with pytest.raises(TypeError):
        item.contract_capabilities[0] = "mutated"  # type: ignore[index]


def test_host_container_agreement_ignores_only_timing_and_trace_paths(tmp_path: Path) -> None:
    environment = {
        "runtime_commit": "abc",
        "runtime_version": "0.1.0",
        "browser_version": "149",
        "playwright_version": "1.61.0",
        "fixture_version": "2.0.0",
        "suite_version": "suite",
        "seed_semantics": "seed-v1",
    }
    base = {
        "suite_version": "suite",
        "metrics_by_variant": {"full_runtime": {"task_success_rate": 1.0}},
        "acceptance_errors": [],
        "environment": environment,
        "runs": [{"task_id": "task", "success": True, "latency_ms": 1.0, "trace_path": "/host"}],
    }
    host_path = tmp_path / "host.json"
    container_path = tmp_path / "container.json"
    host_path.write_text(json.dumps(base), encoding="utf-8")
    container = {**base, "runs": [{**base["runs"][0], "latency_ms": 99.0, "trace_path": "/container"}]}
    container_path.write_text(json.dumps(container), encoding="utf-8")

    assert compare_benchmark_reports(host_path, container_path)["acceptance"] == "passed"
    container["runs"][0]["success"] = False
    container_path.write_text(json.dumps(container), encoding="utf-8")
    report = compare_benchmark_reports(host_path, container_path)
    assert report["acceptance"] == "failed"
    assert "stable per-run outcomes differ" in report["errors"]
