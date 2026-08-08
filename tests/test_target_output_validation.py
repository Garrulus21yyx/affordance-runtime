import hashlib
from dataclasses import replace

import pytest
from test_agent_loop import _world

from affordance_runtime.evaluation import EvaluatedOutput, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_task_evaluation
from affordance_runtime.task import EvaluationSpec, RiskProfile, TaskGoal
from affordance_runtime.world import ObservationSourceProfile, SurfaceObservation


def _task(path: str, digest: str) -> TaskGoal:
    return TaskGoal(
        "export",
        "Export report",
        allowed_effects=("report_exported",),
        requested_outputs=("report",),
        risk_profile=RiskProfile.LOW,
        evaluation_spec=EvaluationSpec(
            {"type": "output_integrity"},
            {"report": {"path": path, "sha256": digest}},
        ),
    )


def _proposal(outputs=()) -> TaskEvaluation:
    return TaskEvaluation(
        "export",
        "after",
        TaskEvaluationStatus.COMPLETE,
        "report exported",
        completion_evidence_refs=("fact:after:enabled",),
        outputs=outputs,
    )


def _validate(task: TaskGoal, proposal: TaskEvaluation, *, artifact: dict | None = None) -> None:
    observation = _world("after", True)
    if artifact is not None:
        source = SurfaceObservation(
            "source:output",
            "dom",
            "revision:output",
            ObservationSourceProfile.dom(),
            artifacts={"report": artifact},
        )
        observation = replace(observation, sources=(source,))
    validate_task_evaluation(
        proposal,
        task,
        observation,
        WorldEvidenceIndex.from_observation(observation),
    )


def test_requested_output_missing_or_without_evidence_cannot_complete(tmp_path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    digest = hashlib.sha256(b"report").hexdigest()

    with pytest.raises(ValueError, match="requested output"):
        _validate(_task(str(path), digest), _proposal())
    with pytest.raises(ValueError, match="evidence"):
        EvaluatedOutput("report", {"status": "written"}, ())


def test_required_output_path_and_sha256_fail_closed(tmp_path) -> None:
    missing = tmp_path / "missing.txt"
    digest = hashlib.sha256(b"report").hexdigest()
    value = {"path": str(missing), "sha256": digest}
    output = EvaluatedOutput("report", value, ("artifact:source:output:report",))
    with pytest.raises(ValueError, match="regular file"):
        _validate(_task(str(missing), digest), _proposal((output,)), artifact=value)

    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    wrong_digest = "0" * 64
    value = {"path": str(path), "sha256": wrong_digest}
    output = EvaluatedOutput("report", value, ("artifact:source:output:report",))
    with pytest.raises(ValueError, match="required output SHA-256 does not match"):
        _validate(_task(str(path), wrong_digest), _proposal((output,)), artifact=value)


def test_matching_file_integrity_and_current_evidence_allows_complete(tmp_path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    digest = hashlib.sha256(b"report").hexdigest()
    value = {"path": str(path), "sha256": digest}
    output = EvaluatedOutput("report", value, ("artifact:source:output:report",))

    _validate(_task(str(path), digest), _proposal((output,)), artifact=value)


def test_symlink_to_regular_file_is_not_the_regular_output_profile(tmp_path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("report", encoding="utf-8")
    link = tmp_path / "report.txt"
    link.symlink_to(target)
    digest = hashlib.sha256(b"report").hexdigest()
    value = {"path": str(link), "sha256": digest}
    output = EvaluatedOutput("report", value, ("artifact:source:output:report",))

    with pytest.raises(ValueError, match="regular file"):
        _validate(_task(str(link), digest), _proposal((output,)), artifact=value)


def test_successful_receipt_cannot_replace_requested_output(tmp_path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    proposal = _proposal()

    with pytest.raises(ValueError, match="requested output"):
        _validate(_task(str(path), hashlib.sha256(b"report").hexdigest()), proposal)
