"""DOM-private interaction support and primitive translators."""

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    AdapterCapabilitySupport,
    AdapterInteractionProfile,
    CapabilityComposer,
    ComposedInteractionCapabilities,
    InteractionSubjectKind,
    PrimitiveTranslator,
)

DOM_BROWSER_GLOBAL_PRIMITIVES = (
    "goto",
    "go_back",
    "go_forward",
    "new_tab",
    "tab_focus",
    "tab_close",
)


DOM_INTERACTION_PROFILE = AdapterInteractionProfile(
    "dom-interactions.v1",
    "dom",
    "dom",
    (
        AdapterCapabilitySupport(
            "activate",
            ("click",),
            (InteractionSubjectKind.ENTITY,),
        ),
        AdapterCapabilitySupport(
            "type_text",
            ("type", "fill"),
            (InteractionSubjectKind.ENTITY,),
        ),
        AdapterCapabilitySupport(
            "select_option",
            ("select",),
            (InteractionSubjectKind.ENTITY,),
        ),
        *(
            AdapterCapabilitySupport(
                primitive,
                (primitive,),
                (InteractionSubjectKind.BROWSER_CONTEXT,),
            )
            for primitive in DOM_BROWSER_GLOBAL_PRIMITIVES
        ),
    ),
)

DOM_PRIMITIVE_TRANSLATORS = (
    PrimitiveTranslator("activate", "click"),
    PrimitiveTranslator("type_text", "type"),
    PrimitiveTranslator("type_text", "fill"),
    PrimitiveTranslator("select_option", "select"),
    *(PrimitiveTranslator(primitive, primitive) for primitive in DOM_BROWSER_GLOBAL_PRIMITIVES),
)

DOM_INTERACTION_CAPABILITIES: ComposedInteractionCapabilities = CapabilityComposer(
    INTERACTION_CAPABILITY_REGISTRY
).compose(DOM_INTERACTION_PROFILE, DOM_PRIMITIVE_TRANSLATORS)
