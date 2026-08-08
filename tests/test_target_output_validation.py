import hashlib

import pytest
from test_agent_loop import _world

from affordance_runtime.evaluation import EvaluatedOutput, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_task_evaluation
from affordance_runtime.task import EvaluationSpec, RiskProfile, TaskGoal


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


def _validate(task: TaskGoal, proposal: TaskEvaluation) -> None:
    observation = _world("after", True)
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
    evidence = ("fact:after:enabled",)
    output = EvaluatedOutput("report", {"status": "written"}, evidence)
    missing = tmp_path / "missing.txt"
    with pytest.raises(ValueError, match="regular file"):
        _validate(_task(str(missing), hashlib.sha256(b"report").hexdigest()), _proposal((output,)))

    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        _validate(_task(str(path), "0" * 64), _proposal((output,)))


def test_matching_file_integrity_and_current_evidence_allows_complete(tmp_path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    output = EvaluatedOutput("report", {"status": "written"}, ("fact:after:enabled",))

    _validate(_task(str(path), hashlib.sha256(b"report").hexdigest()), _proposal((output,)))


def test_successful_receipt_cannot_replace_requested_output(tmp_path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    proposal = _proposal()

    with pytest.raises(ValueError, match="requested output"):
        _validate(_task(str(path), hashlib.sha256(b"report").hexdigest()), proposal)
