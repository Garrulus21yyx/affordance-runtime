"""Narrow preflight-first CLI for the reviewed external smoke manifest."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.adapter_conformance import run_adapter_conformance
from affordance_runtime.benchmarks.external_smoke.adapter_reporting import write_adapter_conformance
from affordance_runtime.benchmarks.external_smoke.admission import evaluate_external_admission
from affordance_runtime.benchmarks.external_smoke.case_environment import external_dependency_status
from affordance_runtime.benchmarks.external_smoke.contracts import ExternalBenchmarkAdmissionEvidence
from affordance_runtime.benchmarks.external_smoke.live_reporting import write_fixed_external_smoke
from affordance_runtime.benchmarks.external_smoke.live_runner import run_fixed_external_smoke
from affordance_runtime.benchmarks.external_smoke.manifest import (
    EXTERNAL_SMOKE_MANIFEST,
    external_manifest_digest,
)
from affordance_runtime.benchmarks.external_smoke.reporting import write_preflight_report
from affordance_runtime.benchmarks.external_smoke.runner import run_external_smoke
from affordance_runtime.model.policy import model_policy_from_environment

EXPECTED_INTERNAL_PROFILES = frozenset({
    "internal-core:deterministic",
    "internal-core:scripted-model",
    "internal-safety:scripted-model",
    "internal-evaluation:local-http-semantic-judge",
    "internal-real-adapters:deterministic",
})


def build_external_admission_evidence(
    internal_path: Path,
    full_ci_path: Path,
    live_policy_path: Path,
    adapter_attestation_path: Path | None = None,
) -> ExternalBenchmarkAdmissionEvidence:
    internal = _object(internal_path)
    full = _object(full_ci_path)
    live = _object(live_policy_path)
    current_sha = _git("rev-parse", "HEAD")
    clean = not bool(_git("status", "--short"))
    dependency = (
        external_dependency_status(adapter_attestation_path)
        if adapter_attestation_path is not None else external_dependency_status()
    )
    profiles = frozenset(str(item) for item in internal.get("run_profiles", ()))
    return ExternalBenchmarkAdmissionEvidence(
        git_sha=current_sha,
        internal_git_sha=str(internal.get("git_sha", "")),
        full_ci_git_sha=str(full.get("git_sha", "")),
        live_policy_git_sha=str(live.get("git_sha", "")),
        internal_harness_attestation_sha256=_sha256(internal_path),
        full_ci_attestation_sha256=_sha256(full_ci_path),
        live_model_policy_attestation_sha256=_sha256(live_policy_path),
        external_manifest_digest=external_manifest_digest(EXTERNAL_SMOKE_MANIFEST),
        internal_harness_accepted=internal.get("accepted") is True,
        expected_internal_run_set_complete=profiles == EXPECTED_INTERNAL_PROFILES,
        full_ci_accepted=full.get("accepted") is True,
        live_policy_accepted=live.get("accepted") is True,
        live_evaluator_required=not EXTERNAL_SMOKE_MANIFEST.mechanical_only,
        live_evaluator_accepted=None,
        forbidden_effect_attempts=_integer(internal, "forbidden_effect_attempts"),
        duplicate_unknown_attempts=_integer(internal, "duplicate_unknown_attempts"),
        stale_zero_call_violations=_integer(internal, "stale_zero_call_violations"),
        clean_tree=clean,
        optional_dependency_available=dependency.available,
        optional_dependency_version=dependency.package_version,
        target_loop_adapter_ready=dependency.target_loop_adapter_ready,
    )


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError:
        return ""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _integer(value: dict, name: str) -> int:
    item = value.get(name)
    return item if isinstance(item, int) and not isinstance(item, bool) else -1


def _git(*args: str) -> str:
    result = subprocess.run(("git", *args), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _unavailable_executor(_manifest):
    raise RuntimeError("target-loop external environment adapter is not admitted")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--manifest", choices=("external-smoke-v1",), required=True)
    preflight.add_argument("--internal-attestation", type=Path, required=True)
    preflight.add_argument("--full-ci-attestation", type=Path, required=True)
    preflight.add_argument("--live-policy-attestation", type=Path, required=True)
    preflight.add_argument("--adapter-attestation", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--execute", action="store_true")
    adapter = subparsers.add_parser("adapter-conformance")
    adapter.add_argument("--manifest", choices=("external-smoke-v1",), required=True)
    adapter.add_argument("--seed", type=int, default=7)
    adapter.add_argument("--output-dir", type=Path, required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--manifest", choices=("external-smoke-v1",), required=True)
    run.add_argument("--profile", choices=("mistral-format-only-mechanical",), required=True)
    run.add_argument("--internal-attestation", type=Path, required=True)
    run.add_argument("--full-ci-attestation", type=Path, required=True)
    run.add_argument("--live-policy-attestation", type=Path, required=True)
    run.add_argument("--adapter-attestation", type=Path, required=True)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--min-policy-call-interval-s", type=float, default=7.5)
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "adapter-conformance":
        adapter_outcome = asyncio.run(run_adapter_conformance(args.seed))
        write_adapter_conformance(adapter_outcome, args.output_dir)
        return 0 if adapter_outcome.accepted else 1
    evidence = build_external_admission_evidence(
        args.internal_attestation, args.full_ci_attestation, args.live_policy_attestation,
        args.adapter_attestation,
    )
    admission = evaluate_external_admission(evidence, EXTERNAL_SMOKE_MANIFEST)
    if args.command == "run":
        gate = run_external_smoke(
            admission, EXTERNAL_SMOKE_MANIFEST, execute=args.execute, executor=lambda _manifest: (),
        )
        write_preflight_report(args.output_dir / "preflight.json", evidence, admission, gate)
        if not gate.executed:
            return 1
        policy = model_policy_from_environment(
            grounding_variant="format-only", provider_recovery=False,
        )
        live_outcome = asyncio.run(run_fixed_external_smoke(
            policy, seed=args.seed,
            minimum_policy_call_interval_s=args.min_policy_call_interval_s,
        ))
        write_fixed_external_smoke(live_outcome, args.output_dir)
        return 0 if live_outcome.accepted else 1
    execution = run_external_smoke(
        admission, EXTERNAL_SMOKE_MANIFEST, execute=args.execute, executor=_unavailable_executor,
    )
    write_preflight_report(args.output, evidence, admission, execution)
    return 1 if args.execute and not execution.executed else 0


if __name__ == "__main__":
    raise SystemExit(main())
