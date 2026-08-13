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
from affordance_runtime.benchmarks.model_protocol import (
    PRIMARY_BENCHMARK_ACTION_PROTOCOL,
    PRIMARY_BENCHMARK_PERCEPTION_PROFILE,
)
from affordance_runtime.model_policy import (
    model_policy_from_environment,
)
from affordance_runtime.visual_disambiguation import visual_candidate_disambiguator_from_environment
from affordance_runtime.visual_grounding import (
    configured_visual_region_proposer_from_environment,
    glm_visual_point_grounder_from_environment,
)
from affordance_runtime.visual_predicate_classification import (
    visual_predicate_classifier_from_environment,
)

_ROOT = Path(__file__).resolve().parents[1]
_FROZEN_MANIFEST = _ROOT / "docs/benchmarks/miniwob-60-seed7-v1-manifest.json"
_WITNESSES = frozenset({
    "browsergym/miniwob.grid-coordinate",
    "browsergym/miniwob.click-pie-nodelay",
    "browsergym/miniwob.click-shades",
    "browsergym/miniwob.click-pie",
    "browsergym/miniwob.visual-addition",
})
_STRUCTURAL_SVG_WITNESSES = frozenset({
    "browsergym/miniwob.grid-coordinate",
    "browsergym/miniwob.click-pie-nodelay",
    "browsergym/miniwob.click-pie",
})
_MARKED_AGENT_SELECTION_WITNESSES = frozenset({
    "browsergym/miniwob.grid-coordinate",
    "browsergym/miniwob.click-shades",
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
        perception_profile=PRIMARY_BENCHMARK_PERCEPTION_PROFILE,
        interaction_protocol=PRIMARY_BENCHMARK_ACTION_PROTOCOL,
    )
    outcome = asyncio.run(run_provider_cohort_arm(
        manifest,
        policy,
        PRIMARY_BENCHMARK_PERCEPTION_PROFILE,
        visual_region_proposer=configured_visual_region_proposer_from_environment(),
        visual_point_grounder=glm_visual_point_grounder_from_environment(),
        visual_candidate_disambiguator=visual_candidate_disambiguator_from_environment(),
        visual_predicate_classifier=visual_predicate_classifier_from_environment(),
        progress_dir=args.output_dir,
        progress_profile="M4_6_E_STEP13_VISUAL_BINDING_TARGETED",
    ))
    report = write_provider_cohort_arm(
        args.output_dir,
        implementation_sha=implementation_sha,
        profile="M4_6_E_STEP13_VISUAL_BINDING_TARGETED",
        arm=outcome,
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    acceptance = _visual_gate_acceptance(outcome)
    payload["visual_gate_acceptance"] = acceptance
    report.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "report": str(report),
        "completed_cases": payload["completed_cases"],
        "success_count": payload["success_count"],
        "outcome_counts": payload["outcome_counts"],
        "run_evidence_valid": payload["run_evidence_valid"],
        "errors": payload["errors"],
        "visual_gate_acceptance": acceptance,
    }, sort_keys=True))
    return 0


def _visual_gate_acceptance(outcome) -> dict[str, object]:
    errors: list[str] = []
    no_effect_opportunities = 0
    no_effect_repeat_violations = 0
    by_task = {record.task_family_label: record for record in outcome.records}
    for task_id in _WITNESSES:
        slug = task_id.removeprefix("browsergym/miniwob.")
        record = by_task[slug]
        metrics = record.result.measurements
        if _metric(metrics, "invalid_tool_argument_count") != 0:
            errors.append(f"{record.case_id}: structured tool argument failure occurred")
        if _metric(metrics, "visual_point_grounder_calls") != 0:
            errors.append(f"{record.case_id}: BrowserGym target loop invoked a point grounder")
        if _metric(metrics, "visual_binding_acquired_count") != 0 or _metric(
            metrics, "visual_binding_dispatch_count"
        ) != 0:
            errors.append(f"{record.case_id}: visual proposal gained execution authority")
        if task_id in _STRUCTURAL_SVG_WITNESSES:
            if _metric(metrics, "structural_binding_dispatch_count") < 1:
                errors.append(f"{record.case_id}: no structural identity binding was dispatched")
            if not any(item.get("selected_grounding") for item in record.diagnostic_trace):
                errors.append(f"{record.case_id}: selected public E-ref evidence is absent")
        if task_id in _MARKED_AGENT_SELECTION_WITNESSES:
            if _metric(metrics, "visual_disambiguator_calls") != 0:
                errors.append(f"{record.case_id}: a redundant pre-policy E-ref call occurred")
            if _metric(metrics, "visual_source_acquired_count") != 0:
                errors.append(f"{record.case_id}: candidate choice created a second visual source")
            selected = tuple(
                item.get("selected_grounding")
                for item in record.diagnostic_trace
                if isinstance(item.get("selected_grounding"), dict)
            )
            if not selected or not all(item.get("marked") is True for item in selected):
                errors.append(f"{record.case_id}: main policy selected no marked public E-ref")
        for index, item in enumerate(record.diagnostic_trace[:-1]):
            transition = item.get("runtime_transition")
            if not isinstance(transition, dict) or transition.get("action_evaluation_status") != "no_effect_confirmed":
                continue
            no_effect_opportunities += 1
            following = record.diagnostic_trace[index + 1]
            feedback = following.get("feedback")
            if not isinstance(feedback, dict) or feedback.get("code") != "action_no_effect_change_strategy":
                no_effect_repeat_violations += 1
                continue
            prior = item.get("selected_grounding")
            selected = following.get("selected_grounding")
            if isinstance(prior, dict) and isinstance(selected, dict) and (
                prior.get("ref"), prior.get("semantic_action")
            ) == (selected.get("ref"), selected.get("semantic_action")):
                no_effect_repeat_violations += 1
    if outcome.success_count < 1:
        errors.append("no structural/visually-assisted witness succeeded end to end")
    if no_effect_repeat_violations:
        errors.append("confirmed no-effect activation was repeated without a strategy transition")
    return {
        "accepted": not errors,
        "errors": errors,
        "witness_case_count": len(_WITNESSES),
        "structural_svg_case_count": len(_STRUCTURAL_SVG_WITNESSES),
        "no_effect_opportunities": no_effect_opportunities,
        "no_effect_repeat_violations": no_effect_repeat_violations,
    }


def _metric(measurements, name: str) -> int:
    measurement = measurements.get(name)
    value = getattr(measurement, "value", 0)
    return int(value) if isinstance(value, int | float) else 0


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
        PRIMARY_BENCHMARK_PERCEPTION_PROFILE.value,
        7.5,
        cases,
    )


if __name__ == "__main__":
    raise SystemExit(main())
