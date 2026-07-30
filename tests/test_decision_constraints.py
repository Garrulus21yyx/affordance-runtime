from __future__ import annotations

import pytest

from affordance_runtime.decision_constraints import (
    DecisionConstraintSet,
    StrictDecisionConstraintBuilder,
)
from affordance_runtime.planner_context import AffordanceSummary, PlannerContext
from affordance_runtime.planning_request import (
    PlannerAdmissionSource,
    PlannerAdmissionView,
    TargetAdmissionDecision,
    TargetAdmissionStatus,
)


def _context(**updates: object) -> PlannerContext:
    payload: dict[str, object] = {
        "task_spec": {"objective": "Update profile"},
        "active_subgoal": "Fill profile name",
        "active_subgoal_action_family": "type_text",
        "observed_text": "",
        "affordances": (
            AffordanceSummary(
                id="name-field",
                surface="dom",
                role="textbox",
                label="Profile name",
                action="fill",
                confidence=1.0,
                state={},
            ),
            AffordanceSummary(
                id="email-field",
                surface="dom",
                role="textbox",
                label="Email address",
                action="fill",
                confidence=1.0,
                state={},
            ),
            AffordanceSummary(
                id="submit-button",
                surface="dom",
                role="button",
                label="Submit",
                action="click",
                confidence=1.0,
                state={},
            ),
        ),
        "permitted_action_kinds": ("type_text", "finish", "ask_user"),
        "selected_artifact_refs": (),
        "granted_capabilities": (),
        "approval_handling": "coordinator_managed",
        "remaining_budgets": {"steps": 3},
        "pending_evidence_obligations": (),
        "latest_outcome": {},
        "recent_proposals": (),
        "verified_effects": (),
        "satisfied_action_targets": {},
        "recovery_summary": {},
        "accepted_knowledge": (),
        "task_revision": 1,
        "state_version": 2,
        "snapshot_id": "snapshot-1",
    }
    payload.update(updates)
    return PlannerContext.model_validate(payload)


def test_current_state_admission_excludes_only_verifier_backed_targets() -> None:
    context = _context(
        active_subgoal="Update profile",
        verified_effects=("profile updated",),
        satisfied_action_targets={"type_text": ("email-field",)},
    )

    permitted, targets = StrictDecisionConstraintBuilder().apply_current_state(
        context,
        ["type_text", "finish", "ask_user"],
        {"type_text": ["name-field", "email-field"], "finish": [], "ask_user": []},
    )

    assert permitted == ["type_text", "finish", "ask_user"]
    assert targets == {"type_text": ["name-field"], "finish": [], "ask_user": []}


def test_current_state_admission_scopes_subgoal_and_blocks_unverified_finish() -> None:
    permitted, targets = StrictDecisionConstraintBuilder().apply_current_state(
        _context(),
        ["type_text", "finish", "ask_user"],
        {"type_text": ["name-field", "email-field"], "finish": [], "ask_user": []},
    )

    assert permitted == ["type_text", "ask_user"]
    assert targets == {"type_text": ["name-field"], "finish": [], "ask_user": []}


def test_current_state_admission_keeps_finish_after_verifier_backed_effect() -> None:
    context = _context(
        active_subgoal="Update profile",
        verified_effects=("profile updated",),
    )

    permitted, targets = StrictDecisionConstraintBuilder().apply_current_state(
        context,
        ["type_text", "finish", "ask_user"],
        {"type_text": ["name-field"], "finish": [], "ask_user": []},
    )

    assert permitted == ["type_text", "finish", "ask_user"]
    assert targets["type_text"] == ["name-field"]


def test_decision_constraint_set_copies_and_freezes_compatible_targets() -> None:
    targets = {"type_text": ("name-field",)}

    constraints = DecisionConstraintSet(
        permitted_action_kinds=("type_text",),
        compatible_target_ids=targets,
    )
    targets["type_text"] = ("email-field",)

    assert constraints.compatible_target_ids["type_text"] == ("name-field",)
    with pytest.raises(TypeError):
        constraints.compatible_target_ids["activate"] = ("save-button",)


def test_apply_admission_filters_excluded_targets_and_returns_summary() -> None:
    admission = PlannerAdmissionView(
        source=PlannerAdmissionSource.LEGACY_TERMINAL_READINESS,
        task_revision=1,
        snapshot_id="snapshot-1",
        target_decisions=(
            TargetAdmissionDecision(
                target_id="submit-button",
                status=TargetAdmissionStatus.BLOCKED,
                reason_code="terminal_dependency_blocked",
                blocking_step_ids=("step:type-name",),
            ),
            TargetAdmissionDecision(
                target_id="help-link",
                status=TargetAdmissionStatus.UNRESOLVED,
                reason_code="terminal_grounding_unresolved",
            ),
        ),
        excluded_target_ids=("submit-button", "help-link"),
    )

    result = StrictDecisionConstraintBuilder().apply_admission(_context(), admission)

    assert tuple(item.id for item in result.context.affordances) == (
        "name-field",
        "email-field",
    )
    assert result.summary.excluded_target_ids == ("help-link", "submit-button")
    assert result.summary.blocked_target_ids == ("submit-button",)
    assert result.summary.unresolved_target_ids == ("help-link",)


def test_apply_admission_without_admission_preserves_context() -> None:
    context = _context()

    result = StrictDecisionConstraintBuilder().apply_admission(context, None)

    assert result.context == context
    assert result.summary.excluded_target_ids == ()


def test_build_scopes_checkbox_ordinal_active_step_to_current_target() -> None:
    context = _context(
        task_spec={"objective": "Click the 3rd checkbox", "targets": ("checkbox_3_state",)},
        active_subgoal="checkbox_3_state has changed",
        active_subgoal_action_family="activate",
        affordances=(
            AffordanceSummary(
                id="checkbox-1",
                surface="dom",
                role="checkbox",
                label="One",
                action="click",
                confidence=1.0,
                state={"input_type": "checkbox"},
            ),
            AffordanceSummary(
                id="checkbox-2",
                surface="dom",
                role="checkbox",
                label="Two",
                action="click",
                confidence=1.0,
                state={"input_type": "checkbox"},
            ),
            AffordanceSummary(
                id="checkbox-3",
                surface="dom",
                role="checkbox",
                label="Three",
                action="click",
                confidence=1.0,
                state={"input_type": "checkbox"},
            ),
            AffordanceSummary(
                id="submit-button",
                surface="dom",
                role="button",
                label="Submit",
                action="click",
                confidence=1.0,
                state={},
            ),
        ),
    )

    constraints = StrictDecisionConstraintBuilder().build(
        context,
        ["activate", "finish", "ask_user"],
        {
            "activate": ["checkbox-1", "checkbox-2", "checkbox-3", "submit-button"],
            "finish": [],
            "ask_user": [],
        },
    )

    assert constraints.permitted_action_kinds == ("activate",)
    assert constraints.compatible_target_ids["activate"] == ("checkbox-3",)
