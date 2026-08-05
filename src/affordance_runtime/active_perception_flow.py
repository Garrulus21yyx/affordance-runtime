"""Typed active-perception collaborator with no Runtime state or trace authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from affordance_runtime.active_perception import (
    ActivePerceptionController,
    ActivePerceptionDecision,
    EvidenceGap,
    EvidenceGapExtractor,
    PerceptionResolution,
    ProbeBudget,
    ProbeBudgetPolicy,
    ProbeCapability,
    ProbeReceipt,
    probe_capabilities_for_requests,
    probe_fingerprint,
    request_for_command,
)
from affordance_runtime.grounding import ActivePerceptionRequest
from affordance_runtime.perception_session import PerceptionCapture, PerceptionSession


@dataclass(frozen=True)
class ActivePerceptionFlowContext:
    snapshot: PerceptionCapture
    run_id: str
    task_revision: int
    plan_version: int
    active_subgoal_id: str
    state_version: int
    remaining_observations: int
    attempted_probe_fingerprints: frozenset[str]
    effectful_action: bool


@dataclass(frozen=True)
class ActivePerceptionPreparation:
    context: ActivePerceptionFlowContext
    gaps: tuple[EvidenceGap, ...]
    capabilities: tuple[ProbeCapability, ...] = ()
    budget: ProbeBudget = field(
        default_factory=lambda: ProbeBudget(
            observations=0,
            timeout_ms=0,
            artifacts=0,
        )
    )
    decision: ActivePerceptionDecision | None = None
    selected_probe_fingerprint: str = ""
    targeted_capture_available: bool = True


@dataclass(frozen=True)
class ActivePerceptionProbeResult:
    targeted_snapshot: PerceptionCapture | None
    receipt: ProbeReceipt
    resolution: PerceptionResolution


@dataclass(frozen=True)
class ActivePerceptionFlow:
    session: PerceptionSession
    gap_extractor: EvidenceGapExtractor = field(default_factory=EvidenceGapExtractor)
    controller: ActivePerceptionController = field(default_factory=ActivePerceptionController)
    budget_policy: ProbeBudgetPolicy = field(default_factory=ProbeBudgetPolicy)

    def prepare(self, context: ActivePerceptionFlowContext) -> ActivePerceptionPreparation:
        gaps = self.gap_extractor.extract(
            context.snapshot,
            run_id=context.run_id,
            task_revision=context.task_revision,
            plan_version=context.plan_version,
            active_subgoal_id=context.active_subgoal_id,
        )
        if not gaps:
            return ActivePerceptionPreparation(context, ())
        if not self.session.supports_targeted_capture:
            budget = ProbeBudget(observations=0, timeout_ms=0, artifacts=0)
            return ActivePerceptionPreparation(
                context,
                gaps,
                budget=budget,
                decision=self.controller.decide(
                    gaps,
                    (),
                    based_on_state_version=context.state_version,
                    based_on_snapshot_id=context.snapshot.observation.snapshot_id,
                    budget=budget,
                    effectful_action=context.effectful_action,
                ),
                targeted_capture_available=False,
            )
        gap_requests = tuple(
            ActivePerceptionRequest(
                entity_key=item.entity_key,
                property_key=item.property_key,
                requested_sources=item.preferred_sources,
                reason=item.reason,
                max_observations=1,
            )
            for item in gaps
            if item.preferred_sources
        )
        requests = (*context.snapshot.active_perception_requests, *gap_requests)
        capabilities = probe_capabilities_for_requests(requests)
        budget = self.budget_policy.remaining_authority(
            context.snapshot.perception_requirements,
            remaining_observations=context.remaining_observations,
        )
        decision = self.controller.decide(
            gaps,
            capabilities,
            based_on_state_version=context.state_version,
            based_on_snapshot_id=context.snapshot.observation.snapshot_id,
            budget=budget,
            attempted_probe_fingerprints=context.attempted_probe_fingerprints,
            effectful_action=context.effectful_action,
        )
        fingerprint = ""
        if decision.plan is not None:
            command = decision.plan.commands[0]
            capability = next(
                item for item in capabilities if item.capability_id == command.capability_id
            )
            gap = next(item for item in gaps if item.gap_id in command.gap_ids)
            fingerprint = probe_fingerprint(capability, gap)
        return ActivePerceptionPreparation(
            context,
            gaps,
            capabilities,
            budget,
            decision,
            fingerprint,
        )

    def execute(self, preparation: ActivePerceptionPreparation) -> ActivePerceptionProbeResult:
        decision = preparation.decision
        if decision is None or decision.plan is None:
            raise ValueError("active perception execution requires a prepared probe plan")
        plan = decision.plan
        command = plan.commands[0]
        started_at_s = time()
        try:
            targeted = self.session.capture_targeted((request_for_command(command),))
        except Exception as exc:
            completed_at_s = time()
            receipt = ProbeReceipt(
                command_id=command.command_id,
                started_at_s=started_at_s,
                completed_at_s=completed_at_s,
                observation_epoch_id=preparation.context.snapshot.observation.snapshot_id,
                source=command.source,
                success=False,
                error_code=type(exc).__name__,
                latency_ms=(completed_at_s - started_at_s) * 1_000,
                model_calls=command.budget.model_calls,
                estimated_cost=command.budget.estimated_cost,
            )
            return ActivePerceptionProbeResult(
                None,
                receipt,
                self.controller.resolve(
                    preparation.gaps,
                    preparation.context.snapshot,
                    based_on_snapshot_id=plan.based_on_snapshot_id,
                    receipts=(receipt,),
                    effectful_action=preparation.context.effectful_action,
                ),
            )
        completed_at_s = time()
        receipt = ProbeReceipt(
            command_id=command.command_id,
            started_at_s=started_at_s,
            completed_at_s=completed_at_s,
            observation_epoch_id=targeted.observation.snapshot_id,
            source=command.source,
            success=True,
            artifact_refs=tuple(targeted.observation.artifact_refs),
            assertion_refs=tuple(item.assertion_id for item in targeted.source_assertions),
            estimated_cost=command.budget.estimated_cost,
            latency_ms=(completed_at_s - started_at_s) * 1_000,
            model_calls=command.budget.model_calls,
        )
        return ActivePerceptionProbeResult(
            targeted,
            receipt,
            self.controller.resolve(
                preparation.gaps,
                targeted,
                based_on_snapshot_id=plan.based_on_snapshot_id,
                receipts=(receipt,),
                effectful_action=preparation.context.effectful_action,
            ),
        )
