"""CLI for serial exact-profile recurrent candidate and support gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.model.policy.grounding import DecisionGroundingVariant
from affordance_runtime.model.providers.port import OllamaModelPort

from .matrix_runner import run_decision_matrix
from .profile_identity import identity_from_ollama_inventory, ollama_inventory
from .recurrent_attestation import attest_recurrent
from .recurrent_qualification import qualify_recurrent_result


async def _run(args) -> int:
    version, models = ollama_inventory(args.ollama_base_url)
    identity = identity_from_ollama_inventory(
        args.model, runtime_version=version, models=models,
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2.value,
        execution_profile="gpu-serial",
    )
    support = bool(args.support_attestation)
    case_ids: tuple[str, ...] = ()
    if support:
        case_ids = ("select", "observe", "page", "ask", "done", "wait", "abort")
    output = Path(args.output_dir)
    result = await run_decision_matrix(
        identity,
        lambda: OllamaModelPort(model=args.model, base_url=args.ollama_base_url),
        repetitions=args.repetitions,
        output_dir=output,
        grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2,
        case_ids=case_ids,
    )
    qualification = qualify_recurrent_result(result, support_attestation=support)
    (output / "qualification.json").write_text(
        json.dumps(asdict(qualification), sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    sha = subprocess.run(
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True,
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ("git", "status", "--porcelain"), check=True, capture_output=True, text=True,
    ).stdout.strip())
    attestation = attest_recurrent(
        result, qualification, (output / "matrix.json", output / "qualification.json"),
        git_sha=sha, git_dirty=dirty,
    )
    (output / "attestation.json").write_text(
        json.dumps(asdict(attestation), sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return 0 if qualification.admitted else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("ollama",), default="ollama")
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--candidate", action="store_true")
    mode.add_argument("--support-attestation", action="store_true")
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if args.candidate and args.repetitions != 5:
        parser.error("candidate gate requires exactly 5 repetitions")
    if args.support_attestation and args.repetitions != 20:
        parser.error("support attestation requires exactly 20 repetitions")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
