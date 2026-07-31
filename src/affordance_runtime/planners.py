"""Deterministic reference planners used for diagnosis and benchmarks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from affordance_runtime.contracts import (
    ProgressEvidenceScope,
    RiskLevel,
    VerifierSpec,
)
from affordance_runtime.fixtures import EXPORT_SHA256, PRICING_DATA
from affordance_runtime.planning import (
    ContractBuilder,
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
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import (
    SubgoalSpec,
    TaskPlan,
    TaskPlanningContext,
    TaskPlanSource,
)

_ARTICLE_PATTERN = re.compile(r"<article\s+([^>]*data-plan=[^>]*)>", re.IGNORECASE)
_ATTRIBUTE_PATTERN = re.compile(r'([\w-]+)=["\']([^"\']*)["\']')


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
            return PlannerUnsupportedResponse(
                "pricing_affordance_missing", "pricing disclosure control"
            )
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

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        return TaskPlan(
            plan_id=f"pricing-plan-v{context.current_plan_version + 1}",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="reveal-pro",
                    objective="Reveal the Pro plan limits",
                    success_criteria=("Pro limits are structurally visible",),
                    evidence_requirements=("post-action DOM shows visible Pro limits",),
                    operation_class=OperationClass.READ_ONLY,
                ),
                SubgoalSpec(
                    subgoal_id="reveal-enterprise",
                    objective="Reveal the Enterprise plan limits",
                    depends_on=("reveal-pro",),
                    success_criteria=("Enterprise limits are structurally visible",),
                    evidence_requirements=("post-action DOM shows visible Enterprise limits",),
                    operation_class=OperationClass.READ_ONLY,
                ),
            ),
            assumptions=("pricing cards can be revealed independently",),
        )


@dataclass(frozen=True)
class SettingsPlanner:
    def propose(
        self, request: PlanningRequest
    ) -> PlannerProposalResponse | PlannerDoneResponse | PlannerUnsupportedResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(
                result={"notifications": "enabled", "verified_by": "fixture_api"}
            )
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
            return PlannerUnsupportedResponse(
                "settings_affordance_missing", "settings control is unavailable"
            )
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
            return PlannerDoneResponse(
                result={"sha256": EXPORT_SHA256, "verified_by": "file_hash"}
            )
        target = _request_affordance_by_label(request, "Export report")
        if target is None:
            return PlannerUnsupportedResponse(
                "export_affordance_missing", "export control is unavailable"
            )
        return _proposal_response(
            request,
            proposal_id="export-report",
            target_id=target.target_id,
            subgoal="export the report after explicit approval",
            producer_id="export-reference-planner",
        )


def pricing_contract_builder() -> ContractBuilder:
    return ContractBuilder(
        requirements={
            "dom_button_1": ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "dom_contains",
                        "html",
                        'data-plan="pro" data-visible="true"',
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                )
            ),
            "dom_button_2": ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "dom_contains",
                        "html",
                        'data-plan="enterprise" data-visible="true"',
                        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                    ),
                )
            ),
        }
    )


def settings_contract_builder(api_url: str) -> ContractBuilder:
    return ContractBuilder(
        requirements={
            "dom_button_1": ContractRequirements(
                verifier_plan=(VerifierSpec("dom_absent", "html", 'id="blocking-modal"'),)
            ),
            "dom_button_2": ContractRequirements(
                verifier_plan=(
                    VerifierSpec(
                        "http_json",
                        api_url,
                        {"path": "settings.notifications", "value": "enabled"},
                    ),
                ),
                required_capabilities=("settings.write.reversible",),
                risk=RiskLevel.MEDIUM,
                idempotency_key="notifications:enabled",
                compensation="restore notifications=disabled",
            ),
        }
    )


def export_contract_builder() -> ContractBuilder:
    return ContractBuilder(
        requirements={
            "dom_button_1": ContractRequirements(
                verifier_plan=(VerifierSpec("evidence", "sha256", EXPORT_SHA256),),
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
