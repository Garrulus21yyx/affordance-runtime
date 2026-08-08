"""Pure WoT TD and affordance identity comparison."""

from affordance_runtime.adapters.wot import ThingAffordanceModel
from affordance_runtime.surfaces.wot.contracts import WotAffordanceBinding


def wot_affordance_is_current(
    binding: WotAffordanceBinding,
    live_td_digest: str,
    live_model: ThingAffordanceModel,
) -> bool:
    if binding.td_digest != live_td_digest or binding.thing_id != live_model.thing_id:
        return False
    affordance = next(
        (item for item in live_model.affordances if item.id == binding.source_affordance_id),
        None,
    )
    if affordance is None:
        return False
    try:
        live = WotAffordanceBinding.from_affordance(
            binding.source_observation_id,
            live_td_digest,
            live_model,
            affordance,
        )
    except ValueError:
        return False
    return (
        binding.affordance_fingerprint == live.affordance_fingerprint
        and binding.affordance_kind == live.affordance_kind
        and binding.affordance_name == live.affordance_name
        and binding.href == live.href
        and binding.method == live.method
        and binding.content_type == live.content_type
        and binding.input_schema == live.input_schema
        and binding.security_scheme_ref == live.security_scheme_ref
        and binding.primitive_action == live.primitive_action
        and binding.semantic_action == live.semantic_action
    )
