"""Provider-neutral, private-payload-free future evaluator inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution.contracts import ActionError, ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.contracts import AgentTaskView
from affordance_runtime.model_boundary.projection import project_public_value, project_task
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.view import AgentWorldView


@dataclass(frozen=True)
class ModelActionIntentView:
    semantic_action: str
    target_id: str
    destination_id: str = ""
    public_parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_parameters", freeze_json(self.public_parameters))


@dataclass(frozen=True)
class ModelActionResultView:
    dispatch_status: DispatchStatus
    public_error_category: ActionError | None


@dataclass(frozen=True)
class ModelActionEvaluationView:
    task: AgentTaskView
    world: AgentWorldView
    intent: ModelActionIntentView
    result: ModelActionResultView
    available_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_evidence_refs", tuple(self.available_evidence_refs))


@dataclass(frozen=True)
class ModelTaskEvaluationView:
    task: AgentTaskView
    world: AgentWorldView
    requested_output_ids: tuple[str, ...]
    available_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_output_ids", tuple(self.requested_output_ids))
        object.__setattr__(self, "available_evidence_refs", tuple(self.available_evidence_refs))


def build_model_action_evaluation_view(
    task: TaskGoal,
    world: AgentWorldView,
    intent: ActionIntent,
    result: ActionResult,
    evidence_index: WorldEvidenceIndex,
) -> ModelActionEvaluationView:
    return ModelActionEvaluationView(
        project_task(task),
        world,
        ModelActionIntentView(
            intent.semantic_action,
            intent.target_id,
            intent.destination_id,
            project_public_value(intent.parameters),
        ),
        ModelActionResultView(result.dispatch_status, result.error),
        evidence_index.refs,
    )


def build_model_task_evaluation_view(
    task: TaskGoal,
    world: AgentWorldView,
    evidence_index: WorldEvidenceIndex,
) -> ModelTaskEvaluationView:
    return ModelTaskEvaluationView(
        project_task(task),
        world,
        task.requested_outputs,
        evidence_index.refs,
    )
