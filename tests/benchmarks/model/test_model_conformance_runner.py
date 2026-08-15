import asyncio
import json
from dataclasses import dataclass

from affordance_runtime.benchmarks.model_conformance.contracts import ModelConformanceStage
from affordance_runtime.benchmarks.model_conformance.levels import Level0Payload
from affordance_runtime.benchmarks.model_conformance.runner import run_structured_attempt
from affordance_runtime.model.providers.port import ModelCallRecord


@dataclass
class ScriptedPort:
    payload: object
    calls: int = 0
    provider: str = "fixture"
    model: str = "scripted"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = None

    async def generate_structured(self, messages, output_schema, config):
        self.calls += 1
        self.last_call = ModelCallRecord(
            provider=self.provider, model=self.model, endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version, schema_name=output_schema.__name__,
            schema_version="test", latency_ms=1, prompt_tokens=3, completion_tokens=2,
            total_tokens=5,
        )
        return output_schema.model_validate(self.payload)


def test_one_attempt_makes_exactly_one_provider_call() -> None:
    port = ScriptedPort({"type": "select_action"})
    attempt = asyncio.run(run_structured_attempt(
        port, Level0Payload, ("Return JSON", "{}"), level="0",
        grounding_variant="format-only", attempt_number=1,
    ))
    assert port.calls == 1
    assert attempt.stage == ModelConformanceStage.SUCCESS
    assert attempt.prompt_tokens == 3
    assert attempt.output_sha256.startswith("sha256:")


def test_attempt_contract_has_no_raw_payload_storage() -> None:
    assert "raw" not in json.dumps(tuple(run_structured_attempt.__annotations__)).casefold()
