import asyncio
import json
from dataclasses import dataclass

from affordance_runtime.benchmarks.model_conformance.contracts import ModelProfileIdentity
from affordance_runtime.benchmarks.model_conformance.destination_ladder import (
    build_destination_case,
)
from affordance_runtime.benchmarks.model_conformance.runner import run_profile
from affordance_runtime.benchmarks.model_conformance.scenario import build_live_dom_scenario
from affordance_runtime.model_port import ModelCallRecord


def _identity() -> ModelProfileIdentity:
    return ModelProfileIdentity(
        "fixture", "scripted", "local", "fixture", "1", "digest", "fixture",
        "small", "none", "p5-m1.1", "agent-decision.v1", "default-64k",
    )


def test_destination_ladder_increases_only_public_grounding_difficulty() -> None:
    scenario = asyncio.run(build_live_dom_scenario())
    cases = {level: build_destination_case(level, scenario) for level in ("D0", "D1", "D2", "D3", "D4")}

    assert cases["D0"].visible_destinations == {cases["D0"].action_id: ("",)}
    assert len(cases["D1"].visible_destinations[cases["D1"].action_id]) == 1
    assert len(cases["D2"].visible_destinations[cases["D2"].action_id]) == 2
    assert json.loads(cases["D3"].serialized_context)["actions"] == json.loads(
        scenario.serialized_context
    )["actions"]
    assert cases["D4"].serialized_context == scenario.serialized_context
    for case in cases.values():
        assert "selector" not in case.serialized_context
        assert "href" not in case.serialized_context
        assert "backend" not in case.serialized_context


@dataclass
class CopyingPort:
    provider: str = "fixture"
    model: str = "scripted"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = None

    async def generate_structured(self, messages, output_schema, config):
        context = json.loads(messages[1].content)
        action = context["actions"]["options"][0]
        items = action["destinations"]["items"]
        destination = items[0]["destination_id"] if action["destination_required"] else ""
        self.last_call = ModelCallRecord(
            provider="fixture", model="scripted", endpoint_class="local",
            prompt_version=config.prompt_version, schema_name=output_schema.__name__,
            schema_version="test", latency_ms=1, prompt_tokens=1,
            completion_tokens=1, total_tokens=2,
        )
        return output_schema.model_validate({
            "type": "select_action", "context_id": context["context_id"],
            "action_id": action["action_id"], "parameters": {},
            "destination_id": destination,
        })


@dataclass
class DonePort(CopyingPort):
    async def generate_structured(self, messages, output_schema, config):
        context = json.loads(messages[1].content)
        self.last_call = ModelCallRecord(
            provider="fixture", model="scripted", endpoint_class="local",
            prompt_version=config.prompt_version, schema_name=output_schema.__name__,
            schema_version="test", latency_ms=1, prompt_tokens=1,
            completion_tokens=1, total_tokens=2,
        )
        return output_schema.model_validate({
            "type": "propose_done",
            "context_id": context["context_id"],
            "claimed_criteria": [],
            "evidence_refs": [],
            "result_summary": "done",
            "unresolved_items": [],
        })


def test_destination_ladder_runs_with_full_union_and_reports_diagnostic_pass(tmp_path) -> None:
    result = asyncio.run(run_profile(
        _identity(), CopyingPort, levels=("D0", "D1", "D2", "D3", "D4"),
        grounding_variants=("format-only",), repetitions=1, output_dir=tmp_path,
    ))

    assert result.passed_levels == ("D0", "D1", "D2", "D3", "D4")
    assert result.classification == "diagnostic_pass"
    assert len({item.schema_bytes for item in result.attempts}) == 1
    assert result.attempts[0].schema_bytes > 0
    assert len(result.cell_summaries) == 5
    assert all(item.success_count == 1 for item in result.cell_summaries)
    assert result.cell_summaries[0].decision_variant_counts == (("select_action", 1),)
    assert result.attempts[-1].salience_metrics.selected_action_id_occurrences > 0
    assert result.attempts[-1].salience_metrics.selected_target_id_occurrences > 0
    assert result.attempts[-1].salience_metrics.actions_block_distance_from_end_bytes is not None


def test_destination_ladder_does_not_count_another_union_variant_as_success(tmp_path) -> None:
    result = asyncio.run(run_profile(
        _identity(), DonePort, levels=("D4",), grounding_variants=("format-only",),
        repetitions=1, output_dir=tmp_path,
    ))

    attempt = result.attempts[0]
    assert not attempt.success
    assert attempt.stage.value == "decision_variant"
    assert attempt.failure_kind == "unexpected_decision_variant"
    assert attempt.decision_variant == "propose_done"
