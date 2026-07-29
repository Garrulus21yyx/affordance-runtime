from __future__ import annotations

import pytest

from affordance_runtime.simplified_runtime_contracts import StepActivityStatus


def test_planning_request_contracts_are_deeply_immutable() -> None:
    from affordance_runtime.planning_request import (
        PlannerAffordanceView,
        PlannerObservationView,
        PlannerStepView,
        PlannerTaskView,
        PlanningRequest,
        PlanningRequestIdentity,
        RuntimeBudgetView,
    )

    mutable_state = {"value": "Alice", "ignored": ["mutable"]}
    affordance = PlannerAffordanceView(
        target_id="semantic:name",
        surface="dom",
        role="textbox",
        label="Name",
        supported_actions=("type_text",),
        state=mutable_state,
        confidence=0.9,
        conflict_codes=("none",),
        source_refs=("source:control:1",),
    )
    request = PlanningRequest(
        identity=PlanningRequestIdentity(
            task_spec_identity="sha256:task",
            task_revision=1,
            evaluated_at_state_version=7,
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
        ),
        task=PlannerTaskView(
            task_spec_identity="sha256:task",
            task_revision=1,
            objective="Type Alice",
            constraints=("no navigation",),
            capabilities=("browser.write",),
            task_completion_criterion=None,
            task_completion_projection_status="pending",
        ),
        step=PlannerStepView(
            plan=None,
            progress=None,
            active_step=None,
            activity_status=StepActivityStatus.NO_PLAN,
        ),
        observation=PlannerObservationView(
            snapshot_id="snapshot-1",
            page_revision="page-1",
            environment_revision="env-1",
            observed_text="Name",
            affordances=(affordance,),
            artifact_refs=("artifact:sha256:abc",),
        ),
        remaining_budget=RuntimeBudgetView(
            steps=1,
            observations=2,
            recoveries=3,
            effectful_actions=4,
            model_calls=5,
        ),
        permitted_action_kinds=("type_text",),
    )

    mutable_state["value"] = "Mallory"
    mutable_state["ignored"].append("changed")

    assert request.observation.affordances[0].state == (("value", "Alice"),)
    with pytest.raises(TypeError):
        request.observation.affordances[0].state[0] = ("value", "Mallory")  # type: ignore[index]


def test_planning_request_rejects_raw_runtime_objects() -> None:
    from affordance_runtime.planning_request import (
        PlannerObservationView,
        PlannerStepView,
        PlannerTaskView,
        PlanningRequest,
        PlanningRequestIdentity,
        RuntimeBudgetView,
    )
    from affordance_runtime.state_kernel import StateKernel

    with pytest.raises(TypeError, match="raw_state"):
        PlanningRequest(
            identity=PlanningRequestIdentity(
                task_spec_identity="sha256:task",
                task_revision=1,
                evaluated_at_state_version=1,
                snapshot_id="snapshot-1",
                page_revision="page-1",
                environment_revision="env-1",
            ),
            task=PlannerTaskView(
                task_spec_identity="sha256:task",
                task_revision=1,
                objective="Do it",
                constraints=(),
                capabilities=(),
                task_completion_criterion=None,
                task_completion_projection_status="pending",
            ),
            step=PlannerStepView(
                plan=None,
                progress=None,
                active_step=None,
                activity_status=StepActivityStatus.NO_PLAN,
            ),
            observation=PlannerObservationView(
                snapshot_id="snapshot-1",
                page_revision="page-1",
                environment_revision="env-1",
                observed_text="",
                affordances=(),
                artifact_refs=(),
            ),
            remaining_budget=RuntimeBudgetView(
                steps=1,
                observations=1,
                recoveries=1,
                effectful_actions=1,
                model_calls=1,
            ),
            permitted_action_kinds=("finish",),
            raw_state=StateKernel(task_id="task", goal="Do it"),  # type: ignore[call-arg]
        )
