from types import SimpleNamespace

from affordance_runtime.benchmarks.target_loop import cli


def test_webarena_target_loop_fails_before_agent_when_w0_admission_rejects(tmp_path, monkeypatch) -> None:
    calls = []

    def reject(**kwargs):
        calls.append(kwargs)
        return {
            "ready": False,
            "acceptance_errors": ["environment:wa_map_integrity_failed:detail_http_error"],
        }

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("Agent suite must not start in an invalid environment")

    monkeypatch.setattr(cli, "inspect_webarena_verified_w0_readiness", reject)
    monkeypatch.setattr(cli, "configured_browsergym_python", lambda: tmp_path / "python")
    monkeypatch.setattr(cli, "_run_benchmark", must_not_run)

    result = cli._run_foreground_benchmark(
        SimpleNamespace(suite_id="webarena-verified-w2"),
        tmp_path,
    )

    assert result == 2
    assert calls == [
        {
            "runtime_python": tmp_path / "python",
            "output_path": tmp_path / "w0-admission.json",
            "exercise_environment": False,
        }
    ]


def test_webarena_target_loop_starts_agent_only_after_w0_admission_passes(tmp_path, monkeypatch) -> None:
    ran = []

    monkeypatch.setattr(
        cli,
        "inspect_webarena_verified_w0_readiness",
        lambda **_kwargs: {"ready": True, "acceptance_errors": []},
    )
    monkeypatch.setattr(cli, "configured_browsergym_python", lambda: tmp_path / "python")

    async def accepted(manifest, output_dir):
        ran.append((manifest, output_dir))
        return 0

    monkeypatch.setattr(cli, "_run_benchmark", accepted)
    manifest = SimpleNamespace(suite_id="webarena-verified-w2")

    result = cli._run_foreground_benchmark(manifest, tmp_path)

    assert result == 0
    assert ran == [(manifest, tmp_path)]
