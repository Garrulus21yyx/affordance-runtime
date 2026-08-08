"""Stable digest and explicit fixed-manifest lookup."""

import hashlib
import json


def manifest_digest(case_ids: tuple[str, ...]) -> str:
    payload = json.dumps(case_ids, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_manifest(suite_id: str, profile_id: str, seed: int):
    from affordance_runtime.benchmarks.target_loop.cases import build_manifest

    return build_manifest(suite_id, profile_id, seed)
