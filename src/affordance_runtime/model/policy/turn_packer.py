"""Deterministic joint packing of one current model turn."""

from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.agent.context.action_candidate_projection import (
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.model_turn_delivery import (
    ModelTurnDelivery,
    build_model_turn_delivery,
)
from affordance_runtime.model.policy.canonical_provider_envelope import (
    CanonicalProviderEnvelopeBinder,
    CanonicalProviderIdentity,
)
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounded_tool_catalog import compile_grounded_action_catalog
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolCatalog
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.reasoning_policy import ActionPolicyCallProfile
from affordance_runtime.model.policy.request_admission import (
    AdmittedProviderEnvelope,
    InvalidProviderEnvelope,
    ModelRequestBudget,
    ModelRequestCapacityError,
    RejectedProviderEnvelope,
    RequestAdmission,
)


@dataclass(frozen=True)
class PackedModelTurn:
    delivery: ModelTurnDelivery
    catalog: GroundedToolCatalog
    admitted_envelope: AdmittedProviderEnvelope
    attempted_record_counts: tuple[tuple[str, int], ...]
    admitted_record_counts: tuple[tuple[str, int], ...]
    packing_backoff_count: int

    def __post_init__(self) -> None:
        if (
            self.delivery.delivery_id != self.catalog.delivery_id
            or self.catalog.delivery_id != self.delivery.delivery_id
            or self.admitted_envelope.envelope.delivery_id != self.delivery.delivery_id
            or self.admitted_envelope.envelope.catalog is not self.catalog
            or self.admitted_record_counts != self.delivery.admitted_record_counts
            or self.packing_backoff_count != self.delivery.packing_backoff_count
            or any(
                admitted > dict(self.attempted_record_counts).get(kind, 0)
                for kind, admitted in self.admitted_record_counts
            )
        ):
            raise ValueError("packed model turn artifacts do not share one frozen selection")


@dataclass(frozen=True)
class TurnPacker:
    """Small greedy fitter using RequestAdmission's one profile and estimator."""

    def pack(
        self,
        request: ModelDecisionRequest,
        *,
        binder: CanonicalProviderEnvelopeBinder,
        identity: CanonicalProviderIdentity,
        call_profile: ActionPolicyCallProfile,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        history_messages: tuple[object, ...] = (),
        pending_tool_call_id: str = "",
        pending_tool_name: str = "",
    ) -> PackedModelTurn:
        plan = request.agent_context.action_delivery_plan
        if plan is None:
            raise ValueError("turn packing requires one ActionDeliveryPlan")
        include_images = binder.context_binder._include_images(  # noqa: SLF001 - same request-boundary owner
            request,
            supports_multimodal,
            perception_profile,
        )
        request_budget = replace(binder.request_budget, max_output_tokens=call_profile.max_output_tokens)

        admitted_counts = {item.kind.value: 0 for item in plan.obligations}
        attempted_counts = dict(admitted_counts)
        accepted = self._attempt(
            request,
            binder=binder,
            identity=identity,
            call_profile=call_profile,
            include_images=include_images,
            supports_multimodal=supports_multimodal,
            perception_profile=perception_profile,
            admitted_records=admitted_counts,
            backoff_count=0,
            request_budget=request_budget,
            history_messages=history_messages,
            pending_tool_call_id=pending_tool_call_id,
            pending_tool_name=pending_tool_name,
        )
        packing_budget = replace(
            request_budget,
            admission_limit=min(
                request_budget.admission_limit,
                request_budget.soft_target_tokens,
            ),
        )
        backoffs = 0
        blocked: set[str] = set()

        foreground = next(
            (
                item
                for item in plan.obligations
                if (item.scope or item.kind.value) == plan.foreground_scope
            ),
            None,
        )
        if foreground is not None and foreground.remaining:
            kind = foreground.kind.value
            required_count = (
                len(foreground.remaining)
                if foreground.kind is DeliveryObligationKind.EXPLICIT_QUERY
                else 1
            )
            attempted_counts[kind] = required_count
            required = dict(admitted_counts)
            required[kind] = required_count
            # A bounded find_controls result is one capability set: every
            # returned route must be callable in this same-World catalog.
            # Other foreground inventories retain their one-record minimum.
            accepted = self._attempt(
                request,
                binder=binder,
                identity=identity,
                call_profile=call_profile,
                include_images=include_images,
                supports_multimodal=supports_multimodal,
                perception_profile=perception_profile,
                admitted_records=required,
                backoff_count=0,
                request_budget=request_budget,
                history_messages=history_messages,
                pending_tool_call_id=pending_tool_call_id,
                pending_tool_name=pending_tool_name,
            )
            admitted_counts = required

        first_extension_round = foreground is not None and bool(foreground.remaining)
        while True:
            admitted_this_round = False
            for obligation in plan.obligations:
                kind = obligation.kind.value
                if first_extension_round and obligation is foreground:
                    # The required foreground atom was this group's attempt in
                    # depth round zero. Every other eligible group gets one
                    # attempt before foreground can receive a second atom.
                    continue
                if kind in blocked or admitted_counts[kind] >= len(obligation.remaining):
                    continue
                tentative = dict(admitted_counts)
                tentative[kind] += 1
                attempted_counts[kind] = max(attempted_counts[kind], tentative[kind])
                try:
                    accepted = self._attempt(
                        request,
                        binder=binder,
                        identity=identity,
                        call_profile=call_profile,
                        include_images=include_images,
                        supports_multimodal=supports_multimodal,
                        perception_profile=perception_profile,
                        admitted_records=tentative,
                        backoff_count=0,
                        request_budget=packing_budget,
                        history_messages=history_messages,
                        pending_tool_call_id=pending_tool_call_id,
                        pending_tool_name=pending_tool_name,
                    )
                except ModelRequestCapacityError:
                    blocked.add(kind)
                    backoffs += 1
                    continue
                admitted_counts = tentative
                admitted_this_round = True
            if first_extension_round:
                first_extension_round = False
                foreground_has_more = bool(
                    foreground is not None
                    and admitted_counts[foreground.kind.value] < len(foreground.remaining)
                )
                if admitted_this_round or foreground_has_more:
                    continue
            if not admitted_this_round:
                break

        accepted = self._attempt(
            request,
            binder=binder,
            identity=identity,
            call_profile=call_profile,
            include_images=include_images,
            supports_multimodal=supports_multimodal,
            perception_profile=perception_profile,
            admitted_records=admitted_counts,
            backoff_count=backoffs,
            request_budget=request_budget,
            history_messages=history_messages,
            pending_tool_call_id=pending_tool_call_id,
            pending_tool_name=pending_tool_name,
        )
        delivery, catalog, admitted = accepted
        return PackedModelTurn(
            delivery,
            catalog,
            admitted,
            tuple(sorted(attempted_counts.items())),
            tuple(sorted(admitted_counts.items())),
            backoffs,
        )

    @staticmethod
    def _attempt(
        request: ModelDecisionRequest,
        *,
        binder: CanonicalProviderEnvelopeBinder,
        identity: CanonicalProviderIdentity,
        call_profile: ActionPolicyCallProfile,
        include_images: bool,
        supports_multimodal: bool,
        perception_profile: DecisionPerceptionProfile,
        admitted_records: dict[str, int],
        backoff_count: int,
        request_budget: ModelRequestBudget,
        history_messages: tuple[object, ...],
        pending_tool_call_id: str,
        pending_tool_name: str,
    ) -> tuple[ModelTurnDelivery, GroundedToolCatalog, AdmittedProviderEnvelope]:
        delivery = build_model_turn_delivery(
            request.agent_context,
            include_images=include_images,
            admitted_records=admitted_records,
            packing_backoff_count=backoff_count,
            committed_step=request.last_step,
            pending_tool_call_id=pending_tool_call_id,
            pending_tool_name=pending_tool_name,
        )
        catalog = compile_grounded_action_catalog(request.agent_context, delivery)
        envelope = binder.bind(
            request,
            delivery,
            catalog,
            identity=identity,
            call_profile=call_profile,
            output_token_reserve=(
                call_profile.max_output_tokens
                + request_budget.protocol_reserve_tokens
                + request_budget.safety_margin_tokens
            ),
            history_messages=history_messages,
        )
        outcome = RequestAdmission().admit(envelope, budget=request_budget)
        if isinstance(outcome, RejectedProviderEnvelope):
            raise ModelRequestCapacityError(outcome.token_breakdown)
        if isinstance(outcome, InvalidProviderEnvelope):
            raise ValueError(f"{outcome.reason}: {outcome.detail}")
        return delivery, catalog, outcome
