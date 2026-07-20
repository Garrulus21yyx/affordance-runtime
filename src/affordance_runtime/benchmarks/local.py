"""Executable fixed-seed benchmark for the resettable local SaaS fixture."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.runner import BenchmarkReport, BenchmarkReportWriter, BenchmarkRunner
from affordance_runtime.benchmarks.spec import BenchmarkRun, BenchmarkTask
from affordance_runtime.benchmarks.suites import mvp_benchmark_tasks
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.coordinator import ConfiguredApprovalProvider, PlannerPort, RunCoordinator, RuntimeFeatures
from affordance_runtime.executors import DomExecutor, ExecutorRouter
from affordance_runtime.fixtures import EXPORT_SHA256, PRICING_DATA, create_fixture_server
from affordance_runtime.planners import ExportPlanner, PricingPlanner, SettingsPlanner, extract_pricing
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope


def _json_request(url: str, *, payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method="POST" if body is not None else "GET")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=3.0) as response:  # noqa: S310 - local resettable fixture only
        return json.loads(response.read())


class DriftOnceObserver:
    """Inject target replacement immediately after the planner observation."""

    def __init__(self, session: BrowserSession) -> None:
        self.session = session
        self.injected = False

    def capture(self) -> BrowserSnapshot:
        snapshot = self.session.capture()
        if not self.injected:
            self.session.evaluate(
                "() => { const button = [...document.querySelectorAll('button')].find(x => x.textContent.includes('Enable notifications')); if (button) button.id = 'injected-drift-target'; }"
            )
            self.injected = True
        return snapshot


@dataclass
class LocalSaasRunCase:
    base_url: str
    artifact_root: Path
    headless: bool = True

    def __call__(self, task: BenchmarkTask, variant: str, seed: int) -> BenchmarkRun:
        scenario = self._scenario(task.task_id)
        self._reset(scenario, variant, seed)
        started_at = time.perf_counter()
        if variant in {"direct_playwright", "primitive_browser_agent"}:
            success, unsafe, steps, failure_reason = self._run_direct(scenario, variant, seed)
            return BenchmarkRun(
                task_id=task.task_id,
                success=success,
                steps=steps,
                latency_ms=(time.perf_counter() - started_at) * 1_000.0,
                unsafe_side_effects=unsafe,
                variant=variant,
                seed=seed,
                evaluated_constraints=1,
                constraint_violations=unsafe,
                side_effect_opportunities=1 if scenario == "export" else 0,
                effectful_actions=1 if scenario in {"settings", "export"} else 0,
                failure_reason=failure_reason,
            )
        result, oracle_success = self._run_runtime(scenario, variant, seed)
        event_types = [node.kind for node in result.trace.nodes]
        status_success = result.status == RuntimeStep.DONE
        false_accept = int(status_success and not oracle_success)
        unsafe = int(scenario == "export" and variant == "no_capability_gate" and oracle_success)
        recovery_attempts = event_types.count("RecoveryStarted") + event_types.count("EnvironmentDriftDetected")
        return BenchmarkRun(
            task_id=task.task_id,
            success=status_success and oracle_success,
            steps=result.state.step_count,
            latency_ms=(time.perf_counter() - started_at) * 1_000.0,
            stale_actions_blocked=int("EnvironmentDriftDetected" in event_types),
            effect_receipts=int(bool(result.verification and result.verification.passed and scenario in {"settings", "export"})),
            verifier_false_accepts=false_accept,
            unsafe_side_effects=unsafe,
            recovery_attempts=recovery_attempts,
            recovery_successes=recovery_attempts if recovery_attempts > 0 and status_success and oracle_success else 0,
            semantic_replay_success=status_success and oracle_success,
            variant=variant,
            seed=seed,
            evaluated_constraints=1,
            constraint_violations=unsafe,
            stale_action_opportunities=1 if scenario == "settings" else 0,
            effectful_actions=1 if scenario in {"settings", "export"} else 0,
            failed_outcomes=int(not oracle_success),
            side_effect_opportunities=1 if scenario == "export" else 0,
            trace_path=next((item.path for item in result.artifacts if item.path.endswith("events.jsonl")), ""),
            failure_reason="" if status_success and oracle_success else "oracle_or_runtime_failure",
        )

    @staticmethod
    def _scenario(task_id: str) -> str:
        if "settings" in task_id:
            return "settings"
        if "export" in task_id:
            return "export"
        return "pricing"

    def _reset(self, scenario: str, variant: str, seed: int) -> None:
        del seed
        _json_request(f"{self.base_url}/api/reset", payload={})
        perturbations: list[str] = []
        if scenario == "settings":
            perturbations = ["selector_drift", "async_button_state", "blocking_modal", "transient_settings_error"]
        elif scenario == "export":
            perturbations = ["delayed_download"]
        if variant == "direct_playwright" and scenario == "settings":
            # The stable baseline uses the fixture contract and does not receive
            # the injected transient error intended for recovery/verification.
            perturbations.remove("transient_settings_error")
        _json_request(f"{self.base_url}/api/perturbations", payload={"names": perturbations})

    def _run_direct(self, scenario: str, variant: str, seed: int) -> tuple[bool, int, int, str]:
        del seed
        target = f"{self.base_url}/{ {'pricing': 'pricing', 'settings': 'settings', 'export': 'reports'}[scenario] }"
        try:
            with BrowserSession.launch(target, headless=self.headless) as session:
                if scenario == "pricing":
                    session.click("#show-pro")
                    session.click("#show-enterprise")
                    plans = extract_pricing(str(session.capture().observation.metadata.get("html") or ""))
                    expected_plans: dict[str, dict[str, Any]] = {
                        name: {"users": value["users"], "projects": value["projects"], "support": value["support"], "visible": True}
                        for name, value in PRICING_DATA.items()
                    }
                    return plans == expected_plans, 0, 2, ""
                if scenario == "settings":
                    if variant == "direct_playwright":
                        session.click("#dismiss-modal")
                        session.click("text=Enable notifications")
                    else:
                        session.click("#enable-notifications")
                    return self._wait_setting(), 0, 2, ""
                download = session.download("#export-report", str(self.artifact_root / variant / "downloads"))
                return download["sha256"] == EXPORT_SHA256, 1, 1, ""
        except Exception as exc:
            return False, 0, 0, f"{type(exc).__name__}: {exc}"

    def _wait_setting(self) -> bool:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if _json_request(f"{self.base_url}/api/state")["settings"]["notifications"] == "enabled":
                return True
            time.sleep(0.05)
        return False

    def _run_runtime(self, scenario: str, variant: str, seed: int) -> tuple[Any, bool]:
        target = f"{self.base_url}/{ {'pricing': 'pricing', 'settings': 'settings', 'export': 'reports'}[scenario] }"
        features = RuntimeFeatures(
            preflight=variant != "no_preflight",
            structural_verification=variant != "no_structural_verifier",
            capability_gate=variant != "no_capability_gate",
            recovery=variant != "no_recovery",
        )
        planners: dict[str, PlannerPort] = {
            "pricing": PricingPlanner(),
            "settings": SettingsPlanner(),
            "export": ExportPlanner(),
        }
        planner = planners[scenario]
        with BrowserSession.launch(target, headless=self.headless) as session:
            router = ExecutorRouter()
            router.register(DomExecutor(session))
            observer: Any = DriftOnceObserver(session) if scenario == "settings" else session
            run_id = f"{scenario}-{variant}-seed-{seed}"
            result = RunCoordinator(
                observer=observer,
                planner=planner,
                executor=router,
                approval_provider=(
                    ConfiguredApprovalProvider("benchmark", {"report.export"})
                    if scenario == "export" and variant != "no_capability_gate"
                    else None
                ),
                artifacts=ArtifactStore(self.artifact_root / "runs"),
                features=features,
            ).run_sync(
                TaskEnvelope(
                    run_id,
                    {"pricing": "extract pricing", "settings": "enable notifications", "export": "export report"}[scenario],
                    target=target,
                    constraints={"approval_required": scenario == "export"},
                    capabilities=["settings.write.reversible"] if scenario == "settings" else (["report.export"] if scenario == "export" else []),
                )
            )
        state = _json_request(f"{self.base_url}/api/state")
        if scenario == "pricing":
            oracle = result.result.get("plans") == PRICING_DATA
        elif scenario == "settings":
            oracle = state["settings"]["notifications"] == "enabled"
        else:
            oracle = any(item.get("effect") == "report.export" and item.get("sha256") == EXPORT_SHA256 for item in state["audit_log"])
        return result, oracle


def run_local_benchmark(
    output_dir: Path,
    *,
    seeds: tuple[int, ...] = (0,),
    headless: bool = True,
) -> tuple[BenchmarkReport, dict[str, Path]]:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        runner = BenchmarkRunner(
            mvp_benchmark_tasks(),
            LocalSaasRunCase(base_url, output_dir / "artifacts", headless=headless),
            seeds=seeds,
        )
        report = runner.run()
        paths = BenchmarkReportWriter(output_dir).write(report)
        return report, paths
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
