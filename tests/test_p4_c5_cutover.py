from __future__ import annotations

import ast
from pathlib import Path

import pytest

from affordance_runtime.action_contract_builder import (
    ActionContractMaterializer,
)
from affordance_runtime.composition import (
    UnsafeProductRuntimeConfiguration,
    compose_run_coordinator,
)
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer


class _Edge:
    supported_backends = ("dom",)
    supported_actions = ("activate",)

    def capture(self):
        raise AssertionError("not called")

    def execute(self, contract, observation):
        raise AssertionError("not called")


def test_product_composition_rejects_legacy_route_configuration() -> None:
    edge = _Edge()
    with pytest.raises(UnsafeProductRuntimeConfiguration, match="canonical transaction"):
        compose_run_coordinator(edge, edge, contract_builder=ActionContractMaterializer())  # type: ignore[arg-type]


def test_product_composition_rejects_arbitrary_external_builder() -> None:
    edge = _Edge()
    with pytest.raises(UnsafeProductRuntimeConfiguration, match="canonical transaction"):
        compose_run_coordinator(edge, edge, contract_builder=object())  # type: ignore[arg-type]


def test_product_composition_rejects_external_route_encoder() -> None:
    edge = _Edge()
    builder = ActionTransactionMaterializer(route_encoder=object())  # type: ignore[arg-type]
    with pytest.raises(UnsafeProductRuntimeConfiguration, match="route encoders"):
        compose_run_coordinator(edge, edge, contract_builder=builder)


def test_canonical_execution_core_has_no_proposal_materializer_import_or_call() -> None:
    runtime = Path(__file__).parents[1] / "src" / "affordance_runtime"
    tree = ast.parse((runtime / "execution_phase.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "ActionContractMaterializer" not in imported
    assert "ActionContractBuilder" not in imported
    assert "_rebuild_preflight_contract" not in called
    assert "execute" not in called
    assert "dispatch" in called


def test_canonical_transaction_module_has_no_legacy_builder_dependency() -> None:
    runtime = Path(__file__).parents[1] / "src" / "affordance_runtime"
    tree = ast.parse((runtime / "transaction_materialization.py").read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "affordance_runtime.action_contract_builder" not in imported_modules
    assert "PlannerProposal" not in names
    assert "replace" not in names
    assert "build" not in attributes or "super" not in names


def test_contract_execution_loop_exposes_only_permit_dispatch() -> None:
    from affordance_runtime.contract_execution_loop import ContractExecutionLoop

    assert hasattr(ContractExecutionLoop, "dispatch")
    assert not hasattr(ContractExecutionLoop, "execute")
