"""Runtime loop transition and event commit helpers."""

from __future__ import annotations

from affordance_runtime.runtime_loop_phase import RuntimeLoopEvent, RuntimeLoopTransition
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode


def apply_runtime_loop_transition(
    state: StateKernel,
    transition: RuntimeLoopTransition,
) -> None:
    state.transition(transition.phase.value)
    if transition.activate_next_subgoal:
        state.activate_next_subgoal()


def commit_runtime_loop_event(
    trace: TraceDag,
    event: RuntimeLoopEvent,
    parent: TraceNode | None = None,
) -> TraceNode:
    parent_ids = event.parent_ids
    if not parent_ids and parent is not None:
        parent_ids = (parent.id,)
    return trace.add(
        event.kind,
        event.payload,
        parents=list(parent_ids) if parent_ids else None,
    )
