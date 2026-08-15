"""Provider-neutral, private-payload-free future evaluator inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget
from affordance_runtime.agent.context.contracts import AgentTaskView
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.context.task_projection import project_task
from affordance_runtime.agent.context.world_projection import ModelWorldView, project_model_world
from affordance_runtime.evaluation.criterion_contracts import NormalizedCriterionSpec
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution.contracts import ActionError, ActionIntent, ActionResult, DispatchStatus
from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


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
    before: ModelWorldView
    after: ModelWorldView
    intent: ModelActionIntentView
    result: ModelActionResultView
    available_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_evidence_refs", tuple(self.available_evidence_refs))


@dataclass(frozen=True)
class ModelTaskEvaluationView:
    task: AgentTaskView
    world: ModelWorldView
    requested_output_ids: tuple[str, ...]
    available_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_output_ids", tuple(self.requested_output_ids))
        object.__setattr__(self, "available_evidence_refs", tuple(self.available_evidence_refs))


@dataclass(frozen=True)
class ModelCriterionView:
    criterion_id: str
    adjudicator: str
    rubric: str
    evidence_scope_target_ids: tuple[str, ...]
    evidence_scope_output_ids: tuple[str, ...]
    required_assurance: str


@dataclass(frozen=True)
class ModelCriterionEvidenceWindow:
    criterion_id: str
    eligible_count: int
    visible_count: int
    truncated: bool


@dataclass(frozen=True)
class ModelEvidenceRecordView:
    evidence_ref: str
    kind: str
    subject_id: str
    predicate: str
    public_value: object
    output_id: str
    modality: str
    assurance: str
    public_summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_value", freeze_json(self.public_value))


@dataclass(frozen=True)
class SemanticJudgeRequest:
    task: AgentTaskView
    criteria: tuple[ModelCriterionView, ...]
    world: ModelWorldView
    evidence_catalog: BoundedSection[ModelEvidenceRecordView]
    evidence_windows: tuple[ModelCriterionEvidenceWindow, ...] = ()

    @property
    def visible_evidence_refs(self) -> tuple[str, ...]:
        return tuple(item.evidence_ref for item in self.evidence_catalog.items)


def build_model_action_evaluation_view(
    task: TaskGoal,
    before: WorldObservation,
    after: WorldObservation,
    intent: ActionIntent,
    result: ActionResult,
    evidence_index: WorldEvidenceIndex,
    budget: ContextProjectionBudget = ContextProjectionBudget(),
) -> ModelActionEvaluationView:
    return ModelActionEvaluationView(
        project_task(task),
        project_model_world(before, budget),
        project_model_world(after, budget),
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
    world: WorldObservation,
    evidence_index: WorldEvidenceIndex,
    budget: ContextProjectionBudget = ContextProjectionBudget(),
) -> ModelTaskEvaluationView:
    return ModelTaskEvaluationView(
        project_task(task),
        project_model_world(world, budget),
        task.requested_outputs,
        evidence_index.refs,
    )


def build_semantic_judge_request(
    task: TaskGoal,
    criteria: tuple[NormalizedCriterionSpec, ...],
    world: WorldObservation,
    evidence_index: WorldEvidenceIndex,
    budget: ContextProjectionBudget = ContextProjectionBudget(),
) -> SemanticJudgeRequest:
    target_scope = tuple(dict.fromkeys(item for criterion in criteria for item in criterion.evidence_scope_target_ids))
    output_scope = tuple(dict.fromkeys(item for criterion in criteria for item in criterion.evidence_scope_output_ids))
    projected_world = project_model_world(world, budget, target_scope, output_scope)
    visible_refs = {
        *(item.fact_ref for item in projected_world.facts.items),
        *(item.evidence_ref for item in projected_world.artifact_summaries.items),
    }
    eligible = tuple(
        record for record in evidence_index.records
        if _semantic_record_in_scope(record, target_scope, output_scope)
        and record.has_typed_source
    )
    shown = tuple(_model_evidence(record) for record in eligible if record.evidence_ref in visible_refs)
    task_view = replace(project_task(task), success_criteria=BoundedSection((), 0, False))
    windows = tuple(_evidence_window(item, eligible, shown) for item in criteria)
    return SemanticJudgeRequest(
        task_view,
        tuple(
            ModelCriterionView(
                item.criterion_id, str(item.adjudicator), item.rubric,
                item.evidence_scope_target_ids, item.evidence_scope_output_ids,
                item.required_assurance,
            )
            for item in criteria
        ),
        projected_world,
        BoundedSection(shown, len(eligible), len(eligible) > len(shown)), windows,
    )


def _evidence_window(criterion, eligible, shown) -> ModelCriterionEvidenceWindow:
    scoped = tuple(
        item for item in eligible
        if _semantic_record_in_scope(
            item, criterion.evidence_scope_target_ids, criterion.evidence_scope_output_ids
        )
    )
    shown_refs = {item.evidence_ref for item in shown}
    visible = sum(item.evidence_ref in shown_refs for item in scoped)
    return ModelCriterionEvidenceWindow(
        criterion.criterion_id, len(scoped), visible, len(scoped) > visible
    )


def _semantic_record_in_scope(record, targets: tuple[str, ...], outputs: tuple[str, ...]) -> bool:
    return (
        record.kind == "fact" and record.subject_id in targets
        or record.kind == "artifact" and record.output_id in outputs
    )


def _model_evidence(record) -> ModelEvidenceRecordView:
    value = project_public_value(record.value) if record.kind == "fact" else None
    summary = record.public_summary or (
        f"{record.subject_id} {record.predicate} evidence" if record.kind == "fact" else f"{record.output_id} artifact available"
    )
    return ModelEvidenceRecordView(
        record.evidence_ref, record.kind, record.subject_id, record.predicate, value,
        record.output_id, record.source_modality, record.source_assurance, summary[:500],
    )
