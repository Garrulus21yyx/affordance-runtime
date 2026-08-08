from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkRunIdentity
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest


def test_manifest_digest_and_run_identity_are_stable_and_secret_free() -> None:
    assert manifest_digest(("a", "b")) == manifest_digest(("a", "b"))
    identity = BenchmarkRunIdentity.create("suite", manifest_digest(("a",)), "deterministic", 7)
    assert identity.git_sha
    assert identity.suite_id == "suite"
    assert "endpoint_url" not in identity.__dict__

