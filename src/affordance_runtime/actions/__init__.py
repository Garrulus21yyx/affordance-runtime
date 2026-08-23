"""Interaction capabilities, current ActionSpace, admission, and binding."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ActionAdmissionResult": ("affordance_runtime.actions.action_space", "ActionAdmissionResult"),
    "ActionSpaceBuilder": ("affordance_runtime.actions.action_space", "ActionSpaceBuilder"),
    "AdmissionIssue": ("affordance_runtime.actions.admission", "AdmissionIssue"),
    "AdmissionIssueCode": ("affordance_runtime.actions.admission", "AdmissionIssueCode"),
    "ActionBinder": ("affordance_runtime.actions.binder", "ActionBinder"),
    "BindingError": ("affordance_runtime.actions.binder", "BindingError"),
    "ActionPager": ("affordance_runtime.actions.paging", "ActionPager"),
    "ActionDiscoveryMatch": ("affordance_runtime.actions.paging", "ActionDiscoveryMatch"),
    "ActionDiscoveryResult": ("affordance_runtime.actions.paging", "ActionDiscoveryResult"),
    "ActionRecallSet": ("affordance_runtime.actions.paging", "ActionRecallSet"),
    "ActionRecallPartition": ("affordance_runtime.actions.paging", "ActionRecallPartition"),
    "ActionReranker": ("affordance_runtime.actions.paging", "ActionReranker"),
    "InternalActionPage": ("affordance_runtime.actions.paging", "InternalActionPage"),
    "ActionRelevance": ("affordance_runtime.actions.relevance", "ActionRelevance"),
    "ActionRelevancePolicy": ("affordance_runtime.actions.relevance", "ActionRelevancePolicy"),
    "ActionRelevanceRole": ("affordance_runtime.actions.relevance", "ActionRelevanceRole"),
    "RouteSelectionCode": ("affordance_runtime.actions.route_selector", "RouteSelectionCode"),
    "RouteSelectionResult": ("affordance_runtime.actions.route_selector", "RouteSelectionResult"),
    "RouteSelector": ("affordance_runtime.actions.route_selector", "RouteSelector"),
}

for _name in (
    "INTERACTION_CAPABILITY_REGISTRY",
    "AdapterCapabilitySupport",
    "AdapterInteractionProfile",
    "CapabilityComposer",
    "ComposedAdapterCapability",
    "ComposedInteractionCapabilities",
    "DestinationMode",
    "InteractionCapabilityError",
    "InteractionCapabilityIssueCode",
    "InteractionCapabilityRegistry",
    "InteractionSubjectKind",
    "ParameterContractKind",
    "PrimitiveTranslator",
    "SemanticActionDefinition",
    "VerificationContract",
    "VerificationFamily",
    "verification_contract_for_action",
):
    _EXPORTS[_name] = ("affordance_runtime.actions.capabilities", _name)

for _name in (
    "ActionOption",
    "ActionRisk",
    "ActionSpace",
    "ActionSpaceIssue",
    "ActionSpaceIssueCode",
    "AdmittedActionSelection",
):
    _EXPORTS[_name] = ("affordance_runtime.actions.space_contracts", _name)

_EXPORTS["ActionBinding"] = ("affordance_runtime.world.contracts", "ActionBinding")

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
