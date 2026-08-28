from __future__ import annotations

import json
from pathlib import Path

from affordance_runtime.agent.decisions import InteractionAttribute
from affordance_runtime.agent.interactions import PublicArtifact, PublicArtifactItem
from affordance_runtime.benchmarks.target_loop.presentation_sidecar import (
    CasePresentationSidecar,
    PresentationReportingStatus,
    decode_public_case_presentation,
    public_case_presentation,
    report_case_presentation,
)
from affordance_runtime.benchmarks.target_loop.result_store import SQLiteRunResultStore


def _artifact() -> PublicArtifact:
    return PublicArtifact(
        "public-artifact:00000000000000000000000000000000",
        "Comparison",
        "One evaluator-confirmed presentation artifact.",
        (
            PublicArtifactItem(
                "artifact-item:00000000000000000000000000000000",
                "Visible item",
                attributes=(InteractionAttribute("state", "visible"),),
                evidence_refs=("fact:visible",),
            ),
        ),
        (),
        ("fact:visible",),
    )


def test_artifact_absent_and_present_sidecars_round_trip_through_sqlite_and_json(
    tmp_path: Path,
) -> None:
    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    absent = CasePresentationSidecar("case:absent")
    present = CasePresentationSidecar("case:present", _artifact())

    for sidecar in (absent, present):
        result = report_case_presentation(store, sidecar, tmp_path)
        assert result.status is PresentationReportingStatus.COMMITTED
        assert store.load_case_presentation(sidecar.case_id) == sidecar
        exported = json.loads(
            (tmp_path / "cases" / f"{sidecar.case_id}.presentation.json").read_text()
        )
        assert decode_public_case_presentation(exported) == sidecar
        assert exported == json.loads(json.dumps(public_case_presentation(sidecar)))


def test_presentation_reporting_failure_is_typed_and_does_not_raise() -> None:
    class FailingStore:
        def commit_case_presentation(self, sidecar):  # type: ignore[no-untyped-def]
            del sidecar
            raise OSError("fixture reporting failure")

        def export_case_presentation(self, case_id, output_dir):  # type: ignore[no-untyped-def]
            raise AssertionError((case_id, output_dir))

    result = report_case_presentation(
        FailingStore(),
        CasePresentationSidecar("case:reporting-failure", _artifact()),
        Path("unused"),
    )

    assert result.status is PresentationReportingStatus.FAILED
    assert result.failure_code == "presentation_sidecar_reporting_failed"
