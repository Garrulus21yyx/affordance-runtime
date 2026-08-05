import pytest

from affordance_runtime.source_envelope import (
    MaterialField,
    SourceEnvelopeBuilder,
)
from affordance_runtime.task_intake import UserRequest


def test_low_risk_request_builds_one_immutable_whole_request_envelope() -> None:
    request = UserRequest(request_id="request-1", raw_text="Open the settings page")

    envelope = SourceEnvelopeBuilder().build(request)

    assert envelope.request_id == request.request_id
    assert envelope.content_length == len(request.raw_text)
    assert envelope.whole_request_anchor.span is None
    assert envelope.anchors == (envelope.whole_request_anchor,)
    assert "Open the settings page" not in envelope.model_dump_json()
    assert envelope == SourceEnvelopeBuilder().build(request)


@pytest.mark.parametrize(
    ("field", "text", "excerpt"),
    (
        (MaterialField.RECIPIENT, "Send the report to Ada", "Ada"),
        (MaterialField.AMOUNT, "Pay exactly EUR 42.50", "EUR 42.50"),
        (MaterialField.DESTRUCTIVE_TARGET, "Delete archive alpha", "archive alpha"),
    ),
)
def test_material_authority_uses_exact_source_anchor(field, text, excerpt) -> None:
    request = UserRequest(request_id="request-2", raw_text=text)
    start = text.index(excerpt)

    envelope = SourceEnvelopeBuilder().build(
        request,
        exact_anchors=((field, start, start + len(excerpt)),),
    )

    anchor = envelope.anchors[1]
    assert anchor.material_field == field
    assert anchor.span == (start, start + len(excerpt))
    assert anchor.content_length == len(excerpt)
    assert excerpt not in anchor.model_dump_json()
