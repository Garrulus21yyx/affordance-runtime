import asyncio
from dataclasses import dataclass
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.intent_compiler import LLMIntentCompiler, LLMMinimalIntentProposal
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.task_intake import UserRequest
from affordance_runtime.task_spec_authority import MinimalIntentProposal

T = TypeVar("T", bound=BaseModel)


@dataclass
class ProposalModel:
    provider: str = "fixed"
    model: str = "proposal"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        assert output_schema is LLMMinimalIntentProposal
        payload = __import__("json").loads(messages[-1].content)
        anchor_id = payload["source_envelope"]["anchors"][0]["anchor_id"]
        return output_schema.model_validate(
            {
                "objective": "Open settings",
                "requested_effects": [
                    {
                        "operation_class": "navigation",
                        "target": "settings",
                        "source_ref": anchor_id,
                    }
                ],
                "success": {
                    "expression_id": "success:settings",
                    "operator": "criterion",
                    "criterion_id": "criterion:settings-visible",
                    "requirement_refs": ["requirement:effect:1"],
                },
            }
        )


def test_compiler_returns_only_untrusted_minimal_proposal() -> None:
    request = UserRequest(request_id="proposal-request", raw_text="Open settings")
    envelope = SourceEnvelopeBuilder().build(request)
    compiler = LLMIntentCompiler(ProposalModel())

    proposal = asyncio.run(compiler.propose(request, envelope))

    assert isinstance(proposal, MinimalIntentProposal)
    assert not hasattr(proposal, "task_spec")
    assert not hasattr(compiler, "compile")
    assert "candidate_source_claims" not in LLMMinimalIntentProposal.model_json_schema()["properties"]
    assert "candidate_obligations" not in LLMMinimalIntentProposal.model_json_schema()["properties"]
