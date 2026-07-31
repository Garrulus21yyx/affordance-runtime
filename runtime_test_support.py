"""Typed contract fixtures shared by tests that intentionally construct plans directly."""

from affordance_runtime.simplified_runtime_contracts import ElementIntent, SourceReference


def make_interaction(target: str) -> ElementIntent:
    return ElementIntent(
        target,
        (SourceReference("test-request", "test-request:interaction"),),
    )
