import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.benchmarks.model_conformance.contracts import (
    DestinationFailureShape,
    ModelConformanceStage,
)
from affordance_runtime.benchmarks.model_conformance.decision_matrix import (
    DECISION_VARIANTS,
    build_destination_case,
    build_multi_action_case,
    build_seven_decision_cases,
    decision_matches_expectation,
)
from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.benchmarks.model_conformance.stages import attribute_decision_payload
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.grounding import (
    MAX_COMPACT_GUIDE_BYTES,
    DecisionGroundingVariant,
    build_compact_decision_guide,
    serialize_compact_decision_guide,
)
from affordance_runtime.model.policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model.policy.spec import SCHEMA_VERSION, decision_response_schema
from affordance_runtime.model.providers.port import ModelConfig


@dataclass
class ScriptedPort:
    payload: object
    provider: str = "fixture"
    model: str = "matrix"
    endpoint_class: str = "local"
    last_call: object = None
    calls: int = 0

    async def generate_structured(self, messages, output_schema, config):
        del messages, config
        self.calls += 1
        # A provider boundary returns JSON arrays, not Python tuples used by the
        # immutable decision-matrix fixture.
        return output_schema.model_validate(_as_json_value(self.payload))


def _as_json_value(value):
    if isinstance(value, Mapping):
        return {key: _as_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_as_json_value(item) for item in value]
    return value


def _run(case):
    port = ScriptedPort(case.expected_payload)
    adapter = ModelPortDecisionAdapter(
        port,
        ModelConfig(rate_limit_retries=0, transient_retries=0),
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT,
    )
    request = ModelDecisionRequest(
        f"request:{case.case_id}", case.serialized_context, SCHEMA_VERSION,
        "instructions", decision_response_schema(),
    )
    response = asyncio.run(adapter.generate(request))
    return port, response.decision


def test_all_seven_decisions_cross_production_bridge_schema_and_parser() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    cases = build_seven_decision_cases(scenario.serialized_context)
    assert tuple(case.expected_variant for case in cases) == DECISION_VARIANTS
    expected_types = {
        "select_action": "SelectAction",
        "request_observation": "RequestObservation",
        "request_action_page": "RequestActionPage",
        "ask_user": "AskUser",
        "propose_done": "ProposeDone",
        "wait": "Wait",
        "abort": "Abort",
    }
    for case in cases:
        port, decision = _run(case)
        assert port.calls == 1
        assert type(decision).__name__ == expected_types[case.expected_variant]
        assert decision_matches_expectation(decision, case.expectation)


def test_seven_decision_expectations_validate_complete_payload_domains() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    cases = {case.expected_variant: case for case in build_seven_decision_cases(scenario.serialized_context)}
    page = cases["request_action_page"]
    assert page.expected_payload["cursor"] == "cursor:next"
    assert page.expectation.exact_fields["cursor"] == "cursor:next"

    mutations = {
        "request_observation": {"subject_id": "hidden-subject"},
        "request_action_page": {"cursor": ""},
        "ask_user": {"requested_fields": ["invented"]},
        "propose_done": {"evidence_refs": ["evidence:hidden"]},
        "wait": {"max_wait_ms": 120_001},
        "abort": {"category": "internal"},
    }
    for variant, changed in mutations.items():
        case = cases[variant]
        payload = dict(case.expected_payload)
        payload.update(changed)
        try:
            decision = type(_run(case)[1])(**{
                key: tuple(value) if key in {"requested_fields", "claimed_criteria", "evidence_refs", "unresolved_items"} else value
                for key, value in payload.items() if key != "type"
            })
        except ValueError:
            continue
        assert not decision_matches_expectation(decision, case.expectation)


def test_compact_multi_action_guide_preserves_order_without_oracle_leakage() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    for count, correct in ((8, 7), (16, 7), (8, 4)):
        case = build_multi_action_case(
            scenario.serialized_context,
            action_count=count,
            correct_index=correct,
        )
        guide = build_compact_decision_guide(case.serialized_context)
        encoded = serialize_compact_decision_guide(guide)
        assert len(guide.visible_actions) == count
        assert [item.action_id for item in guide.visible_actions] == [
            f"public-action-{index + 1}" for index in range(count)
        ]
        assert len(encoded.encode()) <= MAX_COMPACT_GUIDE_BYTES
        assert "expected_payload" not in encoded
        port, decision = _run(case)
        assert port.calls == 1
        assert decision.action_id == f"public-action-{correct + 1}"


def test_compact_destination_matrix_is_truthful_and_parser_does_not_repair() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    cases = (
        build_destination_case(scenario.serialized_context, destinations=0),
        build_destination_case(scenario.serialized_context, destinations=1),
        build_destination_case(scenario.serialized_context, destinations=2, correct_index=1),
        build_destination_case(
            scenario.serialized_context, destinations=2, correct_index=1, similar_ids=True,
        ),
    )
    for case in cases:
        guide = build_compact_decision_guide(case.serialized_context)
        option = guide.visible_actions[0]
        expected = tuple(
            item["destination_id"]
            for item in json.loads(case.serialized_context)["actions"]["options"][0]["destinations"]["items"]
        )
        assert option.visible_destination_ids == expected
        _, decision = _run(case)
        assert decision.destination_id == case.expected_payload["destination_id"]


def test_compact_matrix_contains_no_private_route_or_benchmark_oracle() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    case = build_multi_action_case(scenario.serialized_context, action_count=8, correct_index=7)
    encoded = serialize_compact_decision_guide(build_compact_decision_guide(case.serialized_context))
    for forbidden in (
        "selector", "coordinate", "bbox", "href", "backend", "credential",
        "expected_payload", "correct_action_index", "reference_trajectory",
    ):
        assert forbidden not in encoded.casefold()


def test_cross_action_destination_remains_rejected_without_repair() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    case = build_multi_action_case(scenario.serialized_context, action_count=8, correct_index=7)
    context = json.loads(case.serialized_context)
    first, second = context["actions"]["options"][:2]
    first["destination_required"] = True
    first["destinations"] = {
        "items": [{"destination_id": "destination:first", "label": "First"}],
        "total_count": 1,
        "truncated": False,
    }
    second["destination_required"] = True
    second["destinations"] = {
        "items": [{"destination_id": "destination:second", "label": "Second"}],
        "total_count": 1,
        "truncated": False,
    }
    payload = json.dumps({
        "type": "select_action",
        "context_id": context["context_id"],
        "action_id": first["action_id"],
        "parameters": {},
        "destination_id": "destination:second",
    })
    attributed = attribute_decision_payload(
        payload,
        context["context_id"],
        (first["action_id"], second["action_id"]),
        {
            first["action_id"]: ("destination:first",),
            second["action_id"]: ("destination:second",),
        },
    )
    assert attributed.stage is ModelConformanceStage.DESTINATION_ID
    assert attributed.destination_failure_shape is DestinationFailureShape.BELONGS_TO_OTHER_ACTION
