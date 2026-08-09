"""Build exact, secret-free identities from provider-owned inventory metadata."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping, Sequence

from affordance_runtime.agent.decisions import MAX_RESULT_SUMMARY_CHARS
from affordance_runtime.benchmarks.model_conformance.contracts import ModelProfileIdentity
from affordance_runtime.model_policy.grounding import grounding_profile_version
from affordance_runtime.model_policy.prompt import SCHEMA_VERSION
from affordance_runtime.model_policy.schema_identity import decision_schema_digest

PROMPT_VERSION = "p5-m1.1"
CONTEXT_BUDGET_PROFILE = "default-64k"


def identity_from_ollama_inventory(
    model: str,
    *,
    runtime_version: str,
    models: Sequence[Mapping[str, object]],
    grounding_variant: str = "",
    execution_profile: str = "",
) -> ModelProfileIdentity:
    record = next(
        (item for item in models if str(item.get("name") or item.get("model") or "") == model),
        None,
    )
    details = record.get("details") if record else {}
    details = details if isinstance(details, Mapping) else {}
    return ModelProfileIdentity(
        "ollama", model, "local", "ollama", runtime_version,
        str(record.get("digest") or "") if record else "",
        str(details.get("family") or ""),
        str(details.get("parameter_size") or ""),
        str(details.get("quantization_level") or ""),
        PROMPT_VERSION, SCHEMA_VERSION, CONTEXT_BUDGET_PROFILE,
        decision_schema_digest(), MAX_RESULT_SUMMARY_CHARS, grounding_variant,
        grounding_profile_version(grounding_variant) if grounding_variant else "",
        execution_profile,
        grounding_profile_version(grounding_variant) if grounding_variant else "",
        "",
    )


def remote_profile_identity(
    provider: str,
    model: str,
    endpoint_class: str,
    *,
    grounding_variant: str = "",
    execution_profile: str = "provider-managed",
) -> ModelProfileIdentity:
    return ModelProfileIdentity(
        provider, model, endpoint_class, "provider-managed", "", "", "", "", "",
        PROMPT_VERSION, SCHEMA_VERSION, CONTEXT_BUDGET_PROFILE,
        decision_schema_digest(), MAX_RESULT_SUMMARY_CHARS, grounding_variant,
        grounding_profile_version(grounding_variant) if grounding_variant else "",
        execution_profile,
        grounding_profile_version(grounding_variant) if grounding_variant else "",
        "",
    )


def ollama_inventory(base_url: str = "http://127.0.0.1:11434") -> tuple[str, tuple[Mapping[str, object], ...]]:
    version = _get_json(f"{base_url.rstrip('/')}/api/version")
    tags = _get_json(f"{base_url.rstrip('/')}/api/tags")
    models = tags.get("models", ())
    return str(version.get("version") or ""), tuple(
        item for item in models if isinstance(item, Mapping)
    ) if isinstance(models, Sequence) else ()


def _get_json(url: str) -> Mapping[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - fixed local inventory endpoint
        value = json.loads(response.read())
    if not isinstance(value, Mapping):
        raise ValueError("Ollama inventory response must be an object")
    return value
