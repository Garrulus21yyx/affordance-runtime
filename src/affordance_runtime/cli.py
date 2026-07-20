"""Command-line interface for fixture serving, gold-path runs, and baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.local import run_local_benchmark
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.coordinator import ConfiguredApprovalProvider, PlannerPort, RunCoordinator
from affordance_runtime.evolution_replay import build_evolution_report
from affordance_runtime.executors import DomExecutor, ExecutorRouter
from affordance_runtime.fixtures import serve_fixture
from affordance_runtime.planners import ExportPlanner, PricingPlanner, SettingsPlanner, extract_pricing
from affordance_runtime.runtime import TaskEnvelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="affordance-runtime")
    subcommands = parser.add_subparsers(dest="command", required=True)

    fixture = subcommands.add_parser("serve-fixture", help="serve the resettable local SaaS fixture")
    fixture.add_argument("--host", default="127.0.0.1")
    fixture.add_argument("--port", type=int, default=3000)

    run = subcommands.add_parser("run", help="run a bounded GUI task")
    run.add_argument("--scenario", choices=["pricing", "settings", "export"], default="pricing")
    run.add_argument("--target")
    run.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    run.add_argument("--headed", action="store_true")
    run.add_argument("--approve", action="store_true", help="explicitly approve the export capability")

    baseline = subcommands.add_parser("baseline", help="run the direct Playwright pricing baseline")
    baseline.add_argument("--target", default="http://127.0.0.1:3000/pricing")
    baseline.add_argument("--headed", action="store_true")

    benchmark = subcommands.add_parser("benchmark", help="run the fixed-seed local SaaS baseline and ablation matrix")
    benchmark.add_argument("--output", type=Path, default=Path("benchmark-results"))
    benchmark.add_argument("--seeds", type=int, default=1)
    benchmark.add_argument("--headed", action="store_true")
    benchmark.add_argument("--base-url", help="use an already-running resettable fixture service")

    browsergym = subcommands.add_parser(
        "benchmark-browsergym",
        help="run the isolated BrowserGym MiniWoB full-Coordinator track with an external policy",
    )
    browsergym.add_argument("--output", type=Path, default=Path("browsergym-results"))
    browsergym.add_argument("--profile", choices=("pr", "nightly", "release"), default="pr")
    browsergym.add_argument("--policy-command", required=True, help="JSON-lines planner process; no shell is used")
    browsergym.add_argument("--headed", action="store_true")

    browsergym_generalist = subcommands.add_parser(
        "benchmark-browsergym-generalist",
        help="run the isolated BrowserGym MiniWoB track with the configured GeneralistLMPlanner profile",
    )
    browsergym_generalist.add_argument("--output", type=Path, default=Path("browsergym-generalist-results"))
    browsergym_generalist.add_argument("--profile", choices=("pr", "nightly", "release"), default="pr")
    browsergym_generalist.add_argument("--headed", action="store_true")
    browsergym_generalist.add_argument("--resume", action="store_true", help="reuse complete per-episode checkpoints in --output")

    screenspot = subcommands.add_parser(
        "benchmark-screenspot",
        help="evaluate offline ScreenSpot point-grounding predictions",
    )
    screenspot.add_argument("--annotations", type=Path, required=True)
    screenspot.add_argument("--images", type=Path, required=True)
    screenspot.add_argument("--predictions", type=Path, required=True)
    screenspot.add_argument("--output", type=Path, default=Path("screenspot-results"))

    workarena = subcommands.add_parser(
        "benchmark-workarena-preflight",
        help="inspect isolated WorkArena L1 prerequisites without loading credentials",
    )
    workarena.add_argument("--output", type=Path, default=Path("workarena-results"))

    webarena_verified = subcommands.add_parser(
        "prepare-webarena-verified-subset",
        help="write a reproducible 30--50 task WebArena-Verified manifest for official offline scoring",
    )
    webarena_verified.add_argument("--dataset", type=Path, required=True)
    webarena_verified.add_argument("--output", type=Path, default=Path("webarena-verified-subset.json"))
    webarena_verified.add_argument("--count", type=int, default=30)

    webarena_evaluate = subcommands.add_parser(
        "evaluate-webarena-verified",
        help="delegate a prepared manifest to the upstream deterministic WebArena-Verified evaluator",
    )
    webarena_evaluate.add_argument("--manifest", type=Path, required=True)
    webarena_evaluate.add_argument("--agent-logs", type=Path, required=True)
    webarena_evaluate.add_argument("--config", type=Path)
    webarena_evaluate.add_argument("--executable", default="webarena-verified")
    webarena_evaluate.add_argument("--output", type=Path, default=Path("webarena-verified-evaluation.json"))

    wasp = subcommands.add_parser(
        "prepare-wasp-subset",
        help="write a digest-bound WASP security subset without copying malicious prompt content",
    )
    wasp.add_argument("--config", type=Path, required=True)
    wasp.add_argument("--output", type=Path, default=Path("wasp-subset.json"))
    wasp.add_argument("--count", type=int, default=12)

    evolve = subcommands.add_parser("evolve", help="classify a real failed run and apply the regression replay gate")
    evolve.add_argument("--benchmark-report", type=Path, required=True)
    evolve.add_argument("--output", type=Path, default=Path("evolution-results"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve-fixture":
        serve_fixture(args.host, args.port)
        return 0
    if args.command == "baseline":
        result = run_pricing_baseline(args.target, headless=not args.headed)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "benchmark":
        benchmark_report, paths = run_local_benchmark(
            args.output,
            seeds=tuple(range(args.seeds)),
            headless=not args.headed,
            base_url=args.base_url,
        )
        print(
            json.dumps(
                {
                    "suite_version": benchmark_report.suite_version,
                    "runs": len(benchmark_report.runs),
                    "reports": {name: str(path) for name, path in paths.items()},
                    "acceptance": "passed" if not benchmark_report.acceptance_errors else "failed",
                    "acceptance_errors": benchmark_report.acceptance_errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not benchmark_report.acceptance_errors else 1
    if args.command == "benchmark-browsergym":
        from affordance_runtime.benchmarks.browsergym import run_browsergym_miniwob_suite

        browsergym_report = run_browsergym_miniwob_suite(
            args.output,
            profile=args.profile,
            policy_command=args.policy_command,
            headless=not args.headed,
        )
        print(json.dumps(browsergym_report, indent=2, sort_keys=True))
        return 0 if not browsergym_report["acceptance_errors"] else 1
    if args.command == "benchmark-browsergym-generalist":
        from affordance_runtime.benchmarks.browsergym import run_browsergym_miniwob_generalist_suite
        from affordance_runtime.model_port import model_port_from_environment

        browsergym_report = run_browsergym_miniwob_generalist_suite(
            args.output,
            profile=args.profile,
            model=model_port_from_environment(),
            headless=not args.headed,
            resume=args.resume,
        )
        print(json.dumps(browsergym_report, indent=2, sort_keys=True))
        return 0 if not browsergym_report["acceptance_errors"] else 1
    if args.command == "benchmark-screenspot":
        from affordance_runtime.benchmarks.screenspot import run_screenspot_offline_suite

        report = run_screenspot_offline_suite(
            args.annotations, args.images, args.predictions, args.output
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "benchmark-workarena-preflight":
        from affordance_runtime.benchmarks.workarena import write_workarena_preflight

        report = write_workarena_preflight(args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ready"] else 1
    if args.command == "prepare-webarena-verified-subset":
        from affordance_runtime.benchmarks.webarena_verified import write_webarena_verified_subset

        manifest = write_webarena_verified_subset(args.dataset, args.output, count=args.count)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.command == "evaluate-webarena-verified":
        from affordance_runtime.benchmarks.webarena_verified import evaluate_webarena_verified_manifest

        report = evaluate_webarena_verified_manifest(
            args.manifest, args.agent_logs, config_path=args.config, executable=args.executable
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "prepare-wasp-subset":
        from affordance_runtime.benchmarks.wasp import write_wasp_subset

        manifest = write_wasp_subset(args.config, args.output, count=args.count)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.command == "evolve":
        evolution_report = build_evolution_report(args.benchmark_report, args.output)
        print(
            json.dumps(
                {
                    "source_task": evolution_report.source_run.task_id,
                    "source_variant": evolution_report.source_run.variant,
                    "artifact": evolution_report.artifact.id,
                    "decision": evolution_report.decision.value,
                    "output": str(args.output),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if evolution_report.decision.value == "accepted" else 1
    if args.command == "run":
        result = run_scenario(
            args.scenario,
            args.target,
            args.artifacts,
            headless=not args.headed,
            approve=args.approve,
        )
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result["status"] == "done" else 1
    return 2


def run_scenario(
    scenario: str,
    target: str | None,
    artifact_root: Path,
    *,
    headless: bool = True,
    approve: bool = False,
    run_id: str | None = None,
    approval_approver: str = "cli-user",
    constraints_override: dict[str, Any] | None = None,
    capabilities_override: list[str] | None = None,
) -> dict[str, object]:
    paths = {"pricing": "/pricing", "settings": "/settings", "export": "/reports"}
    target = target or f"http://127.0.0.1:3000{paths[scenario]}"
    planners: dict[str, PlannerPort] = {
        "pricing": PricingPlanner(),
        "settings": SettingsPlanner(),
        "export": ExportPlanner(),
    }
    capabilities = {
        "pricing": [],
        "settings": ["settings.write.reversible"],
        "export": ["report.export"],
    }
    approval_provider = (
        ConfiguredApprovalProvider(approval_approver, {"report.export"}) if scenario == "export" and approve else None
    )
    with BrowserSession.launch(target, headless=headless) as session:
        router = ExecutorRouter()
        router.register(DomExecutor(session))
        result = RunCoordinator(
            observer=session,
            planner=planners[scenario],
            executor=router,
            artifacts=ArtifactStore(artifact_root),
            approval_provider=approval_provider,
        ).run_sync(
            TaskEnvelope(
                task_id=run_id or f"{scenario}-gold-path",
                goal={
                    "pricing": "Extract Pro and Enterprise plan limits with structural evidence.",
                    "settings": "Enable the reversible notifications setting and verify persisted state.",
                    "export": "Export a report only after explicit approval and return the file receipt.",
                }[scenario],
                target=target,
                constraints=constraints_override
                if constraints_override is not None
                else {
                    "read_only": scenario == "pricing",
                    "must_return_evidence": True,
                    "approval_required": scenario == "export",
                },
                capabilities=capabilities_override if capabilities_override is not None else capabilities[scenario],
            )
        )
    return {
        "run_id": result.run_id,
        "status": result.status.value,
        "result": result.result,
        "error_code": result.error_code.value if result.error_code else None,
        "artifacts": [item.path for item in result.artifacts],
    }


def run_pricing(target: str, artifact_root: Path, *, headless: bool = True) -> dict[str, object]:
    return run_scenario("pricing", target, artifact_root, headless=headless)


def run_pricing_baseline(target: str, *, headless: bool = True) -> dict[str, object]:
    with BrowserSession.launch(target, headless=headless) as session:
        session.click("#show-pro")
        session.click("#show-enterprise")
        snapshot = session.capture()
    plans = extract_pricing(str(snapshot.observation.metadata.get("html") or ""))
    return {
        "status": "done" if plans and all(plan["visible"] for plan in plans.values()) else "failed",
        "plans": {name: {key: value for key, value in plan.items() if key != "visible"} for name, plan in plans.items()},
    }
