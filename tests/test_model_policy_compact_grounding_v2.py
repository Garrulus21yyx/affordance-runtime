import asyncio
import inspect
import json

from affordance_runtime.benchmarks.model_conformance.decision_matrix import (
    build_destination_case,
    build_multi_action_case,
    build_seven_decision_cases,
)
from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.model_policy.factory import model_policy_from_environment
from affordance_runtime.model_policy.grounding import (
    COMPACT_CONTRACT_V2_PROFILE_VERSION,
    MAX_COMPACT_GUIDE_BYTES,
    DecisionGroundingVariant,
    build_compact_decision_guide,
    build_compact_decision_guide_v2,
    grounding_profile_version,
    serialize_compact_decision_guide,
    serialize_compact_decision_guide_v2,
)


def _scenario():
    return asyncio.run(build_live_dom_scenario())


def test_v1_guide_shape_wraps_first_action_in_the_v2_decision_package() -> None:
    scenario = _scenario()
    guide = build_compact_decision_guide(scenario.serialized_context)
    encoded = json.loads(serialize_compact_decision_guide(guide))
    assert tuple(encoded) == (
        "current_context_id", "decision_types", "next_page_available", "schema_version",
        "select_action_example", "truncated", "visible_actions", "visible_actions_total",
    )
    example = encoded["select_action_example"]
    assert example["objective_operation"] == {"kind": "none"}
    assert example["decision"]["action_id"] == scenario.context.actions.options[0].action_id


def test_v2_is_explicit_and_contains_symmetric_seven_decision_contracts() -> None:
    guide = build_compact_decision_guide_v2(_scenario().serialized_context)
    assert grounding_profile_version(DecisionGroundingVariant.COMPACT_CONTRACT_V2) == COMPACT_CONTRACT_V2_PROFILE_VERSION
    assert guide.profile_version == "compact-contract.v2"
    assert tuple(item.decision_type for item in guide.decision_contracts) == (
        "select_action", "request_observation", "request_action_page", "ask_user",
        "propose_done", "wait", "abort",
    )
    assert all(item.required_fields and item.field_domains for item in guide.decision_contracts)


def test_v2_has_domains_but_no_concrete_first_action_answer() -> None:
    scenario = _scenario()
    guide = build_compact_decision_guide_v2(scenario.serialized_context)
    encoded = serialize_compact_decision_guide_v2(guide)
    option = scenario.context.actions.options[0]
    assert guide.action_domain.actions[0].action_id == option.action_id
    assert guide.action_domain.actions[0].visible_destination_ids == tuple(
        item.destination_id for item in option.destinations.items
    )
    assert "select_action_example" not in encoded
    assert "example" not in encoded.casefold()

    destination_case = build_destination_case(
        scenario.serialized_context, destinations=2, correct_index=1,
    )
    destination_guide = build_compact_decision_guide_v2(destination_case.serialized_context)
    assert destination_guide.action_domain.actions[0].visible_destination_ids == (
        "public-id-destination-1", "public-id-destination-2",
    )


def test_v2_projects_observation_page_completion_wait_and_abort_domains() -> None:
    guide = build_compact_decision_guide_v2(_scenario().serialized_context)
    assert guide.observation_domain.subject_ids
    assert guide.observation_domain.modalities == ("structural",)
    assert "weak" in guide.observation_domain.assurance_levels
    assert guide.paging_domain.available_filters == ("target_id", "relevance_role", "query")
    assert guide.completion_domain.criterion_ids == ("expanded",)
    assert guide.completion_domain.evidence_refs
    assert guide.completion_domain.runtime_revalidation
    assert guide.completion_domain.summary_max_chars == 1_024
    assert guide.budget_domain.remaining_wait_ms == 120_000
    assert guide.budget_domain.per_decision_max_wait_ms == 60_000
    abort = next(item for item in guide.decision_contracts if item.decision_type == "abort")
    assert "internal" not in abort.field_domains["category"]

    page = next(
        item for item in build_seven_decision_cases(_scenario().serialized_context)
        if item.expected_variant == "request_action_page"
    )
    page_guide = build_compact_decision_guide_v2(page.serialized_context)
    assert page_guide.paging_domain.has_more
    assert page_guide.paging_domain.next_cursor == "cursor:next"


def test_v2_fits_sixteen_actions_is_deterministic_and_truthful() -> None:
    scenario = _scenario()
    case = build_multi_action_case(scenario.serialized_context, action_count=16, correct_index=7)
    guide = build_compact_decision_guide_v2(case.serialized_context)
    encoded = serialize_compact_decision_guide_v2(guide)
    assert len(guide.action_domain.actions) == 16
    assert not guide.truncated
    assert guide.guide_bytes == len(encoded.encode()) <= MAX_COMPACT_GUIDE_BYTES
    assert encoded == serialize_compact_decision_guide_v2(
        build_compact_decision_guide_v2(case.serialized_context)
    )


def test_v2_does_not_project_private_or_oracle_fields() -> None:
    context = json.loads(_scenario().serialized_context)
    context["selector"] = "#private"
    context["actions"]["options"][0]["href"] = "/private/path"
    context["expected_payload"] = {"action_id": "oracle-answer"}
    encoded = serialize_compact_decision_guide_v2(
        build_compact_decision_guide_v2(json.dumps(context))
    ).casefold()
    for forbidden in (
        "selector", "coordinate", "bbox", "point", "href", "method", "backend",
        "executor", "binding", "observation_id", "credential", "authorization",
        "/private/path", "oracle-answer", "expected_payload", "raw_response",
    ):
        assert forbidden not in encoded


def test_v2_selection_has_no_model_or_provider_name_branch() -> None:
    source = inspect.getsource(model_policy_from_environment)
    assert "model_id" not in source and "provider_id" not in source
