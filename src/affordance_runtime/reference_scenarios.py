"""Typed reference-scenario profiles shared by the CLI and local benchmark."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

from affordance_runtime.effect_authority_contracts import EffectAuthorizationScope, EffectClass
from affordance_runtime.material_contracts import MaterialEffectKind
from affordance_runtime.planners import (
    PricingTaskPlanner,
    export_contract_builder,
    export_output_requirement,
    export_required_outputs,
    pricing_contract_builder,
    pricing_output_requirement,
    pricing_required_outputs,
    pricing_success_expression,
    settings_contract_builder,
)
from affordance_runtime.task_intake import (
    OperationClass,
    RequestedEffect,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.task_planner import PlanningRouter, TaskPlannerPort
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceValidityMode,
    SatisfactionMode,
    SuccessExpression,
)

ReferenceScenario = Literal["pricing", "settings", "export"]

_SCENARIO_OBJECTIVES: dict[ReferenceScenario, str] = {
    "pricing": "Extract Pro and Enterprise plan limits with structural evidence.",
    "settings": "Enable the reversible notifications setting and verify persisted state.",
    "export": "Export a report only after explicit approval and return the file receipt.",
}
_SCENARIO_OPERATIONS: dict[ReferenceScenario, OperationClass] = {
    # Revealing collapsed details is a navigation/interaction effect even
    # though the task's business result is read-only.
    "pricing": OperationClass.NAVIGATION,
    "settings": OperationClass.REVERSIBLE_WRITE,
    "export": OperationClass.EXTERNAL_SIDE_EFFECT,
}
_SCENARIO_SUBJECTS: dict[ReferenceScenario, tuple[str, ...]] = {
    "pricing": ("Show Pro limits", "Show Enterprise limits"),
    "settings": ("Enable notifications",),
    "export": ("Export report",),
}
_SCENARIO_RESOURCES: dict[ReferenceScenario, tuple[str, ...]] = {
    "pricing": (
        "semantic:show-pro-limits:d560036f53a2",
        "semantic:show-enterprise-limits:7ac4b4b12278",
    ),
    "settings": ("semantic:enable-notifications:3f140815c7e9",),
    "export": ("semantic:export-report:604f91a3efb3",),
}
_SCENARIO_OPERATION_REFS: dict[ReferenceScenario, str] = {
    "pricing": "interaction.reveal@v1",
    "settings": "resource.update@v1",
    "export": "external.commit@v1",
}
_SCENARIO_EFFECT_CLASSES: dict[ReferenceScenario, EffectClass] = {
    "pricing": EffectClass.INTERACTION_ONLY,
    "settings": EffectClass.UPDATE,
    "export": EffectClass.INVOKE,
}
_SCENARIO_CAPABILITIES: dict[ReferenceScenario, str] = {
    "pricing": "",
    "settings": "settings.write.reversible",
    "export": "report.export",
}


def reference_requested_effects(
    scenario: ReferenceScenario,
    source_ref: str,
) -> tuple[RequestedEffect, ...]:
    """Return source-bound intake effects aligned with the executable profile."""

    return tuple(
        RequestedEffect(
            effect_id=f"requirement:effect:{index}",
            operation_class=_SCENARIO_OPERATIONS[scenario],
            material_effect_kind=(
                MaterialEffectKind.EXTERNAL_ACTION
                if scenario == "export"
                else MaterialEffectKind.NONE
            ),
            target=subject,
            resource_ref=resource_ref,
            capability=_SCENARIO_CAPABILITIES[scenario],
            source_ref=source_ref,
            operation_ref=_SCENARIO_OPERATION_REFS[scenario],
        )
        for index, (subject, resource_ref) in enumerate(
            zip(_SCENARIO_SUBJECTS[scenario], _SCENARIO_RESOURCES[scenario], strict=True),
            start=1,
        )
    )


def reference_task_spec(
    scenario: ReferenceScenario,
    task_id: str,
    *,
    capabilities: tuple[str, ...] = (),
    source_anchor_ref: str = "reference-scenario",
) -> TaskSpec:
    """Return the exact, source-owned authority used by a reference fixture run."""

    subjects = _SCENARIO_SUBJECTS[scenario]
    requirements = canonical_effect_requirements(
        subjects,
        _SCENARIO_OPERATIONS[scenario],
        source_anchor_ref,
        capabilities,
        resource_refs=_SCENARIO_RESOURCES[scenario],
        operation_ref_override=_SCENARIO_OPERATION_REFS[scenario],
        effect_class_override=_SCENARIO_EFFECT_CLASSES[scenario],
    )
    if scenario == "export":
        # DOM evidence remains structural even in the trusted local fixture.
        # Approval plus the authoritative API final recheck carry the stronger
        # claims; page-authored metadata must not mint authoritative assurance.
        requirements = tuple(
            requirement.model_copy(
                update={
                    "payload": requirement.payload.model_copy(
                        update={
                            "effect_authorization_scope": replace(
                                cast(
                                    EffectAuthorizationScope,
                                    requirement.payload.effect_authorization_scope,
                                ),
                                minimum_source_assurance=AssuranceLevel.STRUCTURAL,
                            )
                        }
                    )
                }
            )
            for requirement in requirements
        )
    effect_refs = canonical_effect_requirement_refs(subjects)
    if scenario == "pricing":
        all_requirements = (*requirements, pricing_output_requirement(source_anchor_ref))
        success = pricing_success_expression()
        required_outputs = pricing_required_outputs()
    elif scenario == "export":
        all_requirements = (*requirements, export_output_requirement(source_anchor_ref))
        success = reference_success_expression(effect_refs[0], scenario)
        required_outputs = export_required_outputs()
    else:
        all_requirements = requirements
        success = reference_success_expression(effect_refs[0], scenario)
        required_outputs = ()
    return TaskSpec(
        task_id=task_id,
        revision=1,
        objective=_SCENARIO_OBJECTIVES[scenario],
        operation_class=_SCENARIO_OPERATIONS[scenario],
        requirements=all_requirements,
        allowed_effect_refs=effect_refs,
        success=success,
        required_outputs=required_outputs,
        external_effect_criterion_ids=(("criterion:export-effect",) if scenario == "export" else ()),
        final_recheck_criterion_ids=(("criterion:export-final",) if scenario == "export" else ()),
        capability_ceiling=capabilities,
        source_request_ref=source_anchor_ref,
    )


def reference_contract_builder(
    scenario: ReferenceScenario,
    *,
    base_url: str,
) -> ActionTransactionMaterializer:
    """Return the reference verifier/route requirements for one fixture scenario."""

    if scenario == "pricing":
        return pricing_contract_builder()
    api_state_url = f"{base_url.rstrip('/')}/api/state"
    if scenario == "settings":
        return settings_contract_builder(api_state_url)
    return export_contract_builder(api_state_url)


def reference_task_planner(scenario: ReferenceScenario) -> TaskPlannerPort:
    """Return the semantic task planner used by a reference scenario."""

    return PricingTaskPlanner() if scenario == "pricing" else PlanningRouter()


def reference_success_expression(
    requirement_id: str,
    scenario: ReferenceScenario,
) -> SuccessExpression:
    """Return the typed success expression for a non-pricing reference task."""

    if scenario == "export":
        return SuccessExpression(
            expression_id="success:export",
            operator="all_of",
            children=(
                SuccessExpression(
                    expression_id="success:export-effect",
                    operator="criterion",
                    criterion_id="criterion:export-effect",
                    requirement_refs=(requirement_id,),
                    policy=CriterionPolicy(
                        satisfaction=SatisfactionMode.ACTION_CAUSED,
                        validity=EvidenceValidityMode.RECENT_ACTION,
                        causal_lineage_required=True,
                    ),
                ),
                SuccessExpression(
                    expression_id="success:export-final",
                    operator="criterion",
                    criterion_id="criterion:export-final",
                    requirement_refs=(requirement_id,),
                    policy=CriterionPolicy(
                        validity=EvidenceValidityMode.FINAL_RECHECK,
                        minimum_assurance=AssuranceLevel.AUTHORITATIVE,
                    ),
                ),
            ),
        )
    return SuccessExpression(
        expression_id=f"success:{scenario}",
        operator="criterion",
        criterion_id=f"criterion:{scenario}",
        requirement_refs=(requirement_id,),
    )
