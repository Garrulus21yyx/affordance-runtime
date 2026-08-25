from __future__ import annotations

import json

import pytest

from affordance_runtime.model.policy.progress_checkpoint import (
    MAX_PROGRESS_CHECKPOINT_CHARS,
    ProgressCheckpoint,
    normalize_progress_checkpoint,
)


def test_checkpoint_round_trip_is_canonical_and_complete() -> None:
    checkpoint = ProgressCheckpoint(
        verified_facts=("Portland coordinates: 43.6600,-70.2550",),
        working_hypotheses=("Acadia is the closest candidate; verification remains",),
        remaining_requirements=("Acadia relation ID", "OSRM driving distance"),
        next_intent="Resolve Acadia identifiers and route distance",
        avoid_repeating=("Do not reopen Portland coordinate sources",),
    )

    rendered = checkpoint.render()

    assert ProgressCheckpoint.parse(rendered) == checkpoint
    assert normalize_progress_checkpoint(f"  {rendered}\n") == rendered
    assert len(rendered) <= MAX_PROGRESS_CHECKPOINT_CHARS


@pytest.mark.parametrize(
    "value",
    [
        "I will switch back to the Portland tab now.",
        '<progress_checkpoint>{"version":"progress-checkpoint.v1"}</progress_checkpoint>',
        '<progress_checkpoint>{not-json}</progress_checkpoint>',
        '<progress_checkpoint>{"version":"unknown","verified_facts":[],"working_hypotheses":[],"remaining_requirements":[],"next_intent":"continue","avoid_repeating":[]}</progress_checkpoint>',
        '<progress_checkpoint>{"version":"progress-checkpoint.v1","verified_facts":[],"working_hypotheses":[],"remaining_requirements":[],"next_intent":"","avoid_repeating":[]}</progress_checkpoint>',
    ],
)
def test_arbitrary_or_malformed_text_is_not_a_checkpoint(value: str) -> None:
    assert ProgressCheckpoint.parse(value) is None
    assert normalize_progress_checkpoint(value) == ""


def test_checkpoint_rejects_unknown_fields_and_oversized_content() -> None:
    payload = {
        "version": "progress-checkpoint.v1",
        "verified_facts": [],
        "working_hypotheses": [],
        "remaining_requirements": [],
        "next_intent": "continue",
        "avoid_repeating": [],
        "runtime_state": "must not become a second authority",
    }
    unknown = f"<progress_checkpoint>{json.dumps(payload)}</progress_checkpoint>"

    assert ProgressCheckpoint.parse(unknown) is None
    with pytest.raises(ValueError, match="history bound"):
        ProgressCheckpoint(
            verified_facts=tuple(f"fact-{index}-" + "x" * 32 for index in range(16)),
            remaining_requirements=tuple(
                f"requirement-{index}-" + "y" * 24 for index in range(8)
            ),
            next_intent="continue the bounded semantic subgoal",
        )
