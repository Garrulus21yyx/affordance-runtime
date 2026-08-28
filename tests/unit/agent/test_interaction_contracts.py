from __future__ import annotations

import pytest

from affordance_runtime.agent.decisions import (
    BooleanFieldDraft,
    DateFieldDraft,
    DecimalFieldDraft,
    IntegerFieldDraft,
    InteractionAttribute,
    InteractionOptionDraft,
    InteractionRequestDraft,
    InteractionResponseKind,
    PublicArtifactDraft,
    PublicArtifactItemDraft,
    TextFieldDraft,
)
from affordance_runtime.agent.interactions import (
    BooleanFieldValue,
    DateFieldValue,
    DecimalFieldValue,
    FreeTextResponse,
    IntegerFieldValue,
    InteractionAdmissionCode,
    MultiSelectionResponse,
    SingleSelectionResponse,
    StructuredFieldsResponse,
    TextFieldValue,
    admit_interaction_request,
    admit_interaction_response,
    interaction_request_public_value,
    materialize_public_artifact,
    restore_interaction_request_public_value,
)
from affordance_runtime.world import SemanticTarget, StateFact
from tests.support.world import fused_world


def _world():
    source_id = "observation:interaction"
    return fused_world(
        source_id,
        targets=(SemanticTarget("target:one", "status", "Visible item", {"visible": True}),),
        facts=(StateFact("fact:visible", "target:one", "visible", True, source_id),),
    )


def _admit(draft: InteractionRequestDraft):
    admission = admit_interaction_request(_world(), draft)
    assert admission.request is not None
    return admission.request


def test_all_interaction_request_response_variants_are_closed_and_admitted() -> None:
    free = _admit(
        InteractionRequestDraft(
            "context:interaction",
            "Explain the missing value.",
        )
    )
    assert admit_interaction_response(free, FreeTextResponse(free.request_id, "value")).admitted

    single = _admit(
        InteractionRequestDraft(
            "context:interaction",
            "Choose one.",
            InteractionResponseKind.SINGLE_SELECT,
            option_drafts=(InteractionOptionDraft("First"), InteractionOptionDraft("Second")),
        )
    )
    assert admit_interaction_response(
        single,
        SingleSelectionResponse(single.request_id, single.options[1].option_id),
    ).admitted

    multiple = _admit(
        InteractionRequestDraft(
            "context:interaction",
            "Choose any.",
            InteractionResponseKind.MULTI_SELECT,
            option_drafts=(InteractionOptionDraft("First"), InteractionOptionDraft("Second")),
        )
    )
    assert admit_interaction_response(
        multiple,
        MultiSelectionResponse(
            multiple.request_id,
            tuple(item.option_id for item in multiple.options),
        ),
    ).admitted

    structured = _admit(
        InteractionRequestDraft(
            "context:interaction",
            "Provide the fields.",
            InteractionResponseKind.STRUCTURED_FIELDS,
            (
                TextFieldDraft("Text"),
                IntegerFieldDraft("Integer"),
                DecimalFieldDraft("Decimal"),
                BooleanFieldDraft("Boolean"),
                DateFieldDraft("Date"),
            ),
        )
    )
    field_ids = tuple(item.field_id for item in structured.fields)
    response = StructuredFieldsResponse(
        structured.request_id,
        (
            TextFieldValue(field_ids[0], "hello"),
            IntegerFieldValue(field_ids[1], 3),
            DecimalFieldValue(field_ids[2], "12.50"),
            BooleanFieldValue(field_ids[3], True),
            DateFieldValue(field_ids[4], "2026-08-28"),
        ),
    )
    assert admit_interaction_response(structured, response).admitted


def test_interaction_response_rejects_wrong_request_duplicate_and_unknown_values() -> None:
    request = _admit(
        InteractionRequestDraft(
            "context:interaction",
            "Choose any.",
            InteractionResponseKind.MULTI_SELECT,
            option_drafts=(InteractionOptionDraft("First"), InteractionOptionDraft("Second")),
        )
    )
    option_id = request.options[0].option_id
    wrong = admit_interaction_response(
        request,
        MultiSelectionResponse("interaction:wrong", (option_id,)),
    )
    duplicate = admit_interaction_response(
        request,
        MultiSelectionResponse(request.request_id, (option_id, option_id)),
    )
    unknown = admit_interaction_response(
        request,
        MultiSelectionResponse(request.request_id, ("option:unknown",)),
    )

    assert wrong.rejection_code is InteractionAdmissionCode.REQUEST_MISMATCH
    assert duplicate.rejection_code is InteractionAdmissionCode.OPTION_DUPLICATE
    assert unknown.rejection_code is InteractionAdmissionCode.OPTION_UNKNOWN


def test_interaction_request_persistence_round_trip_preserves_assigned_identity() -> None:
    request = _admit(
        InteractionRequestDraft(
            "context:interaction",
            "Choose one.",
            InteractionResponseKind.SINGLE_SELECT,
            option_drafts=(
                InteractionOptionDraft(
                    "First",
                    "Description",
                    attributes=(InteractionAttribute("rank", "1"),),
                    uncertainties=("one property is unknown",),
                ),
            ),
            public_intent="I need your choice.",
        )
    )

    restored = restore_interaction_request_public_value(
        interaction_request_public_value(request)
    )

    assert restored == request


def test_public_artifact_is_current_evidence_only_and_never_invents_links() -> None:
    world = _world()
    draft = PublicArtifactDraft(
        "Comparison",
        "One current result.",
        (
            PublicArtifactItemDraft(
                "Visible item",
                attributes=(InteractionAttribute("state", "visible"),),
                evidence_refs=("fact:visible",),
            ),
        ),
        ("fact:visible",),
    )

    artifact = materialize_public_artifact(
        world,
        draft,
        response_identity="context:final",
    )

    assert artifact is not None
    assert artifact.links == ()
    assert artifact.evidence_refs == ("fact:visible",)
    with pytest.raises(ValueError, match="public_artifact_evidence_not_current"):
        materialize_public_artifact(
            world,
            PublicArtifactDraft("Invalid", evidence_refs=("fact:stale",)),
            response_identity="context:final",
        )
