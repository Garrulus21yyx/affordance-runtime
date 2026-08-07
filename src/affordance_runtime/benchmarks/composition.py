"""Benchmark-only runtime composition, including declared safety ablations."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from affordance_runtime.action_contract_builder import ActionContractMaterializer
from affordance_runtime.benchmarks.browsergym_encoder import (
    BrowserGymContractBuilder,
    GeneralistBrowserGymContractBuilder,
    GeneralistBrowserGymRouteEncoder,
)
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.coordinator import RunBudget, RuntimeFeatures
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer


def compose_benchmark_run_coordinator(
    observer: Any,
    executor: Any,
    *,
    features: RuntimeFeatures | None = None,
    budget: RunBudget | None = None,
    **kwargs: Any,
):
    """Construct an offline benchmark profile without weakening product composition."""

    resolved_features = features or RuntimeFeatures()
    contract_builder = kwargs.get("contract_builder")
    if isinstance(contract_builder, BrowserGymContractBuilder):
        raise TypeError(
            "proposal-bound BrowserGymContractBuilder is isolated from canonical benchmark composition"
        )
    if isinstance(contract_builder, GeneralistBrowserGymContractBuilder):
        kwargs["contract_builder"] = ActionTransactionMaterializer(
            requirements=contract_builder.requirements,
            unified_resolver=contract_builder.unified_resolver,
            gesture_binder=contract_builder.gesture_binder,
            route_encoder=GeneralistBrowserGymRouteEncoder(),
        )
    elif isinstance(contract_builder, ActionContractMaterializer):
        kwargs["contract_builder"] = ActionTransactionMaterializer(
            requirements=contract_builder.requirements,
            unified_resolver=contract_builder.unified_resolver,
            gesture_binder=contract_builder.gesture_binder,
        )
    benchmark_builder = kwargs.get("contract_builder")
    benchmark_route_encoder = (
        benchmark_builder.route_encoder
        if isinstance(benchmark_builder, ActionTransactionMaterializer)
        else None
    )
    if isinstance(benchmark_builder, ActionTransactionMaterializer) and benchmark_route_encoder is not None:
        kwargs["contract_builder"] = replace(benchmark_builder, route_encoder=None)
    coordinator = compose_run_coordinator(
        observer,
        executor,
        budget=budget or RunBudget(),
        features=RuntimeFeatures(),
        **kwargs,
    )
    if isinstance(benchmark_builder, ActionTransactionMaterializer) and benchmark_route_encoder is not None:
        benchmark_builder.provenance_manifest = coordinator.provenance_manifest
        coordinator = replace(
            coordinator,
            action_stage=replace(
                coordinator.action_stage,
                contract_builder=benchmark_builder,
            ),
        )
    return replace(
        coordinator,
        action_stage=replace(
            coordinator.action_stage,
            preflight_enabled=resolved_features.preflight,
            capability_gate_enabled=resolved_features.capability_gate,
            recovery_enabled=resolved_features.recovery,
        ),
        progress_stage=replace(
            coordinator.progress_stage,
            structural_verification_enabled=resolved_features.structural_verification,
            recovery_enabled=resolved_features.recovery,
        ),
    )
