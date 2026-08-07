"""Pure failure catalogue for migrated environment fixtures.

Expected outcomes describe observable runtime behaviour, not a legacy recovery
tier.  The short agent loop remains free to reobserve, reroute, ask the user,
or stop according to its own bounded policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import FrozenDict, freeze_json


class FailureSurface(StrEnum):
    DOM = "dom"
    VISUAL = "visual"
    WOT = "wot"


@dataclass(frozen=True)
class FailureSpec:
    failure_type: str
    surface: FailureSurface
    control_payload: FrozenDict
    expected_observation: str
    expected_evaluation: str

    def __init__(
        self,
        failure_type: str,
        surface: FailureSurface,
        control_payload: dict[str, Any],
        expected_observation: str,
        expected_evaluation: str,
    ) -> None:
        object.__setattr__(self, "failure_type", failure_type)
        object.__setattr__(self, "surface", surface)
        object.__setattr__(self, "control_payload", freeze_json(control_payload))
        object.__setattr__(self, "expected_observation", expected_observation)
        object.__setattr__(self, "expected_evaluation", expected_evaluation)


FAILURE_CATALOGUE: tuple[FailureSpec, ...] = (
    FailureSpec(
        "visual_misclick",
        FailureSurface.VISUAL,
        {"fault": "visual_misclick"},
        "fresh screenshot does not contain the expected state change",
        "postcondition_unsatisfied",
    ),
    FailureSpec(
        "dom_selector_mutation",
        FailureSurface.DOM,
        {"fault": "selector_mutation"},
        "bound DOM fingerprint or selector is stale",
        "binding_stale",
    ),
    FailureSpec(
        "layout_shift",
        FailureSurface.DOM,
        {"fault": "layout_shift"},
        "fresh geometry differs from the bound observation",
        "binding_stale",
    ),
    FailureSpec(
        "wot_timeout",
        FailureSurface.WOT,
        {"type": "timeout", "delay_ms": 1_500},
        "transport result is sent_unknown until state is reobserved",
        "post_state_required",
    ),
    FailureSpec(
        "postcondition_mismatch",
        FailureSurface.WOT,
        {"type": "postcondition_mismatch"},
        "operation returns success while fresh state remains unchanged",
        "postcondition_unsatisfied",
    ),
    FailureSpec(
        "backend_offline",
        FailureSurface.WOT,
        {"type": "offline"},
        "WoT source is unavailable",
        "route_unavailable",
    ),
    FailureSpec(
        "malformed_td",
        FailureSurface.WOT,
        {"type": "malformed"},
        "TD acquisition or parsing fails without contaminating other surfaces",
        "source_rejected",
    ),
    FailureSpec(
        "surface_disagreement",
        FailureSurface.WOT,
        {"type": "postcondition_mismatch"},
        "current DOM and WoT assertions materially disagree",
        "conflict_requires_resolution",
    ),
)


def failure_spec(failure_type: str) -> FailureSpec:
    try:
        return next(item for item in FAILURE_CATALOGUE if item.failure_type == failure_type)
    except StopIteration as exc:
        raise KeyError(f"unknown failure type {failure_type!r}") from exc
