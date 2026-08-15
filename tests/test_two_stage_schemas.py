import asyncio
import json

from affordance_runtime.agent.context.failures import ModelFailure
from affordance_runtime.benchmarks.model_conformance.critical_cases import build_cross_action_destination_case
from affordance_runtime.benchmarks.model_conformance.decision_matrix import build_seven_decision_cases
from affordance_runtime.benchmarks.model_conformance.runtime_decision_matrix import replay_runtime_decision
from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.benchmarks.model_conformance.two_stage.contracts import DecisionKind
from affordance_runtime.benchmarks.model_conformance.two_stage.payload_schema import (
    BRANCH_MODELS,
    build_variant_payload_schema,
)
from affordance_runtime.benchmarks.model_conformance.two_stage.route_schema import build_route_schema
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.parser import parse_agent_decision


def _cases():
    scenario = asyncio.run(build_live_dom_scenario())
    return build_seven_decision_cases(scenario.serialized_context)


def test_route_schema_has_only_context_and_canonical_candidate_domain() -> None:
    for case in _cases():
        schema = build_route_schema(case.serialized_context)
        assert set(schema["properties"]) == {"context_id", "decision_type"}
        assert schema["additionalProperties"] is False
        assert schema["properties"]["context_id"]["const"] == json.loads(case.serialized_context)["context_id"]
        assert len(schema["properties"]["decision_type"]["enum"]) >= 3
        assert case.expected_variant in schema["properties"]["decision_type"]["enum"]


def test_payload_schema_derives_canonical_branch_and_binds_type_context() -> None:
    for case in _cases():
        kind = DecisionKind(case.expected_variant)
        schema = build_variant_payload_schema(kind, case.serialized_context)
        canonical = BRANCH_MODELS[kind].model_json_schema()
        assert set(schema["required"]) == set(canonical["required"])
        assert schema["properties"]["type"]["const"] == kind.value
        assert schema["properties"]["context_id"]["const"] == json.loads(case.serialized_context)["context_id"]


def test_page_observation_done_wait_and_abort_domains_are_exact() -> None:
    cases = {case.case_id: case for case in _cases()}
    page_context = json.loads(cases["page"].serialized_context)
    page = build_variant_payload_schema(DecisionKind.REQUEST_ACTION_PAGE, cases["page"].serialized_context)
    assert page["properties"]["cursor"]["const"] == page_context["actions"]["next_cursor"]
    observation = build_variant_payload_schema(DecisionKind.REQUEST_OBSERVATION, cases["observe"].serialized_context)
    assert observation["properties"]["modality"]["enum"] == ["structural"]
    assert observation["properties"]["required_assurance"]["enum"] == ["weak", "structural"]
    done_context = json.loads(cases["done"].serialized_context)
    done = build_variant_payload_schema(DecisionKind.PROPOSE_DONE, cases["done"].serialized_context)
    criteria = [item["criterion_id"] for item in done_context["task"]["success_criteria"]["items"]]
    assert done["properties"]["claimed_criteria"]["items"]["enum"] == criteria
    assert done["properties"]["evidence_refs"]["items"]["enum"]
    wait = build_variant_payload_schema(DecisionKind.WAIT, cases["wait"].serialized_context)
    assert wait["properties"]["max_wait_ms"] == {"type": "integer", "minimum": 1, "maximum": 60_000}
    abort = build_variant_payload_schema(DecisionKind.ABORT, cases["abort"].serialized_context)
    assert "internal" not in json.dumps(abort)


def test_dynamic_schema_never_replaces_canonical_parser_or_runtime_membership() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    case = build_cross_action_destination_case(scenario.serialized_context)
    payload = to_json_compatible(case.expected_payload)
    payload["destination_id"] = "destination:action-1"
    decision = parse_agent_decision(json.dumps(payload), json.loads(case.serialized_context)["context_id"])
    assert not isinstance(decision, ModelFailure)
    replay = asyncio.run(replay_runtime_decision(case, decision))
    assert replay.success is False
    assert replay.execution_count == 0
