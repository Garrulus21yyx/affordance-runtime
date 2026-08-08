import asyncio
import hashlib
import json

from affordance_runtime.benchmarks.target_loop.attestation import create_attestation
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.reporting import write_run_report
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_attestation_binds_exact_git_manifest_and_report_digests(tmp_path) -> None:
    run_dir = tmp_path / "core"
    result = asyncio.run(run_suite(get_manifest("internal-core", "deterministic", 7)))
    write_run_report(result, str(run_dir))
    output = tmp_path / "attestation.json"

    attestation = create_attestation(tmp_path, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert attestation.accepted
    assert attestation.git_sha == result.identity.git_sha
    assert attestation.manifest_digests == (result.identity.manifest_digest,)
    assert len(attestation.report_files) == 7
    assert payload["report_files"][0]["sha256"]
    assert hashlib.sha256(output.read_bytes()).hexdigest()
