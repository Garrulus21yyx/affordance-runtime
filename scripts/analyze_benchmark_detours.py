"""Offline, non-authoritative comparison of compatible benchmark trajectories."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.benchmarks.target_loop.analysis import (
    TrajectoryComparison,
    assess_suspected_detour,
    derive_trajectory_facts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("cohort", nargs="*", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    candidate = _load(args.candidate)
    cohort = tuple(_load(path) for path in args.cohort)
    assessment = assess_suspected_detour(candidate, cohort)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(assessment), indent=2, sort_keys=True) + "\n")
    return 0


def _load(run_directory: Path) -> TrajectoryComparison:
    run = json.loads((run_directory / "run.json").read_text())
    identity = run["identity"]
    cases = tuple(sorted((run_directory / "cases").glob("*.json")))
    if len(cases) != 1:
        raise ValueError("detour CLI accepts one-case run directories")
    result = json.loads(cases[0].read_text())
    trace_path = run_directory / "traces" / result["case_id"] / "trace.jsonl"
    events = tuple(json.loads(line) for line in trace_path.read_text().splitlines())
    facts = derive_trajectory_facts(events)

    def metric(name: str) -> int:
        measurement = result.get("measurements", {}).get(name, {})
        return int(measurement.get("value", 0)) if measurement.get("measured") else 0

    return TrajectoryComparison(
        run_attempt_id=identity["run_attempt_id"],
        case_id=result["case_id"],
        task_contract_id=result["case_id"],
        environment_id=str(identity.get("runtime", "core")),
        profile_id=identity["profile_id"],
        successful=result["status"] == "done",
        turns=metric("turns"),
        prompt_tokens=metric("prompt_tokens"),
        effectful_dispatches=metric("effectful_dispatches"),
        recovery_count=metric("action_policy_recovery_calls"),
        semantic_page_revisits=facts.public_world_revisits,
        semantic_action_revisits=facts.semantic_action_revisits,
        longest_no_progress_span=facts.longest_no_progress_span,
        evidence_refs=facts.evidence_refs,
    )


if __name__ == "__main__":
    raise SystemExit(main())
