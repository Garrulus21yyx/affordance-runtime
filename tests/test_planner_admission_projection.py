from __future__ import annotations

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    UnifiedAffordance,
)
from affordance_runtime.planning_request import TargetAdmissionStatus
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_planning import (
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
from runtime_test_support import make_interaction


def _plan() -> TaskPlan:
    return TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=2,
        plan_version=1,
        based_on_state_version=4,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="field:value",
                objective="field equals dark",
                interaction=make_interaction('field'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="field",
                    relation=SubgoalOutcomeRelation.EQUALS,
                    value="dark",
                ),
            ),
            SubgoalSpec(
                subgoal_id="settings:submitted",
                objective="settings submission is completed",
                interaction=make_interaction('settings submission'),
                depends_on=("field:value",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=SubgoalOutcome(
                    subject="settings submission",
                    relation=SubgoalOutcomeRelation.IS_COMPLETED,
                ),
            ),
        ),
    )


def _candidate(
    *,
    semantic_target_id: str = "semantic:submit",
    candidate_id: str = "candidate:dom:submit",
    fingerprint: str = "sha256:submit",
) -> GroundingCandidate:
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id=semantic_target_id,
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(backend_handle="submit"),
        compatible_executor="browsergym",
        observation_epoch_id="snapshot-2",
        environment_revision="environment-1",
        page_revision="page-1",
        target_fingerprint=fingerprint,
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset({EvidenceKind.STRUCTURAL}),
    )


def _target(
    *,
    semantic_target_id: str = "semantic:submit",
    label: str = "settings submission",
    candidates: tuple[GroundingCandidate, ...] | None = None,
) -> UnifiedAffordance:
    return UnifiedAffordance(
        semantic_target_id=semantic_target_id,
        role="button",
        label=label,
        supported_actions=frozenset({"activate"}),
        grounding_candidates=candidates if candidates is not None else (_candidate(),),
    )


def _snapshot(
    *,
    targets: tuple[UnifiedAffordance, ...] = (_target(),),
    fingerprint: str = "sha256:submit",
) -> BrowserSnapshot:
    observation = Observation(
        "environment-1",
        snapshot_id="snapshot-2",
        page_revision="page-1",
        target_fingerprints={"candidate:dom:submit": fingerprint},
    )
    return BrowserSnapshot(
        observation=observation,
        affordance_model=DomAdapter().transduce(
            "<main></main>",
            environment_revision="environment-1",
            snapshot_id="snapshot-2",
            page_revision="page-1",
        ),
        unified_affordances=targets,
    )


def test_legacy_projector_returns_none_without_plan_or_progress() -> None:
    from affordance_runtime.planner_admission_projection import LegacyPlannerAdmissionProjector

    assert (
        LegacyPlannerAdmissionProjector().project(
            task_revision=2,
            task_plan=None,
            plan_progress=None,
            snapshot=_snapshot(),
        )
        is None
    )


def test_legacy_projector_admits_ready_terminal_target() -> None:
    from affordance_runtime.planner_admission_projection import LegacyPlannerAdmissionProjector

    admission = LegacyPlannerAdmissionProjector().project(
        task_revision=2,
        task_plan=_plan(),
        plan_progress=PlanProgress(
            active_subgoal_id="settings:submitted",
            completed_subgoal_ids=["field:value"],
            evidence_by_subgoal={"field:value": ["artifact:verification"]},
        ),
        snapshot=_snapshot(),
    )

    assert admission is not None
    assert admission.snapshot_id == "snapshot-2"
    assert admission.excluded_target_ids == ()
    assert admission.target_decisions[0].target_id == "semantic:submit"
    assert admission.target_decisions[0].status == TargetAdmissionStatus.ALLOWED


def test_legacy_projector_blocks_terminal_with_open_dependency() -> None:
    from affordance_runtime.planner_admission_projection import LegacyPlannerAdmissionProjector

    admission = LegacyPlannerAdmissionProjector().project(
        task_revision=2,
        task_plan=_plan(),
        plan_progress=PlanProgress(active_subgoal_id="settings:submitted"),
        snapshot=_snapshot(),
    )

    assert admission is not None
    assert admission.excluded_target_ids == ("semantic:submit",)
    decision = admission.target_decisions[0]
    assert decision.status == TargetAdmissionStatus.BLOCKED
    assert decision.blocking_step_ids == ("field:value",)


def test_legacy_projector_marks_ambiguous_grounding_unresolved() -> None:
    from affordance_runtime.planner_admission_projection import LegacyPlannerAdmissionProjector

    admission = LegacyPlannerAdmissionProjector().project(
        task_revision=2,
        task_plan=_plan(),
        plan_progress=PlanProgress(
            active_subgoal_id="settings:submitted",
            completed_subgoal_ids=["field:value"],
            evidence_by_subgoal={"field:value": ["artifact:verification"]},
        ),
        snapshot=_snapshot(
            targets=(
                _target(semantic_target_id="semantic:submit"),
                _target(
                    semantic_target_id="semantic:submit-alternate",
                    candidates=(
                        _candidate(
                            semantic_target_id="semantic:submit-alternate",
                            candidate_id="candidate:dom:submit-alternate",
                        ),
                    ),
                ),
            )
        ),
    )

    assert admission is not None
    assert admission.excluded_target_ids == (
        "semantic:submit",
        "semantic:submit-alternate",
    )
    assert tuple(item.status for item in admission.target_decisions) == (
        TargetAdmissionStatus.UNRESOLVED,
        TargetAdmissionStatus.UNRESOLVED,
    )
