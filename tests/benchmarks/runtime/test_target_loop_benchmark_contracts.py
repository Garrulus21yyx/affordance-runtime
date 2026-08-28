from dataclasses import replace

from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkRunIdentity
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest, manifest_digest


def test_manifest_digest_and_run_identity_are_stable_and_secret_free() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    assert manifest_digest(manifest) == manifest_digest(manifest)
    identity = BenchmarkRunIdentity.create("suite", manifest_digest(manifest), "deterministic", 7)
    assert identity.git_sha
    assert identity.suite_id == "suite"
    assert identity.runtime == "core"
    assert identity.run_attempt_id.startswith("attempt:")
    assert "endpoint_url" not in identity.__dict__


def test_repeated_configuration_has_stable_run_id_and_unique_attempt_identity() -> None:
    first = BenchmarkRunIdentity.create("suite", "digest", "deterministic", 7)
    second = BenchmarkRunIdentity.create("suite", "digest", "deterministic", 7)

    assert first.run_id == second.run_id
    assert first.run_attempt_id != second.run_attempt_id


def test_manifest_digest_covers_auto_confirm() -> None:
    manifest = get_manifest("internal-safety", "scripted-model", 7)
    confirmation = next(item for item in manifest.cases if item.auto_confirm)
    changed = replace(
        manifest,
        cases=tuple(
            replace(item, auto_confirm=False) if item.case_id == confirmation.case_id else item
            for item in manifest.cases
        ),
    )

    assert manifest_digest(manifest) != manifest_digest(changed)


def test_case_contract_has_no_inert_acceptance_profile() -> None:
    case = get_manifest("internal-core", "deterministic", 7).cases[0]
    assert "acceptance_profile" not in case.__dict__
