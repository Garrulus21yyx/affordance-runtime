import asyncio
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.cli import run_scenario
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import Observation
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
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.planners import (
    ExportPlanner,
    PricingPlanner,
    PricingTaskPlanner,
    SettingsPlanner,
    extract_pricing,
    pricing_contract_builder,
    pricing_output_requirement,
    pricing_required_outputs,
    pricing_success_expression,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression
from runtime_test_support import canonical_observation, remember_observation


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


def _requirement(
    requirement_id: str,
    subject: str,
    operation_class: OperationClass = OperationClass.READ_ONLY,
) -> TaskRequirement:
    return TaskRequirement(
        requirement_id=requirement_id,
        payload=TaskSemanticPayload(
            kind="effect",
            subject=subject,
            operation_class=operation_class,
        ),
        source_anchor_refs=(f"source:{requirement_id}",),
    )


def test_pricing_gold_path_uses_shared_runtime_and_structural_verification(tmp_path: Path) -> None:
    session = BrowserSession(InteractivePricingPage())
    router = ExecutorRouter()
    router.register(DomExecutor(session))
    result = asyncio.run(
        compose_run_coordinator(
            observer=session,
            executor=router,
            contract_builder=pricing_contract_builder(),
            task_planner=PricingTaskPlanner(),
            artifacts=ArtifactStore(tmp_path / "artifacts"),
        ).run(
            RunRequest(
                task_spec=TaskSpec(
                    task_id="pricing-test",
                    revision=1,
                    objective="extract pricing",
                    operation_class=OperationClass.READ_ONLY,
                    requirements=(
                        *canonical_effect_requirements(
                            ("Show Pro limits", "Show Enterprise limits"),
                            OperationClass.READ_ONLY,
                            "pricing-test",
                            (),
                        ),
                        pricing_output_requirement("pricing-test"),
                    ),
                    allowed_effect_refs=canonical_effect_requirement_refs(
                        ("Show Pro limits", "Show Enterprise limits")
                    ),
                    success=pricing_success_expression(),
                    required_outputs=pricing_required_outputs(),
                    source_request_ref="pricing-test",
                ),
                constraints={"read_only": True, "must_return_evidence": True},
            )
        )
    )

    assert result.status == RuntimeStep.DONE
    assert result.result["plans"]["output_id"] == "plans"
    assert result.result["plans"]["materialization_criterion_id"] == ("criterion:pricing-enterprise-visible")
    assert result.state.step_count == 2
    assert result.state.step_count == 2
    assert result.state.last_receipt is not None
    assert result.state.last_receipt.evidence["selector"] == "#show-enterprise"
    observation_artifacts = list((tmp_path / "artifacts/pricing-test/observations").glob("*.json"))
    assert len(observation_artifacts) >= result.state.step_count + 1


def test_reference_pricing_task_plan_runs_through_normal_coordinator_path() -> None:
    session = BrowserSession(InteractivePricingPage())
    router = ExecutorRouter()
    router.register(DomExecutor(session))
    task = TaskSpec(
        task_id="pricing-plan-reference",
        revision=1,
        objective="Reveal Pro and Enterprise plan limits with structural evidence.",
        operation_class=OperationClass.READ_ONLY,
        requirements=(
            *canonical_effect_requirements(
                ("Show Pro limits", "Show Enterprise limits"),
                OperationClass.READ_ONLY,
                "reference-test",
                (),
            ),
            pricing_output_requirement("reference-test"),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("Show Pro limits", "Show Enterprise limits")),
        success=pricing_success_expression(),
        required_outputs=pricing_required_outputs(),
        evidence_requirements=("post-action DOM evidence for each plan",),
        source_request_ref="reference-test",
    )

    result = compose_run_coordinator(
        observer=session,
        executor=router,
        contract_builder=pricing_contract_builder(),
        task_planner=PricingTaskPlanner(),
    ).run_sync(RunRequest(task_spec=task))

    assert result.status == RuntimeStep.DONE
    assert result.state.task_progress is not None
    assert result.state.task_progress.completed_step_ids == (
        "reveal-pro",
        "reveal-enterprise",
    )
    proposed = next(node for node in result.trace.nodes if node.kind == "TaskPlanProposed")
    encoded_context = json.dumps(to_json_compatible(proposed.payload["planning_context"]), sort_keys=True)
    assert "selector" not in encoded_context
    assert "coordinates" not in encoded_context
    assert "backend" not in encoded_context


def test_reference_pricing_planner_builds_request_before_contract_binding() -> None:
    revision = "pricing-request-v1"
    model = DomAdapter().transduce(
        pricing_html(),
        environment_revision=revision,
        snapshot_id="snapshot-pricing-request",
    )
    observation = Observation(
        revision,
        url="http://fixture/pricing",
        snapshot_id="snapshot-pricing-request",
        page_revision=model.page_revision,
        metadata={"html": pricing_html()},
    )
    state = StateKernel("pricing-request", "Reveal pricing")
    state.transition("observing")
    remember_observation(state, observation)
    state.transition("planning")
    task = TaskSpec(
        task_id="pricing-request",
        revision=1,
        objective="Reveal pricing",
        operation_class=OperationClass.READ_ONLY,
        requirements=(_requirement("requirement:reveal-pricing", "Reveal Pro and Enterprise pricing"),),
        success=SuccessExpression(
            expression_id="success:reveal-pricing",
            operator="criterion",
            criterion_id="criterion:reveal-pricing",
            requirement_refs=("requirement:reveal-pricing",),
        ),
        evidence_requirements=("structural pricing evidence",),
        source_request_ref="pricing-request-source",
    )

    @dataclass
    class RecordingRequestBuilder:
        inner: PlanningRequestBuilder = PlanningRequestBuilder()
        built: PlanningRequest | None = None

        def build(
            self,
            envelope: RunRequest,
            state: StateKernel,
            snapshot: BrowserSnapshot,
        ) -> PlanningRequest:
            self.built = self.inner.build(envelope, state, canonical_observation(snapshot))
            return self.built

    request_builder = RecordingRequestBuilder()
    request = request_builder.build(RunRequest(task_spec=task), state, BrowserSnapshot(observation, model))
    response = PricingPlanner().propose(request)

    assert request_builder.built is request
    assert response.proposal.target_affordance_id == "dom_button_1"
    assert request_builder.built.observation.affordances[0].label == "Show Pro limits"


def test_settings_and_export_reference_planners_consume_canonical_request() -> None:
    revision = "reference-request-v1"

    cases = (
        (
            SettingsPlanner,
            '<button id="notify" bid="notify">Enable notifications</button>',
            "http://fixture/settings",
            "Enable notifications",
        ),
        (
            ExportPlanner,
            '<button id="export" bid="export">Export report</button>',
            "http://fixture/export",
            "Export report",
        ),
    )
    for planner_type, html, url, expected_label in cases:
        model = DomAdapter().transduce(
            html,
            environment_revision=revision,
            snapshot_id=f"snapshot-{expected_label.replace(' ', '-').lower()}",
        )
        observation = Observation(
            revision,
            url=url,
            snapshot_id=model.snapshot_id,
            page_revision=model.page_revision,
            metadata={"html": html},
        )
        state = StateKernel("reference-request", expected_label)
        state.transition("observing")
        remember_observation(state, observation)
        state.transition("planning")
        task = TaskSpec(
            task_id="reference-request",
            revision=1,
            objective=expected_label,
            operation_class=OperationClass.REVERSIBLE_WRITE,
            requirements=(
                _requirement(
                    "requirement:reference-action",
                    expected_label,
                    OperationClass.REVERSIBLE_WRITE,
                ),
            ),
            allowed_effect_refs=("requirement:reference-action",),
            success=SuccessExpression(
                expression_id="success:reference-action",
                operator="criterion",
                criterion_id="criterion:reference-action",
                requirement_refs=("requirement:reference-action",),
            ),
            evidence_requirements=(f"{expected_label} evidence",),
            source_request_ref="reference-request-source",
        )
        request = PlanningRequestBuilder().build(
            RunRequest(task_spec=task),
            state,
            canonical_observation(BrowserSnapshot(observation, model)),
        )
        response = planner_type().propose(request)

        assert response.proposal.target_affordance_id == "dom_button_1"


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
    assert [event["payload"]["step_id"] for event in events if event["event_type"] == "StepCompleted"] == [
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
    assert result["status"] == RuntimeStep.FAILED.value
    assert result["runtime_profile_digest"].startswith("sha256:")
    assert result["loaded_profile_artifact_ids"] == [artifact.id]
    assert first["payload"]["runtime_profile_digest"] == result["runtime_profile_digest"]
    assert first["payload"]["loaded_profile_artifact_ids"] == [artifact.id]
