"""Immutable fixed target-loop manifests and declarative identity digests."""

import hashlib
import json
from dataclasses import asdict

from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest


def manifest_digest(manifest: BenchmarkManifest) -> str:
    payload = {
        "schema_version": manifest.schema_version,
        "suite_id": manifest.suite_id,
        "profile_id": manifest.profile_id,
        "seed": manifest.seed,
        "cases": [
            {
                "case_id": item.case_id,
                "suite_id": item.suite_id,
                "description": item.description,
                "expected_terminal_statuses": [str(status) for status in item.expected_terminal_statuses],
                "timeout_s": item.timeout_s,
                "required_measurements": item.required_measurements,
                "metric_expectations": [asdict(expectation) for expectation in item.metric_expectations],
                "auto_confirm": item.auto_confirm,
                **(
                    {"local_objective_requirement": item.local_objective_requirement.value}
                    if item.local_objective_requirement.value != "not_required"
                    else {}
                ),
            }
            for item in manifest.cases
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def get_manifest(suite_id: str, profile_id: str, seed: int) -> BenchmarkManifest:
    from affordance_runtime.benchmarks.target_loop.cases import build_manifest

    return build_manifest(suite_id, profile_id, seed)
