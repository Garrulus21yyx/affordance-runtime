"""Deterministic reference planners used for diagnosis and benchmarks."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.parse import urlsplit

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, RiskLevel, VerifierSpec
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.fixtures import EXPORT_SHA256
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.planning_request import PlanningRequest, thaw_request_mapping
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import (
    SubgoalSpec,
    TaskPlan,
    TaskPlanningContext,
    TaskPlanSource,
)

_ARTICLE_PATTERN = re.compile(r"<article\s+([^>]*data-plan=[^>]*)>", re.IGNORECASE)
_ATTRIBUTE_PATTERN = re.compile(r'([\w-]+)=["\']([^"\']*)["\']')


class ReferencePlanningRequestBuilderPort(Protocol):
    def build(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlanningRequest: ...


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


@dataclass
class PricingPlanner:
    """Reveal both pricing cards, then return structured limits with evidence."""

    planning_request_builder: ReferencePlanningRequestBuilderPort | None = None

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        request = _reference_planning_request(
            self.planning_request_builder,
            envelope,
            state,
            snapshot,
        )
        html = str(snapshot.observation.metadata.get("html") or "")
        plans = extract_pricing(html)
        for plan_name in ("pro", "enterprise"):
            if plan_name in plans and not plans[plan_name]["visible"]:
                label = f"Show {plan_name.title()} limits"
                affordance = _affordance_by_label(request, snapshot, label)
                if affordance is None:
                    return PlannerDecision(done=False, reason=f"missing affordance: {label}")
                contract = ActionContract.from_affordance(
                    affordance,
                    intent=f"reveal {plan_name} limits",
                    backend="dom",
                    verifier_plan=[
                        VerifierSpec(
                            kind="dom_contains",
                            target="html",
                            expected=f'data-plan="{plan_name}" data-visible="true"',
                            criterion_ids=_active_step_criterion_ids(request, state),
                            requirement_ids=_active_step_requirement_ids(request, state),
                        )
                    ],
                )
                return PlannerDecision(contract=contract, reason=f"reveal hidden {plan_name} evidence")
        if plans and all(plan.get("visible") for plan in plans.values()):
            result = {
                name: {key: value for key, value in plan.items() if key != "visible"} for name, plan in plans.items()
            }
            return PlannerDecision(
                done=True,
                result={"plans": result, "source_url": snapshot.observation.url},
                reason="all pricing limits are structurally visible",
            )
        return PlannerDecision(done=False, reason="pricing data is not available")


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


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass
class SettingsPlanner:
    planning_request_builder: ReferencePlanningRequestBuilderPort | None = None

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        request = _reference_planning_request(
            self.planning_request_builder,
            envelope,
            state,
            snapshot,
        )
        latest_outcome = thaw_request_mapping(request.latest_outcome) if request is not None else {}
        verification_passed = (
            latest_outcome.get("verification_status") == "passed"
            if request is not None
            else bool(state.latest_verification and state.latest_verification.passed)
        )
        last_selector = state.receipts[-1].evidence.get("selector") if state.receipts else None
        if verification_passed and last_selector != "#dismiss-modal":
            return PlannerDecision(
                done=True,
                result={"notifications": "enabled", "verified_by": "fixture_api"},
                reason="persisted settings oracle passed",
            )
        modal_affordance = next(
            (
                item
                for item in snapshot.affordance_model.affordances
                if item.locator.get("selector") == "#dismiss-modal"
            ),
            None,
        )
        if modal_affordance is not None:
            return PlannerDecision(
                contract=ActionContract.from_affordance(
                    modal_affordance,
                    intent="dismiss registered low-risk blocking modal",
                    backend="dom",
                    verifier_plan=[VerifierSpec("dom_absent", "html", 'id="blocking-modal"')],
                ),
                reason="registered blocking modal policy",
            )
        affordance = _affordance_by_label(request, snapshot, "Enable notifications")
        if affordance is None:
            return PlannerDecision(reason="settings control is unavailable")
        contract = ActionContract.from_affordance(
            affordance,
            intent="enable reversible notifications setting",
            backend="dom",
            required_capabilities=["settings.write.reversible"],
            verifier_plan=[
                VerifierSpec(
                    "http_json",
                    f"{_origin(snapshot.observation.url)}/api/state",
                    {"path": "settings.notifications", "value": "enabled"},
                )
            ],
        )
        return PlannerDecision(
            contract=replace(
                contract,
                risk=RiskLevel.MEDIUM,
                idempotency_key=f"{snapshot.observation.url}:notifications:enabled",
                compensation="restore notifications=disabled",
                contract_hash="",
            ),
            reason="apply reversible setting",
        )


@dataclass
class ExportPlanner:
    planning_request_builder: ReferencePlanningRequestBuilderPort | None = None

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        request = _reference_planning_request(
            self.planning_request_builder,
            envelope,
            state,
            snapshot,
        )
        latest_outcome = thaw_request_mapping(request.latest_outcome) if request is not None else {}
        verification_passed = (
            latest_outcome.get("verification_status") == "passed"
            if request is not None
            else bool(state.latest_verification and state.latest_verification.passed)
        )
        if verification_passed and state.receipts:
            receipt = state.receipts[-1]
            return PlannerDecision(
                done=True,
                result={
                    "download": receipt.evidence.get("path"),
                    "sha256": receipt.evidence.get("sha256"),
                    "verified_by": "file_hash",
                },
                reason="approved download receipt matches fixture hash",
            )
        affordance = _affordance_by_label(request, snapshot, "Export report")
        if affordance is None:
            return PlannerDecision(reason="export control is unavailable")
        contract = ActionContract.from_affordance(
            affordance,
            intent="export the report after explicit approval",
            backend="dom",
            required_capabilities=["report.export"],
            verifier_plan=[VerifierSpec("evidence", "sha256", EXPORT_SHA256)],
        )
        return PlannerDecision(
            contract=replace(
                contract,
                action="download",
                risk=RiskLevel.HIGH,
                idempotency_key=f"{snapshot.observation.url}:report-export",
                contract_hash="",
            ),
            reason="download requires a bound approval token",
        )


def _reference_planning_request(
    builder: ReferencePlanningRequestBuilderPort | None,
    envelope: TaskEnvelope,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlanningRequest | None:
    """Project standard reference-planner inputs when a validated TaskSpec exists."""

    if envelope.task_spec is None:
        return None
    return (builder or PlanningRequestBuilder()).build(envelope, state, snapshot)


def _affordance_by_label(
    request: PlanningRequest | None,
    snapshot: BrowserSnapshot,
    label: str,
) -> Any | None:
    if request is not None:
        target_ids = tuple(
            item.target_id
            for item in request.observation.affordances
            if item.label == label
        )
        if target_ids:
            matched = next(
                (
                    item
                    for item in snapshot.affordance_model.affordances
                    if item.id == target_ids[0]
                ),
                None,
            )
            if matched is not None:
                return matched
    return next(
        (item for item in snapshot.affordance_model.affordances if item.label == label),
        None,
    )


def _active_step_id(request: PlanningRequest | None, state: StateKernel) -> str:
    if request is not None and request.step.progress is not None:
        return request.step.progress.active_step_id or ""
    if state.plan_progress is None:
        return ""
    return state.plan_progress.active_subgoal_id


def _active_step_criterion_ids(
    request: PlanningRequest | None,
    state: StateKernel,
) -> tuple[str, ...]:
    active_step_id = _active_step_id(request, state)
    if not active_step_id:
        return ()
    return (criterion_id("subgoal", active_step_id, 0),)


def _active_step_requirement_ids(
    request: PlanningRequest | None,
    state: StateKernel,
) -> tuple[str, ...]:
    active_step_id = _active_step_id(request, state)
    if not active_step_id:
        return ()
    return (evidence_requirement_id("subgoal", active_step_id, 0),)
