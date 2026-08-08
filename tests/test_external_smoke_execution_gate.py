from affordance_runtime.benchmarks.external_smoke.contracts import ExternalBenchmarkAdmission
from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST
from affordance_runtime.benchmarks.external_smoke.runner import run_external_smoke


def test_external_runner_requires_admission_environment_and_execute_flag(monkeypatch) -> None:
    calls = 0

    def executor(_manifest):
        nonlocal calls
        calls += 1
        return ()

    admitted = ExternalBenchmarkAdmission(True, ())
    blocked = ExternalBenchmarkAdmission(False, ("blocked",))
    monkeypatch.delenv("RUN_EXTERNAL_SMOKE", raising=False)
    assert not run_external_smoke(admitted, EXTERNAL_SMOKE_MANIFEST, execute=True, executor=executor).executed
    monkeypatch.setenv("RUN_EXTERNAL_SMOKE", "1")
    assert not run_external_smoke(admitted, EXTERNAL_SMOKE_MANIFEST, execute=False, executor=executor).executed
    assert not run_external_smoke(blocked, EXTERNAL_SMOKE_MANIFEST, execute=True, executor=executor).executed
    assert calls == 0

    assert run_external_smoke(admitted, EXTERNAL_SMOKE_MANIFEST, execute=True, executor=executor).executed
    assert calls == 1
