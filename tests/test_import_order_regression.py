from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "imports",
    (
        (
            "affordance_runtime.benchmarks.external_smoke.verifier_policy",
            "affordance_runtime.agent",
            "affordance_runtime.model_boundary",
        ),
        (
            "affordance_runtime.model_boundary",
            "affordance_runtime.agent",
            "affordance_runtime.surfaces.browsergym.environment",
        ),
        (
            "affordance_runtime.agent",
            "affordance_runtime.surfaces.browsergym.environment",
            "affordance_runtime.evaluation",
        ),
    ),
)
def test_public_packages_import_in_any_supported_order_in_clean_process(
    imports: tuple[str, ...],
) -> None:
    source = "\n".join(
        [*(f"import {module}" for module in imports), *(
            f"package = __import__({name!r}, fromlist=['*']); "
            "[getattr(package, exported) for exported in package.__all__]"
            for name in ("affordance_runtime.agent", "affordance_runtime.model_boundary")
        )]
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
