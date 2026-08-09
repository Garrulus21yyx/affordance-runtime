"""Reviewed fixed BrowserGym/MiniWoB-compatible mechanical smoke manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from affordance_runtime.benchmarks.external_smoke.contracts import (
    ExternalSmokeCase,
    ExternalSmokeManifest,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    MetricExpectation,
    MetricExpectationOperator,
)

PACKAGE_VERSION = "0.14.3"
SOURCE_COMMIT = "7fd85d71a4b60325c6585396ec4f48377d049838"


def _case(case_id: str, task_id: str, description: str, primitives: tuple[str, ...]) -> ExternalSmokeCase:
    return ExternalSmokeCase(
        case_id, "browsergym-miniwob", task_id, description,
        20, 120.0, 0, primitives, "environment-native-mechanical",
        ("done",),
        (
            "observations", "executions", "provider_attempts", "official_success_count",
            "forbidden_effect_attempts", "duplicate_unknown_attempts", "stale_zero_call_violations",
            "provider_retry_count", "fallback_count", "cleanup_failures",
        ),
        (
            MetricExpectation("official_success_count", MetricExpectationOperator.EQ, 1),
            MetricExpectation("forbidden_effect_attempts", MetricExpectationOperator.ZERO),
            MetricExpectation("duplicate_unknown_attempts", MetricExpectationOperator.ZERO),
            MetricExpectation("stale_zero_call_violations", MetricExpectationOperator.ZERO),
            MetricExpectation("provider_retry_count", MetricExpectationOperator.ZERO),
            MetricExpectation("fallback_count", MetricExpectationOperator.ZERO),
            MetricExpectation("cleanup_failures", MetricExpectationOperator.ZERO),
        ),
    )


EXTERNAL_SMOKE_MANIFEST = ExternalSmokeManifest(
    "external-smoke-manifest.v1", "external-smoke-v1", "browsergym-miniwob",
    "browsergym-miniwob", PACKAGE_VERSION, SOURCE_COMMIT, True, True,
    (
        _case("miniwob-click-button", "browsergym/miniwob.click-button", "single local button activation", ("activate",)),
        _case("miniwob-enter-text", "browsergym/miniwob.enter-text", "local text entry and submit", ("fill", "activate")),
        _case("miniwob-choose-list", "browsergym/miniwob.choose-list", "local finite list selection", ("select",)),
    ),
)


def external_manifest_digest(manifest: ExternalSmokeManifest) -> str:
    encoded = json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
