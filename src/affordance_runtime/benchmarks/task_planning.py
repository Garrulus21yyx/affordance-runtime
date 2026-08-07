"""Controlled Flat/Always-plan/Adaptive task-planning ablation.

The environment is deliberately tiny but uses the real Coordinator, task-plan
validators, contract verification, and an independent stage oracle.  It is a
runtime-ablation harness, not a claim about a remote model's capability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from affordance_runtime.action_contract_builder import ActionContractMaterializer
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.benchmarks.composition import compose_benchmark_run_coordinator as compose_run_coordinator
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.criteria import (
    LiteralValue,
    PredicateExpr,
    PredicateOperator,
    SubjectExpr,
    criterion_id,
    evidence_requirement_id,
)
from affordance_runtime.effect_authority_contracts import (
    EffectAuthorizationScope,
    EffectClass,
    ResourceScopeRef,
)
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import PlannerProposalResponse
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import legacy_run_request
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StepSpec,
)
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
)
from affordance_runtime.task_plan_contracts import PlanProposal, TaskPlanGeneratorSource
from affordance_runtime.task_planner import PlanningRouter, TaskPlannerPort, TaskPlanningRequest
from affordance_runtime.unified_observation import SourceCoverage
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    PredicateEvidence,
    SatisfactionMode,
    SuccessExpression,
)

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
    rejection_reasons: tuple[str, ...] = ()
    progress_blocks: tuple[dict[str, Any], ...] = ()
    step_rejections: tuple[dict[str, Any], ...] = ()


@dataclass
class _StageEnvironment:
    supported_actions = ("activate", "click")
    provider_capabilities = ()
    adapter_capabilities = ()
    stage: int = 0
    capture_sequence: int = 0
    backend: str = "controlled-stage"
    supported_backends: tuple[str, ...] = ("dom",)

    def capture(self) -> BrowserSnapshot:
        self.capture_sequence += 1
        snapshot_id = f"stage-snapshot-{self.stage}-{self.capture_sequence}"
        model = DomAdapter().transduce(
            (
                "<button id='advance' data-runtime-operation='resource.update@v1' "
                "data-runtime-effect-class='update' data-runtime-externality='local' "
                "data-runtime-reversibility='reversible' "
                "data-runtime-source-assurance='structural' "
                "data-runtime-risk='medium'>Advance</button>"
            ),
            environment_revision=f"stage-{self.stage}",
            snapshot_id=snapshot_id,
            page_revision=f"stage-page-{self.stage}",
        )
        observation = Observation(
            environment_revision=f"stage-{self.stage}",
            snapshot_id=snapshot_id,
            page_revision=f"stage-page-{self.stage}",
            target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
            metadata={
                "stage": self.stage,
                "advanced": self.stage > 0,
                "criterion_evaluations": {
                    f"criterion:stage-{self.stage}": {
                        "status": "satisfied",
                        "evidence_refs": [f"stage:{self.stage}:{snapshot_id}"],
                    },
                },
                "predicate_evidence": {
                    "stage": {
                        "evidence_ref": f"stage:{self.stage}:{snapshot_id}",
                        "observed_value": self.stage,
                        "source_kind": "dom_state",
                        "assurance": "structural",
                    },
                    "advanced": {
                        "evidence_ref": f"advanced:{self.stage}:{snapshot_id}",
                        "observed_value": self.stage > 0,
                        "source_kind": "dom_state",
                        "assurance": "structural",
                    },
                },
            },
        )
        return BrowserSnapshot(
            observation,
            model,
            predicate_evidence=(
                PredicateEvidence(
                    evidence_ref=f"stage:{self.stage}:{snapshot_id}",
                    subject_ref="stage",
                    observed_value=self.stage,
                    source_kind=EvidenceSourceKind.DOM_STATE,
                    assurance=AssuranceLevel.STRUCTURAL,
                    observation_ref=snapshot_id,
                    effect_criterion_ids=(f"criterion:stage-{self.stage}",),
                ),
                PredicateEvidence(
                    evidence_ref=f"advanced:{self.stage}:{snapshot_id}",
                    subject_ref="advanced",
                    observed_value=self.stage > 0,
                    source_kind=EvidenceSourceKind.DOM_STATE,
                    assurance=AssuranceLevel.STRUCTURAL,
                    observation_ref=snapshot_id,
                ),
            ),
            source_coverage=(
                SourceCoverage.complete(
                    GroundingSource.DOM,
                    captured_item_count=len(model.affordances),
                    capture_policy_id="controlled-stage-dom@v1",
                    acquisition_epoch_ref=snapshot_id,
                    adapter_version="controlled-stage@v1",
                ),
            ),
        )

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        del observation
        self.stage += 1
        return ExecutionReceipt(
            contract.id,
            contract.backend,
            True,
            f"stage-{self.stage - 1}",
            f"stage-{self.stage}",
            0.0,
            evidence={"advanced_to": self.stage},
        )


class _StageActionPlanner:
    def propose(self, request: PlanningRequest) -> PlannerProposalResponse:
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id=f"stage-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal=request.step.compatibility_active_step_objective,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=request.observation.affordances[0].target_id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="task-planning-ablation",
            ),
        )


@dataclass
class _FixedCanonicalPlanner:
    target_stage: int
    calls: int = 0

    def propose(self, request: TaskPlanningRequest) -> PlanProposal:
        self.calls += 1
        source_refs = (SourceReference("task-planning-ablation", "task-planning-ablation:advance"),)
        return PlanProposal(
            task_spec_identity=request.task_spec.identity,
            task_revision=request.task_spec.revision,
            generated_by=TaskPlanGeneratorSource.LLM,
            generator_id="controlled-task-plan",
            based_on_observation_ref=request.environment.snapshot_id,
            based_on_state_version=request.state_version,
            steps=tuple(
                _stage_step(
                    index,
                    requirement_refs=tuple(item.requirement_id for item in request.task_spec.requirements),
                    effect_refs=request.task_spec.allowed_effect_refs,
                )
                for index in range(1, self.target_stage + 1)
            ),
            source_refs=source_refs,
        )


def _stage_step(
    index: int,
    *,
    requirement_refs: tuple[str, ...],
    effect_refs: tuple[str, ...],
) -> StepSpec:
    step_id = f"stage-{index}"
    source_refs = (
        SourceReference(
            "task-planning-ablation",
            evidence_requirement_id("subgoal", step_id, 0),
        ),
    )
    return StepSpec(
        step_id=step_id,
        objective=f"stage equals {index}",
        interaction=ElementIntent("Advance", source_refs),
        completion_criteria=(
            PredicateExpr(
                criterion_id("subgoal", step_id, 0),
                SubjectExpr("target", "advanced", "equals"),
                PredicateOperator.EQUALS,
                CriterionPolicy(
                    satisfaction=SatisfactionMode.ACTION_CAUSED,
                    minimum_assurance=AssuranceLevel.STRUCTURAL,
                    allowed_source_kinds=(EvidenceSourceKind.DOM_STATE,),
                    causal_lineage_required=True,
                ),
                LiteralValue(True),
                tuple(ref.source_unit_id for ref in source_refs),
            ),
        ),
        source_refs=source_refs,
        requirement_refs=requirement_refs,
        effect_authorization_refs=effect_refs,
        effectful=True,
        operation_class=OperationClass.REVERSIBLE_WRITE.value,
        depends_on=(f"stage-{index - 1}",) if index > 1 else (),
    )


@dataclass
class _CountingPlanner:
    delegate: TaskPlannerPort
    calls: int = 0

    def propose(self, request: TaskPlanningRequest) -> PlanProposal:
        self.calls += 1
        result = self.delegate.propose(request)
        if not isinstance(result, PlanProposal):
            raise TypeError("controlled benchmark planner must return a synchronous PlanProposal")
        return result


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
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:advance-stage",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="Advance",
                    target_identity="Advance",
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    effect_authorization_scope=EffectAuthorizationScope(
                        requirement_ref="requirement:advance-stage",
                        effect_class=EffectClass.UPDATE,
                        resource_scope=ResourceScopeRef(
                            "dom_button_1",
                            ("task-planning-ablation:advance",),
                        ),
                        operation_constraint="resource.update@v1",
                    ),
                ),
                source_anchor_refs=("task-planning-ablation:advance",),
            ),
        ),
        allowed_effect_refs=("requirement:advance-stage",),
        success=SuccessExpression(
            expression_id=f"success:stage-{target_stage}",
            operator="criterion",
            criterion_id=f"criterion:stage-{target_stage}",
            requirement_refs=("requirement:advance-stage",),
        ),
        source_request_ref="task-planning-ablation",
    )
    planner, model = _profile_planner(profile, target_stage)
    counting = _CountingPlanner(planner)
    result = compose_run_coordinator(
        observer=environment,
        executor=environment,
        contract_builder=ActionContractMaterializer(
            requirements={
                "*": ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "observation_metadata",
                            "advanced",
                            True,
                            progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                        ),
                    )
                )
            }
        ),
        task_planner=counting,
    ).run_sync(legacy_run_request(task_spec=spec))
    return TaskPlanningAblationRun(
        profile=profile,
        case_id=case_id,
        expected_stage=target_stage,
        observed_stage=environment.stage,
        # This is an offline benchmark oracle over the controlled environment;
        # runtime completion remains governed by typed evidence and may fail closed.
        success=environment.stage == target_stage,
        action_count=result.state.step_count,
        task_plan_calls=counting.calls,
        model_calls=model.calls if model is not None else 0,
        task_replans=result.state.task_progress.replan_count if result.state.task_progress else 0,
        trace_events=tuple(node.kind for node in result.trace.nodes),
        rejection_reasons=tuple(
            str(node.payload.get("reason", ""))
            for node in result.trace.nodes
            if node.kind == "PlannerProposalRejected"
        ),
        progress_blocks=tuple(
            dict(node.payload) for node in result.trace.nodes if node.kind == "PlannerProgressBlocked"
        ),
        step_rejections=tuple(
            dict(node.payload) for node in result.trace.nodes if node.kind == "StepEvidenceRejected"
        ),
    )


def _profile_planner(
    profile: str,
    target_stage: int,
) -> tuple[TaskPlannerPort, _FixedCanonicalPlanner | None]:
    if profile == "flat":
        return PlanningRouter(), None
    model = _FixedCanonicalPlanner(target_stage)
    if profile == "always_plan":
        return model, model
    if profile == "adaptive":
        return (PlanningRouter(), None) if target_stage == 1 else (model, model)
    raise ValueError(f"unsupported task-planning profile: {profile}")
