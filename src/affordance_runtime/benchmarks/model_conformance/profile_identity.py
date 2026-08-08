"""Build exact, secret-free identities from provider-owned inventory metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from affordance_runtime.benchmarks.model_conformance.contracts import ModelProfileIdentity
from affordance_runtime.model_policy.prompt import SCHEMA_VERSION

PROMPT_VERSION = "p5-m1.1"
CONTEXT_BUDGET_PROFILE = "default-64k"


def identity_from_ollama_inventory(
    model: str,
    *,
    runtime_version: str,
    models: Sequence[Mapping[str, object]],
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
    )


def remote_profile_identity(provider: str, model: str, endpoint_class: str) -> ModelProfileIdentity:
    return ModelProfileIdentity(
        provider, model, endpoint_class, "provider-managed", "", "", "", "", "",
        PROMPT_VERSION, SCHEMA_VERSION, CONTEXT_BUDGET_PROFILE,
    )

