import asyncio
from dataclasses import dataclass, field

import pytest
from test_production_task_evaluator import _semantic_task, _world

from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.semantic_contracts import SemanticCriterionProposal
from affordance_runtime.model_boundary import ModelFailure
from affordance_runtime.model_boundary.evaluator_views import build_semantic_judge_request
from affordance_runtime.model_evaluator.bridge import ModelPortSemanticCriterionJudge
from affordance_runtime.model_evaluator.spec import SemanticProposalResponse
from affordance_runtime.model_policy.strict_json import StrictJsonError
from affordance_runtime.model_port import FallbackModelPort, ModelCallRecord, ModelConfig, ModelMessage


@dataclass
class RecordingPort:
    payload: object
    provider: str = "fixture"
    model: str = "semantic-model"
    endpoint_class: str = "local"
    last_call: ModelCallRecord | None = None
    calls: int = 0
    messages: list[ModelMessage] = field(default_factory=list)
    schema: object = None

    async def generate_structured(self, messages, output_schema, config):
        self.calls += 1
        self.messages = list(messages)
        self.schema = output_schema
        self.last_call = ModelCallRecord(
            provider=self.provider, model=self.model, endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version, schema_name=output_schema.__name__,
            schema_version="semantic-criterion-proposal.v1", latency_ms=4,
        )
        return output_schema.model_validate(self.payload)


def test_semantic_judge_bridge_uses_existing_model_port_once_and_cannot_return_task_status() -> None:
    world = _world("clear conclusion", subject="report:1", predicate="content")
    payload = {
        "proposals": [{"criterion_id": "quality", "status": "satisfied", "evidence_refs": ["fact:current"], "reason": "meets rubric"}]
    }
    port = RecordingPort(payload)
    judge = ModelPortSemanticCriterionJudge(
        port, ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0), call_timeout_s=2
    )

    request = build_semantic_judge_request(
        _semantic_task(), normalize_task_criteria(_semantic_task()), world,
        WorldEvidenceIndex.from_observation(world),
    )
    outcome = asyncio.run(judge.evaluate(request))

    assert port.calls == 1 and port.schema is SemanticProposalResponse
    assert [message.role for message in port.messages] == ["system", "user"]
    assert "task complete" in port.messages[0].content.casefold()
    assert "task_status" not in str(SemanticProposalResponse.model_json_schema())
    assert isinstance(outcome, tuple) and isinstance(outcome[0], SemanticCriterionProposal)


def test_semantic_judge_bridge_rejects_retry_fallback_and_bad_deadline() -> None:
    port = RecordingPort({"proposals": []})
    with pytest.raises(ValueError, match="zero retry"):
        ModelPortSemanticCriterionJudge(port, ModelConfig(rate_limit_retries=1, transient_retries=0))
    with pytest.raises(ValueError, match="fallback"):
        ModelPortSemanticCriterionJudge(FallbackModelPort((port,)), ModelConfig(rate_limit_retries=0, transient_retries=0))
    with pytest.raises(ValueError, match="timeout"):
        ModelPortSemanticCriterionJudge(port, ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0), call_timeout_s=2)


def test_semantic_judge_malformed_payload_is_typed_failure() -> None:
    world = _world("text", subject="report:1", predicate="content")
    judge = ModelPortSemanticCriterionJudge(
        RecordingPort({"proposals": [{"criterion_id": "quality", "status": "complete"}]}),
        ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0),
        call_timeout_s=2,
    )
    request = build_semantic_judge_request(
        _semantic_task(), normalize_task_criteria(_semantic_task()), world,
        WorldEvidenceIndex.from_observation(world),
    )
    outcome = asyncio.run(judge.evaluate(request))
    assert isinstance(outcome, ModelFailure)


@pytest.mark.parametrize(
    "raw",
    (
        '{"proposals":[],"proposals":[]}',
        '{"proposals":[{"criterion_id":"quality","status":"satisfied","evidence_refs":[],"reason":NaN}]}',
    ),
)
def test_semantic_response_reuses_hostile_json_boundary(raw: str) -> None:
    with pytest.raises(StrictJsonError):
        SemanticProposalResponse.model_validate_json(raw)
