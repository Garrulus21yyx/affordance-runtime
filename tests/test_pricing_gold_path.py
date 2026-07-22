import asyncio
import json
import threading
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.cli import run_scenario
from affordance_runtime.coordinator import RunCoordinator
from affordance_runtime.evolution import (
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
    RecoverySkillPayload,
)
from affordance_runtime.executors import DomExecutor, ExecutorRouter
from affordance_runtime.fixtures import PRICING_DATA, create_fixture_server, pricing_html
from affordance_runtime.planners import PricingPlanner, PricingTaskPlanner, extract_pricing
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.task_intake import OperationClass, TaskSpec


class InteractivePricingPage:
    url = "http://fixture/pricing"

    def __init__(self) -> None:
        self.html = pricing_html()

    def content(self) -> str:
        return self.html

    def click(self, selector: str) -> None:
        plan = selector.removeprefix("#show-")
        self.html = self.html.replace(
            f'data-plan="{plan}" data-visible="false"', f'data-plan="{plan}" data-visible="true"'
        )

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


def test_reference_pricing_task_plan_runs_through_normal_coordinator_path() -> None:
    session = BrowserSession(InteractivePricingPage())
    router = ExecutorRouter()
    router.register(DomExecutor(session))
    task = TaskSpec(
        task_id="pricing-plan-reference",
        revision=1,
        objective="Reveal Pro and Enterprise plan limits with structural evidence.",
        operation_class=OperationClass.READ_ONLY,
        targets=("Pro", "Enterprise"),
        success_criteria=("both pricing plans are structurally visible",),
        evidence_requirements=("post-action DOM evidence for each plan",),
        source_request_ref="reference-test",
    )

    result = RunCoordinator(
        observer=session,
        planner=PricingPlanner(),
        executor=router,
        task_planner=PricingTaskPlanner(),
    ).run_sync(TaskEnvelope(task_spec=task))

    assert result.status == RuntimeStep.DONE
    assert result.state.plan_progress is not None
    assert result.state.plan_progress.completed_subgoal_ids == [
        "reveal-pro",
        "reveal-enterprise",
    ]
    proposed = next(node for node in result.trace.nodes if node.kind == "TaskPlanProposed")
    encoded_context = json.dumps(proposed.payload["planning_context"], sort_keys=True)
    assert "selector" not in encoded_context
    assert "coordinates" not in encoded_context
    assert "backend" not in encoded_context


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


def test_real_chromium_pricing_task_uses_normal_task_planning_entrypoint(
    tmp_path: Path,
) -> None:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        result = run_scenario(
            "pricing",
            f"http://{host}:{port}/pricing",
            tmp_path / "artifacts",
            task_planning=True,
            run_id="pricing-r2-chromium",
        )
        trace_path = next(Path(item) for item in result["artifacts"] if str(item).endswith("events.jsonl"))
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        observation_path = sorted(
            Path(item) for item in result["artifacts"] if "/observations/observation_" in str(item)
        )[-1]
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
        oracle_plans = extract_pricing(str(observation["metadata"]["html"]))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result["status"] == RuntimeStep.DONE.value
    assert result["error_code"] is None
    assert {
        name: {key: value for key, value in plan.items() if key != "visible"} for name, plan in oracle_plans.items()
    } == PRICING_DATA
    assert oracle_plans and all(plan["visible"] for plan in oracle_plans.values())
    assert [event["payload"]["subgoal_id"] for event in events if event["event_type"] == "SubgoalCompleted"] == [
        "reveal-pro",
        "reveal-enterprise",
    ]
    assert any(event["event_type"] == "TaskPlanProposed" for event in events)
    assert any(event["event_type"] == "TaskCompleted" for event in events)


def test_normal_cli_entrypoint_loads_digest_bound_accepted_recovery_profile(tmp_path: Path) -> None:
    payload = RecoverySkillPayload(
        "1.0",
        "recovery_skill",
        ["pricing-profile-load"],
        {"phase": "execution", "normalized_error": "synthetic-never-match"},
        ["reobserve"],
        1,
        ["fresh observation"],
        ["state is independently verified"],
    )
    artifact = EvolutionArtifact(
        id="recovery.profile-load-proof",
        artifact_type=EvolutionArtifactType.SKILL.value,
        summary="accepted generic recovery profile loading proof",
        applicability={"task_id": "pricing-profile-load"},
        source_traces=["sha256:" + "1" * 64],
        status=EvolutionStatus.ACCEPTED,
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )
    registry = EvolutionRegistry()
    registry.propose(artifact)
    profile_path = tmp_path / "accepted-profile.json"
    EvolutionRegistryStore(profile_path).save(registry)
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        result = run_scenario(
            "pricing",
            f"http://{host}:{port}/pricing",
            tmp_path / "profile-artifacts",
            run_id="pricing-profile-load",
            accepted_profile=profile_path,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    trace_path = next(Path(item) for item in result["artifacts"] if str(item).endswith("events.jsonl"))
    first = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert result["status"] == RuntimeStep.DONE.value
    assert result["runtime_profile_digest"].startswith("sha256:")
    assert result["loaded_profile_artifact_ids"] == [artifact.id]
    assert first["payload"]["runtime_profile_digest"] == result["runtime_profile_digest"]
    assert first["payload"]["loaded_profile_artifact_ids"] == [artifact.id]
