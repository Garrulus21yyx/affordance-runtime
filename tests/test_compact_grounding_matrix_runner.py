import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from affordance_runtime.benchmarks.model_conformance.contracts import ModelProfileIdentity
from affordance_runtime.benchmarks.model_conformance.matrix_runner import run_decision_matrix
from affordance_runtime.model_policy.spec import SCHEMA_VERSION
from affordance_runtime.model_port import (
    ModelCallRecord,
    ProviderFailureKind,
    ProviderModelError,
)


@dataclass
class ContextFollowingPort:
    provider: str = "fixture"
    model: str = "context-following"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = None

    async def generate_structured(self, messages, output_schema, config):
        value = json.loads(messages[1].content)
        context = value["agent_context"]
        task = context["task"]["instruction"]
        context_id = context["context_id"]
        actions = context["actions"]
        payload = _payload(task, context_id, context, actions)
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name="AgentDecisionPayload",
            schema_version=SCHEMA_VERSION,
            latency_ms=1.0,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        return output_schema.model_validate(payload)


def _payload(task, context_id, context, actions):
    if "unsupported" in task:
        return {"type": "abort", "context_id": context_id, "reason": "unsupported", "category": "unsupported"}
    if "Wait briefly" in task:
        return {"type": "wait", "context_id": context_id, "reason": "settle", "max_wait_ms": 10}
    if context["progress"]["validated_task_status"] == "complete":
        return {
            "type": "propose_done", "context_id": context_id, "claimed_criteria": [],
            "evidence_refs": [], "result_summary": "complete", "unresolved_items": [],
        }
    if "missing" in task:
        return {"type": "ask_user", "context_id": context_id, "question": "Which value?", "requested_fields": ["value"]}
    if actions["has_more"] and not actions["options"]:
        return {
            "type": "request_action_page", "context_id": context_id, "query": "",
            "target_id": "", "relevance_role": "", "cursor": actions["next_cursor"],
        }
    if "fresh structural" in task:
        capability = context["world"]["observation_capabilities"][0]
        return {
            "type": "request_observation", "context_id": context_id,
            "subject_id": "dom_button_1", "modality": capability["modality"],
            "required_assurance": capability["assurance"], "reason": "refresh",
        }
    options = actions["options"]
    selected = next((item for item in options if "Matches" in item["description"]), options[0])
    destinations = selected["destinations"]["items"]
    destination = destinations[-1]["destination_id"] if "Destination 2" in task else (
        destinations[0]["destination_id"] if destinations else ""
    )
    return {
        "type": "select_action", "context_id": context_id, "action_id": selected["action_id"],
        "parameters": {}, "destination_id": destination,
    }


def test_matrix_runner_records_complete_secret_free_behavior(tmp_path: Path) -> None:
    identity = ModelProfileIdentity(
        "fixture", "model", "local", "fixture", "1", "digest", "family", "1B", "Q4",
        "p5-m1.1", "agent-decision.v1", "default-64k", "sha256:schema", 1_024,
        "compact-contract", "compact-contract.v1", "fixture",
    )
    result = asyncio.run(run_decision_matrix(
        identity, ContextFollowingPort, repetitions=1, output_dir=tmp_path,
    ))
    assert result.success_count == 15
    assert result.nonfirst_case_first_action_count == 0
    assert result.nonfirst_case_count == 4
    assert all(item.provider_attempts == 1 for item in result.attempts)
    encoded = (tmp_path / "matrix.json").read_text().casefold()
    for forbidden in ("raw_response", "selector", "credential", "destination:first"):
        assert forbidden not in encoded
    progress = json.loads((tmp_path / "matrix-progress.json").read_text())
    progress_encoded = json.dumps(progress).casefold()
    for forbidden in ("raw_response", "selector", "credential", "destination:first"):
        assert forbidden not in progress_encoded
    assert progress["complete"] is True
    assert progress["completed_attempt_count"] == 15
    assert progress["planned_attempt_count"] == 15
    assert len(progress["attempts"]) == 15
    assert not (tmp_path / "matrix-progress.json.tmp").exists()


@dataclass
class WrongVariantPort(ContextFollowingPort):
    async def generate_structured(self, messages, output_schema, config):
        del config
        context = json.loads(messages[1].content)["agent_context"]
        return output_schema.model_validate({
            "type": "abort",
            "context_id": context["context_id"],
            "reason": "wrong variant proof",
            "category": "no_progress",
        })


@dataclass
class UnavailablePort(ContextFollowingPort):
    async def generate_structured(self, messages, output_schema, config):
        del messages, output_schema, config
        raise ProviderModelError(ProviderFailureKind.PROVIDER_CAPACITY)


@dataclass
class CheckpointInspectingPort(ContextFollowingPort):
    calls: ClassVar[int] = 0
    progress_path: ClassVar[Path]
    observed_completed: ClassVar[int] = -1

    async def generate_structured(self, messages, output_schema, config):
        type(self).calls += 1
        if self.calls == 2:
            progress = json.loads(self.progress_path.read_text())
            assert progress["complete"] is False
            type(self).observed_completed = progress["completed_attempt_count"]
        return await super().generate_structured(messages, output_schema, config)


def test_matrix_runner_checkpoints_each_completed_attempt(tmp_path: Path) -> None:
    identity = ModelProfileIdentity(
        "fixture", "model", "local", "fixture", "1", "digest", "family", "1B", "Q4",
        "p5-m1.1", "agent-decision.v1", "default-64k", "sha256:schema", 1_024,
        "compact-contract", "compact-contract.v1", "fixture",
    )
    CheckpointInspectingPort.calls = 0
    CheckpointInspectingPort.observed_completed = -1
    CheckpointInspectingPort.progress_path = tmp_path / "matrix-progress.json"
    result = asyncio.run(run_decision_matrix(
        identity, CheckpointInspectingPort, repetitions=2, output_dir=tmp_path,
        case_ids=("select",),
    ))
    assert result.success_count == 2
    assert CheckpointInspectingPort.observed_completed == 1
    progress = json.loads((tmp_path / "matrix-progress.json").read_text())
    assert progress["complete"] is True
    assert progress["completed_attempt_count"] == 2
    assert progress["planned_attempt_count"] == 2
    assert len(progress["attempts"]) == 2
    assert (tmp_path / "matrix.json").exists()
    assert not (tmp_path / "matrix-progress.json.tmp").exists()


def test_wrong_variant_is_distinct_from_provider_unavailability(tmp_path: Path) -> None:
    identity = ModelProfileIdentity(
        "fixture", "model", "local", "fixture", "1", "digest", "family", "1B", "Q4",
        "p5-m1.1", "agent-decision.v1", "default-64k", "sha256:schema", 1_024,
        "compact-contract", "compact-contract.v1", "fixture",
    )
    wrong = asyncio.run(run_decision_matrix(
        identity, WrongVariantPort, repetitions=1, output_dir=tmp_path / "wrong",
        case_ids=("select",),
    ))
    unavailable = asyncio.run(run_decision_matrix(
        identity, UnavailablePort, repetitions=1, output_dir=tmp_path / "unavailable",
        case_ids=("select",),
    ))
    assert wrong.attempts[0].failure_stage == "wrong_variant"
    assert unavailable.attempts[0].failure_stage == "provider_unavailable"
