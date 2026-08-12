"""Run and persist the bounded Step-13 MiniWoB visual-binding gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobBreadthCase,
    MiniWobBreadthManifest,
)
from affordance_runtime.benchmarks.external_breadth.perception_ab import (
    run_provider_cohort_arm,
    write_provider_cohort_arm,
)
from affordance_runtime.model_policy import model_policy_from_environment
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.visual_grounding import visual_region_proposer_from_environment

_ROOT = Path(__file__).resolve().parents[1]
_FROZEN_MANIFEST = _ROOT / "docs/benchmarks/miniwob-60-seed7-v1-manifest.json"
_WITNESSES = frozenset({
    "browsergym/miniwob.grid-coordinate",
    "browsergym/miniwob.click-pie-nodelay",
    "browsergym/miniwob.click-shades",
    "browsergym/miniwob.click-pie",
    "browsergym/miniwob.visual-addition",
})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--miniwob-url", default="http://127.0.0.1:18888/miniwob/")
    parser.add_argument("--model", default="glm-4.1v-thinking-flashx")
    args = parser.parse_args()
    load_dotenv(_ROOT / ".env", override=False)
    os.environ.update({
        "MINIWOB_URL": args.miniwob_url,
        "LLM_ACTIVE_PROFILE": "zhipu",
        "LLM_ZHIPU_MODEL": args.model,
        "LLM_ZHIPU_VISION_MODEL": args.model,
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    })
    implementation_sha = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True,
    ).strip()
    if subprocess.run(("git", "diff", "--quiet"), cwd=_ROOT, check=False).returncode:
        raise RuntimeError("Step-13 live gate requires a clean implementation SHA")
    manifest = _manifest(args.model)
    policy = model_policy_from_environment(
        call_timeout_s=90,
        perception_profile=DecisionPerceptionProfile.SCREENSHOT_AX,
        interaction_protocol="grounded_tools.v2",
    )
    outcome = asyncio.run(run_provider_cohort_arm(
        manifest,
        policy,
        DecisionPerceptionProfile.SCREENSHOT_AX,
        visual_region_proposer=visual_region_proposer_from_environment(),
    ))
    report = write_provider_cohort_arm(
        args.output_dir,
        implementation_sha=implementation_sha,
        profile="M4_6_E_STEP13_VISUAL_BINDING_TARGETED",
        arm=outcome,
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps({
        "report": str(report),
        "completed_cases": payload["completed_cases"],
        "success_count": payload["success_count"],
        "outcome_counts": payload["outcome_counts"],
        "run_evidence_valid": payload["run_evidence_valid"],
        "errors": payload["errors"],
    }, sort_keys=True))
    return 0


def _manifest(model: str) -> MiniWobBreadthManifest:
    payload = json.loads(_FROZEN_MANIFEST.read_text(encoding="utf-8"))
    cases = tuple(
        MiniWobBreadthCase(
            item["case_id"],
            item["task_id"],
            item["capability_profile"],
            tuple(item["required_primitives"]),
            item["max_turns"],
            item["timeout_s"],
            item["seed"],
        )
        for item in payload["cases"]
        if item["task_id"] in _WITNESSES
    )
    if len(cases) != len(_WITNESSES):
        raise RuntimeError("frozen manifest does not contain the exact visual witness set")
    return MiniWobBreadthManifest(
        payload["schema_version"],
        "m4-6-e-step13-visual-binding-targeted",
        payload["package_name"],
        payload["package_version"],
        payload["source_commit"],
        payload["registry_digest"],
        payload["capability_inventory_digest"],
        payload["selection_namespace"],
        model,
        "screenshot-ax.v1",
        7.5,
        cases,
    )


if __name__ == "__main__":
    raise SystemExit(main())
