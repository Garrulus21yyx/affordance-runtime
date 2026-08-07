"""Deterministic reference planners used for diagnosis and benchmarks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from affordance_runtime.choice_contracts import ChoicePlanningRequest, SelectChoice
from affordance_runtime.contracts import (
    ProgressEvidenceScope,
    RiskLevel,
    VerifierSpec,
)
from affordance_runtime.fixtures import EXPORT_SHA256, PRICING_DATA
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerDoneResponse,
    PlannerProposalResponse,
    PlannerUnsupportedResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.task_intake import TaskRequirement, TaskSemanticPayload
from affordance_runtime.task_planner import TaskPlanningNoPlan, TaskPlanningRequest
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer
from affordance_runtime.verification.contracts import (
    CriterionPolicy,
    EvidenceValidityMode,
    OutputSpec,
    SatisfactionMode,
    SuccessExpression,
)

_ARTICLE_PATTERN = re.compile(r"<article\s+([^>]*data-plan=[^>]*)>", re.IGNORECASE)
_ATTRIBUTE_PATTERN = re.compile(r'([\w-]+)=["\']([^"\']*)["\']')


def pricing_success_expression() -> SuccessExpression:
    return SuccessExpression(
        expression_id="success:pricing-visible",
        operator="all_of",
        children=(
            SuccessExpression(
                expression_id="success:pricing-pro-visible",
                operator="criterion",
                criterion_id="criterion:pricing-pro-visible",
                requirement_refs=("requirement:effect:1",),
                policy=CriterionPolicy(
                    satisfaction=SatisfactionMode.ACTION_CAUSED,
                    validity=EvidenceValidityMode.RECENT_ACTION,
                    causal_lineage_required=True,
                ),
            ),
            SuccessExpression(
                expression_id="success:pricing-enterprise-visible",
                operator="criterion",
                criterion_id="criterion:pricing-enterprise-visible",
                requirement_refs=("requirement:effect:2", "requirement:output:1"),
                policy=CriterionPolicy(
                    satisfaction=SatisfactionMode.ACTION_CAUSED,
                    validity=EvidenceValidityMode.RECENT_ACTION,
                    causal_lineage_required=True,
                ),
            ),
        ),
    )


def pricing_required_outputs() -> tuple[OutputSpec, ...]:
    return (
        OutputSpec(
            output_id="plans",
            requirement_ref="requirement:output:1",
            materialization_criterion_id="criterion:pricing-output",
            schema_id="json:object@v1",
        ),
    )


def export_required_outputs() -> tuple[OutputSpec, ...]:
    """The flagship export returns the exact downloaded artifact."""

    return (
        OutputSpec(
            output_id="report",
            requirement_ref="requirement:output:1",
            materialization_criterion_id="criterion:export-final",
            schema_id="artifact:file@v1",
        ),
    )


def export_output_requirement(source_anchor_ref: str) -> TaskRequirement:
    return TaskRequirement(
        requirement_id="requirement:output:1",
        payload=TaskSemanticPayload(
            kind="output",
            subject="report",
            relation="materialized_by",
            value="criterion:export-final",
        ),
        source_anchor_refs=(source_anchor_ref,),
    )


def pricing_output_requirement(source_anchor_ref: str) -> TaskRequirement:
    return TaskRequirement(
        requirement_id="requirement:output:1",
        payload=TaskSemanticPayload(
            kind="output",
            subject="plans",
            relation="materialized_by",
            value="criterion:pricing-enterprise-visible",
        ),
        source_anchor_refs=(source_anchor_ref,),
    )


def extract_pricing(html: str) -> dict[str, dict[str, Any]]:
    plans: dict[str, dict[str, Any]] = {}
    for match in _ARTICLE_PATTERN.finditer(html):
        attributes = dict(_ATTRIBUTE_PATTERN.findall(match.group(1)))
        name = attributes.get("data-plan")
        if not name:
            continue
        plans[name] = {
            "users": _number_or_text(attributes.get("data-users", "")),
            "projects": _number_or_text(attributes.get("data-projects", "")),
            "support": attributes.get("data-support", ""),
            "visible": attributes.get("data-visible") == "true",
        }
    return plans


def _number_or_text(value: str) -> int | str:
    return int(value) if value.isdigit() else value


@dataclass(frozen=True)
class PricingPlanner:
    """Reveal both pricing cards, then return structured limits with evidence."""

    def select(self, request: ChoicePlanningRequest) -> SelectChoice:
        expected = "enterprise" if "enterprise" in request.active_step_id.casefold() else "pro"
        choice = next(item for item in request.page.choices if expected in item.target_label.casefold())
        return SelectChoice(choice.choice_id, "match accepted pricing step")

    def propose(
        self, request: PlanningRequest
    ) -> PlannerProposalResponse | PlannerDoneResponse | PlannerUnsupportedResponse:
        satisfied = dict(request.satisfied_action_targets).get("activate", ())
        pro = _request_affordance_by_label(request, "Show Pro limits")
        enterprise = _request_affordance_by_label(request, "Show Enterprise limits")
        if (
            pro is not None
            and enterprise is not None
            and pro.target_id in satisfied
            and enterprise.target_id in satisfied
        ):
            return PlannerDoneResponse(
                result={"plans": PRICING_DATA},
                reason="both pricing disclosures were independently verified",
            )
        target = pro if pro is not None and pro.target_id not in satisfied else enterprise
        if target is None:
            return PlannerUnsupportedResponse("pricing_affordance_missing", "pricing disclosure control")
        plan_name = "pro" if target is pro else "enterprise"
        return _proposal_response(
            request,
            proposal_id=f"reveal-{plan_name}",
            target_id=target.target_id,
            subgoal=f"reveal {plan_name} limits",
            producer_id="pricing-reference-planner",
        )


@dataclass(frozen=True)
class PricingTaskPlanner:
    """Reference-app multi-stage plan; no selectors or backend authority."""

    def propose(self, request: TaskPlanningRequest):  # noqa: ANN201
        from affordance_runtime.task_plan_generators import PricingPlanProposalGenerator

        if {"reveal-pro", "reveal-enterprise"}.issubset(request.completed_step_ids):
            return TaskPlanningNoPlan(reason="pricing milestones complete; deterministic output projection remains")
        return PricingPlanProposalGenerator().generate(request)


@dataclass(frozen=True)
class SettingsPlanner:
    def propose(
        self, request: PlanningRequest
    ) -> PlannerProposalResponse | PlannerDoneResponse | PlannerUnsupportedResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"notifications": "enabled", "verified_by": "fixture_api"})
        modal = _request_affordance_by_label(request, "Dismiss")
        if modal is not None:
            return _proposal_response(
                request,
                proposal_id="dismiss-modal",
                target_id=modal.target_id,
                subgoal="dismiss registered low-risk blocking modal",
                producer_id="settings-reference-planner",
            )
        target = _request_affordance_by_label(request, "Enable notifications")
        if target is None:
            return PlannerUnsupportedResponse("settings_affordance_missing", "settings control is unavailable")
        return _proposal_response(
            request,
            proposal_id="enable-notifications",
            target_id=target.target_id,
            subgoal="enable reversible notifications setting",
            producer_id="settings-reference-planner",
        )


@dataclass(frozen=True)
class ExportPlanner:
    def propose(
        self, request: PlanningRequest
    ) -> PlannerProposalResponse | PlannerDoneResponse | PlannerUnsupportedResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"sha256": EXPORT_SHA256, "verified_by": "file_hash"})
        target = _request_affordance_by_label(request, "Export report")
        if target is None:
            return PlannerUnsupportedResponse("export_affordance_missing", "export control is unavailable")
        return _proposal_response(
            request,
            proposal_id="export-report",
            target_id=target.target_id,
            subgoal="export the report after explicit approval",
            producer_id="export-reference-planner",
        )


def pricing_contract_builder() -> ActionTransactionMaterializer:
    pro_requirements = ContractRequirements(
        verifier_plan=(
            VerifierSpec(
                "dom_contains",
                "html",
                'data-plan="pro" data-visible="true"',
                criterion_ids=("criterion:pricing-pro-visible",),
                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
            ),
        )
    )
    enterprise_requirements = ContractRequirements(
        verifier_plan=(
            VerifierSpec(
                "dom_contains",
                "html",
                'data-plan="enterprise" data-visible="true"',
                criterion_ids=("criterion:pricing-enterprise-visible",),
                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
            ),
            VerifierSpec(
                "dom_data_records",
                "html",
                {
                    "identity_attribute": "data-plan",
                    "record_ids": ("pro", "enterprise"),
                    "fields": {
                        "users": "data-users",
                        "projects": "data-projects",
                        "support": "data-support",
                    },
                    "required_attributes": {"data-visible": "true"},
                    "integer_fields": ("users", "projects"),
                },
                criterion_ids=("criterion:pricing-output",),
                requirement_ids=("requirement:output:1",),
                evidence_key="pricing-plan-limits",
            ),
        )
    )
    return ActionTransactionMaterializer(
        requirements={
            "semantic:show-pro-limits:d560036f53a2": pro_requirements,
            "semantic:show-enterprise-limits:7ac4b4b12278": enterprise_requirements,
            # Compatibility for old proposal-bound fixture callers. Runtime
            # binding uses the semantic keys above, which remain stable when a
            # held-out fixture inserts or reorders unrelated DOM controls.
            "dom_button_1": pro_requirements,
            "dom_button_2": enterprise_requirements,
        }
    )


def settings_contract_builder(api_url: str) -> ActionTransactionMaterializer:
    dismiss_requirements = ContractRequirements(
        verifier_plan=(VerifierSpec("dom_absent", "html", 'id="blocking-modal"'),)
    )
    setting_requirements = ContractRequirements(
        verifier_plan=(
            VerifierSpec(
                "http_json",
                api_url,
                {"path": "settings.notifications", "value": "enabled"},
                criterion_ids=("criterion:settings",),
                requirement_ids=("requirement:effect:1",),
                progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
            ),
        ),
        required_capabilities=("settings.write.reversible",),
        risk=RiskLevel.MEDIUM,
        idempotency_key="notifications:enabled",
        compensation="restore notifications=disabled",
    )
    return ActionTransactionMaterializer(
        requirements={
            "semantic:dismiss:4c17285e9237": dismiss_requirements,
            "semantic:enable-notifications:3f140815c7e9": setting_requirements,
            # Compatibility for old proposal-bound fixture callers.
            "dom_button_1": dismiss_requirements,
            "dom_button_2": setting_requirements,
        }
    )


def export_contract_builder(api_url: str) -> ActionTransactionMaterializer:
    return ActionTransactionMaterializer(
        requirements={
            "*": ContractRequirements(
                verifier_plan=(
                    VerifierSpec("evidence", "sha256", EXPORT_SHA256),
                    VerifierSpec(
                        "api_final_recheck",
                        api_url,
                        {
                            "path": "audit_log",
                            "contains": {"effect": "report.export", "sha256": EXPORT_SHA256},
                        },
                        criterion_ids=("criterion:export-effect", "criterion:export-final"),
                        requirement_ids=("requirement:effect:1",),
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                ),
                required_capabilities=("report.export",),
                risk=RiskLevel.HIGH,
                idempotency_key="report-export",
            )
        }
    )


def _request_affordance_by_label(request: PlanningRequest, label: str) -> Any | None:
    return next(
        (item for item in request.observation.affordances if item.label == label),
        None,
    )


def _proposal_response(
    request: PlanningRequest,
    *,
    proposal_id: str,
    target_id: str,
    subgoal: str,
    producer_id: str,
) -> PlannerProposalResponse:
    return PlannerProposalResponse(
        proposal=PlannerProposal(
            proposal_id=proposal_id,
            based_on_task_revision=request.identity.task_revision,
            based_on_state_version=request.identity.evaluated_at_state_version,
            snapshot_id=request.identity.snapshot_id,
            subgoal=subgoal,
            action_kind=PlannerActionKind.ACTIVATE,
            target_affordance_id=target_id,
        ),
        proposal_provenance=PlannerProposalProvenance(
            source=PlannerProposalSource.DETERMINISTIC_RULE,
            producer_id=producer_id,
        ),
    )
