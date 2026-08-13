from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Thread

from affordance_runtime import (
    NaturalLanguageTaskRequest,
    TargetRuntimeClient,
    TaskBoundary,
    compose_target_runtime,
)
from affordance_runtime.agent import AgentLoopStatus, SelectAction
from affordance_runtime.browser_thread_session import ThreadBoundBrowserSession
from affordance_runtime.evaluation import ProductionActionEvaluator, ProductionTaskEvaluator
from affordance_runtime.fixtures import create_fixture_server
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.task import LoopBudget
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


@dataclass
class PricingPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        assert "/api/pricing" not in repr(context)
        assert "selector" not in repr(context)
        desired_label = "Show Pro limits" if self.calls == 1 else "Show Enterprise limits"
        labels = {item.target_id: item.label for item in context.world.targets.items}
        option = next(
            item for item in context.actions.options
            if labels.get(item.target_id) == desired_label
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
    server = create_fixture_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    async def scenario() -> None:
        policy = PricingPolicy()
        client = TargetRuntimeClient(compose_target_runtime(
            policy,
            ProductionActionEvaluator(),
            ProductionTaskEvaluator(),
        ))
        with ThreadBoundBrowserSession.launch(f"{base_url}/pricing") as browser:
            environment = UnifiedWorldEnvironment((
                DomSurfaceAdapter(
                    browser,
                    frozenset({"interaction.reveal@v1"}),
                ),
            ))
            started = await client.run(environment, _request())

        assert started.result is not None
        assert started.session is not None
        assert started.result.status is AgentLoopStatus.DONE
        assert started.result.reason_code == "task_complete"
        assert started.result.execution_count == 2
        assert policy.calls == 2
        evaluation = started.session.state.current_task_evaluation
        assert evaluation is not None
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
        assert {source.surface for source in started.result.final_observation.sources} == {"dom"}
        assert all("/api/pricing" not in repr(source.artifacts) for source in started.result.final_observation.sources)

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
