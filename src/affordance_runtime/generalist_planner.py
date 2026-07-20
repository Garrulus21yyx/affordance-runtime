"""Environment-general LM planner over semantic affordance summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.coordinator import PlannerDecision
from affordance_runtime.model_port import ModelConfig, ModelMessage, ModelPort
from affordance_runtime.planning import PlannerProposal
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel

GENERALIST_PLANNER_PROMPT_VERSION = "generalist-planner-v5"

_SYSTEM_PROMPT = """You are an environment-general GUI planner. Return exactly one semantic PlannerProposal under the strict schema.
You may choose only an affordance id from the supplied inventory. Never output a selector, bid, coordinate, backend, capability, approval, credential, cookie, or executable code.
Use action_kind activate, type_text, select_option, navigate, scroll, wait, ask_user, or finish. Put only semantic values such as text or option in parameters.
For activate, parameters must be {}; type_text permits only {"text": ...}; select_option permits only {"option": ...}. For finish and ask_user, target_affordance_id must be "" and parameters must be {}. Put any summary, evidence, or user-visible completion data in result, never parameters.
For select_option, the target must be an affordance whose action is "select" or "select_option". Do not target an option, button, or clickable item merely because its label matches the desired option; use activate for those affordances instead.
Copy based_on_task_revision, based_on_state_version, and snapshot_id exactly. Requested capabilities are context, not granted authority; only granted_capabilities describe current authority. approval_handling is a runtime rule, not approval evidence or a token.
Finish only when supplied verification/evidence proves the TaskSpec success criteria. A passed independent state, API, receipt, or structural verifier proves its stated expected effect; if it satisfies the success criteria, finish rather than refreshing, navigating, or repeating the action. Never repeat the same passed target/action unless the task explicitly requires repetition.
Never ask the user to grant or confirm approval. If a requested external effect has a valid affordance, propose the bounded semantic action; the Coordinator alone requests, binds, and consumes any approval token.
Ask the user for blocking ambiguity. After a failed or inconclusive effect, replan or request clarification without assuming success.
Choose one action, state its expected effect and evidence need, and stay within the remaining budgets."""


class AffordanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    surface: str
    role: str
    label: str
    action: str
    confidence: float
    state: dict[str, Any]


class PlannerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_spec: dict[str, Any]
    active_subgoal: str
    affordances: tuple[AffordanceSummary, ...]
    selected_artifact_refs: tuple[str, ...]
    granted_capabilities: tuple[str, ...]
    approval_handling: str
    remaining_budgets: dict[str, int]
    pending_evidence_obligations: tuple[str, ...]
    latest_outcome: dict[str, Any]
    recent_proposals: tuple[dict[str, Any], ...]
    verified_effects: tuple[str, ...]
    recovery_summary: dict[str, Any]
    accepted_knowledge: tuple[str, ...]
    task_revision: int
    state_version: int
    snapshot_id: str


@dataclass(frozen=True)
class PlannerLimits:
    max_steps: int = 20
    max_observations: int = 30
    max_recoveries: int = 3
    max_effectful_actions: int = 5


@dataclass
class GeneralistLMPlanner:
    model: ModelPort
    limits: PlannerLimits = field(default_factory=PlannerLimits)
    accepted_knowledge: tuple[str, ...] = ()
    config: ModelConfig = field(
        default_factory=lambda: ModelConfig(
            temperature=0.0,
            max_tokens=1_024,
            prompt_version=GENERALIST_PLANNER_PROMPT_VERSION,
        )
    )

    async def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        if envelope.task_spec is None:
            raise ValueError("GeneralistLMPlanner requires a validated TaskSpec")
        context = self.build_context(envelope, state, snapshot)
        proposal = await self.model.generate_structured(
            [
                ModelMessage(role="system", content=_SYSTEM_PROMPT),
                ModelMessage(role="user", content=context.model_dump_json()),
            ],
            PlannerProposal,
            self.config,
        )
        return PlannerDecision(
            proposal=proposal,
            reason=proposal.reason,
            planner_context={
                "task_revision": context.task_revision,
                "state_version": context.state_version,
                "snapshot_id": context.snapshot_id,
                "affordance_count": len(context.affordances),
                "granted_capabilities": list(context.granted_capabilities),
                "remaining_budgets": context.remaining_budgets,
                "context": json.loads(context.model_dump_json()),
                "prompt_version": self.config.prompt_version,
            },
            model_call=self.model.last_call,
        )

    def build_context(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerContext:
        return build_planner_context(
            envelope,
            state,
            snapshot,
            limits=self.limits,
            accepted_knowledge=self.accepted_knowledge,
        )


def build_planner_context(
    envelope: TaskEnvelope,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    *,
    limits: PlannerLimits = PlannerLimits(),
    accepted_knowledge: tuple[str, ...] = (),
) -> PlannerContext:
    task_spec = envelope.task_spec
    if task_spec is None:
        raise ValueError("GeneralistLMPlanner requires a validated TaskSpec")
    receipt = state.receipts[-1] if state.receipts else None
    verification = state.latest_verification
    latest_outcome = {
        "receipt_success": receipt.success if receipt else None,
        "receipt_backend": receipt.backend if receipt else "",
        "error_code": receipt.error_code.value if receipt and receipt.error_code else "",
        "verification_status": verification.status.value if verification else "",
        "verification_reason": verification.reason if verification else "",
        "verification_evidence": [
            {
                "verifier_kind": item.verifier_kind,
                "target": item.target,
                "passed": item.passed,
                "expected": item.expected,
            }
            for item in (verification.evidence[-3:] if verification else [])
        ],
    }
    latest_proposal = state.planner_history[-1] if state.planner_history else {}
    verified_effects = (
        tuple(str(item) for item in latest_proposal.get("expected_effects", []))
        if verification and verification.passed
        else ()
    )
    return PlannerContext(
        task_spec=task_spec.model_dump(mode="json"),
        active_subgoal=state.subgoals[-1] if state.subgoals else task_spec.objective,
        affordances=tuple(
            AffordanceSummary(
                id=item.id,
                surface=item.surface.value,
                role=item.role,
                label=item.label,
                action=item.action,
                confidence=item.confidence,
                state=dict(item.state),
            )
            for item in snapshot.affordance_model.affordances
        ),
        selected_artifact_refs=tuple(snapshot.observation.artifact_refs),
        granted_capabilities=tuple(sorted(set(envelope.capabilities))),
        approval_handling="coordinator_managed",
        remaining_budgets={
            "steps": max(0, limits.max_steps - state.step_count),
            "observations": max(0, limits.max_observations - state.observation_count),
            "recoveries": max(0, limits.max_recoveries - state.recovery_count),
            "effectful_actions": max(
                0,
                limits.max_effectful_actions - state.effectful_action_count,
            ),
        },
        pending_evidence_obligations=tuple(state.pending_obligations),
        latest_outcome=latest_outcome,
        recent_proposals=tuple(state.planner_history[-5:]),
        verified_effects=verified_effects,
        recovery_summary=dict(state.recovery_diagnostics),
        accepted_knowledge=accepted_knowledge,
        task_revision=task_spec.revision,
        state_version=state.version,
        snapshot_id=snapshot.observation.snapshot_id,
    )
