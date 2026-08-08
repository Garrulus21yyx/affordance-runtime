"""Pure fail-closed external smoke admission evaluation."""

from affordance_runtime.benchmarks.external_smoke.contracts import (
    ExternalBenchmarkAdmission,
    ExternalBenchmarkAdmissionEvidence,
    ExternalSmokeManifest,
)
from affordance_runtime.benchmarks.external_smoke.manifest import external_manifest_digest

SUPPORTED_SCHEMA = "external-smoke-manifest.v1"


def evaluate_external_admission(
    evidence: ExternalBenchmarkAdmissionEvidence,
    manifest: ExternalSmokeManifest,
) -> ExternalBenchmarkAdmission:
    errors: list[str] = []
    if len(evidence.git_sha) != 40 or len({
        evidence.git_sha, evidence.internal_git_sha,
        evidence.full_ci_git_sha, evidence.live_policy_git_sha,
    }) != 1:
        errors.append("all admission attestations must bind one exact git SHA")
    gates = {
        "internal harness attestation is unavailable or rejected": evidence.internal_harness_accepted,
        "expected internal run set is incomplete": evidence.expected_internal_run_set_complete,
        "full exact-head CI attestation is unavailable or rejected": evidence.full_ci_accepted,
        "exact live model-policy attestation unavailable": evidence.live_policy_accepted,
        "external admission requires a clean tree": evidence.clean_tree,
        "external optional dependency is unavailable": evidence.optional_dependency_available,
        "target-loop external environment adapter is not closed": evidence.target_loop_adapter_ready,
    }
    errors.extend(message for message, accepted in gates.items() if not accepted)
    if manifest.schema_version != SUPPORTED_SCHEMA or not manifest.reviewed:
        errors.append("external manifest is not a reviewed supported schema")
    if evidence.external_manifest_digest != external_manifest_digest(manifest):
        errors.append("external manifest digest mismatch")
    if evidence.optional_dependency_version != manifest.package_version:
        errors.append("external optional dependency version mismatch")
    if any((
        evidence.forbidden_effect_attempts,
        evidence.duplicate_unknown_attempts,
        evidence.stale_zero_call_violations,
    )):
        errors.append("internal safety metrics are not all zero")
    if not all(_digest(value) for value in (
        evidence.internal_harness_attestation_sha256,
        evidence.full_ci_attestation_sha256,
        evidence.live_model_policy_attestation_sha256,
    )):
        errors.append("admission attestation digest is missing or malformed")
    if not manifest.mechanical_only and (
        not evidence.live_evaluator_required or evidence.live_evaluator_accepted is not True
    ):
        errors.append("semantic external manifest requires an accepted live semantic evaluator")
    return ExternalBenchmarkAdmission(not errors, tuple(errors))


def _digest(value: str) -> bool:
    prefix, separator, digest = value.partition(":")
    return prefix == "sha256" and separator == ":" and len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )
