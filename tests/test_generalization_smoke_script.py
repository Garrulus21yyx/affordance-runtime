from __future__ import annotations

import sys

from scripts import generalization_smoke


def test_generalization_smoke_acceptance_failure_requires_explicit_diagnostic_flag(
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    def fake_suite(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        return {
            "acceptance": "failed",
            "acceptance_errors": ["visual heldout success_rate below threshold"],
        }

    monkeypatch.setattr(generalization_smoke, "run_generalization_suite", fake_suite)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generalization_smoke.py",
            "--benchmark",
            str(tmp_path / "benchmark.json"),
            "--output",
            str(tmp_path / "generalization"),
        ],
    )
    assert generalization_smoke.main() == 1

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generalization_smoke.py",
            "--benchmark",
            str(tmp_path / "benchmark.json"),
            "--output",
            str(tmp_path / "generalization"),
            "--allow-acceptance-fail",
        ],
    )
    assert generalization_smoke.main() == 0
