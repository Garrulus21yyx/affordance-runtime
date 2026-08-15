from pathlib import Path

from affordance_runtime.benchmarks.workarena import (
    WORKARENA_PLAYWRIGHT_VERSION,
    configured_workarena_python,
    inspect_workarena_l1,
    inspect_workarena_runtime,
    validate_workarena_runtime_payload,
    write_workarena_preflight,
)


def test_workarena_preflight_accepts_complete_explicit_instance_without_exposing_values() -> None:
    report = inspect_workarena_l1(
        environment={
            "SNOW_INSTANCE_URL": "https://example.invalid",
            "SNOW_INSTANCE_UNAME": "admin",
            "SNOW_INSTANCE_PWD": "secret",
        },
        package_version="0.5.3",
        playwright_version=WORKARENA_PLAYWRIGHT_VERSION,
        l1_task_count=33,
    )

    assert report.ready is True
    assert report.instance_source == "explicit_instance"
    assert report.errors == ()
    assert "secret" not in str(report)


def test_workarena_preflight_reports_incomplete_install_and_credentials() -> None:
    report = inspect_workarena_l1(
        environment={"SNOW_INSTANCE_URL": "https://example.invalid"},
        package_version="",
        playwright_version="1.61.0",
        l1_task_count=None,
    )

    assert report.ready is False
    assert report.instance_source == "unconfigured"
    assert report.errors == (
        "browsergym-workarena is not installed",
        "WorkArena requires playwright==1.44.0",
        "ServiceNow instance configuration is incomplete",
        "configure ServiceNow instance credentials or gated WorkArena instance access",
        "WorkArena L1 task registration is unavailable",
    )


def test_workarena_preflight_writes_non_oracle_report(tmp_path: Path) -> None:
    report = write_workarena_preflight(
        tmp_path,
        runtime_python=tmp_path / "missing-workarena/bin/python",
        environment={},
    )

    assert report["oracle_used"] is False
    assert report["ready"] is False
    assert report["runtime"]["sys_executable"].endswith("missing-workarena/bin/python")
    assert (tmp_path / "workarena-preflight.json").exists()


def test_workarena_runtime_payload_accepts_dedicated_pinned_stack(tmp_path: Path) -> None:
    report = validate_workarena_runtime_payload(
        {
            "sys_executable": str(tmp_path / "workarena/bin/python"),
            "python_version": [3, 12, 3],
            "browsergym_workarena": "0.5.3",
            "playwright": WORKARENA_PLAYWRIGHT_VERSION,
            "l1_task_count": 33,
        },
        repository_root=tmp_path,
    )

    assert report.ready is True
    assert report.python_version == "3.12.3"
    assert report.package_version == "0.5.3"


def test_workarena_runtime_rejects_repository_venv_and_version_drift(tmp_path: Path) -> None:
    report = validate_workarena_runtime_payload(
        {
            "sys_executable": str(tmp_path / ".venv/bin/python"),
            "python_version": [3, 13, 0],
            "browsergym_workarena": "0.5.3",
            "playwright": "1.61.0",
            "l1_task_count": 32,
        },
        repository_root=tmp_path,
    )

    assert report.ready is False
    assert report.errors == (
        "WorkArena must not run from the repository .venv",
        "WorkArena requires playwright==1.44.0",
        "expected 33 WorkArena L1 tasks, found 32",
    )


def test_workarena_runtime_probe_uses_credential_free_environment(tmp_path: Path) -> None:
    executable = tmp_path / "workarena-python"
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    calls: list[dict[str, object]] = []

    class Completed:
        returncode = 0
        stdout = '{"sys_executable":"/isolated/python","python_version":[3,12,3],"browsergym_workarena":"0.5.3","playwright":"1.44.0","l1_task_count":33}\n'

    def runner(command: list[str], **kwargs: object) -> Completed:
        calls.append({"command": command, **kwargs})
        return Completed()

    report = inspect_workarena_runtime(executable, repository_root=tmp_path, runner=runner)

    assert report.ready is True
    assert calls[0]["env"] == {"PATH": calls[0]["env"]["PATH"], "PYTHONIOENCODING": "utf-8"}
    assert "SNOW_INSTANCE_PWD" not in calls[0]["env"]


def test_workarena_runtime_path_uses_explicit_environment_without_dotenv(tmp_path: Path) -> None:
    selected = configured_workarena_python(
        {"AFFORDANCE_WORKARENA_PYTHON": str(tmp_path / "python")}
    )

    assert selected == tmp_path / "python"
