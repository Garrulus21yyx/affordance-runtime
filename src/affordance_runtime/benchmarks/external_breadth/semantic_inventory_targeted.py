"""Fixed no-model semantic-inventory diagnostic for the M4.6-C cohort."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.browsergym_semantic_profile import (
    BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
)
from affordance_runtime.world import (
    ActionSpaceBuilder,
    CoverageState,
    SemanticInventoryStatus,
    SemanticInventorySummary,
)

CAMPAIGN_PROFILE = "MINIWOB_SEMANTIC_INVENTORY_17_NO_MODEL"
SEED = 7
CASE_MANIFEST = (
    ("miniwob-60-04", "email-inbox-forward-nl"),
    ("miniwob-60-05", "grid-coordinate"),
    ("miniwob-60-07", "tic-tac-toe"),
    ("miniwob-60-14", "order-food"),
    ("miniwob-60-17", "social-media-all"),
    ("miniwob-60-26", "email-inbox-noscroll"),
    ("miniwob-60-28", "click-link"),
    ("miniwob-60-33", "email-inbox"),
    ("miniwob-60-34", "click-pie-nodelay"),
    ("miniwob-60-36", "click-menu"),
    ("miniwob-60-38", "hot-cold"),
    ("miniwob-60-43", "social-media-some"),
    ("miniwob-60-44", "social-media"),
    ("miniwob-60-47", "email-inbox-nl-turk"),
    ("miniwob-60-49", "click-pie"),
    ("miniwob-60-52", "ascending-numbers"),
    ("miniwob-60-57", "email-inbox-forward-nl-turk"),
)

_RUN_ID = re.compile(r"miniwob-inventory-17:[0-9a-f]{32}")
_SHA = re.compile(r"[0-9a-f]{40}")
_FORBIDDEN_KEYS = frozenset({
    "api_key",
    "bid",
    "credential",
    "instruction",
    "native_option_value",
    "node_id",
    "raw_ax",
    "raw_reward",
    "reward",
    "selector",
})


@dataclass(frozen=True)
class _CaseFailure(RuntimeError):
    code: str


def manifest_digest() -> str:
    payload = [
        {"case_id": case_id, "task_family_label": slug, "seed": SEED}
        for case_id, slug in CASE_MANIFEST
    ]
    return _sha256(_canonical_json(payload))


async def run_targeted_inventory(
    output_dir: Path,
    *,
    run_id: str,
    implementation_sha: str,
) -> dict[str, object]:
    _validate_identity(run_id, implementation_sha)
    _require_clean_implementation(implementation_sha)
    output_dir.mkdir(parents=True, exist_ok=False)
    admitted = frozenset(f"browsergym/miniwob.{slug}" for _case, slug in CASE_MANIFEST)
    cases = [
        await _run_case(case_id, slug, admitted, run_id, implementation_sha)
        for case_id, slug in CASE_MANIFEST
    ]
    campaign = {
        "schema_version": "miniwob-semantic-inventory-targeted.v1",
        "campaign_profile": CAMPAIGN_PROFILE,
        "run_id": run_id,
        "implementation_sha": implementation_sha,
        "git_dirty": False,
        "seed": SEED,
        "inventory_profile_id": BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
        "manifest_digest": manifest_digest(),
        "manifest_digest_algorithm": (
            "sha256 of UTF-8 canonical JSON records with case_id, task_family_label, seed"
        ),
        "case_manifest": [
            {"case_id": case_id, "task_family_label": slug}
            for case_id, slug in CASE_MANIFEST
        ],
        "cases": cases,
    }
    case_errors = validate_campaign(campaign)
    statuses = Counter(str(case["inventory_status"]) for case in cases)
    count_shapes = Counter(
        (
            _exact_int(case["recognized_target_count"]),
            _exact_int(case["projected_target_count"]),
            _exact_int(case["actionable_target_count"]),
            _exact_int(case["non_executable_target_count"]),
            _exact_int(case["omitted_target_count"]),
            _exact_int(case["informational_target_count"]),
        )
        for case in cases
    )
    summary = {
        "schema_version": "miniwob-semantic-inventory-summary.v1",
        "run_id": run_id,
        "implementation_sha": implementation_sha,
        "case_count": len(cases),
        "completed_case_count": sum(
            bool(case["acquisition_complete"])
            and bool(case["projection_complete"])
            and bool(case["cleanup_complete"])
            for case in cases
        ),
        "inventory_status_counts": dict(sorted(statuses.items())),
        "inventory_count_shape_counts": [
            {
                "counts": list(shape),
                "case_count": count,
            }
            for shape, count in sorted(count_shapes.items())
        ],
        "policy_calls": sum(_exact_int(case["policy_calls"]) for case in cases),
        "provider_attempts": sum(
            _exact_int(case["provider_attempts"]) for case in cases
        ),
        "tokens": sum(_exact_int(case["tokens"]) for case in cases),
        "step_calls": sum(_exact_int(case["step_calls"]) for case in cases),
        "currentness_probe_calls": sum(
            _exact_int(case["currentness_probe_calls"]) for case in cases
        ),
        "independent_capture_calls": sum(
            _exact_int(case["independent_capture_calls"]) for case in cases
        ),
        "schema_count_invariant_errors": len(case_errors),
        "privacy_errors": 0,
        "harness_integrity_errors": 0,
        "unclassified_errors": sum(
            bool(case["diagnostic_error_code"])
            and str(case["diagnostic_error_code"]) not in _BOUNDED_ERROR_CODES
            for case in cases
        ),
    }
    campaign_bytes = _json_bytes(campaign)
    _write_new(output_dir / "campaign.json", campaign_bytes)
    privacy_errors = privacy_scan(campaign) + privacy_scan(summary)
    summary["privacy_errors"] = len(privacy_errors)
    evidence_valid = not any((
        case_errors,
        privacy_errors,
        summary["harness_integrity_errors"],
        summary["unclassified_errors"],
        summary["completed_case_count"] != len(CASE_MANIFEST),
    ))
    summary["evidence_valid"] = evidence_valid
    summary_bytes = _json_bytes(summary)
    _write_new(output_dir / "summary.json", summary_bytes)
    attestation = {
        "schema_version": "miniwob-semantic-inventory-attestation.v1",
        "run_id": run_id,
        "implementation_sha": implementation_sha,
        "git_dirty": False,
        "seed": SEED,
        "campaign_profile": CAMPAIGN_PROFILE,
        "inventory_profile_id": BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
        "manifest_digest": manifest_digest(),
        "campaign_sha256": _sha256(campaign_bytes),
        "summary_sha256": _sha256(summary_bytes),
        "model_enabled": False,
        "provider_enabled": False,
        "evidence_valid": evidence_valid,
    }
    _write_new(output_dir / "attestation.json", _json_bytes(attestation))
    validation_errors = validate_evidence_directory(output_dir)
    if validation_errors:
        raise RuntimeError("targeted semantic inventory evidence validation failed")
    return summary


async def _run_case(
    case_id: str,
    slug: str,
    admitted: frozenset[str],
    run_id: str,
    implementation_sha: str,
) -> dict[str, object]:
    from affordance_runtime.benchmarks.external_smoke.browsergym_environment import (
        BrowserGymMiniWobEnvironment,
    )

    task_id = f"browsergym/miniwob.{slug}"
    environment = None
    error_code = ""
    source = None
    world = None
    action_space = None
    acquisition_complete = False
    projection_complete = False
    cleanup_complete = False
    try:
        environment, task = BrowserGymMiniWobEnvironment.open(
            task_id,
            SEED,
            max_turns=1,
            admitted_task_ids=admitted,
        )
        acquisition = await environment.reset(task)
        if acquisition.observation is None:
            raise _CaseFailure("initial_acquisition_failed")
        acquisition_complete = True
        world = acquisition.observation
        if len(world.sources) != 1 or world.sources[0].surface != "browsergym":
            raise _CaseFailure("source_projection_invalid")
        source = world.sources[0]
        projection_complete = True
        action_space = ActionSpaceBuilder().build(task, world)
    except _CaseFailure as exc:
        error_code = exc.code
    except Exception:
        error_code = "environment_or_projection_failed"
    finally:
        if environment is not None:
            try:
                await environment.close()
                cleanup_complete = True
            except Exception:
                error_code = error_code or "cleanup_failed"

    inventory = (
        source.semantic_inventory
        if source is not None
        else SemanticInventorySummary.unassessed(
            BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID
        )
    )
    unique_binding_targets = (
        len({binding.target_id for binding in source.bindings}) if source is not None else 0
    )
    return {
        "case_id": case_id,
        "task_family_label": slug,
        "benchmark_task_id": task_id,
        "seed": SEED,
        "run_id": run_id,
        "implementation_sha": implementation_sha,
        "acquisition_complete": acquisition_complete,
        "projection_complete": projection_complete,
        "cleanup_complete": cleanup_complete,
        "projection_coverage": (
            str(world.coverage.get("browsergym")) if world is not None else "not_acquired"
        ),
        "inventory_profile_id": inventory.profile_id,
        "inventory_status": inventory.status.value,
        "recognized_target_count": inventory.recognized_target_count,
        "projected_target_count": inventory.projected_target_count,
        "actionable_target_count": inventory.actionable_target_count,
        "non_executable_target_count": inventory.non_executable_target_count,
        "omitted_target_count": inventory.omitted_target_count,
        "informational_target_count": inventory.informational_target_count,
        "world_target_count": len(world.targets) if world is not None else 0,
        "world_fact_count": len(world.facts) if world is not None else 0,
        "world_binding_count": len(world.bindings) if world is not None else 0,
        "unique_binding_target_count": unique_binding_targets,
        "action_space_option_count": len(action_space.options) if action_space is not None else 0,
        "backend_reset_calls": environment.backend_reset_calls if environment is not None else 0,
        "logical_reset_calls": environment.logical_reset_calls if environment is not None else 0,
        "independent_capture_calls": environment.capture_calls if environment is not None else 0,
        "step_calls": environment.step_calls if environment is not None else 0,
        "currentness_probe_calls": environment.probe_calls if environment is not None else 0,
        "model_enabled": False,
        "policy_calls": 0,
        "provider_attempts": 0,
        "tokens": 0,
        "diagnostic_error_code": error_code,
    }


def validate_campaign(campaign: object) -> tuple[str, ...]:
    if not isinstance(campaign, dict):
        return ("campaign_not_mapping",)
    errors: list[str] = []
    expected_manifest = [
        {"case_id": case_id, "task_family_label": slug}
        for case_id, slug in CASE_MANIFEST
    ]
    if campaign.get("case_manifest") != expected_manifest:
        errors.append("manifest_mismatch")
    if campaign.get("manifest_digest") != manifest_digest():
        errors.append("manifest_digest_mismatch")
    cases = campaign.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CASE_MANIFEST):
        return (*errors, "case_count_mismatch")
    run_id = campaign.get("run_id")
    implementation_sha = campaign.get("implementation_sha")
    for expected, case in zip(CASE_MANIFEST, cases, strict=True):
        errors.extend(_validate_case(case, expected, run_id, implementation_sha))
    return tuple(errors)


def _validate_case(
    case: object,
    expected: tuple[str, str],
    run_id: object,
    implementation_sha: object,
) -> tuple[str, ...]:
    if not isinstance(case, dict):
        return ("case_not_mapping",)
    errors: list[str] = []
    case_id, slug = expected
    expected_values = {
        "case_id": case_id,
        "task_family_label": slug,
        "benchmark_task_id": f"browsergym/miniwob.{slug}",
        "seed": SEED,
        "run_id": run_id,
        "implementation_sha": implementation_sha,
        "inventory_profile_id": BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
    }
    if any(case.get(key) != value for key, value in expected_values.items()):
        errors.append("case_identity_mismatch")
    for key in (
        "acquisition_complete",
        "projection_complete",
        "cleanup_complete",
    ):
        if case.get(key) is not True:
            errors.append(f"{key}_false")
    for key in (
        "model_enabled",
    ):
        if case.get(key) is not False:
            errors.append(f"{key}_true")
    for key in (
        "policy_calls",
        "provider_attempts",
        "tokens",
        "step_calls",
        "currentness_probe_calls",
        "independent_capture_calls",
    ):
        if type(case.get(key)) is not int or case.get(key) != 0:
            errors.append(f"{key}_nonzero")
    if case.get("backend_reset_calls") != 1 or case.get("logical_reset_calls") != 1:
        errors.append("reset_count_mismatch")
    count_keys = (
        "recognized_target_count",
        "projected_target_count",
        "actionable_target_count",
        "non_executable_target_count",
        "omitted_target_count",
        "informational_target_count",
    )
    try:
        counts = [_exact_int(case.get(key)) for key in count_keys]
        summary = SemanticInventorySummary(
            str(case.get("inventory_profile_id")),
            SemanticInventoryStatus(str(case.get("inventory_status"))),
            counts[0],
            counts[1],
            counts[2],
            counts[3],
            counts[4],
            counts[5],
        )
    except (TypeError, ValueError):
        errors.append("inventory_contract_invalid")
        return tuple(errors)
    if summary.status is SemanticInventoryStatus.UNASSESSED:
        errors.append("inventory_unassessed")
    if summary.projected_target_count != case.get("world_target_count"):
        errors.append("projected_world_target_mismatch")
    if summary.actionable_target_count != case.get("unique_binding_target_count"):
        errors.append("actionable_binding_target_mismatch")
    if summary.projected_target_count == 0:
        if summary.status is SemanticInventoryStatus.REPRESENTED:
            errors.append("zero_target_represented")
        if summary.recognized_target_count > 0 and (
            summary.status is not SemanticInventoryStatus.PARTIAL
            or summary.omitted_target_count != summary.recognized_target_count
        ):
            errors.append("recognized_omission_misclassified")
        if summary.status is SemanticInventoryStatus.EMPTY and summary.recognized_target_count != 0:
            errors.append("empty_with_recognized_target")
    if str(case.get("projection_coverage")) not in {str(item) for item in CoverageState}:
        errors.append("projection_coverage_invalid")
    if case.get("diagnostic_error_code") != "":
        errors.append("diagnostic_error_present")
    return tuple(errors)


def validate_evidence_directory(path: Path) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        campaign_bytes = (path / "campaign.json").read_bytes()
        summary_bytes = (path / "summary.json").read_bytes()
        campaign = json.loads(campaign_bytes)
        summary = json.loads(summary_bytes)
        attestation = json.loads((path / "attestation.json").read_bytes())
    except (OSError, json.JSONDecodeError):
        return ("evidence_read_failed",)
    errors.extend(validate_campaign(campaign))
    if attestation.get("campaign_sha256") != _sha256(campaign_bytes):
        errors.append("campaign_hash_mismatch")
    if attestation.get("summary_sha256") != _sha256(summary_bytes):
        errors.append("summary_hash_mismatch")
    for key in ("run_id", "implementation_sha", "manifest_digest"):
        if attestation.get(key) != campaign.get(key):
            errors.append(f"attestation_{key}_mismatch")
    if summary.get("evidence_valid") is not True or attestation.get("evidence_valid") is not True:
        errors.append("evidence_not_valid")
    if privacy_scan(campaign) or privacy_scan(summary) or privacy_scan(attestation):
        errors.append("privacy_scan_failed")
    return tuple(errors)


def privacy_scan(value: object) -> tuple[str, ...]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                errors.append(f"forbidden_key:{normalized}")
            errors.extend(privacy_scan(item))
    elif isinstance(value, list | tuple):
        for item in value:
            errors.extend(privacy_scan(item))
    return tuple(errors)


_BOUNDED_ERROR_CODES = frozenset({
    "",
    "cleanup_failed",
    "environment_or_projection_failed",
    "initial_acquisition_failed",
    "source_projection_invalid",
})


def _validate_identity(run_id: str, implementation_sha: str) -> None:
    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("targeted semantic inventory run ID is invalid")
    if _SHA.fullmatch(implementation_sha) is None:
        raise ValueError("targeted semantic inventory implementation SHA is invalid")


def _require_clean_implementation(implementation_sha: str) -> None:
    root = Path(__file__).resolve().parents[4]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != implementation_sha or dirty:
        raise RuntimeError("targeted semantic inventory run requires the exact clean implementation")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_int(value: object) -> int:
    if type(value) is not int:
        raise TypeError("targeted semantic inventory count must be an exact integer")
    return value


def _write_new(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--implementation-sha")
    parser.add_argument("--validate-existing", type=Path)
    args = parser.parse_args()
    if args.validate_existing is not None:
        return int(bool(validate_evidence_directory(args.validate_existing)))
    if args.output_dir is None or args.run_id is None or args.implementation_sha is None:
        parser.error("run mode requires output dir, run ID, and implementation SHA")
    summary = asyncio.run(run_targeted_inventory(
        args.output_dir,
        run_id=args.run_id,
        implementation_sha=args.implementation_sha,
    ))
    return int(summary.get("evidence_valid") is not True)


if __name__ == "__main__":
    raise SystemExit(main())
