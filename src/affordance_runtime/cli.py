"""Command-line interface for fixture serving, gold-path runs, and baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.approval_contracts import ConfiguredApprovalProvider
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.benchmarks.local import run_local_benchmark
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.coordinator import RuntimeFeatures
from affordance_runtime.evolution_replay import build_evolution_report
from affordance_runtime.executors import DomExecutor, ExecutorRouter
from affordance_runtime.fixtures import serve_fixture
from affordance_runtime.planners import (
    ExportPlanner,
    PricingPlanner,
    PricingTaskPlanner,
    SettingsPlanner,
    export_contract_builder,
    extract_pricing,
    pricing_contract_builder,
    pricing_required_outputs,
    pricing_success_expression,
    settings_contract_builder,
)
from affordance_runtime.planning_contracts import PlannerPort
from affordance_runtime.runtime import RunRequest
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_planner import PlanningRouter


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
    run.add_argument(
        "--task-planning",
        action="store_true",
        help="enable the optional task-planning layer for the reference pricing path",
    )
    run.add_argument(
        "--accepted-profile",
        type=Path,
        help="load a digest-validated registry containing accepted TaskSkill/RecoverySkill artifacts",
    )

    baseline = subcommands.add_parser("baseline", help="run the direct Playwright pricing baseline")
    baseline.add_argument("--target", default="http://127.0.0.1:3000/pricing")
    baseline.add_argument("--headed", action="store_true")

    benchmark = subcommands.add_parser("benchmark", help="run the fixed-seed local SaaS baseline and ablation matrix")
    benchmark.add_argument("--output", type=Path, default=Path("benchmark-results"))
    benchmark.add_argument("--seeds", type=int, default=1)
    benchmark.add_argument("--headed", action="store_true")
    benchmark.add_argument("--base-url", help="use an already-running resettable fixture service")
    benchmark.add_argument(
        "--allow-acceptance-fail",
        action="store_true",
        help="return success after writing a diagnostic report even when release acceptance thresholds fail",
    )

    task_planning = subcommands.add_parser(
        "benchmark-task-planning",
        help="run the controlled Flat/Always-plan/Adaptive task-planning ablation",
    )
    task_planning.add_argument("--output", type=Path, default=Path("task-planning-results"))

    adaptive_routing = subcommands.add_parser(
        "benchmark-adaptive-routing",
        help="run the controlled M8.5 routing/System 1 six-profile ablation",
    )
    adaptive_routing.add_argument(
        "--output",
        type=Path,
        default=Path("adaptive-routing-results"),
    )

    browsergym = subcommands.add_parser(
        "benchmark-browsergym",
        help="run the isolated BrowserGym MiniWoB full-Coordinator track with an external policy",
    )
    browsergym.add_argument("--output", type=Path, default=Path("browsergym-results"))
    browsergym.add_argument("--profile", choices=("smoke", "pr", "diagnostic", "nightly", "release"), default="pr")
    browsergym.add_argument("--policy-command", required=True, help="JSON-lines planner process; no shell is used")
    browsergym.add_argument("--headed", action="store_true")

    browsergym_generalist = subcommands.add_parser(
        "benchmark-browsergym-generalist",
        help="run the isolated BrowserGym MiniWoB track with the configured GeneralistLMPlanner profile",
    )
    browsergym_generalist.add_argument("--output", type=Path, default=Path("browsergym-generalist-results"))
    browsergym_generalist.add_argument(
        "--profile", choices=("smoke", "pr", "diagnostic", "nightly", "release"), default="pr"
    )
    browsergym_generalist.add_argument(
        "--planner-profile",
        choices=("strict-generalist", "historical-compatibility"),
        default="strict-generalist",
        help="behavioral planner identity; compatibility results cannot support generalist claims",
    )
    browsergym_generalist.add_argument("--headed", action="store_true")
    browsergym_generalist.add_argument(
        "--visual-grounding",
        action="store_true",
        help="enable screenshot-only visual fallback when no structured control is available",
    )
    browsergym_generalist.add_argument(
        "--task",
        action="append",
        default=[],
        help="repeatable targeted regression task; does not create an official profile score",
    )
    browsergym_generalist.add_argument(
        "--seed-count",
        type=int,
        help="override profile seed count for a targeted regression replay",
    )
    browsergym_generalist.add_argument(
        "--resume",
        action="store_true",
        help="resume only an identical immutable run after interruption; changed code/prompt/schema/context needs a new --output",
    )
    browsergym_generalist.add_argument("--episode-timeout-s", type=float, default=165.0)
    browsergym_generalist.add_argument("--model-call-timeout-s", type=float, default=10.0)
    browsergym_generalist.add_argument("--max-model-calls", type=int, default=15)
    browsergym_generalist.add_argument("--execution-reserve-s", type=float, default=15.0)

    screenspot = subcommands.add_parser(
        "benchmark-screenspot",
        help="evaluate offline ScreenSpot point-grounding predictions",
    )
    screenspot.add_argument("--annotations", type=Path, required=True)
    screenspot.add_argument("--images", type=Path, required=True)
    screenspot.add_argument("--predictions", type=Path, required=True)
    screenspot.add_argument("--output", type=Path, default=Path("screenspot-results"))

    screenspot_grounder = subcommands.add_parser(
        "benchmark-screenspot-grounder",
        help="generate and score ScreenSpot predictions with the configured visual grounder",
    )
    screenspot_grounder.add_argument("--annotations", type=Path, required=True)
    screenspot_grounder.add_argument("--images", type=Path, required=True)
    screenspot_grounder.add_argument("--output", type=Path, default=Path("screenspot-grounder-results"))

    workarena = subcommands.add_parser(
        "benchmark-workarena-preflight",
        help="inspect isolated WorkArena L1 prerequisites without loading credentials",
    )
    workarena.add_argument("--output", type=Path, default=Path("workarena-results"))
    workarena.add_argument("--runtime-python", type=Path)

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

    ollama_preflight = subcommands.add_parser(
        "provider-preflight-ollama",
        help="record Ollama identity, container GPU visibility, and non-zero model VRAM residency",
    )
    ollama_preflight.add_argument("--output", type=Path, default=Path("artifacts/ollama-preflight.json"))
    ollama_preflight.add_argument("--base-url", default="http://127.0.0.1:11434")
    ollama_preflight.add_argument("--model", default="qwen2.5:7b")
    ollama_preflight.add_argument("--container", default="ollama")
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
        return 0 if args.allow_acceptance_fail or not benchmark_report.acceptance_errors else 1
    if args.command == "benchmark-task-planning":
        from affordance_runtime.benchmarks.task_planning import run_task_planning_ablation

        report = run_task_planning_ablation(args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "benchmark-adaptive-routing":
        from affordance_runtime.benchmarks.adaptive_routing import (
            run_adaptive_routing_ablation,
        )

        report = run_adaptive_routing_ablation(args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
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
        from affordance_runtime.generalist_planner import GeneralistPlannerProfile
        from affordance_runtime.model_port import model_port_from_environment
        from affordance_runtime.visual_grounding import (
            visual_grounder_from_environment,
            visual_region_proposer_from_environment,
        )

        browsergym_report = run_browsergym_miniwob_generalist_suite(
            args.output,
            profile=args.profile,
            model=model_port_from_environment(),
            visual_grounder=visual_grounder_from_environment() if args.visual_grounding else None,
            visual_region_proposer=visual_region_proposer_from_environment() if args.visual_grounding else None,
            task_ids=args.task or None,
            seed_count=args.seed_count,
            headless=not args.headed,
            resume=args.resume,
            episode_timeout_s=args.episode_timeout_s,
            model_call_timeout_s=args.model_call_timeout_s,
            max_model_calls=args.max_model_calls,
            execution_reserve_s=args.execution_reserve_s,
            planner_profile=GeneralistPlannerProfile(args.planner_profile),
        )
        print(json.dumps(browsergym_report, indent=2, sort_keys=True))
        return 0 if not browsergym_report["acceptance_errors"] else 1
    if args.command == "benchmark-screenspot":
        from affordance_runtime.benchmarks.screenspot import run_screenspot_offline_suite

        report = run_screenspot_offline_suite(args.annotations, args.images, args.predictions, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "benchmark-screenspot-grounder":
        from affordance_runtime.benchmarks.screenspot import run_screenspot_grounder_suite
        from affordance_runtime.visual_grounding import visual_grounder_from_environment

        report = run_screenspot_grounder_suite(
            args.annotations, args.images, visual_grounder_from_environment(), args.output
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "benchmark-workarena-preflight":
        from affordance_runtime.benchmarks.workarena import write_workarena_preflight

        report = write_workarena_preflight(args.output, runtime_python=args.runtime_python)
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
    if args.command == "provider-preflight-ollama":
        from affordance_runtime.provider_preflight import write_ollama_gpu_preflight

        ollama_report = write_ollama_gpu_preflight(
            args.output,
            base_url=args.base_url,
            model=args.model,
            container_name=args.container,
        )
        print(json.dumps(ollama_report.to_dict(), indent=2, sort_keys=True))
        return 0 if ollama_report.ready else 1
    if args.command == "run":
        result = run_scenario(
            args.scenario,
            args.target,
            args.artifacts,
            headless=not args.headed,
            approve=args.approve,
            task_planning=args.task_planning,
            accepted_profile=args.accepted_profile,
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
    task_planning: bool = False,
    accepted_profile: Path | None = None,
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
    if task_planning and scenario != "pricing":
        raise ValueError("reference task planning is currently defined for pricing only")
    selected_run_id = run_id or f"{scenario}-gold-path"
    loaded_profile = None
    if accepted_profile is not None:
        from affordance_runtime.evolution import AcceptedProfileLoader

        loaded_profile = AcceptedProfileLoader(accepted_profile).load()
    task_spec = None
    if task_planning:
        task_spec = TaskSpec(
            task_id=selected_run_id,
            revision=1,
            objective="Reveal Pro and Enterprise plan limits with structural evidence.",
            operation_class=OperationClass.READ_ONLY,
            targets=("Pro", "Enterprise"),
            success_criteria=("both requested pricing plans are structurally visible",),
            success=pricing_success_expression(),
            required_outputs=pricing_required_outputs(),
            evidence_requirements=("post-action DOM evidence for each pricing plan",),
            source_request_ref="reference-cli",
        )
    elif loaded_profile is not None:
        profile_objectives = {
            "pricing": "Extract Pro and Enterprise plan limits with structural evidence.",
            "settings": "Enable the reversible notifications setting and verify persisted state.",
            "export": "Export a report only after explicit approval and return the file receipt.",
        }
        task_spec = TaskSpec(
            task_id=selected_run_id,
            revision=1,
            objective=profile_objectives[scenario],
            operation_class={
                "pricing": OperationClass.READ_ONLY,
                "settings": OperationClass.REVERSIBLE_WRITE,
                "export": OperationClass.EXTERNAL_SIDE_EFFECT,
            }[scenario],
            targets={
                "pricing": ("Pro", "Enterprise"),
                "settings": ("notifications",),
                "export": ("report",),
            }[scenario],
            success_criteria={
                "pricing": ("both requested pricing plans are structurally visible",),
                "settings": ("notification setting is persisted",),
                "export": ("approved report file is exported",),
            }[scenario],
            success=(pricing_success_expression() if scenario == "pricing" else None),
            required_outputs=(
                pricing_required_outputs() if scenario == "pricing" else ()
            ),
            evidence_requirements=("independent post-action evidence",),
            requested_capabilities=tuple(
                capabilities_override if capabilities_override is not None else capabilities[scenario]
            ),
            source_request_ref="reference-cli-accepted-profile",
        )
    if task_spec is None:
        task_spec = TaskSpec(
            task_id=selected_run_id,
            revision=1,
            objective={
                "pricing": "Extract Pro and Enterprise plan limits with structural evidence.",
                "settings": "Enable the reversible notifications setting and verify persisted state.",
                "export": "Export a report only after explicit approval and return the file receipt.",
            }[scenario],
            operation_class={
                "pricing": OperationClass.READ_ONLY,
                "settings": OperationClass.REVERSIBLE_WRITE,
                "export": OperationClass.EXTERNAL_SIDE_EFFECT,
            }[scenario],
            targets={
                "pricing": ("Pro", "Enterprise"),
                "settings": ("notifications",),
                "export": ("report",),
            }[scenario],
            success_criteria=("requested scenario result is independently verified",),
            success=(pricing_success_expression() if scenario == "pricing" else None),
            required_outputs=(
                pricing_required_outputs() if scenario == "pricing" else ()
            ),
            evidence_requirements=("independent post-action evidence",),
            requested_capabilities=tuple(
                capabilities_override
                if capabilities_override is not None
                else capabilities[scenario]
            ),
            source_request_ref="reference-cli",
        )
    runtime_features = (
        loaded_profile.profile.features_for(selected_run_id)
        if loaded_profile is not None
        else RuntimeFeatures()
    )
    with BrowserSession.launch(target, headless=headless) as session:
        router = ExecutorRouter()
        router.register(DomExecutor(session))
        result = compose_run_coordinator(
            observer=session,
            planner=planners[scenario],
            executor=router,
            contract_builder={
                "pricing": pricing_contract_builder(),
                "settings": settings_contract_builder(
                    target.rsplit("/", 1)[0] + "/api/state"
                ),
                "export": export_contract_builder(),
            }[scenario],
            artifacts=ArtifactStore(artifact_root),
            approval_provider=approval_provider,
            task_planner=(
                PricingTaskPlanner()
                if task_planning
                else PlanningRouter()
                if runtime_features.structural_verification
                else None
            ),
            features=runtime_features,
            task_skill_runtime=(loaded_profile.task_skill_runtime if loaded_profile is not None else None),
            runtime_profile_digest=(loaded_profile.profile_digest if loaded_profile is not None else ""),
            loaded_profile_artifact_ids=(loaded_profile.artifact_ids if loaded_profile is not None else ()),
        ).run_sync(
            RunRequest(
                task_id=selected_run_id,
                goal=(
                    task_spec.objective
                    if task_spec is not None
                    else {
                        "pricing": "Extract Pro and Enterprise plan limits with structural evidence.",
                        "settings": "Enable the reversible notifications setting and verify persisted state.",
                        "export": "Export a report only after explicit approval and return the file receipt.",
                    }[scenario]
                ),
                target=target,
                constraints=constraints_override
                if constraints_override is not None
                else {
                    "read_only": scenario == "pricing",
                    "must_return_evidence": True,
                    "approval_required": scenario == "export",
                },
                capabilities=capabilities_override if capabilities_override is not None else capabilities[scenario],
                task_spec=task_spec,
            )
        )
    return {
        "run_id": result.run_id,
        "status": result.status.value,
        "result": result.result,
        "error_code": result.error_code.value if result.error_code else None,
        "artifacts": [item.path for item in result.artifacts],
        "runtime_profile_digest": loaded_profile.profile_digest if loaded_profile is not None else "",
        "loaded_profile_artifact_ids": list(loaded_profile.artifact_ids) if loaded_profile is not None else [],
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
        "plans": {
            name: {key: value for key, value in plan.items() if key != "visible"} for name, plan in plans.items()
        },
    }
