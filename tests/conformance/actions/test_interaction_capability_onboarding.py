from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from affordance_runtime.actions import (
    INTERACTION_CAPABILITY_REGISTRY,
    ActionBinding,
    ActionSpaceBuilder,
)
from affordance_runtime.actions.capabilities import (
    AdapterCapabilitySupport,
    AdapterInteractionProfile,
    CapabilityComposer,
    InteractionCapabilityError,
    InteractionCapabilityIssueCode,
    InteractionSubjectKind,
    PrimitiveTranslator,
    VerificationContract,
)
from affordance_runtime.agent.context.projection import project_action_space
from affordance_runtime.model.policy.grounded_tool_catalog import resolve_grounded_tool_call
from affordance_runtime.model.policy.grounded_tool_compiler import GroundedToolCompiler
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedActionResolution,
    GroundedToolCatalog,
)
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallIssueCode,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.providers.tool_transport_contracts import ToolCall
from affordance_runtime.surfaces.browsergym.interaction_profile import (
    BROWSERGYM_INTERACTION_CAPABILITIES,
    BROWSERGYM_INTERACTION_PROFILE,
)
from affordance_runtime.surfaces.dom.interaction_profile import (
    DOM_INTERACTION_CAPABILITIES,
    DOM_INTERACTION_PROFILE,
)
from affordance_runtime.surfaces.visual.interaction_profile import (
    VISUAL_INTERACTION_CAPABILITIES,
    VISUAL_INTERACTION_PROFILE,
)
from affordance_runtime.surfaces.wot.interaction_profile import (
    WOT_INTERACTION_CAPABILITIES,
    WOT_INTERACTION_PROFILE,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    WorldObservation,
    build_agent_world_view,
)
from tests.support.world import fused_world

_ROOT = Path(__file__).resolve().parents[3]
_CURRENT_ACTIONS = {"activate", "type_text", "select_option", "read"}
_FUTURE_ACTIONS = {"scroll", "press_key", "focus", "drag_to", "set_value", "hover"}


def _type_text_world() -> tuple[TaskGoal, WorldObservation]:
    schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "enum": ["alpha", "beta"],
            }
        },
        "required": ["text"],
        "additionalProperties": False,
    }
    target = SemanticTarget("field:1", "textbox", "Name", {"value": ""})
    fact = StateFact("state:value", target.target_id, "value", "", "obs:1")
    binding = ActionBinding(
        "binding:1",
        "obs:1",
        "obs:1",
        "revision:1",
        "fingerprint:1",
        target.target_id,
        target.target_id,
        "dom",
        "dom",
        "type_text",
        "fill",
        "local_reversible",
        ("external_ui_interaction",),
        schema,
        {"selector": "#private"},
    )
    task = TaskGoal(
        "task:1",
        "Enter the name",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    world = fused_world("obs:1", (target,), (fact,), (binding,), surface="dom")
    return task, world


def test_registry_is_closed_unique_and_code_versioned() -> None:
    definitions = INTERACTION_CAPABILITY_REGISTRY.definitions
    names = tuple(item.semantic_action for item in definitions)

    assert INTERACTION_CAPABILITY_REGISTRY.registry_id == "interaction-capabilities.v1"
    assert len(names) == len(set(names)) == 10
    assert set(names) == _CURRENT_ACTIONS | _FUTURE_ACTIONS
    with pytest.raises(InteractionCapabilityError) as unsupported:
        INTERACTION_CAPABILITY_REGISTRY.require("click_button")
    assert unsupported.value.code is InteractionCapabilityIssueCode.UNSUPPORTED_SEMANTIC_ACTION


@pytest.mark.parametrize(
    ("profile", "composed"),
    (
        (DOM_INTERACTION_PROFILE, DOM_INTERACTION_CAPABILITIES),
        (VISUAL_INTERACTION_PROFILE, VISUAL_INTERACTION_CAPABILITIES),
        (WOT_INTERACTION_PROFILE, WOT_INTERACTION_CAPABILITIES),
        (BROWSERGYM_INTERACTION_PROFILE, BROWSERGYM_INTERACTION_CAPABILITIES),
    ),
)
def test_each_profile_action_and_primitive_has_one_composed_owner(profile, composed) -> None:
    declared = {
        (capability.semantic_action, primitive)
        for capability in profile.capabilities
        for primitive in capability.primitive_actions
    }
    resolved = {
        (
            composed.resolve_primitive(primitive).semantic_action,
            composed.resolve_primitive(primitive).primitive_action,
        )
        for _action, primitive in declared
    }

    assert resolved == declared
    assert all(
        composed.resolve_action(capability.semantic_action).semantic_definition
        is INTERACTION_CAPABILITY_REGISTRY.require(capability.semantic_action)
        for capability in profile.capabilities
    )


def test_composer_and_schema_contracts_fail_closed_with_typed_issues() -> None:
    profile = AdapterInteractionProfile(
        "fixture.v1",
        "fixture",
        "fixture",
        (
            AdapterCapabilitySupport(
                "activate",
                ("tap",),
                (InteractionSubjectKind.ENTITY,),
            ),
        ),
    )
    with pytest.raises(InteractionCapabilityError) as primitive:
        CapabilityComposer(INTERACTION_CAPABILITY_REGISTRY).compose(profile, ())
    assert primitive.value.code is InteractionCapabilityIssueCode.UNSUPPORTED_PRIMITIVE

    with pytest.raises(InteractionCapabilityError) as schema:
        INTERACTION_CAPABILITY_REGISTRY.validate_parameter_schema(
            "type_text",
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
    assert schema.value.code is InteractionCapabilityIssueCode.SCHEMA_CONTRACT_MISMATCH

    with pytest.raises(InteractionCapabilityError) as unknown:
        CapabilityComposer(INTERACTION_CAPABILITY_REGISTRY).compose(
            AdapterInteractionProfile(
                "unknown.v1",
                "fixture",
                "fixture",
                (
                    AdapterCapabilitySupport(
                        "unknown",
                        ("unknown_primitive",),
                        (InteractionSubjectKind.ENTITY,),
                    ),
                ),
            ),
            (PrimitiveTranslator("unknown", "unknown_primitive"),),
        )
    assert unknown.value.code is InteractionCapabilityIssueCode.UNSUPPORTED_SEMANTIC_ACTION


def test_profile_support_never_creates_an_action_space_member() -> None:
    task = TaskGoal("task:none", "Observe", risk_profile=RiskProfile.READ_ONLY)
    world = fused_world(
        "obs:none",
        (SemanticTarget("viewport:1", "viewport", "Viewport"),),
        surface="visual",
        profile=ObservationSourceProfile.visual(),
    )

    assert "set_value" in {
        item.semantic_action for item in WOT_INTERACTION_PROFILE.capabilities
    }
    assert ActionSpaceBuilder().build(task, world).options == ()


def test_existing_business_schema_is_conserved_binding_to_exact_resolution_and_admission() -> None:
    task, world = _type_text_world()
    binding = world.bindings[0]
    action_space = ActionSpaceBuilder().build(task, world)
    option = action_space.options[0]
    projected = project_action_space(
        action_space,
        build_agent_world_view(world),
    ).options[0]
    projected = replace(
        projected,
        operation="type_text",
        target_ref="E1",
        target_semantics={"role": "textbox", "label": "Name"},
        target_role="textbox",
        destination_mode="forbidden",
        grounding_context_id="context:schema",
    )
    compiled = GroundedToolCompiler().compile(
        (projected,),
        context_id="context:schema",
    )[0]
    catalog = GroundedToolCatalog(
        "grounded-catalog:schema",
        "context:schema",
        (compiled.public_spec,),
        (compiled,),
        1,
    )
    arguments = {"text": "beta"}
    normalized = ProviderCallNormalizer().normalize(
        ToolCall(compiled.public_spec.name, arguments),
        catalog,
    )
    assert normalized.status is ToolCallReconciliationStatus.EXACT
    assert normalized.exact_call == ToolCall(compiled.public_spec.name, arguments)
    resolved = resolve_grounded_tool_call(
        catalog,
        normalized.exact_call,
        expected_context_id="context:schema",
    )
    assert isinstance(resolved, GroundedActionResolution)
    admitted = ActionSpaceBuilder().try_admit_selection(
        action_space,
        resolved.decision.action_id,
        dict(resolved.decision.parameters),
    ).admitted

    assert binding.parameter_schema == option.parameter_schema == projected.parameter_schema
    assert compiled.public_spec.input_schema["properties"] == binding.parameter_schema["properties"]
    assert compiled.public_spec.input_schema["required"] == binding.parameter_schema["required"]
    assert admitted is not None
    assert admitted.parameters == arguments
    assert admitted.schema_digest == option.schema_digest
    assert isinstance(binding.verification_contract, VerificationContract)
    assert binding.verification_contract_digest == option.verification_contract_digest
    assert option.verification_contract_digest == admitted.verification_contract_digest
    assert admitted.verification_contract.digest == admitted.verification_contract_digest
    assert binding.verification_contract_digest != (
        INTERACTION_CAPABILITY_REGISTRY.require("type_text").definition_digest
    )
    assert "selector" not in repr(compiled.public_spec.input_schema)
    assert "binding:1" not in repr(compiled.public_spec.input_schema)


def test_state_compatibility_projection_rejects_contradiction_at_construction() -> None:
    with pytest.raises(ValueError, match="contradicts canonical StateFact"):
        fused_world(
            "obs:contradiction",
            (SemanticTarget("field:1", "textbox", "Name", {"value": "old"}),),
            (StateFact("state:value", "field:1", "value", "new", "obs:contradiction"),),
            surface="dom",
        )


def test_tool_compilation_cannot_delete_actor_world_nodes_or_facts() -> None:
    task, world = _type_text_world()
    action_space = ActionSpaceBuilder().build(task, world)
    actor_world = build_agent_world_view(world)
    before_targets = actor_world.targets
    before_facts = actor_world.facts

    project_action_space(action_space, actor_world)

    assert actor_world.targets == before_targets
    assert actor_world.facts == before_facts


def test_normalizer_import_boundary_and_deleted_owners_are_unreachable() -> None:
    normalizer_path = (
        _ROOT
        / "src/affordance_runtime/model/policy/provider_call_normalizer.py"
    )
    tree = ast.parse(normalizer_path.read_text())
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        name.endswith(
            (
                "actor_world_snapshot",
                "world.contracts",
                "world.action_space",
                "execution.contracts",
            )
        )
        for name in imports
    )
    assert not (_ROOT / "src/affordance_runtime/world/action_vocabulary.py").exists()
    production = "\n".join(
        path.read_text()
        for path in (_ROOT / "src/affordance_runtime").rglob("*.py")
    )
    assert "_CANONICAL_COMPATIBILITY" not in production
    assert "canonical_action_operation" not in production
    assert "_normalize_catalog_call" not in production


def test_non_equivalent_representation_returns_typed_did_you_mean_without_exact_call() -> None:
    task, world = _type_text_world()
    action_space = ActionSpaceBuilder().build(task, world)
    projected = project_action_space(action_space, build_agent_world_view(world)).options[0]
    projected = replace(
        projected,
        operation="type_text",
        target_ref="E1",
        target_semantics={"role": "textbox", "label": "Name"},
        target_role="textbox",
        destination_mode="forbidden",
        grounding_context_id="context:owner",
    )
    canonical = GroundedToolCompiler().compile(
        (projected,),
        context_id="context:owner",
    )[0]
    wrong_spec = replace(canonical.public_spec, name="type_text_wrong_owner")
    wrong = replace(
        canonical,
        public_spec=wrong_spec,
        authority_equivalence_digest="sha256:not-equivalent",
    )
    catalog = GroundedToolCatalog(
        "grounded-catalog:owner",
        "context:owner",
        (wrong_spec, canonical.public_spec),
        (wrong, canonical),
        1,
    )
    result = ProviderCallNormalizer().normalize(
        ToolCall("type_text_wrong_owner", {"grounding_ref": "E1", "text": "alpha"}),
        catalog,
    )

    assert result.status is ToolCallReconciliationStatus.REPAIR_REQUIRED
    assert result.issue_code is ToolCallIssueCode.NON_EQUIVALENT_TOOL_INTENT
    assert result.exact_call is None
    assert len(result.did_you_mean) == 1
    assert result.did_you_mean[0].tool_name == canonical.public_spec.name
    assert result.did_you_mean[0].public_arguments == {"text": "alpha"}
