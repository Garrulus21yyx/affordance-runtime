import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from affordance_runtime.model.context import ModelFailure, ModelFailureKind
from affordance_runtime.model.policy.contracts import ModelDecisionRequest
from affordance_runtime.model.policy.factory import model_policy_from_environment
from affordance_runtime.model.policy.grounding import (
    COMPACT_CONTRACT_PROFILE_VERSION,
    COMPACT_CONTRACT_V2_PROFILE_VERSION,
    FORMAT_ONLY_PROFILE_VERSION,
    DecisionGroundingVariant,
)
from affordance_runtime.model.policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model.policy.schema_identity import decision_schema_digest
from affordance_runtime.model.policy.spec import SCHEMA_VERSION, AgentDecisionPayload, decision_response_schema
from affordance_runtime.model.providers.port import ModelConfig


@dataclass
class Port:
    provider: str = "fixture"
    model: str = "model"
    endpoint_class: str = "local"
    last_call: object = None
    calls: int = 0
    messages: list[object] = field(default_factory=list)

    async def generate_structured(self, messages, output_schema, config):
        del config
        self.calls += 1
        self.messages = list(messages)
        value = json.loads(messages[1].content)
        context = value.get("agent_context", value)
        return output_schema.model_validate(
            {
                "type": "abort",
                "context_id": context["context_id"],
                "reason": "fixture",
                "category": "policy",
            }
        )


def _factory(monkeypatch, environment, *, grounding_variant=None):
    port = Port()
    monkeypatch.setattr(
        "affordance_runtime.model.policy.factory.model_port_from_environment",
        lambda env: port,
    )
    policy = model_policy_from_environment(
        environment,
        call_timeout_s=20,
        grounding_variant=grounding_variant,
    )
    return policy, port


def test_factory_grounding_precedence_and_default(monkeypatch) -> None:
    policy, _ = _factory(monkeypatch, {"LLM_ACTIVE_PROFILE": "local"})
    assert policy.port.grounding_variant is DecisionGroundingVariant.FORMAT_ONLY
    assert policy.port.grounding_profile_version == FORMAT_ONLY_PROFILE_VERSION

    policy, _ = _factory(
        monkeypatch,
        {"LLM_ACTIVE_PROFILE": "local", "LLM_DECISION_GROUNDING": "compact-contract"},
    )
    assert policy.port.grounding_variant is DecisionGroundingVariant.COMPACT_CONTRACT
    assert policy.port.grounding_profile_version == COMPACT_CONTRACT_PROFILE_VERSION

    policy, _ = _factory(
        monkeypatch,
        {"LLM_ACTIVE_PROFILE": "local", "LLM_DECISION_GROUNDING": "format-only"},
        grounding_variant="compact-contract",
    )
    assert policy.port.grounding_variant is DecisionGroundingVariant.COMPACT_CONTRACT


def test_factory_compact_v2_fails_closed_without_experimental_gate(monkeypatch) -> None:
    with pytest.raises(ValueError, match="experimental.*not admitted"):
        _factory(
            monkeypatch,
            {"LLM_ACTIVE_PROFILE": "local", "LLM_DECISION_GROUNDING": "compact-contract-v2"},
        )


def test_factory_compact_v2_requires_explicit_experimental_gate(monkeypatch) -> None:
    policy, _ = _factory(
        monkeypatch,
        {
            "LLM_ACTIVE_PROFILE": "local",
            "LLM_DECISION_GROUNDING": "compact-contract-v2",
            "LLM_ENABLE_EXPERIMENTAL_GROUNDING": "1",
        },
    )
    assert policy.port.grounding_variant is DecisionGroundingVariant.COMPACT_CONTRACT_V2
    assert policy.port.grounding_profile_version == COMPACT_CONTRACT_V2_PROFILE_VERSION


def test_factory_explicit_argument_cannot_bypass_compact_v2_gate(monkeypatch) -> None:
    with pytest.raises(ValueError, match="experimental.*not admitted"):
        _factory(
            monkeypatch,
            {"LLM_ACTIVE_PROFILE": "local"},
            grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2,
        )


def test_factory_rejects_unknown_grounding(monkeypatch) -> None:
    with pytest.raises(ValueError, match="grounding"):
        _factory(
            monkeypatch,
            {"LLM_ACTIVE_PROFILE": "local", "LLM_DECISION_GROUNDING": "model-magic"},
        )


def test_schema_digest_is_deterministic_namespaced_and_constraint_sensitive(monkeypatch) -> None:
    first = decision_schema_digest()
    assert first == decision_schema_digest()
    assert first.startswith("sha256:") and len(first) == 71
    schema = decision_response_schema()
    schema["$defs"]["ProposeDonePayload"]["properties"]["result_summary"]["maxLength"] = 1_023
    monkeypatch.setattr(
        "affordance_runtime.model.policy.spec.decision_response_schema",
        lambda: schema,
    )
    assert decision_schema_digest() != first


def test_compact_build_failure_is_internal_and_zero_call(monkeypatch) -> None:
    port = Port()
    adapter = ModelPortDecisionAdapter(
        port,
        ModelConfig(rate_limit_retries=0, transient_retries=0),
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT,
    )
    monkeypatch.setattr(
        "affordance_runtime.model.policy.model_port_bridge.build_compact_decision_guide",
        lambda value: (_ for _ in ()).throw(ValueError("private context")),
    )
    request = ModelDecisionRequest(
        "request:test",
        '{"context_id":"context:1","actions":{"options":[]}}',
        SCHEMA_VERSION,
        "instructions",
        decision_response_schema(),
    )
    result = asyncio.run(adapter.generate(request))
    assert isinstance(result, ModelFailure)
    assert result.kind is ModelFailureKind.INTERNAL_ERROR
    assert "private context" not in result.reason
    assert port.calls == 0


def test_compact_v2_build_failure_is_internal_and_zero_call(monkeypatch) -> None:
    port = Port()
    adapter = ModelPortDecisionAdapter(
        port,
        ModelConfig(rate_limit_retries=0, transient_retries=0),
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2,
    )
    monkeypatch.setattr(
        "affordance_runtime.model.policy.model_port_bridge.build_compact_decision_guide_v2",
        lambda value: (_ for _ in ()).throw(ValueError("private context")),
    )
    request = ModelDecisionRequest(
        "request:test",
        '{"context_id":"context:1","actions":{"options":[]}}',
        SCHEMA_VERSION,
        "instructions",
        decision_response_schema(),
    )
    result = asyncio.run(adapter.generate(request))
    assert isinstance(result, ModelFailure)
    assert result.kind is ModelFailureKind.INTERNAL_ERROR
    assert port.calls == 0


def test_provider_schema_and_runtime_keep_summary_limit() -> None:
    summary = decision_response_schema()["$defs"]["ProposeDonePayload"]["properties"]["result_summary"]
    assert summary["maxLength"] == 1_024
    with pytest.raises(Exception):
        AgentDecisionPayload.model_validate(
            {
                "type": "propose_done",
                "context_id": "context:1",
                "claimed_criteria": [],
                "evidence_refs": [],
                "result_summary": "x" * 1_025,
                "unresolved_items": [],
            }
        )


def test_production_policy_does_not_import_two_stage_or_branch_on_identity() -> None:
    package = Path("src/affordance_runtime/model/policy")
    source = "\n".join(path.read_text() for path in package.glob("*.py"))
    assert "benchmarks.model_conformance.two_stage" not in source
    factory_source = (package / "factory.py").read_text()
    assert "LLM_MODEL" not in factory_source
    assert "LLM_PROVIDER" not in factory_source
    assert "port.model" not in factory_source
    assert "port.provider" not in factory_source
