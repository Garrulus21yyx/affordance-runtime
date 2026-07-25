import hashlib

import pytest

from affordance_runtime.source_ledger import (
    SourceKind,
    SourceLedgerBuilder,
    SourceSensitivity,
)
from affordance_runtime.task_intake import UserRequest


def _request(**changes: object) -> UserRequest:
    values = {
        "request_id": "request-17",
        "raw_text": "Read the source value. Transform it; then save the result.",
        "conversation_refs": ("conversation:42",),
        "attachment_refs": ("attachment:brief",),
        "target_refs": ("target:settings",),
        "profile_context_refs": ("profile:locale",),
    }
    values.update(changes)
    return UserRequest(**values)


def test_source_ledger_is_deterministic_and_preserves_exact_request_spans() -> None:
    request = _request()

    first = SourceLedgerBuilder().build(request)
    second = SourceLedgerBuilder().build(request)

    assert first == second
    assert first.identity == second.identity
    assert first.raw_text_unit_id == "request-17:source:request:whole"
    clauses = [unit for unit in first.units if unit.required_candidate]
    assert [request.raw_text[unit.span_start : unit.span_end] for unit in clauses] == [
        "Read the source value.",
        "Transform it;",
        "then save the result.",
    ]
    assert all(unit.source_kind == SourceKind.REQUEST for unit in clauses)
    assert all(unit.sensitivity == SourceSensitivity.USER_CONTENT for unit in clauses)
    assert clauses[0].content_sha256 == hashlib.sha256(
        b"Read the source value."
    ).hexdigest()


def test_source_ledger_keeps_external_references_as_metadata_only() -> None:
    ledger = SourceLedgerBuilder().build(_request())
    external = [unit for unit in ledger.units if unit.source_kind != SourceKind.REQUEST]

    assert [unit.source_kind for unit in external] == [
        SourceKind.CONVERSATION,
        SourceKind.ATTACHMENT,
        SourceKind.TARGET,
        SourceKind.PROFILE_CONTEXT,
    ]
    assert all(unit.span_start is None and unit.span_end is None for unit in external)
    assert all(unit.content_length == 0 for unit in external)
    assert all(unit.sensitivity == SourceSensitivity.REFERENCE_ONLY for unit in external)
    context = ledger.model_context()
    assert "Read the source value" not in str(context)
    assert "conversation:42" in str(context)
    assert context["raw_text_source_unit_id"] == ledger.raw_text_unit_id


def test_source_ledger_fails_closed_when_bounded_clause_limit_is_exceeded() -> None:
    raw_text = " ".join(f"Clause {index}." for index in range(33))

    with pytest.raises(ValueError, match="clause bound exceeded"):
        SourceLedgerBuilder().build(_request(raw_text=raw_text))
