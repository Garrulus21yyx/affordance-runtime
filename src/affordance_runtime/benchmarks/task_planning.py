"""Controlled Flat/Always-plan/Adaptive task-planning ablation.

The environment is deliberately tiny but uses the real Coordinator, task-plan
validators, contract verification, and an independent stage oracle.  It is a
runtime-ablation harness, not a claim about a remote model's capability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_planning import (
    LLMTaskPlanner,
    RuleTaskPlanner,
    TaskPlanCandidate,
    TaskPlannerPort,
    TaskPlanningContext,
)

T = TypeVar("T", bound=BaseModel)
ABLATION_PROFILES = ("flat", "always_plan", "adaptive")


@dataclass(frozen=True)
class TaskPlanningAblationRun:
    profile: str
    case_id: str
    expected_stage: int
    observed_stage: int
    success: bool
    action_count: int
    task_plan_calls: int
    model_calls: int
    task_replans: int
    trace_events: tuple[str, ...]


@dataclass
class _StageEnvironment:
    stage: int = 0
    backend: str = "controlled-stage"

    def capture(self) -> BrowserSnapshot:
        model = DomAdapter().transduce(
            "<button id='advance'>Advance</button>",
            environment_revision=f"stage-{self.stage}",
            snapshot_id=f"stage-snapshot-{self.stage}",
            page_revision=f"stage-page-{self.stage}",
        )
        observation = Observation(
            environment_revision=f"stage-{self.stage}",
            snapshot_id=f"stage-snapshot-{self.stage}",
            page_revision=f"stage-page-{self.stage}",
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            metadata={"stage": self.stage},
        )
        return BrowserSnapshot(observation, model)

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        del observation
        self.stage += 1
        return ExecutionReceipt(
            contract.id,
            "controlled-stage",
            True,
            f"stage-{self.stage - 1}",
            f"stage-{self.stage}",
            0.0,
            evidence={"advanced_to": self.stage},
        )


class _StageActionPlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        next_stage = int(snapshot.observation.metadata["stage"]) + 1
        active_objective = state.active_subgoal()
        active_id = state.plan_progress.active_subgoal_id if state.plan_progress else "subgoal-1"
        return PlannerDecision(
            contract=ActionContract.from_affordance(
                snapshot.affordance_model.affordances[0],
                intent=active_objective or state.goal,
                backend="controlled-stage",
                verifier_plan=[
                    VerifierSpec(
                        "observation_metadata",
                        "stage",
                        next_stage,
                        criterion_ids=(criterion_id("subgoal", active_id, 0),),
                        requirement_ids=(evidence_requirement_id("subgoal", active_id, 0),),
                    )
                ],
            )
        )


@dataclass
class _FixedTaskPlanModel:
    candidate: TaskPlanCandidate
    provider: str = "fixed"
    model: str = "controlled-task-plan"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        self.calls += 1
        return output_schema.model_validate(self.candidate.model_dump(mode="json"))


@dataclass
class _CountingPlanner:
    delegate: TaskPlannerPort
    calls: int = 0

    def plan(self, context: TaskPlanningContext):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.delegate.plan(context)


def run_task_planning_ablation(output_dir: Path) -> dict[str, Any]:
    """Run the fixed short and two-stage cases through all planning profiles."""

    output_dir.mkdir(parents=True, exist_ok=True)
    runs = [
        _run_case(profile, case_id, target_stage)
        for profile in ABLATION_PROFILES
        for case_id, target_stage in (("short", 1), ("long", 3))
    ]
    by_profile = {
        profile: {
            "task_success_rate": sum(item.success for item in runs if item.profile == profile) / 2,
            "short_success": next(item.success for item in runs if item.profile == profile and item.case_id == "short"),
            "long_success": next(item.success for item in runs if item.profile == profile and item.case_id == "long"),
            "mean_action_count": sum(item.action_count for item in runs if item.profile == profile) / 2,
            "model_calls": sum(item.model_calls for item in runs if item.profile == profile),
        }
        for profile in ABLATION_PROFILES
    }
    errors: list[str] = []
    if not by_profile["adaptive"]["short_success"]:
        errors.append("adaptive profile regressed the short-task oracle")
    if not by_profile["adaptive"]["long_success"]:
        errors.append("adaptive profile did not complete the controlled long task")
    if by_profile["flat"]["long_success"]:
        errors.append("flat profile unexpectedly completed the two-stage oracle")
    report = {
        "schema_version": "task-planning-ablation-v1",
        "profiles": by_profile,
        "runs": [item.__dict__ for item in runs],
        "acceptance_errors": errors,
        "oracle": "final controlled environment stage equals target_stage",
        "remote_model_used": False,
    }
    (output_dir / "task-planning-ablation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def _run_case(profile: str, case_id: str, target_stage: int) -> TaskPlanningAblationRun:
    environment = _StageEnvironment()
    spec = TaskSpec(
        task_id=f"task-planning-{profile}-{case_id}",
        revision=1,
        objective=f"Reach stage {target_stage}",
        operation_class=OperationClass.READ_ONLY,
        targets=("advance",),
        success_criteria=(f"stage equals {target_stage}",),
        evidence_requirements=("stage observation",),
        source_request_ref="task-planning-ablation",
    )
    planner, model = _profile_planner(profile, target_stage)
    counting = _CountingPlanner(planner)
    result = RunCoordinator(
        observer=environment,
        planner=_StageActionPlanner(),
        executor=environment,
        task_planner=counting,
    ).run_sync(TaskEnvelope(task_spec=spec))
    return TaskPlanningAblationRun(
        profile=profile,
        case_id=case_id,
        expected_stage=target_stage,
        observed_stage=environment.stage,
        success=result.status == RuntimeStep.DONE and environment.stage == target_stage,
        action_count=result.state.step_count,
        task_plan_calls=counting.calls,
        model_calls=model.calls if model is not None else 0,
        task_replans=result.state.plan_progress.task_replan_count if result.state.plan_progress else 0,
        trace_events=tuple(node.kind for node in result.trace.nodes),
    )


def _profile_planner(profile: str, target_stage: int) -> tuple[TaskPlannerPort, _FixedTaskPlanModel | None]:
    if profile == "flat":
        return RuleTaskPlanner(), None
    candidate = TaskPlanCandidate.model_validate(
        {
            "subgoals": [
                {
                    "subgoal_id": f"stage-{index}",
                    "outcome": {
                        "subject": "stage",
                        "relation": "equals",
                        "value": str(index),
                    },
                    "depends_on": [f"stage-{index - 1}"] if index > 1 else [],
                    "evidence_requirements": ["stage observation"],
                    "operation_class": "read_only",
                    "action_family": "activate",
                }
                for index in range(1, 4)
            ]
        }
    )
    model = _FixedTaskPlanModel(candidate)
    llm = LLMTaskPlanner(model)
    if profile == "always_plan":
        return llm, model
    if profile == "adaptive":
        return (RuleTaskPlanner(), None) if target_stage == 1 else (llm, model)
    raise ValueError(f"unsupported task-planning profile: {profile}")
