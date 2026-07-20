"""Apply executable evolution proposals and collect fresh replay evidence."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from affordance_runtime.benchmarks.local import LocalSaasRunCase
from affordance_runtime.benchmarks.metrics import aggregate
from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.benchmarks.suites import mvp_benchmark_tasks
from affordance_runtime.evolution import (
    CandidateRuntimeProfile,
    EvolutionArtifact,
    EvolutionArtifactType,
    EvolutionRegistry,
    EvolutionRegistryStore,
    EvolutionStatus,
    FailureClassifier,
    MetricDirection,
    RegressionRule,
    RuntimePatchPayload,
)
from affordance_runtime.fixtures import create_fixture_server


@dataclass(frozen=True)
class ReplayRequest:
    category: str
    task_id: str
    seed: int


@dataclass(frozen=True)
class ExecutedReplay:
    category: str
    run: BenchmarkRun


@dataclass(frozen=True)
class ReplayEvidence:
    category: str
    task_id: str
    variant: str
    seed: int
    success: bool
    trace_path: str
    unsafe_side_effects: int = 0


@dataclass
class EvolutionReplayReport:
    source_run: BenchmarkRun
    proposal: dict[str, Any]
    artifact: EvolutionArtifact
    replay_evidence: list[ReplayEvidence]
    decision: EvolutionStatus
    candidate_runtime_id: str
    payload_path: str
    registry_path: str
    rollback_proof_path: str
    rollback_verified: bool


ReplayRunner = Callable[[list[ReplayRequest], EvolutionArtifact, Path], list[ExecutedReplay]]
MANDATORY_REPLAY_CATEGORIES = {"original", "task_family", "global_smoke", "safety_smoke"}
CANDIDATE_RUNTIME_ID = "fresh-runtime-no-structural-verifier"


def build_evolution_report(
    benchmark_report_path: Path,
    output_dir: Path,
    *,
    replay_runner: ReplayRunner | None = None,
) -> EvolutionReplayReport:
    benchmark = json.loads(benchmark_report_path.read_text(encoding="utf-8"))
    runs = [BenchmarkRun(**row) for row in benchmark["runs"]]
    source = next((run for run in runs if not run.success and run.verifier_false_accepts), None)
    if source is None:
        raise ValueError("benchmark report contains no executable verifier failure")

    classifier = FailureClassifier()
    proposal = classifier.propose(source)
    if proposal.artifact_type != EvolutionArtifactType.VERIFIER_PATCH:
        raise ValueError(f"first executable candidate only supports verifier patches, got {proposal.artifact_type.value}")
    payload = RuntimePatchPayload(
        schema_version="1.0",
        patch_kind="runtime_features",
        task_ids=[source.task_id],
        feature_overrides={"structural_verification": True},
    )
    payload.validate()
    artifact = EvolutionArtifact(
        id=f"{proposal.artifact_type.value}-{source.task_id}",
        artifact_type=proposal.artifact_type.value,
        summary=proposal.change_summary,
        applicability=proposal.applicability,
        source_traces=[source.trace_path],
        negative_examples=[f"{source.task_id}:{source.variant}:seed-{source.seed}"],
        source_runtime_version="0.1.0",
        target_suite_versions=[str(benchmark["suite_version"])],
        rollback_artifact="built-in-runtime-defaults",
        payload=payload.to_dict(),
        payload_digest=payload.digest(),
    )

    requests = _replay_requests(source)
    executed = (replay_runner or run_fresh_candidate_replays)(requests, artifact, output_dir / "candidate-runs")
    evidence = [_evidence(item.category, item.run) for item in executed]
    family_runs = [item.run for item in executed if item.category == "task_family"]
    metrics = aggregate(family_runs).values
    artifact.regression_results = {
        "task_success_rate": metrics["task_success_rate"],
        "unsafe_side_effect_rate": metrics["unsafe_side_effect_rate"],
        "verifier_false_accept_rate": metrics["verifier_false_accept_rate"],
    }

    registry = EvolutionRegistry()
    registry.propose(artifact)
    categories = {item.category for item in evidence if item.success}
    if MANDATORY_REPLAY_CATEGORIES <= categories:
        decision = registry.accept_if_regression_passes(
            artifact.id,
            rules=[
                RegressionRule("task_success_rate", MetricDirection.HIGHER_IS_BETTER, 1.0),
                RegressionRule("unsafe_side_effect_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("verifier_false_accept_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
            ],
        )
    else:
        artifact.status = EvolutionStatus.QUARANTINED
        missing = sorted(MANDATORY_REPLAY_CATEGORIES - categories)
        artifact.decision_reason = f"missing successful replay categories: {', '.join(missing)}"
        decision = artifact.status

    payload_path = output_dir / "artifacts" / artifact.id / artifact.version / "payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(artifact.payload, indent=2, sort_keys=True), encoding="utf-8")
    registry_path = output_dir / "registry.json"
    EvolutionRegistryStore(registry_path).save(registry)
    rollback_path = output_dir / "rollback-proof.json"
    rollback_verified = _prove_persisted_load_and_rollback(registry, artifact.id, rollback_path)

    report = EvolutionReplayReport(
        source,
        asdict(proposal),
        artifact,
        evidence,
        decision,
        CANDIDATE_RUNTIME_ID,
        str(payload_path),
        str(registry_path),
        str(rollback_path),
        rollback_verified,
    )
    _write_report(report, output_dir, str(benchmark["suite_version"]))
    return report


def run_fresh_candidate_replays(
    requests: list[ReplayRequest],
    artifact: EvolutionArtifact,
    artifact_root: Path,
) -> list[ExecutedReplay]:
    """Load the proposal into a fresh profile and execute every replay in Chromium."""

    profile = CandidateRuntimeProfile()
    profile.load(artifact, allow_candidate=True)
    tasks = {task.task_id: task for task in mvp_benchmark_tasks()}
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        run_case = LocalSaasRunCase(base_url, artifact_root)
        executed: list[ExecutedReplay] = []
        for index, request in enumerate(requests):
            task = tasks[request.task_id]
            variant = f"candidate_{request.category}_{index}_{artifact.id}"
            run = run_case.run_runtime_case(task, variant, request.seed, profile.features_for(task.task_id))
            executed.append(ExecutedReplay(request.category, run))
        return executed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _replay_requests(source: BenchmarkRun) -> list[ReplayRequest]:
    task_ids = [task.task_id for task in mvp_benchmark_tasks()]
    pricing = next(task_id for task_id in task_ids if "read_only" in task_id)
    export = next(task_id for task_id in task_ids if "export" in task_id)
    return [
        ReplayRequest("original", source.task_id, source.seed),
        *(ReplayRequest("task_family", task_id, source.seed) for task_id in task_ids),
        ReplayRequest("global_smoke", pricing, source.seed),
        ReplayRequest("safety_smoke", export, source.seed),
    ]


def _evidence(category: str, run: BenchmarkRun) -> ReplayEvidence:
    return ReplayEvidence(
        category,
        run.task_id,
        run.variant,
        run.seed,
        run.success and run.unsafe_side_effects == 0 and run.verifier_false_accepts == 0,
        run.trace_path,
        run.unsafe_side_effects,
    )


def _prove_persisted_load_and_rollback(
    registry: EvolutionRegistry,
    artifact_id: str,
    rollback_path: Path,
) -> bool:
    if registry.artifacts[artifact_id].status != EvolutionStatus.ACCEPTED:
        EvolutionRegistryStore(rollback_path).save(deepcopy(registry))
        return False
    persisted_path = rollback_path.with_name("accepted-load-proof.json")
    EvolutionRegistryStore(persisted_path).save(registry)
    persisted = EvolutionRegistryStore(persisted_path).load()
    profile = CandidateRuntimeProfile()
    profile.load(persisted.artifacts[artifact_id])
    enabled = profile.features_for("reversible_settings_update").structural_verification
    profile.rollback(artifact_id)
    disabled_after_runtime_rollback = not profile.features_for("reversible_settings_update").structural_verification

    rolled_back = deepcopy(persisted)
    rolled_back.rollback(artifact_id, reason="M6 rollback proof", reviewer="automated-regression-gate")
    EvolutionRegistryStore(rollback_path).save(rolled_back)
    reloaded = EvolutionRegistryStore(rollback_path).load()
    rejected_after_registry_rollback = False
    try:
        CandidateRuntimeProfile().load(reloaded.artifacts[artifact_id])
    except ValueError:
        rejected_after_registry_rollback = True
    return enabled and disabled_after_runtime_rollback and rejected_after_registry_rollback


def _write_report(report: EvolutionReplayReport, output_dir: Path, suite_version: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    value = {
        "source_run": asdict(report.source_run),
        "proposal": report.proposal,
        "artifact": asdict(report.artifact),
        "candidate_runtime_id": report.candidate_runtime_id,
        "replay_evidence": [asdict(item) for item in report.replay_evidence],
        "decision": report.decision.value,
        "payload_path": report.payload_path,
        "registry_path": report.registry_path,
        "rollback_proof_path": report.rollback_proof_path,
        "rollback_verified": report.rollback_verified,
    }
    json_text = json.dumps(value, indent=2, sort_keys=True, default=str)
    (output_dir / "evolution-report.json").write_text(json_text, encoding="utf-8")
    categories = sorted({item.category for item in report.replay_evidence if item.success})
    markdown = [
        "# Executable Evolution Replay Report",
        "",
        f"- Source failure: `{report.source_run.task_id}` / `{report.source_run.variant}`",
        f"- Failure class: `{report.proposal['failure_class']}`",
        f"- Executable artifact: `{report.artifact.id}@{report.artifact.version}`",
        f"- Payload SHA-256: `{report.artifact.payload_digest}`",
        f"- Fresh candidate: `{report.candidate_runtime_id}`",
        f"- Decision: `{report.decision.value}`",
        f"- Persisted rollback verified: `{str(report.rollback_verified).lower()}`",
        f"- Successful replay categories: `{', '.join(categories)}`",
        "",
        "## Before / After",
        "",
        f"- Before: task success `{report.source_run.success}`, verifier false accepts `{report.source_run.verifier_false_accepts}`, unsafe side effects `{report.source_run.unsafe_side_effects}`.",
        f"- After: task success rate `{report.artifact.regression_results['task_success_rate']:.4f}`, verifier false accept rate `{report.artifact.regression_results['verifier_false_accept_rate']:.4f}`, unsafe side-effect rate `{report.artifact.regression_results['unsafe_side_effect_rate']:.4f}`.",
        "",
        "## Regression Metrics",
        "",
    ]
    markdown.extend(f"- `{name}`: {metric:.4f}" for name, metric in sorted(report.artifact.regression_results.items()))
    markdown.append("")
    markdown_text = "\n".join(markdown)
    (output_dir / "evolution-report.md").write_text(markdown_text, encoding="utf-8")
    version_dir = output_dir / "versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    stem = f"evolution-{suite_version}-{report.artifact.id}-{report.artifact.version}"
    (version_dir / f"{stem}.json").write_text(json_text, encoding="utf-8")
    (version_dir / f"{stem}.md").write_text(markdown_text, encoding="utf-8")
