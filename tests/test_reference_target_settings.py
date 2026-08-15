from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Thread

from affordance_runtime import (
    NaturalLanguageTaskRequest,
    TaskBoundary,
)
from affordance_runtime.agent import AgentLoopStatus, RequestObservation, SelectAction, compose_target_runtime
from affordance_runtime.browser_thread_session import ThreadBoundBrowserSession
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.evaluation import ProductionActionEvaluator, ProductionTaskEvaluator
from affordance_runtime.fixtures import create_fixture_server
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.http_json import (
    HttpJsonAuthority,
    HttpJsonFactProjection,
    HttpJsonSourceRegistration,
    HttpJsonSurfaceAdapter,
)
from affordance_runtime.task import LoopBudget, RiskProfile
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


@dataclass
class SettingsPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        public_context = repr(context)
        assert "/api/state" not in public_context
        assert "selector" not in public_context
        if self.calls == 1:
            assert len(context.actions.options) == 1
            return SelectAction(context.context_id, context.actions.options[0].action_id)
        return RequestObservation(
            context.context_id,
            "settings",
            "environment_state",
            "authoritative",
            "verify that notification settings were persisted",
        )


def _request() -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        "task:reference-settings-target",
        "Enable notifications in settings",
        TaskBoundary(
            allowed_effects=("update",),
            success_criteria=({
                "id": "settings-persisted",
                "kind": "fact_equals",
                "subject_id": "settings",
                "predicate": "notifications",
                "expected_value": "enabled",
                "required_assurance": "authoritative",
            },),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(max_turns=6, max_observations=12),
        ),
    )


def test_target_settings_confirms_action_then_completes_from_unified_authoritative_world() -> None:
    server = create_fixture_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    async def scenario() -> None:
        policy = SettingsPolicy()
        runtime = compose_target_runtime(
            policy,
            ProductionActionEvaluator(),
            ProductionTaskEvaluator(),
        )
        registration = HttpJsonSourceRegistration(
            "reference-settings-state",
            f"{base_url}/api/state",
            (
                HttpJsonFactProjection(
                    "settings",
                    "resource",
                    "Notification settings",
                    "notifications",
                    ("settings", "notifications"),
                ),
            ),
            HttpJsonAuthority.REGISTERED_STATE_API,
        )
        with ThreadBoundBrowserSession.launch(f"{base_url}/settings") as browser:
            environment = UnifiedWorldEnvironment((
                DomSurfaceAdapter(browser),
                HttpJsonSurfaceAdapter(registration),
            ))
            started = await runtime.run_request(environment, _request())

            assert started.result is not None
            assert started.session is not None
            assert started.result.status is AgentLoopStatus.WAITING_CONFIRMATION
            assert started.result.execution_count == 0
            confirmation = started.result.confirmation_request
            assert confirmation is not None

            completed = await started.session.resolve_confirmation(
                ConfirmationDecision(
                    confirmation.confirmation_id,
                    confirmation.subject_id,
                    ConfirmationDecisionKind.CONFIRM,
                ),
            )

            assert completed.status is AgentLoopStatus.DONE
            assert completed.reason_code == "task_complete"
            assert completed.execution_count == 1
            assert policy.calls == 2
            assert {source.surface for source in completed.final_observation.sources} == {
                "dom",
                "http_json",
            }
            persisted = next(
                fact for fact in completed.final_observation.facts
                if fact.subject_id == "settings" and fact.predicate == "notifications"
            )
            assert persisted.value == "enabled"
            evaluation = started.session.state.current_task_evaluation
            assert evaluation is not None
            assert evaluation.completion_evidence_refs == (persisted.fact_id,)
            assert started.session.state.unresolved_observable_request is None

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
