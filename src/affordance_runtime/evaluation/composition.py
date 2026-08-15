"""Runtime-owned criterion-specific production task evaluation composition."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.context.evaluator_views import build_semantic_judge_request
from affordance_runtime.agent.context.failures import ModelFailure
from affordance_runtime.evaluation.contracts import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.criterion_contracts import CriterionAdjudicator
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_applicability import EvidenceApplicability, assess_semantic_evidence
from affordance_runtime.evaluation.mechanical_criteria import MechanicalCriterionEvaluator
from affordance_runtime.evaluation.output_binding import collect_current_outputs
from affordance_runtime.evaluation.output_validation import validate_required_outputs
from affordance_runtime.evaluation.semantic_contracts import SemanticCriterionJudge, SemanticCriterionProposal
from affordance_runtime.evaluation.semantic_readiness import SemanticReadiness, assess_semantic_readiness
from affordance_runtime.evaluation.success_expression import evaluate_success_expression
from affordance_runtime.evaluation.user_acceptance import UserAcceptanceCriterionEvaluator
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import CoverageState, WorldObservation


@dataclass(frozen=True)
class ProductionTaskEvaluator:
    semantic_judge: SemanticCriterionJudge | None = None
    mechanical: MechanicalCriterionEvaluator = MechanicalCriterionEvaluator()
    user_acceptance: UserAcceptanceCriterionEvaluator = UserAcceptanceCriterionEvaluator()

    async def evaluate(self, task: TaskGoal, observation: WorldObservation) -> TaskEvaluation:
        try:
            specs = normalize_task_criteria(task)
        except ValueError:
            return _task(task, observation, TaskEvaluationStatus.BLOCKED, (), (), "criterion contract is unsupported")
        index = WorldEvidenceIndex.from_observation(observation)
        mechanical = {
            spec.criterion_id: self.mechanical.evaluate(spec, observation)
            for spec in specs
            if spec.adjudicator in {CriterionAdjudicator.MECHANICAL, CriterionAdjudicator.HYBRID}
        }
        semantic = await self._semantic(task, observation, index, specs, mechanical)
        evaluations = tuple(
            self._criterion(spec, observation, index, mechanical, semantic) for spec in specs
        )
        try:
            evaluations = _apply_authority_and_lineage(task, observation, index, evaluations)
        except ValueError:
            return _task(task, observation, TaskEvaluationStatus.BLOCKED, evaluations, (), "authoritative or lineage contract is unsupported")
        outputs = collect_current_outputs(task.requested_outputs, observation)
        try:
            expression = task.evaluation_spec.success_expression if task.evaluation_spec else None
            success = evaluate_success_expression(expression, {item.criterion_id: item.status for item in evaluations})
            status = _status(success, evaluations)
            if task.requested_outputs and len(outputs) != len(task.requested_outputs):
                complete_inventory = bool(observation.coverage) and all(
                    value == CoverageState.COMPLETE for value in observation.coverage.values()
                )
                output_status = TaskEvaluationStatus.INCOMPLETE if complete_inventory else TaskEvaluationStatus.UNKNOWN
                if status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.INCOMPLETE}:
                    return _task(task, observation, output_status, evaluations, outputs, "required outputs are not yet available")
                return _task(task, observation, status, evaluations, outputs, "criterion status precedes missing output")
            candidate = _task(task, observation, status, evaluations, outputs, "Runtime composed criterion status")
            if status == TaskEvaluationStatus.COMPLETE:
                validate_required_outputs(task, candidate, index)
            return candidate
        except ValueError:
            return _task(task, observation, TaskEvaluationStatus.BLOCKED, evaluations, outputs, "evaluation contract is unsupported or violated")

    async def _semantic(self, task, observation, index, specs, mechanical):
        candidates = tuple(
            spec for spec in specs
            if spec.adjudicator == CriterionAdjudicator.SEMANTIC
            or spec.adjudicator == CriterionAdjudicator.HYBRID
            and mechanical[spec.criterion_id].status == CriterionEvaluationStatus.SATISFIED
        )
        try:
            initial = build_semantic_judge_request(task, candidates, observation, index)
        except (TypeError, ValueError):
            return _SemanticBatch({}, {
                item.criterion_id: SemanticReadiness.INCONCLUSIVE for item in candidates
            }, ())
        readiness = {
            spec.criterion_id: assess_semantic_readiness(spec, initial, observation)
            for spec in candidates
        }
        ready = tuple(spec for spec in candidates if readiness[spec.criterion_id] == SemanticReadiness.READY)
        try:
            request = build_semantic_judge_request(task, ready, observation, index)
        except (TypeError, ValueError):
            return _SemanticBatch({}, {
                **readiness, **{item.criterion_id: SemanticReadiness.INCONCLUSIVE for item in ready}
            }, ())
        if not ready or self.semantic_judge is None:
            return _SemanticBatch({}, readiness, request.visible_evidence_refs)
        try:
            outcome = await self.semantic_judge.evaluate(request)
        except Exception:
            return _SemanticBatch({}, readiness, request.visible_evidence_refs)
        if isinstance(outcome, ModelFailure):
            return _SemanticBatch({}, readiness, request.visible_evidence_refs)
        identities = tuple(item.criterion_id for item in outcome)
        expected = tuple(item.criterion_id for item in ready)
        if len(set(identities)) != len(identities) or set(identities) != set(expected):
            return _SemanticBatch({}, readiness, request.visible_evidence_refs)
        return _SemanticBatch(
            {item.criterion_id: item for item in outcome}, readiness, request.visible_evidence_refs
        )

    def _criterion(self, spec, observation, index, mechanical, semantic):
        if spec.adjudicator == CriterionAdjudicator.MECHANICAL:
            return mechanical[spec.criterion_id]
        if spec.adjudicator == CriterionAdjudicator.USER_ACCEPTANCE:
            return self.user_acceptance.evaluate(spec, index)
        if spec.adjudicator == CriterionAdjudicator.HYBRID and mechanical[spec.criterion_id].status != CriterionEvaluationStatus.SATISFIED:
            return mechanical[spec.criterion_id]
        semantic_result = _semantic_evaluation(spec, semantic, index)
        if spec.adjudicator == CriterionAdjudicator.SEMANTIC:
            return semantic_result
        return _hybrid(spec, mechanical[spec.criterion_id], semantic_result)


@dataclass(frozen=True)
class _SemanticBatch:
    proposals: dict[str, SemanticCriterionProposal]
    readiness: dict[str, SemanticReadiness]
    visible_evidence_refs: tuple[str, ...]


def _semantic_evaluation(spec, batch, index) -> CriterionEvaluation:
    readiness = batch.readiness.get(spec.criterion_id, SemanticReadiness.INCONCLUSIVE)
    if readiness == SemanticReadiness.NOT_READY:
        return CriterionEvaluation(spec.criterion_id, CriterionEvaluationStatus.UNSATISFIED, (), "semantic scope is not yet present")
    if readiness == SemanticReadiness.INCONCLUSIVE:
        return CriterionEvaluation(spec.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "semantic scope readiness is inconclusive")
    proposal = batch.proposals.get(spec.criterion_id)
    if proposal is None:
        return CriterionEvaluation(spec.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "semantic proposal unavailable")
    try:
        evaluation = CriterionEvaluation(spec.criterion_id, proposal.status, proposal.evidence_refs, proposal.reason)
    except ValueError:
        return CriterionEvaluation(spec.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "semantic proposal invalid")
    if assess_semantic_evidence(
        spec, evaluation, index, batch.visible_evidence_refs
    ) != EvidenceApplicability.ACCEPTED:
        return CriterionEvaluation(spec.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "semantic evidence is not applicable")
    return evaluation


def _hybrid(spec, mechanical, semantic) -> CriterionEvaluation:
    statuses = {mechanical.status, semantic.status}
    if CriterionEvaluationStatus.UNSATISFIED in statuses:
        status = CriterionEvaluationStatus.UNSATISFIED
    elif statuses == {CriterionEvaluationStatus.SATISFIED}:
        status = CriterionEvaluationStatus.SATISFIED
    else:
        return CriterionEvaluation(spec.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "hybrid component is unknown")
    refs = tuple(dict.fromkeys((*mechanical.evidence_refs, *semantic.evidence_refs)))
    return CriterionEvaluation(spec.criterion_id, status, refs, "mechanical and semantic components composed")


def _apply_authority_and_lineage(task, observation, index, evaluations):
    spec = task.evaluation_spec
    required = set(spec.authoritative_checks) if spec else set()
    known = {item.criterion_id for item in evaluations}
    if not required.issubset(known):
        raise ValueError("authoritative check references unknown criterion")
    result = []
    for evaluation in evaluations:
        records = tuple(index.resolve_record(ref) for ref in evaluation.evidence_refs)
        resolved = evaluation.status in {
            CriterionEvaluationStatus.SATISFIED, CriterionEvaluationStatus.UNSATISFIED
        }
        invalid_lineage = bool(spec and spec.strict_source_lineage) and (
            not records or any(
            record is None or record.observation_id != observation.observation_id
            or not record.source_observation_id
            or all(source.observation_id != record.source_observation_id for source in observation.sources)
            for record in records
        ))
        insufficient = evaluation.criterion_id in required and (
            not records or any(
            record is None or record.source_assurance != "authoritative" for record in records
        ))
        if resolved and (invalid_lineage or insufficient):
            evaluation = CriterionEvaluation(evaluation.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "criterion assurance or lineage is insufficient")
        result.append(evaluation)
    return tuple(result)


def _status(success: bool | None, evaluations) -> TaskEvaluationStatus:
    if any(item.status == CriterionEvaluationStatus.BLOCKED for item in evaluations):
        return TaskEvaluationStatus.BLOCKED
    if success is True:
        return TaskEvaluationStatus.COMPLETE
    if success is False:
        return TaskEvaluationStatus.INCOMPLETE
    return TaskEvaluationStatus.UNKNOWN


def _task(task, observation, status, criteria, outputs, reason) -> TaskEvaluation:
    refs = tuple(
        dict.fromkeys(
            [ref for item in criteria for ref in item.evidence_refs]
            + [ref for item in outputs for ref in item.evidence_refs]
        )
    ) if status == TaskEvaluationStatus.COMPLETE else ()
    return TaskEvaluation(task.task_id, observation.observation_id, status, reason, tuple(criteria), refs, tuple(outputs))
