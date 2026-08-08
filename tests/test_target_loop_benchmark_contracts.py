from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkRunIdentity
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest, manifest_digest


def test_manifest_digest_and_run_identity_are_stable_and_secret_free() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    assert manifest_digest(manifest) == manifest_digest(manifest)
    identity = BenchmarkRunIdentity.create("suite", manifest_digest(manifest), "deterministic", 7)
    assert identity.git_sha
    assert identity.suite_id == "suite"
    assert "endpoint_url" not in identity.__dict__
