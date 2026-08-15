import json

from affordance_runtime.benchmarks.external_smoke.case_environment import external_dependency_status
from affordance_runtime.benchmarks.external_smoke.manifest import (
    EXTERNAL_SMOKE_MANIFEST,
    REVIEWED_TASK_IDS,
    SOURCE_COMMIT,
    external_manifest_digest,
)


def test_adapter_ready_only_from_matching_real_attestation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("affordance_runtime.benchmarks.external_smoke.case_environment.version", lambda _name: "0.14.3")
    attestation = tmp_path / "attestation.json"
    payload = {
        "accepted": True,
        "git_dirty": False,
        "package_version": "0.14.3",
        "source_commit": SOURCE_COMMIT,
        "manifest_digest": external_manifest_digest(EXTERNAL_SMOKE_MANIFEST),
        "task_ids": REVIEWED_TASK_IDS,
        "target_loop_adapter_ready": True,
    }
    attestation.write_text(json.dumps(payload))
    assert external_dependency_status(attestation).target_loop_adapter_ready
    payload["package_version"] = "0.14.2"
    attestation.write_text(json.dumps(payload))
    assert not external_dependency_status(attestation).target_loop_adapter_ready


def test_unknown_task_id_fails_closed_before_environment_use() -> None:
    from affordance_runtime.benchmarks.external_smoke.case_environment import open_browsergym_case

    def reject(task_id, **_kwargs):
        raise AssertionError(f"factory must not receive unknown task: {task_id}")

    try:
        open_browsergym_case("browsergym/miniwob.not-reviewed", 7, gym_factory=reject)
    except ValueError as exc:
        assert "reviewed fixed manifest" in str(exc)
    else:
        raise AssertionError("unknown task ID was not rejected")
