from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from affordance_runtime import cli


def test_benchmark_acceptance_failure_can_be_recorded_without_promotion_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report = SimpleNamespace(
        suite_version="local-saas-v2",
        runs=[object()],
        acceptance_errors=["full_runtime task_success_rate=0.6667 violates min threshold 1.0000"],
    )

    def fake_run_local_benchmark(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        return report, {"json": tmp_path / "benchmark-report.json"}

    monkeypatch.setattr(cli, "run_local_benchmark", fake_run_local_benchmark)

    assert cli.main(["benchmark", "--output", str(tmp_path)]) == 1
    assert cli.main(["benchmark", "--output", str(tmp_path), "--allow-acceptance-fail"]) == 0

