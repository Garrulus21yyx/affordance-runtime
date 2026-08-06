"""Single admission owner for accepted task meaning."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from pydantic import ConfigDict, Field, ValidationError

from affordance_runtime.effect_authority_contracts import (
    EffectAuthorizationScope,
    EffectClass,
    Externality,
    ParameterAuthorization,
    ResourceScopeRef,
    Reversibility,
)
from affordance_runtime.effect_operation_policy import semantics_for_operation
from affordance_runtime.high_risk_effect_policy import policy_for_effect
from affordance_runtime.material_binding_policy import MaterialBindingPolicy
from affordance_runtime.material_contracts import MaterialBinding
from affordance_runtime.source_envelope import SourceEnvelope, SourceKind
from affordance_runtime.task_intake import (
    AmbiguityRisk,
    CompilationIssue,
    CompilationPolicy,
    CompilationStatus,
    CriterionSourceBinding,
    InputBinding,
    IntentAmbiguity,
    IntentEntity,
    OperationClass,
    RequestedEffect,
    SemanticValueConstraint,
    StrictModel,
    TaskInteractionRelationKind,
    TaskRequirement,
    TaskRiskPolicy,
    TaskSemanticPayload,
    TaskSpec,
    TaskStructure,
    UserRequest,
    operation_class_rank,
    success_criterion_policies,
    success_criterion_requirement_bindings,
)
from affordance_runtime.verification.contracts import AssuranceLevel, OutputSpec, SuccessExpression


class MinimalIntentProposal(StrictModel):
    """Untrusted candidate meaning; it carries no admission or planning authority."""

    objective: str = Field(min_length=1, max_length=2_000)
    requested_effects: tuple[RequestedEffect, ...] = Field(min_length=1)
    entities: tuple[IntentEntity, ...] = ()
    preferences: tuple[str, ...] = ()
    success: SuccessExpression
    required_outputs: tuple[OutputSpec, ...] = ()
    constraint_criterion_ids: tuple[str, ...] = ()
    external_effect_criterion_ids: tuple[str, ...] = ()
    final_recheck_criterion_ids: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    semantic_value_constraints: tuple[SemanticValueConstraint, ...] = ()
    material_bindings: tuple[MaterialBinding, ...] = ()
    forbidden_effects: tuple[str, ...] = ()
    ambiguities: tuple[IntentAmbiguity, ...] = ()
    task_structure: TaskStructure = TaskStructure.FLAT


_ADMISSION_CAPABILITY = object()


@dataclass(frozen=True, init=False)
class AdmittedTaskSpec:
    """In-process capability proving that Authority admitted this exact TaskSpec."""

    task_spec: TaskSpec
    admission_id: str
    source_envelope_identity: str
    previous_task_identity: str

    def __init__(
        self,
        task_spec: TaskSpec,
        admission_id: str,
        source_envelope_identity: str,
        previous_task_identity: str = "",
        *,
        _capability: object | None = None,
    ) -> None:
        if _capability is not _ADMISSION_CAPABILITY:
            raise TypeError("AdmittedTaskSpec can only be issued by TaskSpecAuthority")
        if task_spec.source_envelope_ref != source_envelope_identity:
            raise ValueError("admitted TaskSpec does not match its SourceEnvelope identity")
        object.__setattr__(self, "task_spec", task_spec)
        object.__setattr__(self, "admission_id", admission_id)
        object.__setattr__(self, "source_envelope_identity", source_envelope_identity)
        object.__setattr__(self, "previous_task_identity", previous_task_identity)


class TaskSpecAdmissionResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    status: CompilationStatus
    request_id: str
    proposal: MinimalIntentProposal
    task_spec: TaskSpec | None = None
    admitted_task: AdmittedTaskSpec | None = None
    issues: tuple[CompilationIssue, ...] = ()

    @property
    def draft(self) -> MinimalIntentProposal:
        """Read-only edge alias while pipeline result naming migrates at P3-4."""

        return self.proposal


@dataclass(frozen=True)
class TaskSpecAuthority:
    """Validate, canonicalize and admit exactly one TaskSpec revision."""

    policy: CompilationPolicy = field(default_factory=CompilationPolicy)
    material_binding_policy: MaterialBindingPolicy = field(default_factory=MaterialBindingPolicy)

    def admit(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        proposal: MinimalIntentProposal,
        *,
        revision: int = 1,
        task_id: str | None = None,
        previous_admitted_task: AdmittedTaskSpec | None = None,
    ) -> TaskSpecAdmissionResult:
        lineage_issue = _revision_lineage_issue(
            request,
            proposal,
            revision=revision,
            task_id=task_id,
            previous_admitted_task=previous_admitted_task,
        )
        if lineage_issue is not None:
            return TaskSpecAdmissionResult(
                status=CompilationStatus.UNSUPPORTED,
                request_id=request.request_id,
                proposal=proposal,
                issues=(lineage_issue,),
            )
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
                "success_requirement_ref_not_admitted",
                "criterion_requirement_binding_missing",
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
            effect.model_copy(update={"effect_id": effect.effect_id or f"requirement:effect:{index}"})
            for index, effect in enumerate(proposal.requested_effects, start=1)
        )
        requirements = _canonical_requirements(proposal, effects, envelope)
        requirement_ids = {item.requirement_id for item in requirements}
        try:
            canonical_issues = _canonical_binding_issues(proposal, requirements, effects)
        except (ValidationError, ValueError) as exc:
            return _task_spec_validation_failure(request, proposal, exc)
        if canonical_issues:
            return TaskSpecAdmissionResult(
                status=CompilationStatus.NEEDS_CLARIFICATION,
                request_id=request.request_id,
                proposal=proposal,
                issues=canonical_issues,
            )
        inputs = tuple(InputBinding.from_material(item) for item in proposal.material_bindings)
        outputs = tuple(
            output.model_copy(
                update={
                    "requirement_ref": f"requirement:output:{index}",
                    "source_binding_requirement": (
                        output.source_binding_requirement
                        if output.source_binding_requirement != ("source:any",)
                        else tuple(
                            item.binding_id
                            for item in inputs
                            if not output.requirement_ref or item.requirement_ref == output.requirement_ref
                        )
                        or output.source_binding_requirement
                    ),
                }
            )
            for index, output in enumerate(proposal.required_outputs, start=1)
        )
        try:
            criterion_source_bindings = _criterion_source_bindings(proposal, requirements, outputs)
        except (ValidationError, ValueError) as exc:
            return _task_spec_validation_failure(request, proposal, exc)
        try:
            task_spec = TaskSpec(
                task_id=task_id or request.request_id,
                revision=revision,
                objective=proposal.objective.strip(),
                operation_class=operation,
                requirements=requirements,
                inputs=inputs,
                allowed_effect_refs=tuple(item.effect_id for item in effects),
                hard_constraint_refs=tuple(
                    item.requirement_id for item in requirements if item.payload.kind == "constraint"
                ),
                preference_refs=tuple(
                    item.requirement_id for item in requirements if item.payload.kind == "preference"
                ),
                forbidden_effect_refs=tuple(
                    item.requirement_id
                    for item in requirements
                    if item.payload.kind == "effect" and item.payload.subject in proposal.forbidden_effects
                ),
                capability_ceiling=_ordered_unique(item.capability for item in effects if item.capability),
                risk_policy=TaskRiskPolicy(
                    maximum_operation_class=operation,
                    approval_required=operation in {OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE},
                    authoritative_final_recheck_required=operation
                    in {OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE},
                ),
                success=proposal.success,
                required_outputs=outputs,
                criterion_source_bindings=criterion_source_bindings,
                constraint_criterion_ids=proposal.constraint_criterion_ids,
                external_effect_criterion_ids=proposal.external_effect_criterion_ids,
                final_recheck_criterion_ids=proposal.final_recheck_criterion_ids,
                source_request_ref=request.request_id,
                source_envelope_ref=envelope.identity,
                source_binding_digest=self.material_binding_policy.binding_digest(envelope, proposal.material_bindings),
            )
        except (ValidationError, ValueError) as exc:
            return _task_spec_validation_failure(request, proposal, exc)
        assert all(item.requirement_ref in requirement_ids for item in inputs)
        admitted_task = _issue_admitted_task(
            task_spec,
            envelope.identity,
            previous_task_identity=(
                previous_admitted_task.task_spec.identity if previous_admitted_task is not None else ""
            ),
        )
        return TaskSpecAdmissionResult(
            status=CompilationStatus.READY,
            request_id=request.request_id,
            proposal=proposal,
            task_spec=task_spec,
            admitted_task=admitted_task,
        )

    def _validate(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        proposal: MinimalIntentProposal,
    ) -> list[CompilationIssue]:
        if envelope.request_id != request.request_id:
            return [CompilationIssue(code="source_envelope_request_mismatch", field="request_id")]
        authority_source_ids = {item.source_id for item in envelope.sources if item.kind != SourceKind.TARGET}
        authorized = {item.anchor_id for item in envelope.anchors if item.source_id in authority_source_ids}
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
                issues.append(
                    CompilationIssue(
                        code="operation_denied", field="requested_effects", detail=effect.operation_class.value
                    )
                )
            if effect.capability in self.policy.denied_capabilities:
                issues.append(
                    CompilationIssue(code="capability_denied", field="requested_effects", detail=effect.capability)
                )
            if (
                effect.capability
                and self.policy.allowed_requested_capabilities is not None
                and effect.capability not in self.policy.allowed_requested_capabilities
            ):
                issues.append(
                    CompilationIssue(code="capability_not_allowed", field="requested_effects", detail=effect.capability)
                )
            if forbidden.intersection({_normalized(effect.target), _normalized(effect.description)}):
                issues.append(
                    CompilationIssue(code="forbidden_effect", field="requested_effects", detail=effect.target)
                )
        for index, entity in enumerate(proposal.entities):
            if entity.source_ref not in authorized:
                issues.append(
                    CompilationIssue(
                        code="unsourced_intent_entity", field=f"entities[{index}]", detail=entity.source_ref
                    )
                )
        for index, constraint in enumerate(proposal.semantic_value_constraints):
            if constraint.source_ref not in authorized:
                issues.append(
                    CompilationIssue(
                        code="unsourced_semantic_value_constraint",
                        field=f"semantic_value_constraints[{index}]",
                        detail=constraint.source_ref,
                    )
                )
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


def _task_spec_validation_failure(
    request: UserRequest,
    proposal: MinimalIntentProposal,
    error: Exception,
) -> TaskSpecAdmissionResult:
    return TaskSpecAdmissionResult(
        status=CompilationStatus.UNSUPPORTED,
        request_id=request.request_id,
        proposal=proposal,
        issues=(
            CompilationIssue(
                code="task_spec_validation_failed",
                field="task_spec",
                detail=str(error),
            ),
        ),
    )


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical_requirements(
    proposal: MinimalIntentProposal,
    effects: tuple[RequestedEffect, ...],
    envelope: SourceEnvelope,
) -> tuple[TaskRequirement, ...]:
    whole = envelope.whole_request_anchor.anchor_id
    bindings_by_effect = {
        effect.effect_id: tuple(
            ParameterAuthorization(item.field.value, item.value, item.binding_id)
            for item in proposal.material_bindings
            if item.effect_ref == effect.effect_id
        )
        for effect in effects
    }
    rows = [
        TaskRequirement(
            requirement_id=effect.effect_id,
            payload=TaskSemanticPayload(
                kind="effect",
                subject=effect.target,
                target_identity=effect.target,
                destination_identity=(
                    effect.interaction_relation.destination
                    if effect.interaction_relation is not None
                    and effect.interaction_relation.kind == TaskInteractionRelationKind.DRAG_TO
                    else ""
                ),
                relation="requested_effect",
                value=effect.description,
                operation_class=effect.operation_class,
                material_effect_kind=effect.material_effect_kind,
                capability=effect.capability,
                effect_authorization_scope=_effect_authorization_scope(
                    effect, bindings_by_effect[effect.effect_id]
                ),
            ),
            source_anchor_refs=(effect.source_ref,),
        )
        for effect in effects
    ]
    rows.extend(
        TaskRequirement(
            requirement_id=f"requirement:entity:{index}",
            payload=TaskSemanticPayload(
                kind="entity",
                subject=entity.name,
                relation="equals",
                value=entity.value,
            ),
            source_anchor_refs=(entity.source_ref,),
        )
        for index, entity in enumerate(proposal.entities, start=1)
    )
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
            requirement_id=f"requirement:value-constraint:{index}",
            payload=TaskSemanticPayload(
                kind="constraint",
                subject=constraint.target or "input_value",
                relation=constraint.relation.value,
                value=constraint.value,
            ),
            source_anchor_refs=(constraint.source_ref,),
        )
        for index, constraint in enumerate(proposal.semantic_value_constraints, start=1)
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
    rows.extend(
        TaskRequirement(
            requirement_id=f"requirement:output:{index}",
            payload=TaskSemanticPayload(
                kind="output",
                subject=output.output_id,
                relation="materialized_by",
                value=output.materialization_criterion_id,
            ),
            source_anchor_refs=(whole,),
        )
        for index, output in enumerate(proposal.required_outputs, start=1)
    )
    return tuple(rows)


def _effect_authorization_scope(
    effect: RequestedEffect,
    parameters: tuple[ParameterAuthorization, ...],
) -> EffectAuthorizationScope:
    effect_class = {
        OperationClass.READ_ONLY: EffectClass.READ,
        OperationClass.NAVIGATION: EffectClass.NAVIGATE,
        OperationClass.REVERSIBLE_WRITE: EffectClass.UPDATE,
        OperationClass.EXTERNAL_SIDE_EFFECT: EffectClass.INVOKE,
        OperationClass.IRREVERSIBLE: EffectClass.DELETE,
    }[effect.operation_class]
    operation_ref = effect.operation_ref or {
        OperationClass.READ_ONLY: "resource.read@v1",
        OperationClass.NAVIGATION: "navigation.navigate@v1",
        OperationClass.REVERSIBLE_WRITE: "field.set@v1" if parameters else "resource.update@v1",
        OperationClass.EXTERNAL_SIDE_EFFECT: "external.commit@v1",
        OperationClass.IRREVERSIBLE: "resource.delete@v1",
    }[effect.operation_class]
    operation_semantics = semantics_for_operation(operation_ref)
    if operation_semantics is not None:
        effect_class = operation_semantics.effect_class
    destination = (
        ResourceScopeRef(effect.interaction_relation.destination, (effect.source_ref,))
        if effect.interaction_relation is not None
        and effect.interaction_relation.kind == TaskInteractionRelationKind.DRAG_TO
        else None
    )
    externality = (
        Externality.EXTERNAL_SYSTEM
        if effect.operation_class == OperationClass.EXTERNAL_SIDE_EFFECT
        else Externality.LOCAL
    )
    reversibility = (
        Reversibility.IRREVERSIBLE
        if effect.operation_class == OperationClass.IRREVERSIBLE
        else Reversibility.REVERSIBLE
    )
    if operation_semantics is not None:
        externality = operation_semantics.externality
        reversibility = operation_semantics.reversibility
    high_risk_policy = policy_for_effect(effect_class, operation_ref)
    high_risk = high_risk_policy is not None or externality in {
        Externality.EXTERNAL_SYSTEM,
        Externality.PHYSICAL_WORLD,
    } or reversibility in {Reversibility.IRREVERSIBLE, Reversibility.UNKNOWN}
    return EffectAuthorizationScope(
        requirement_ref=effect.effect_id,
        operation_constraint=operation_ref,
        resource_scope=ResourceScopeRef(effect.target, (effect.source_ref,)),
        destination_scope=destination,
        parameters=parameters,
        effect_class=effect_class,
        externality=externality,
        reversibility=reversibility,
        risk_policy_ref=(high_risk_policy.policy_ref if high_risk_policy else "runtime-standard@v1"),
        minimum_source_assurance=(
            high_risk_policy.minimum_assurance
            if high_risk_policy is not None
            else AssuranceLevel.AUTHORITATIVE
            if high_risk
            else AssuranceLevel.STRUCTURAL
        ),
        required_capabilities=frozenset({effect.capability} if effect.capability else ()),
        approval_policy_ref="exact-contract@v1" if high_risk else "",
        completion_policy_ref=f"task-success:{effect.effect_id}",
    )


def _criterion_source_bindings(
    proposal: MinimalIntentProposal,
    requirements: tuple[TaskRequirement, ...],
    outputs: tuple[OutputSpec, ...],
) -> tuple[CriterionSourceBinding, ...]:
    constraint_refs = tuple(item.requirement_id for item in requirements if item.payload.kind == "constraint")
    success_bindings = success_criterion_requirement_bindings(proposal.success)
    rows: dict[str, list[str]] = {}

    def bind(criterion_id: str, refs: tuple[str, ...]) -> None:
        if not criterion_id or not refs or criterion_id in success_bindings:
            return
        bucket = rows.setdefault(criterion_id, [])
        bucket.extend(ref for ref in refs if ref not in bucket)

    for index, criterion_id in enumerate(proposal.constraint_criterion_ids):
        if index < len(constraint_refs):
            bind(criterion_id, (constraint_refs[index],))
    for criterion_id in (*proposal.external_effect_criterion_ids, *proposal.final_recheck_criterion_ids):
        bind(criterion_id, success_bindings.get(criterion_id, ()))
    for output in outputs:
        if output.materialization_criterion_id not in success_bindings:
            bind(output.materialization_criterion_id, (output.requirement_ref,))
    return tuple(
        CriterionSourceBinding(criterion_id=criterion_id, requirement_refs=tuple(refs))
        for criterion_id, refs in rows.items()
    )


def _canonical_binding_issues(
    proposal: MinimalIntentProposal,
    requirements: tuple[TaskRequirement, ...],
    effects: tuple[RequestedEffect, ...],
) -> tuple[CompilationIssue, ...]:
    known = {item.requirement_id for item in requirements}
    effect_refs = {item.effect_id for item in effects}
    success_bindings = success_criterion_requirement_bindings(proposal.success)
    success_policies = success_criterion_policies(proposal.success)
    issues: list[CompilationIssue] = []
    scopes = {
        item.requirement_id: item.payload.effect_authorization_scope
        for item in requirements
        if item.payload.kind == "effect" and item.payload.effect_authorization_scope is not None
    }
    for criterion_id, refs in success_bindings.items():
        for ref in set(refs) - known:
            issues.append(
                CompilationIssue(
                    code="success_requirement_ref_not_admitted",
                    field=criterion_id,
                    detail=ref,
                )
            )
    high_risk = False
    for effect in effects:
        scope = scopes.get(effect.effect_id)
        if scope is None:
            issues.append(
                CompilationIssue(
                    code="effect_authorization_scope_missing",
                    field=effect.effect_id,
                )
            )
            continue
        canonical_operation = _operation_class_for_scope(scope)
        if effect.operation_class != canonical_operation:
            issues.append(
                CompilationIssue(
                    code="operation_semantics_mismatch",
                    field=effect.effect_id,
                    detail=f"{effect.operation_class.value}!={canonical_operation.value}",
                )
            )
        policy = policy_for_effect(scope.effect_class, scope.operation_constraint)
        scope_high_risk = policy is not None or scope.externality in {
            Externality.EXTERNAL_SYSTEM,
            Externality.PHYSICAL_WORLD,
        } or scope.reversibility in {Reversibility.IRREVERSIBLE, Reversibility.UNKNOWN}
        high_risk = high_risk or scope_high_risk
        if not scope_high_risk:
            continue
        if scope.approval_policy_ref != "exact-contract@v1":
            issues.append(
                CompilationIssue(code="high_risk_approval_policy_required", field=effect.effect_id)
            )
        if policy is None:
            continue
        parameter_slots = {item.slot for item in scope.parameters}
        for field_name in sorted(policy.required_material_fields - parameter_slots):
            issues.append(
                CompilationIssue(
                    code="high_risk_material_field_required",
                    field=field_name,
                    detail=effect.effect_id,
                )
            )
        if policy.required_capability not in scope.required_capabilities:
            issues.append(
                CompilationIssue(
                    code="high_risk_capability_required",
                    field=effect.effect_id,
                    detail=policy.required_capability,
                )
            )
    if high_risk and not proposal.external_effect_criterion_ids:
        issues.append(CompilationIssue(code="high_risk_external_criterion_required", field="success"))
    if high_risk and not proposal.final_recheck_criterion_ids:
        issues.append(CompilationIssue(code="high_risk_final_recheck_required", field="success"))
    if set(proposal.external_effect_criterion_ids) & set(proposal.final_recheck_criterion_ids):
        issues.append(CompilationIssue(code="high_risk_criterion_roles_overlap", field="success"))
    for criterion_id in (*proposal.external_effect_criterion_ids, *proposal.final_recheck_criterion_ids):
        refs = success_bindings.get(criterion_id, ())
        if not refs or not set(refs).intersection(effect_refs):
            issues.append(
                CompilationIssue(
                    code="criterion_requirement_binding_missing",
                    field=criterion_id,
                )
            )
    for criterion_id in proposal.external_effect_criterion_ids:
        policy = success_policies.get(criterion_id)
        if policy is not None and (
            policy.satisfaction.value != "action_caused"
            or policy.validity.value != "recent_action"
            or not policy.causal_lineage_required
        ):
            issues.append(CompilationIssue(code="external_effect_policy_invalid", field=criterion_id))
    for criterion_id in proposal.final_recheck_criterion_ids:
        policy = success_policies.get(criterion_id)
        if policy is not None and (
            policy.validity.value != "final_recheck" or policy.minimum_assurance.value != "authoritative"
        ):
            issues.append(CompilationIssue(code="final_recheck_policy_invalid", field=criterion_id))
    if len(proposal.constraint_criterion_ids) > len(proposal.constraints):
        issues.append(
            CompilationIssue(
                code="criterion_requirement_binding_missing",
                field="constraint_criterion_ids",
            )
        )
    return tuple(issues)


def _operation_class_for_scope(scope: EffectAuthorizationScope) -> OperationClass:
    """Project the canonical effect scope to the legacy aggregate risk class."""

    if scope.effect_class == EffectClass.DELETE:
        return OperationClass.IRREVERSIBLE
    if scope.externality in {Externality.EXTERNAL_SYSTEM, Externality.PHYSICAL_WORLD} or (
        scope.reversibility == Reversibility.UNKNOWN
    ):
        return OperationClass.EXTERNAL_SIDE_EFFECT
    if scope.reversibility == Reversibility.IRREVERSIBLE:
        return OperationClass.IRREVERSIBLE
    if scope.effect_class == EffectClass.READ:
        return OperationClass.READ_ONLY
    if scope.effect_class in {EffectClass.NAVIGATE, EffectClass.INTERACTION_ONLY}:
        return OperationClass.NAVIGATION
    return OperationClass.REVERSIBLE_WRITE


def _issue_admitted_task(
    task_spec: TaskSpec,
    source_envelope_identity: str,
    *,
    previous_task_identity: str = "",
) -> AdmittedTaskSpec:
    return AdmittedTaskSpec(
        task_spec,
        f"task-admission:v2:{uuid4().hex}",
        source_envelope_identity,
        previous_task_identity,
        _capability=_ADMISSION_CAPABILITY,
    )


def _admit_legacy_task_spec(task_spec: TaskSpec) -> AdmittedTaskSpec:
    """P5-3 compatibility adapter for preconstructed fixtures and legacy profiles.

    Canonical production intake must use ``TaskSpecAuthority.admit``. Keeping the
    bypass named and centralized prevents raw TaskSpec construction from becoming
    an implicit Runtime admission path while the remaining compatibility profiles
    are retired.
    """

    return _issue_admitted_task(task_spec, task_spec.source_envelope_ref)


def _revision_lineage_issue(
    request: UserRequest,
    proposal: MinimalIntentProposal,
    *,
    revision: int,
    task_id: str | None,
    previous_admitted_task: AdmittedTaskSpec | None,
) -> CompilationIssue | None:
    del proposal
    if revision < 1:
        return CompilationIssue(code="invalid_task_revision", field="revision")
    if revision == 1:
        return (
            CompilationIssue(code="unexpected_revision_lineage", field="revision")
            if previous_admitted_task is not None
            else None
        )
    if previous_admitted_task is None:
        return CompilationIssue(code="revision_lineage_missing", field="revision")
    previous = previous_admitted_task.task_spec
    if previous.task_id != (task_id or request.request_id):
        return CompilationIssue(code="revision_task_id_mismatch", field="task_id")
    if revision != previous.revision + 1:
        return CompilationIssue(code="revision_not_monotonic", field="revision")
    return None
