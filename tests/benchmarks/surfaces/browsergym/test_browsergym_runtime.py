from pathlib import Path

import pytest

from affordance_runtime.benchmarks.browsergym_runtime import validate_browsergym_runtime_payload


def _payload(executable: Path) -> dict[str, object]:
    return {
        "sys_executable": str(executable),
        "python_version": [3, 12, 3],
        "browsergym_miniwob": "0.14.3",
        "playwright": "1.44.0",
    }


def test_browsergym_runtime_payload_accepts_the_pinned_isolated_stack(tmp_path: Path) -> None:
    result = validate_browsergym_runtime_payload(_payload(tmp_path / "py312/bin/python"), repository_root=tmp_path)

    assert result["ready"] is True
    assert result["python_version"] == "3.12.3"


def test_browsergym_runtime_payload_rejects_repository_venv_and_version_drift(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not run from the repository .venv"):
        validate_browsergym_runtime_payload(_payload(tmp_path / ".venv/bin/python"), repository_root=tmp_path)
    drifted = _payload(tmp_path / "py313/bin/python")
    drifted["python_version"] = [3, 13, 0]
    with pytest.raises(ValueError, match="Python 3.12"):
        validate_browsergym_runtime_payload(drifted, repository_root=tmp_path)
