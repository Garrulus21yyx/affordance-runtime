"""Visual-private interaction support and primitive translators."""

from affordance_runtime.world.interaction_capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    AdapterCapabilitySupport,
    AdapterInteractionProfile,
    CapabilityComposer,
    ComposedInteractionCapabilities,
    InteractionSubjectKind,
    PrimitiveTranslator,
)

VISUAL_INTERACTION_PROFILE = AdapterInteractionProfile(
    "visual-interactions.v1",
    "visual",
    "visual",
    (
        AdapterCapabilitySupport(
            "activate", ("point_activate",), (InteractionSubjectKind.ENTITY,),
        ),
    ),
)

VISUAL_PRIMITIVE_TRANSLATORS = (
    PrimitiveTranslator("activate", "point_activate"),
)

VISUAL_INTERACTION_CAPABILITIES: ComposedInteractionCapabilities = CapabilityComposer(
    INTERACTION_CAPABILITY_REGISTRY
).compose(VISUAL_INTERACTION_PROFILE, VISUAL_PRIMITIVE_TRANSLATORS)
