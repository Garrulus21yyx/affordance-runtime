import asyncio

import pytest

from affordance_runtime.model_boundary.budgets import ContextProjectionBudget
from affordance_runtime.model_boundary.world_projection import project_model_world
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model_policy.provider_orchestrator import ProviderCallPolicy
from affordance_runtime.model_policy.requirement_proposer import (
    ModelRequirementHypothesisProposer,
    RequirementHypothesisBatchPayload,
)
from affordance_runtime.model_port import (
    ModelConfig,
    ModelImageURLPart,
    ProviderFailureKind,
    ProviderModelError,
    StructuredOutputError,
)
from affordance_runtime.task import (
    HypothesisProposalMode,
    HypothesisRejectionCode,
    HypothesisSetCompleteness,
    RequirementHypothesisFailure,
    RequirementHypothesisProposal,
    RequirementHypothesisProposalBatch,
    TaskGoal,
)
from affordance_runtime.task.frontier_contracts import LiteralExpected, TargetFieldEquals
from affordance_runtime.world import (
    ActionSpace,
    CoverageState,
    ObservationMedia,
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldObservation,
)


class _Port:
    provider = "fixture"
    model = "fixture"
    endpoint_class = "local"
    last_call = None
    supports_multimodal = True

    def __init__(self, payload) -> None:
        self.payload = payload
        self.messages = ()

    async def generate_structured(self, messages, output_schema, config):
        del config
        self.messages = tuple(messages)
        assert output_schema is RequirementHypothesisBatchPayload
        return output_schema.model_validate(self.payload)


def _world(*, screenshot: bool = False) -> WorldObservation:
    target = SemanticTarget("entity:name", "textbox", "Name", {"value": ""})
    media = (ObservationMedia("screenshot", "screenshot", "image/png", b"not-a-real-png"),) if screenshot else ()
    source = SurfaceObservation(
        "observation:1",
        "dom",
        "revision:1",
        ObservationSourceProfile.dom(),
        targets=(target,),
        media=media,
    )
    return WorldObservation(
        "observation:1",
        (target,),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )


def _payload():
    return {
        "hypotheses": [
            {
                "summary": "Set the Name field to Ada",
                "predicate": {
                    "kind": "target_field_equals",
                    "target_id": "entity:name",
                    "field_name": "value",
                    "expected": {"kind": "literal", "value": "Ada"},
                },
                "candidate_entity_ids": ["entity:name"],
            }
        ],
        "hypothesis_set_completeness": "unknown",
    }


def test_proposal_batch_is_bounded_and_completeness_cannot_be_claimed() -> None:
    proposal = RequirementHypothesisProposal(
        "Set the Name field",
        TargetFieldEquals("entity:name", "value", LiteralExpected("Ada")),
        ("entity:name",),
    )
    batch = RequirementHypothesisProposalBatch(HypothesisProposalMode.INITIAL, (proposal,))

    assert batch.completeness is HypothesisSetCompleteness.UNKNOWN
    with pytest.raises(ValueError, match="exceeds"):
        RequirementHypothesisProposalBatch(HypothesisProposalMode.INITIAL, (proposal,) * 9)
    with pytest.raises(ValueError, match="candidate"):
        RequirementHypothesisProposal(
            "too many candidates",
            proposal.predicate,
            tuple(f"entity:{index}" for index in range(9)),
        )


def test_model_proposer_receives_only_public_context_and_returns_unadmitted_proposals() -> None:
    port = _Port(_payload())
    proposer = ModelRequirementHypothesisProposer(port, ModelConfig())

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert isinstance(result, RequirementHypothesisProposalBatch)
    assert result.proposals[0].candidate_entity_ids == ("entity:name",)
    assert isinstance(result.proposals[0].predicate, TargetFieldEquals)
    assert port.messages[1].content.__class__ is str
    assert "entity:name" in port.messages[1].content
    assert "hypotheses_are_task_requirements" in port.messages[1].content


def test_model_proposer_projects_valid_items_when_a_sibling_predicate_contract_is_invalid() -> None:
    payload = _payload()
    payload["hypotheses"].insert(
        0,
        {
            "summary": "Invalid fact reference",
            "predicate": {"kind": "fact_available", "fact_ref": "entity:name"},
            "candidate_entity_ids": ["entity:name"],
        },
    )
    proposer = ModelRequirementHypothesisProposer(_Port(payload), ModelConfig())

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert isinstance(result, RequirementHypothesisProposalBatch)
    assert result.proposal_item_indices == (1,)
    assert len(result.proposals) == 1
    assert result.rejections[0].item_index == 0
    assert result.rejections[0].code is HypothesisRejectionCode.INVALID_PREDICATE_CONTRACT


def test_model_proposer_projects_valid_items_when_a_sibling_proposal_contract_is_invalid() -> None:
    payload = _payload()
    payload["hypotheses"].insert(
        0,
        {
            "summary": "   ",
            "predicate": {"kind": "target_present", "target_id": "entity:name"},
            "candidate_entity_ids": ["entity:name"],
        },
    )
    proposer = ModelRequirementHypothesisProposer(_Port(payload), ModelConfig())

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert isinstance(result, RequirementHypothesisProposalBatch)
    assert result.proposal_item_indices == (1,)
    assert result.rejections[0].item_index == 0
    assert result.rejections[0].code is HypothesisRejectionCode.INVALID_PROPOSAL_CONTRACT


def test_screenshot_profile_transports_image_without_changing_hypothesis_authority() -> None:
    port = _Port(_payload())
    proposer = ModelRequirementHypothesisProposer(
        port,
        ModelConfig(),
        DecisionPerceptionProfile.SCREENSHOT_AX,
    )

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(screenshot=True),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert not isinstance(result, RequirementHypothesisFailure)
    content = port.messages[1].content
    assert isinstance(content, tuple)
    assert sum(isinstance(item, ModelImageURLPart) for item in content) == 1


def test_incremental_proposer_receives_the_current_frozen_observation_page() -> None:
    targets = tuple(SemanticTarget(f"entity:{index}", "statictext", f"Item {index}") for index in range(65))
    source = SurfaceObservation(
        "observation:1",
        "dom",
        "revision:1",
        ObservationSourceProfile.dom(),
        targets=targets,
    )
    world = WorldObservation(
        "observation:1",
        targets,
        (),
        (),
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )
    first = project_model_world(world, ContextProjectionBudget())
    assert first.traversal is not None
    port = _Port({"hypotheses": [], "hypothesis_set_completeness": "unknown"})
    proposer = ModelRequirementHypothesisProposer(port, ModelConfig())

    asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Inspect all items"),
            world,
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.AUGMENT,
            observation_cursor=first.traversal.next_cursor,
        )
    )

    assert isinstance(port.messages[1].content, str)
    assert "entity:64" in port.messages[1].content


def test_requirement_proposer_recovers_provider_failure_without_a_gui_turn() -> None:
    class RecoveringPort(_Port):
        calls = 0

        async def generate_structured(self, messages, output_schema, config):
            self.calls += 1
            if self.calls == 1:
                raise ProviderModelError(ProviderFailureKind.RATE_LIMIT_TRANSIENT)
            return await super().generate_structured(messages, output_schema, config)

    port = RecoveringPort(_payload())
    proposer = ModelRequirementHypothesisProposer(
        port,
        ModelConfig(),
        provider_policy=ProviderCallPolicy(
            max_attempts_per_profile=2,
            backoff_s=(0.0,),
            jitter_ratio=0.0,
        ),
    )

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert isinstance(result, RequirementHypothesisProposalBatch)
    assert port.calls == 2
    assert proposer.last_attempt_count == 2


def test_requirement_proposer_repairs_one_invalid_structured_response_before_admission() -> None:
    class RepairingPort(_Port):
        calls = 0

        async def generate_structured(self, messages, output_schema, config):
            self.calls += 1
            if self.calls == 1:
                raise StructuredOutputError("invalid structured output")
            assert any(message.role == "system" and "Do not repeat" in message.content for message in messages)
            return await super().generate_structured(messages, output_schema, config)

    port = RepairingPort(_payload())
    proposer = ModelRequirementHypothesisProposer(port, ModelConfig())

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert isinstance(result, RequirementHypothesisProposalBatch)
    assert port.calls == 2
    assert proposer.last_attempt_count == 2


def test_requirement_proposer_never_installs_after_repeated_invalid_structured_output() -> None:
    class InvalidPort(_Port):
        calls = 0

        async def generate_structured(self, messages, output_schema, config):
            del messages, output_schema, config
            self.calls += 1
            raise StructuredOutputError("invalid structured output")

    port = InvalidPort(_payload())
    proposer = ModelRequirementHypothesisProposer(port, ModelConfig())

    result = asyncio.run(
        proposer.propose(
            TaskGoal("task:1", "Enter Ada in the Name field"),
            _world(),
            ActionSpace("observation:1", ()),
            mode=HypothesisProposalMode.INITIAL,
        )
    )

    assert isinstance(result, RequirementHypothesisFailure)
    assert port.calls == 2
    assert proposer.last_attempt_count == 2
