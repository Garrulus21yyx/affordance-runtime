"""Test helpers that preserve the single production ModelTurnDelivery owner."""

from affordance_runtime.agent.context.model_turn_delivery import (
    ModelTurnDelivery,
    build_model_turn_delivery,
)
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolPhase


def delivery_for(context, *, include_images: bool = False) -> ModelTurnDelivery:
    return build_model_turn_delivery(context, include_images=include_images)


def catalog_for(context, phase: GroundedToolPhase = GroundedToolPhase.ACTION_SELECTION):
    delivery = delivery_for(context)
    return delivery, compile_grounded_tool_catalog(context, phase, delivery)


def resolve_catalog_call(catalog, call, **kwargs):
    kwargs.setdefault("expected_delivery_id", catalog.delivery_id)
    return resolve_grounded_tool_call(catalog, call, **kwargs)
