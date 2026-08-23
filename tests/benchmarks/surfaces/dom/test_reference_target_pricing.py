from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Thread

from affordance_runtime import (
    NaturalLanguageTaskRequest,
    TaskBoundary,
)
from affordance_runtime.agent import (
    RunStatus,
    SelectAction,
)
from affordance_runtime.app import (
    compose_target_runtime,
)
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, ProductionTaskEvaluator
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.thread_session import ThreadBoundBrowserSession
from affordance_runtime.task import LoopBudget
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.surfaces.dom.reference_site_support import create_reference_server


@dataclass
class PricingPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        assert "/api/pricing" not in repr(context)
        assert "selector" not in repr(context)
        desired_label = "Show Pro limits" if self.calls == 1 else "Show Enterprise limits"
        option = next(
            item for item in context.complete_actions
            if item.target_label == desired_label
        )
        return SelectAction(context.context_id, option.action_id)


def _request() -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        "task:reference-pricing-target",
        "Reveal the Pro and Enterprise pricing limits and return structured evidence",
        TaskBoundary(
            success_criteria=(
                {
                    "id": "all-pricing-records-visible",
                    "kind": "fact_equals",
                    "subject_id": "dom_document",
                    "predicate": "visible_record_count",
                    "expected_value": 2,
                    "required_assurance": "structural",
                },
                {
                    "id": "structured-document-available",
                    "kind": "artifact_exists",
                    "output_id": "structured_document",
                },
            ),
            requested_outputs=("structured_document",),
            loop_budget=LoopBudget(max_turns=5, max_observations=10),
        ),
    )


def test_target_pricing_reveals_records_and_returns_current_structured_dom_output() -> None:
    server = create_reference_server()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    async def scenario() -> None:
        policy = PricingPolicy()
        runtime = compose_target_runtime(
            policy,
            ProductionActionOutcomeProjector(),
            ProductionTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_reference_target_test"),
        )
        with ThreadBoundBrowserSession.launch(f"{base_url}/pricing") as browser:
            environment = UnifiedWorldEnvironment((
                DomSurfaceAdapter(
                    browser,
                    frozenset({"interaction.reveal@v1"}),
                ),
            ))
            started = await runtime.run_request(environment, _request())

        assert started.state is not None
        assert started.state.status is RunStatus.DONE
        assert started.state.execution_count == 2
        assert policy.calls == 2
        evaluation = started.state.current_task_evaluation
        assert {item.output_id for item in evaluation.outputs} == {"structured_document"}
        output = evaluation.outputs[0]
        records = {item["label"]: item["fields"] for item in output.value["records"]}
        assert records == {
            "Pro": {"users": 25, "projects": 100, "support": "Business hours"},
            "Enterprise": {
                "users": "Unlimited",
                "projects": "Unlimited",
                "support": "24/7",
            },
        }
        assert output.value["source_url"] == f"{base_url}/pricing"
        assert output.evidence_refs[0].endswith(":structured_document")
        assert {source.surface for source in started.state.final_observation.sources} == {"dom"}
        assert all("/api/pricing" not in repr(source.artifacts) for source in started.state.final_observation.sources)

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
