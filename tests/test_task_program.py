import pytest
from test_agent_loop import _world

from affordance_runtime.agent.decisions import EstablishObjectiveSequence
from affordance_runtime.agent.state import AgentLoopState, SemanticControlMode
from affordance_runtime.benchmarks.target_loop.instrumentation import _decision_trace
from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.task import ActionTemplate, FactEquals, TaskProgram, TaskProgramDisposition
from affordance_runtime.task.objective_sequence import EntitySelector, ObjectiveStep, refresh_objective_sequence_state


def _entity_step(index: int, label: str, action: str, parameters=None) -> ObjectiveStep:
    return ObjectiveStep(
        f"task-step:{index}",
        EntitySelector(FactEquals("identity.label", label)),
        ActionTemplate(action, parameters=parameters or {}),
    )


def test_task_program_persists_future_selector_and_re_resolves_after_fresh_observation() -> None:
    observation = _world("observation:before", False)
    state = AgentLoopState(observation, semantic_control_required=True)
    program = TaskProgram(
        "task-program:login",
        (
            _entity_step(1, "Enable shared state", "activate"),
            _entity_step(2, "Shared state enabled", "activate"),
        ),
    )

    state.install_task_program(program)

    first = state.active_objective_sequence
    assert first is not None
    assert first.resolved_target_id
    assert first.active_step is not None
    assert first.active_step.selector.predicate.expected == "Enable shared state"
    assert state.semantic_control_mode is SemanticControlMode.MEMBER_EXECUTION

    fresh = _world("observation:after", True)
    state.current_observation = fresh
    state.active_objective_sequence = refresh_objective_sequence_state(
        first,
        fresh,
        acted_entity_id=first.resolved_target_id,
        action_status=ActionEvaluationStatus.EFFECT_CONFIRMED,
        effect_evidence_refs=("effect:enabled",),
        enumerator=state.scope_enumerator,
    )
    state._advance_task_program_if_complete()

    assert state.active_task_program is not None
    assert state.active_task_program.completed_step_ids == ("task-step:1",)
    second = state.active_objective_sequence
    assert second is not None
    assert second.active_step is not None
    assert second.active_step.selector.predicate.expected == "Shared state enabled"
    assert second.observation_epoch == fresh.observation_id
    assert second.resolved_target_id == first.resolved_target_id


def test_task_program_cannot_advance_out_of_order_or_duplicate_step_identity() -> None:
    step = _entity_step(1, "Enable shared state", "activate")
    with pytest.raises(ValueError):
        TaskProgram("task-program:duplicate", (step, step))

    state = AgentLoopState(_world("observation:one", False), semantic_control_required=True)
    state.install_task_program(TaskProgram("task-program:one", (step,)))

    assert state.active_task_program is not None
    assert state.active_task_program.disposition is TaskProgramDisposition.ACTIVE
    assert state.active_task_program.completed_step_ids == ()


def test_task_program_propagates_child_resolution_failure_to_typed_program_stop() -> None:
    state = AgentLoopState(_world("observation:missing", False), semantic_control_required=True)
    state.install_task_program(
        TaskProgram(
            "task-program:missing",
            (_entity_step(1, "Control that is not present", "activate"),),
        )
    )

    assert state.active_task_program is not None
    assert state.active_task_program.disposition is TaskProgramDisposition.BLOCKED
    assert state.active_task_program.issue_code == "sequence_selector_no_match"
    assert state.active_objective_sequence is None
    assert state.semantic_control_mode is SemanticControlMode.OBJECTIVE_TRANSITION


def test_task_program_trace_uses_its_own_public_contract() -> None:
    program = TaskProgram(
        "task-program:trace",
        (_entity_step(1, "Login", "activate"),),
    )

    trace = _decision_trace(EstablishObjectiveSequence("context:trace", program))

    assert trace["task_program"]["program_id"] == "task-program:trace"
    assert "sequence" not in trace
