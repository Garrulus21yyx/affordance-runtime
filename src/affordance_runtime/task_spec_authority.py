"""Single admission owner for accepted task meaning."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from affordance_runtime.material_binding_policy import MaterialBindingPolicy
from affordance_runtime.material_contracts import MaterialBinding
from affordance_runtime.source_envelope import SourceEnvelope, SourceKind
from affordance_runtime.task_intake import (
    AmbiguityRisk,
    CompilationIssue,
    CompilationPolicy,
    CompilationStatus,
    InputBinding,
    IntentAmbiguity,
    IntentEntity,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    StrictModel,
    TaskRequirement,
    TaskRiskPolicy,
    TaskSemanticPayload,
    TaskSpec,
    TaskStructure,
    UserRequest,
    operation_class_rank,
)
from affordance_runtime.verification.contracts import OutputSpec, SuccessExpression


class MinimalIntentProposal(StrictModel):
    """Untrusted candidate meaning; it carries no admission or planning authority."""

    objective: str = Field(min_length=1, max_length=2_000)
    requested_effects: tuple[RequestedEffect, ...] = Field(min_length=1)
    entities: tuple[IntentEntity, ...] = ()
    preferences: tuple[str, ...] = ()
    desired_outputs: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = Field(min_length=1)
    success: SuccessExpression | None = None
    required_outputs: tuple[OutputSpec, ...] = ()
    constraint_criterion_ids: tuple[str, ...] = ()
    external_effect_criterion_ids: tuple[str, ...] = ()
    final_recheck_criterion_ids: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    semantic_value_constraints: tuple[SemanticValueConstraint, ...] = ()
    material_bindings: tuple[MaterialBinding, ...] = ()
    forbidden_effects: tuple[str, ...] = ()
    ambiguities: tuple[IntentAmbiguity, ...] = ()
    task_structure: TaskStructure = TaskStructure.FLAT


class TaskSpecAdmissionResult(StrictModel):
    status: CompilationStatus
    request_id: str
    proposal: MinimalIntentProposal
    task_spec: TaskSpec | None = None
    issues: tuple[CompilationIssue, ...] = ()

    @property
    def draft(self) -> MinimalIntentProposal:
        """Read-only edge alias while pipeline result naming migrates at P3-4."""

        return self.proposal


@dataclass(frozen=True)
class TaskSpecAuthority:
    """Validate, canonicalize and admit exactly one TaskSpec revision."""

    policy: CompilationPolicy = field(default_factory=CompilationPolicy)
    material_binding_policy: MaterialBindingPolicy = field(
        default_factory=MaterialBindingPolicy
    )

    def admit(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        proposal: MinimalIntentProposal,
        *,
        revision: int = 1,
        task_id: str | None = None,
    ) -> TaskSpecAdmissionResult:
        issues = self._validate(request, envelope, proposal)
        blocking = tuple(
            ambiguity
            for ambiguity in proposal.ambiguities
            if ambiguity.blocking or ambiguity.risk == AmbiguityRisk.HIGH
        )
        if blocking:
            return TaskSpecAdmissionResult(
                status=CompilationStatus.NEEDS_CLARIFICATION,
                request_id=request.request_id,
                proposal=proposal,
                issues=tuple(
                    CompilationIssue(
                        code="blocking_ambiguity",
                        field=item.field,
                        detail=item.reason,
                    )
                    for item in blocking
                ),
            )
        if issues:
            policy_codes = {
                "operation_denied",
                "capability_denied",
                "capability_not_allowed",
                "forbidden_effect",
                "unauthorized_external_effect",
                "observation_cannot_authorize_material_binding",
                "material_effect_operation_mismatch",
            }
            clarification_codes = {
                "material_effect_id_required",
                "material_effect_kind_required",
                "material_binding_missing",
                "material_binding_conflict",
                "material_binding_provenance_insufficient",
            }
            if any(item.code in policy_codes for item in issues):
                status = CompilationStatus.POLICY_CONFLICT
            elif any(item.code in clarification_codes for item in issues):
                status = CompilationStatus.NEEDS_CLARIFICATION
            else:
                status = CompilationStatus.UNSUPPORTED
            return TaskSpecAdmissionResult(
                status=status,
                request_id=request.request_id,
                proposal=proposal,
                issues=tuple(issues),
            )

        operation = max(
            (effect.operation_class for effect in proposal.requested_effects),
            key=operation_class_rank,
        )
        effects = tuple(
            effect.model_copy(
                update={"effect_id": effect.effect_id or f"requirement:effect:{index}"}
            )
            for index, effect in enumerate(proposal.requested_effects, start=1)
        )
        requirements = _canonical_requirements(proposal, effects, envelope)
        requirement_ids = {item.requirement_id for item in requirements}
        inputs = tuple(InputBinding.from_material(item) for item in proposal.material_bindings)
        outputs = tuple(
            output.model_copy(
                update={
                    "requirement_ref": output.requirement_ref
                    or _default_output_requirement(requirements),
                    "source_binding_requirement": (
                        output.source_binding_requirement
                        if output.source_binding_requirement != ("source:any",)
                        else tuple(
                            item.binding_id
                            for item in inputs
                            if item.requirement_ref
                            == (
                                output.requirement_ref
                                or _default_output_requirement(requirements)
                            )
                        )
                        or output.source_binding_requirement
                    ),
                }
            )
            for output in proposal.required_outputs
        )
        task_spec = TaskSpec(
            task_id=task_id or request.request_id,
            revision=revision,
            objective=proposal.objective.strip(),
            operation_class=operation,
            requirements=requirements,
            inputs=inputs,
            allowed_effect_refs=tuple(item.effect_id for item in effects),
            hard_constraint_refs=tuple(
                item.requirement_id
                for item in requirements
                if item.payload.kind == "constraint"
            ),
            preference_refs=tuple(
                item.requirement_id
                for item in requirements
                if item.payload.kind == "preference"
            ),
            forbidden_effect_refs=tuple(
                item.requirement_id
                for item in requirements
                if item.payload.kind == "effect" and item.payload.subject in proposal.forbidden_effects
            ),
            capability_ceiling=_ordered_unique(
                item.capability for item in effects if item.capability
            ),
            risk_policy=TaskRiskPolicy(
                maximum_operation_class=operation,
                approval_required=operation
                in {OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE},
                authoritative_final_recheck_required=operation
                in {OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE},
            ),
            task_structure=proposal.task_structure,
            targets=_ordered_unique(item.target for item in effects),
            entities=proposal.entities,
            preferences=proposal.preferences,
            desired_outputs=proposal.desired_outputs,
            success_criteria=proposal.success_criteria,
            success=proposal.success,
            required_outputs=outputs,
            constraint_criterion_ids=proposal.constraint_criterion_ids,
            external_effect_criterion_ids=proposal.external_effect_criterion_ids,
            final_recheck_criterion_ids=proposal.final_recheck_criterion_ids,
            constraints=proposal.constraints,
            semantic_value_constraints=proposal.semantic_value_constraints,
            forbidden_effects=proposal.forbidden_effects,
            evidence_requirements=proposal.evidence_requirements,
            requested_capabilities=_ordered_unique(
                item.capability for item in proposal.requested_effects if item.capability
            ),
            ambiguity_status="resolved" if not proposal.ambiguities else "non_blocking",
            source_request_ref=request.request_id,
            source_envelope_ref=envelope.identity,
            source_binding_digest=self.material_binding_policy.binding_digest(
                envelope, proposal.material_bindings
            ),
            field_provenance=(),
        )
        assert all(item.requirement_ref in requirement_ids for item in inputs)
        return TaskSpecAdmissionResult(
            status=CompilationStatus.READY,
            request_id=request.request_id,
            proposal=proposal,
            task_spec=task_spec,
        )

    def _validate(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        proposal: MinimalIntentProposal,
    ) -> list[CompilationIssue]:
        if envelope.request_id != request.request_id:
            return [CompilationIssue(code="source_envelope_request_mismatch", field="request_id")]
        authority_source_ids = {
            item.source_id for item in envelope.sources if item.kind != SourceKind.TARGET
        }
        authorized = {
            item.anchor_id
            for item in envelope.anchors
            if item.source_id in authority_source_ids
        }
        authorized.update(authority_source_ids)
        issues: list[CompilationIssue] = []
        forbidden = {_normalized(item) for item in (*self.policy.forbidden_effects, *proposal.forbidden_effects)}
        for index, effect in enumerate(proposal.requested_effects):
            sourced = effect.source_ref in authorized
            if not sourced:
                issues.append(
                    CompilationIssue(
                        code=(
                            "unauthorized_external_effect"
                            if effect.operation_class
                            in {OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE}
                            else "unsourced_requested_effect"
                        ),
                        field=f"requested_effects[{index}]",
                        detail=effect.source_ref,
                    )
                )
            if effect.operation_class not in self.policy.allowed_operations:
                issues.append(CompilationIssue(code="operation_denied", field="requested_effects", detail=effect.operation_class.value))
            if effect.capability in self.policy.denied_capabilities:
                issues.append(CompilationIssue(code="capability_denied", field="requested_effects", detail=effect.capability))
            if (
                effect.capability
                and self.policy.allowed_requested_capabilities is not None
                and effect.capability not in self.policy.allowed_requested_capabilities
            ):
                issues.append(CompilationIssue(code="capability_not_allowed", field="requested_effects", detail=effect.capability))
            if forbidden.intersection({_normalized(effect.target), _normalized(effect.description)}):
                issues.append(CompilationIssue(code="forbidden_effect", field="requested_effects", detail=effect.target))
        for index, entity in enumerate(proposal.entities):
            if entity.source_ref not in authorized:
                issues.append(CompilationIssue(code="unsourced_intent_entity", field=f"entities[{index}]", detail=entity.source_ref))
        for index, constraint in enumerate(proposal.semantic_value_constraints):
            if constraint.source_ref not in authorized:
                issues.append(CompilationIssue(code="unsourced_semantic_value_constraint", field=f"semantic_value_constraints[{index}]", detail=constraint.source_ref))
        issues.extend(
            self.material_binding_policy.validate(
                request,
                envelope,
                proposal.requested_effects,
                proposal.material_bindings,
            )
        )
        return issues


def _ordered_unique(values: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if str(item)))


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical_requirements(
    proposal: MinimalIntentProposal,
    effects: tuple[RequestedEffect, ...],
    envelope: SourceEnvelope,
) -> tuple[TaskRequirement, ...]:
    whole = envelope.whole_request_anchor.anchor_id
    rows = [
        TaskRequirement(
            requirement_id=effect.effect_id,
            payload=TaskSemanticPayload(
                kind="effect",
                subject=effect.target,
                relation="requested_effect",
                value=effect.description,
                operation_class=effect.operation_class,
                material_effect_kind=effect.material_effect_kind,
                capability=effect.capability,
            ),
            source_anchor_refs=(effect.source_ref,),
        )
        for effect in effects
    ]
    rows.extend(
        TaskRequirement(
            requirement_id=f"requirement:constraint:{index}",
            payload=TaskSemanticPayload(kind="constraint", subject=value),
            source_anchor_refs=(whole,),
        )
        for index, value in enumerate(proposal.constraints, start=1)
    )
    rows.extend(
        TaskRequirement(
            requirement_id=f"requirement:preference:{index}",
            payload=TaskSemanticPayload(kind="preference", subject=value),
            source_anchor_refs=(whole,),
        )
        for index, value in enumerate(proposal.preferences, start=1)
    )
    rows.extend(
        TaskRequirement(
            requirement_id=f"requirement:forbidden-effect:{index}",
            payload=TaskSemanticPayload(kind="effect", subject=value, relation="forbidden"),
            source_anchor_refs=(whole,),
        )
        for index, value in enumerate(proposal.forbidden_effects, start=1)
    )
    return tuple(rows)


def _default_output_requirement(requirements: tuple[TaskRequirement, ...]) -> str:
    return next(
        (item.requirement_id for item in requirements if item.payload.kind == "effect"),
        requirements[0].requirement_id if requirements else "",
    )
