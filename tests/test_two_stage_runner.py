import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.benchmarks.model_conformance.two_stage.cases import (
    build_critical_cases,
    build_recurrent_cases,
)
from affordance_runtime.benchmarks.model_conformance.two_stage.contracts import (
    PacingConfiguration,
    TwoStageRunMode,
)
from affordance_runtime.benchmarks.model_conformance.two_stage.runner import run_two_stage_matrix
from affordance_runtime.model_port import ModelCallRecord, StructuredOutputError


@dataclass
class SemanticFollowingPort:
    provider: str = "fixture"
    model: str = "semantic-following"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = None

    async def generate_structured(self, messages, output_schema, config):
        context = json.loads(messages[1].content)["agent_context"]
        schema = output_schema.model_json_schema()
        if set(schema["properties"]) == {"context_id", "decision_type"}:
            payload = {"context_id": context["context_id"], "decision_type": _kind(context)}
        else:
            payload = _payload(context)
        self.last_call = ModelCallRecord(
            provider=self.provider, model=self.model, endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version, schema_name=output_schema.__name__,
            schema_version="fixture", latency_ms=1, prompt_tokens=10,
            completion_tokens=5, total_tokens=15,
        )
        return output_schema.model_validate_json(json.dumps(payload))


def _kind(context):
    task = context["task"]["instruction"]
    if "fresh structural" in task:
        return "request_observation"
    if "next action page" in task:
        return "request_action_page"
    if "required value is missing" in task:
        return "ask_user"
    if context["progress"]["validated_task_status"] == "complete":
        return "propose_done"
    if "Wait briefly" in task:
        return "wait"
    if "explicitly unsupported" in task:
        return "abort"
    return "select_action"


def _payload(context):
    kind = _kind(context)
    context_id = context["context_id"]
    if kind == "request_observation":
        capability = context["world"]["observation_capabilities"][0]
        return {"type": kind, "context_id": context_id, "subject_id": "dom_button_1",
                "modality": capability["modality"], "required_assurance": capability["assurance"],
                "reason": "refresh current evidence"}
    if kind == "request_action_page":
        actions = context["actions"]
        return {"type": kind, "context_id": context_id, "query": actions["active_query"],
                "target_id": actions["active_target_filter"],
                "relevance_role": actions["active_relevance_filter"], "cursor": actions["next_cursor"]}
    if kind == "ask_user":
        return {"type": kind, "context_id": context_id, "question": "Which required value should be used?",
                "requested_fields": ["value"]}
    if kind == "propose_done":
        criteria = [item["criterion_id"] for item in context["task"]["success_criteria"]["items"]]
        evidence = [context["world"]["facts"]["items"][0]["fact_ref"]]
        return {"type": kind, "context_id": context_id, "claimed_criteria": criteria,
                "evidence_refs": evidence, "result_summary": "Current evidence supports completion.",
                "unresolved_items": []}
    if kind == "wait":
        return {"type": kind, "context_id": context_id, "reason": "allow the asynchronous state to settle",
                "max_wait_ms": 10}
    if kind == "abort":
        return {"type": kind, "context_id": context_id, "reason": "the requested operation is unsupported",
                "category": "unsupported"}
    options = context["actions"]["options"]
    selected = next((item for item in options if "Matches" in item["description"]), None)
    selected = selected or next((item for item in options if item["relevance_role"] == "direct"), options[0])
    destinations = selected["destinations"]["items"]
    requested = context["task"]["instruction"]
    destination = destinations[-1]["destination_id"] if "Destination 2" in requested else (
        destinations[0]["destination_id"] if destinations else ""
    )
    return {"type": kind, "context_id": context_id, "action_id": selected["action_id"],
            "parameters": {}, "destination_id": destination}


def _case_sets():
    scenario = asyncio.run(build_live_dom_scenario())
    return build_recurrent_cases(scenario.serialized_context), build_critical_cases(scenario.serialized_context)


def test_scripted_routing_payload_and_end_to_end_close_seven_variants(tmp_path: Path) -> None:
    recurrent, _ = _case_sets()
    for mode in TwoStageRunMode:
        result = asyncio.run(run_two_stage_matrix(
            run_id=f"run:{mode.value}", mode=mode, port_factory=SemanticFollowingPort,
            cases=recurrent, repetitions=1, output_dir=tmp_path / mode.value,
            pacing=PacingConfiguration(),
        ))
        assert result.success_count == 7
        assert result.runtime_control_success_count == 7
        assert result.retry_count == result.fallback_count == 0


def test_scripted_end_to_end_closes_all_critical_cases(tmp_path: Path) -> None:
    _, critical = _case_sets()
    result = asyncio.run(run_two_stage_matrix(
        run_id="run:critical", mode=TwoStageRunMode.END_TO_END,
        port_factory=SemanticFollowingPort, cases=critical, repetitions=1,
        output_dir=tmp_path, pacing=PacingConfiguration(),
    ))
    assert result.success_count == 8
    assert result.provider_calls == 16
    encoded = (tmp_path / "end_to_end.json").read_text().casefold()
    encoded += (tmp_path / "two-stage-progress.json").read_text().casefold()
    for forbidden in ("raw_response", "raw_prompt", "selector", "credential"):
        assert forbidden not in encoded


@dataclass
class WrongRoutePort(SemanticFollowingPort):
    async def generate_structured(self, messages, output_schema, config):
        context = json.loads(messages[1].content)["agent_context"]
        return output_schema.model_validate_json(json.dumps({
            "context_id": context["context_id"], "decision_type": "abort",
        }))


@dataclass
class PayloadFailurePort(SemanticFollowingPort):
    async def generate_structured(self, messages, output_schema, config):
        schema = output_schema.model_json_schema()
        if set(schema["properties"]) == {"context_id", "decision_type"}:
            return await super().generate_structured(messages, output_schema, config)
        raise StructuredOutputError("fixture payload failure")


def test_routing_failure_skips_payload_and_payload_failure_skips_runtime(tmp_path: Path) -> None:
    recurrent, _ = _case_sets()
    select = (recurrent[0],)
    routed = asyncio.run(run_two_stage_matrix(
        run_id="run:wrong-route", mode=TwoStageRunMode.END_TO_END,
        port_factory=WrongRoutePort, cases=select, repetitions=1,
        output_dir=tmp_path / "route",
    ))
    assert routed.attempts[0].failure_category == "routing_wrong_variant"
    assert routed.attempts[0].routing_provider_attempts == 1
    assert routed.attempts[0].payload_provider_attempts == 0
    payload = asyncio.run(run_two_stage_matrix(
        run_id="run:payload-fail", mode=TwoStageRunMode.END_TO_END,
        port_factory=PayloadFailurePort, cases=select, repetitions=1,
        output_dir=tmp_path / "payload",
    ))
    assert payload.attempts[0].failure_category == "payload_structured_output"
    assert payload.attempts[0].provider_calls == 2
    assert payload.attempts[0].runtime_correct is False
