from __future__ import annotations

import pytest
from pydantic import ValidationError

from affordance_runtime.model.policy.checkpoint_reducer import validate_reduction_sources
from affordance_runtime.model.policy.progress_checkpoint import (
    MAX_PROGRESS_CHECKPOINT_BYTES,
    CheckpointReduction,
    FailedStrategy,
    ProgressCheckpoint,
    SourceRef,
    VerifiedFact,
    WorkingHypothesis,
)


def _checkpoint() -> ProgressCheckpoint:
    source = SourceRef(tool_call_id="call:portland", tool_name="search_page_content")
    return ProgressCheckpoint(
        verified_facts=(
            VerifiedFact(
                claim="Portland coordinates",
                value="43.6600,-70.2550",
                source_refs=(source,),
            ),
        ),
        working_hypotheses=(
            WorkingHypothesis(
                claim="Acadia may be the closest candidate",
                needs_verification=True,
            ),
        ),
        remaining_questions=("Acadia relation ID", "OSRM driving distance"),
        next_intent="Resolve Acadia identifiers and route distance",
        failed_strategies=(
            FailedStrategy(
                strategy="Repeated Portland tab switching",
                outcome="No new task information",
            ),
        ),
    )


def test_checkpoint_round_trip_is_canonical_bounded_and_source_typed() -> None:
    checkpoint = _checkpoint()
    rendered = checkpoint.render()

    assert ProgressCheckpoint.parse(rendered) == checkpoint
    assert len(rendered.encode()) <= MAX_PROGRESS_CHECKPOINT_BYTES
    assert checkpoint.source_refs() == {
        ("search_page_content", "call:portland")
    }


@pytest.mark.parametrize(
    "value",
    [
        "I will switch back to the Portland tab now.",
        "Non-authoritative progress checkpoint (fresh World wins):\n{not-json}",
        'Non-authoritative progress checkpoint (fresh World wins):\n{"version":"unknown"}',
    ],
)
def test_arbitrary_or_malformed_text_is_not_a_checkpoint(value: str) -> None:
    assert ProgressCheckpoint.parse(value) is None


def test_checkpoint_keeps_literal_task_identifiers_and_rejects_oversized_content() -> None:
    checkpoint = ProgressCheckpoint(
        remaining_questions=("Compare European route E25 with document section R9",),
        next_intent="Verify the literal identifiers from a successful source",
    )

    assert ProgressCheckpoint.parse(checkpoint.render()) == checkpoint
    with pytest.raises(ValidationError, match="history bound"):
        ProgressCheckpoint(
            verified_facts=tuple(
                VerifiedFact(
                    claim=f"fact {index}",
                    value="深" * 800,
                    source_refs=(
                        SourceRef(
                            tool_call_id=f"call:{index}",
                            tool_name="read_region",
                        ),
                    ),
                )
                for index in range(16)
            ),
            next_intent="Continue",
        )


def test_reducer_update_requires_only_available_successful_sources() -> None:
    checkpoint = _checkpoint()
    reduction = CheckpointReduction(outcome="updated", checkpoint=checkpoint)

    assert validate_reduction_sources(
        reduction,
        successful_sources=(("search_page_content", "call:portland"),),
        previous_checkpoint=None,
    ) == checkpoint
    with pytest.raises(ValueError, match="unavailable"):
        validate_reduction_sources(
            reduction,
            successful_sources=(),
            previous_checkpoint=None,
        )


def test_reducer_outcome_cannot_claim_update_without_payload() -> None:
    with pytest.raises(ValidationError, match="outcome and payload"):
        CheckpointReduction(outcome="updated")
