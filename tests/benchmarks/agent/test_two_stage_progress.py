import json
from pathlib import Path

from affordance_runtime.benchmarks.model_conformance.two_stage.contracts import (
    PacingConfiguration,
    TwoStageDecisionIdentity,
)
from affordance_runtime.benchmarks.model_conformance.two_stage.progress import (
    TwoStageProgressAttempt,
    TwoStageProgressStage,
    write_two_stage_progress,
)


def test_progress_atomically_records_each_stage_without_private_data(tmp_path: Path) -> None:
    path = tmp_path / "two-stage-progress.json"
    identity = TwoStageDecisionIdentity("logical:1", "context:1", "routing:1", "payload:1")
    attempts = []
    for stage in TwoStageProgressStage:
        attempts.append(TwoStageProgressAttempt(
            identity, stage, routing_attempts=1,
            payload_attempts=int(stage.value.startswith("payload") or stage is TwoStageProgressStage.RUNTIME_COMPLETED),
            provider_calls=1 if stage in {TwoStageProgressStage.ROUTING_STARTED, TwoStageProgressStage.ROUTING_COMPLETED} else 2,
            routing_schema_digest="sha256:routing", payload_schema_digest="sha256:payload",
        ))
        write_two_stage_progress(
            path, run_id="run:1", pacing=PacingConfiguration(1.5, 2.5),
            attempts=tuple(attempts), planned_attempt_count=1,
            completed_attempt_count=int(stage is TwoStageProgressStage.RUNTIME_COMPLETED),
            complete=stage is TwoStageProgressStage.RUNTIME_COMPLETED,
        )
        report = json.loads(path.read_text())
        assert report["attempts"][-1]["stage"] == stage.value
        assert not path.with_suffix(".json.tmp").exists()
    encoded = path.read_text().casefold()
    for forbidden in ("raw_response", "raw_prompt", "selector", "credential", "action_id", "destination_id"):
        assert forbidden not in encoded
    assert report["complete"] is True
    assert report["pacing"] == {"inter_stage_delay_s": 1.5, "inter_attempt_delay_s": 2.5}
