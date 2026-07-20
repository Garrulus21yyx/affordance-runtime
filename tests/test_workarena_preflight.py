from pathlib import Path

from affordance_runtime.benchmarks.workarena import (
    WORKARENA_PLAYWRIGHT_VERSION,
    inspect_workarena_l1,
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
    report = write_workarena_preflight(tmp_path)

    assert report["oracle_used"] is False
    assert (tmp_path / "workarena-preflight.json").exists()
