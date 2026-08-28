from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Thread

from affordance_runtime import (
    NaturalLanguageTaskRequest,
    TaskBoundary,
)
from affordance_runtime.agent import (
    RequestObservation,
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
from affordance_runtime.surfaces.http_json import (
    HttpJsonAuthority,
    HttpJsonFactProjection,
    HttpJsonSourceRegistration,
    HttpJsonSurfaceAdapter,
)
from affordance_runtime.task import LoopBudget, RiskProfile
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.surfaces.dom.reference_site_support import create_reference_server


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
            context_id=context.context_id,
            query_id="observation-query:settings",
            purpose="criterion_verification",
            subject_ids=("settings",),
            public_intent="verify that notification settings were persisted",
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
    server = create_reference_server()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    async def scenario() -> None:
        policy = SettingsPolicy()
        runtime = compose_target_runtime(
            policy,
            ProductionActionOutcomeProjector(),
            ProductionTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("atomic_reference_target_test"),
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

            assert started.state is not None
            assert started.state.status is RunStatus.WAITING_CONFIRMATION
            assert started.state.execution_count == 0
            assert started.state.last_step is not None
            confirmation = started.state.last_step.confirmation
            assert confirmation is not None

            completed = await runtime.resume_confirmation(
                environment,
                started.intake.task,
                started.state,
                approved=True,
            )

            assert completed.status is RunStatus.DONE
            assert completed.execution_count == 1
            assert policy.calls == 2
            assert {source.surface for source in completed.final_observation.sources} == {
                "http_json",
            }
            persisted = next(
                fact for fact in completed.final_observation.facts
                if fact.subject_id == "settings" and fact.predicate == "notifications"
            )
            assert persisted.value == "enabled"
            evaluation = completed.current_task_evaluation
            assert evaluation.completion_evidence_refs == (persisted.fact_id,)

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
