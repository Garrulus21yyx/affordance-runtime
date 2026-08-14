"""WoT-private interaction support and primitive translators."""

from affordance_runtime.world.interaction_capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    AdapterCapabilitySupport,
    AdapterInteractionProfile,
    CapabilityComposer,
    ComposedInteractionCapabilities,
    InteractionSubjectKind,
    PrimitiveTranslator,
)

WOT_INTERACTION_PROFILE = AdapterInteractionProfile(
    "wot-interactions.v1",
    "wot",
    "wot",
    (
        AdapterCapabilitySupport(
            "activate", ("invoke",), (InteractionSubjectKind.ENTITY,),
        ),
        AdapterCapabilitySupport(
            "read", ("read_property",), (InteractionSubjectKind.ENTITY,),
        ),
        # Existing WoT property writes remain an already implemented private
        # route. This declaration does not create a current ActionSpace member.
        AdapterCapabilitySupport(
            "set_value", ("write_property",), (InteractionSubjectKind.ENTITY,),
        ),
    ),
)

WOT_PRIMITIVE_TRANSLATORS = (
    PrimitiveTranslator("activate", "invoke"),
    PrimitiveTranslator("read", "read_property"),
    PrimitiveTranslator("set_value", "write_property"),
)

WOT_INTERACTION_CAPABILITIES: ComposedInteractionCapabilities = CapabilityComposer(
    INTERACTION_CAPABILITY_REGISTRY
).compose(WOT_INTERACTION_PROFILE, WOT_PRIMITIVE_TRANSLATORS)
