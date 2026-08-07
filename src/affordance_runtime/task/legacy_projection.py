"""One-way legacy intake edge. Target-core modules must not import this module."""

from __future__ import annotations

from typing import Any

from affordance_runtime.task.contracts import LoopBudget, RiskProfile, TaskGoal


def task_spec_to_goal(spec: Any) -> TaskGoal:
    """Project only semantic task data; discard plans, routes, and selectors."""

    task_id = str(getattr(spec, "task_id", "") or getattr(spec, "id", ""))
    instruction = str(getattr(spec, "instruction", "") or getattr(spec, "objective", ""))
    return TaskGoal(
        task_id=task_id,
        instruction=instruction,
        constraints=tuple(getattr(spec, "constraints", ()) or ()),
        forbidden_effects=tuple(getattr(spec, "forbidden_effects", ()) or ()),
        inputs=dict(getattr(spec, "inputs", {}) or {}),
        success_criteria=tuple(getattr(spec, "success_criteria", ()) or ()),
        requested_outputs=tuple(getattr(spec, "requested_outputs", ()) or ()),
        risk_profile=RiskProfile.READ_ONLY,
        loop_budget=LoopBudget(max_turns=int(getattr(spec, "max_steps", 20) or 20), max_observations=40),
    )
