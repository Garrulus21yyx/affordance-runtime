"""Decision-neutral compact-contract.v2 projection from public AgentContext JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model_policy.spec import SCHEMA_VERSION
from affordance_runtime.world.source_profile import ObservationAssurance, assurance_satisfies

MAX_COMPACT_GUIDE_BYTES = 4 * 1024
COMPACT_CONTRACT_V2_PROFILE_VERSION = "compact-contract.v2"


@dataclass(frozen=True)
class CompactActionGuideV2:
    action_id: str
    semantic_action: str
    target_id: str
    target_label: str
    visible_destination_ids: tuple[str, ...]
    required_parameter_names: tuple[str, ...]


@dataclass(frozen=True)
class CompactActionDomain:
    actions: tuple[CompactActionGuideV2, ...]
    total_count: int
    truncated: bool


@dataclass(frozen=True)
class CompactObservationDomain:
    subject_ids: tuple[str, ...]
    modalities: tuple[str, ...]
    assurance_levels: tuple[str, ...]
    remaining_observations: int


@dataclass(frozen=True)
class CompactPagingDomain:
    has_more: bool
    next_cursor: str
    query: str
    target_id: str
    relevance_role: str
    available_filters: tuple[str, ...]


@dataclass(frozen=True)
class CompactCompletionDomain:
    criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    unresolved_criteria: tuple[str, ...]
    unresolved_outputs: tuple[str, ...]
    runtime_revalidation: bool
    summary_max_chars: int


@dataclass(frozen=True)
class CompactBudgetDomain:
    remaining_wait_ms: int
    per_decision_max_wait_ms: int
    fresh_observation_after_wait: bool


@dataclass(frozen=True)
class CompactDecisionContract:
    decision_type: str
    currently_usable: bool
    required_fields: tuple[str, ...]
    field_domains: Mapping[str, object]
    runtime_revalidates: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_domains", freeze_json(self.field_domains))


@dataclass(frozen=True)
class CompactDecisionGuideV2:
    schema_version: str
    profile_version: str
    current_context_id: str
    action_domain: CompactActionDomain
    observation_domain: CompactObservationDomain
    paging_domain: CompactPagingDomain
    completion_domain: CompactCompletionDomain
    budget_domain: CompactBudgetDomain
    decision_contracts: tuple[CompactDecisionContract, ...]
    guide_bytes: int
    truncated: bool


def build_compact_decision_guide_v2(serialized_context: str) -> CompactDecisionGuideV2:
    context = json.loads(serialized_context)
    if not isinstance(context, dict):
        raise ValueError("serialized AgentContext must be an object")
    actions = context.get("actions", {})
    options = actions.get("options", ()) if isinstance(actions, dict) else ()
    if not isinstance(options, list):
        raise ValueError("AgentContext action options must be a list")
    projected = tuple(_action_guide(item) for item in options if isinstance(item, dict))
    while True:
        guide = _with_guide_bytes(_guide(context, projected, len(projected) < len(options)))
        if guide.guide_bytes <= MAX_COMPACT_GUIDE_BYTES:
            return guide
        if not projected:
            raise ValueError("compact v2 decision guide cannot fit its fixed metadata bound")
        projected = projected[:-1]


def serialize_compact_decision_guide_v2(guide: CompactDecisionGuideV2) -> str:
    return json.dumps(_json_value(guide), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_value(guide: CompactDecisionGuideV2) -> dict[str, object]:
    actions, contracts = guide.action_domain, guide.decision_contracts
    return {
        "schema_version": guide.schema_version, "profile_version": guide.profile_version,
        "current_context_id": guide.current_context_id,
        "action_domain": {
            "fields": ("action_id", "semantic_action", "target_id", "target_label",
                       "visible_destination_ids", "required_parameter_names"),
            "items": tuple((item.action_id, item.semantic_action, item.target_id, item.target_label,
                            item.visible_destination_ids, item.required_parameter_names)
                           for item in actions.actions),
            "total": actions.total_count, "truncated": actions.truncated,
        },
        "observation_domain": {
            "subject_ids": "@action_domain.target_id+agent_context.world.targets[].target_id",
            "modalities": guide.observation_domain.modalities,
            "assurance_levels": guide.observation_domain.assurance_levels,
            "remaining_observations": guide.observation_domain.remaining_observations,
        },
        "paging_domain": to_json_compatible(guide.paging_domain),
        "completion_domain": {
            "criterion_ids": guide.completion_domain.criterion_ids,
            "evidence_refs": _compact_refs(guide.completion_domain.evidence_refs),
            "unresolved_criteria": guide.completion_domain.unresolved_criteria,
            "unresolved_outputs": guide.completion_domain.unresolved_outputs,
            "runtime_revalidation": guide.completion_domain.runtime_revalidation,
            "summary_max_chars": guide.completion_domain.summary_max_chars,
        },
        "budget_domain": to_json_compatible(guide.budget_domain),
        "decision_contracts": {
            "fields": ("decision_type", "currently_usable", "required_fields",
                       "field_domains_aligned", "runtime_revalidates"),
            "items": tuple((item.decision_type, item.currently_usable, ",".join(item.required_fields),
                            _aligned_domains(item), item.runtime_revalidates)
                           for item in contracts),
        },
        "guide_bytes": guide.guide_bytes, "truncated": guide.truncated,
    }


def _aligned_domains(contract: CompactDecisionContract) -> tuple[object, ...]:
    common = {"type": contract.decision_type, "context_id": "@current_context_id"}
    return tuple(
        to_json_compatible(contract.field_domains.get(field, common.get(field, "canonical-schema")))
        for field in contract.required_fields
    )


def _compact_refs(refs: tuple[str, ...]) -> dict[str, object]:
    groups: dict[str, list[str]] = {}
    for ref in refs:
        groups.setdefault(ref.split(":", 1)[0], []).append(ref)
    encoded = []
    for values in groups.values():
        prefix = _segment_prefix(values)
        encoded.append((prefix, tuple(value[len(prefix):] for value in values)))
    return {"encoding": "prefix+suffix", "groups": tuple(encoded)}


def _segment_prefix(values: list[str]) -> str:
    prefix = values[0]
    for value in values[1:]:
        mismatch = next(
            (index for index, pair in enumerate(zip(prefix, value)) if pair[0] != pair[1]),
            min(len(prefix), len(value)),
        )
        prefix = prefix[:mismatch]
    return prefix[:prefix.rfind(":") + 1]


def _guide(context, projected, truncated) -> CompactDecisionGuideV2:
    actions, world = context.get("actions", {}), context.get("world", {})
    task, progress, budgets = context.get("task", {}), context.get("progress", {}), context.get("budgets", {})
    capabilities = tuple(world.get("observation_capabilities", ()))
    subject_ids = _unique((
        *(item.get("target_id", "") for item in world.get("targets", {}).get("items", ())),
        *(item.get("target_id", "") for item in actions.get("options", ())),
    ))
    modalities = _unique(item.get("modality", "") for item in capabilities)
    offered = tuple(item.get("assurance", "") for item in capabilities)
    assurances = tuple(
        item.value for item in ObservationAssurance
        if any(assurance_satisfies(candidate, item) for candidate in offered)
    )
    completion = CompactCompletionDomain(
        tuple(item.get("criterion_id", "") for item in task.get("success_criteria", {}).get("items", ())),
        _evidence_refs(world), tuple(progress.get("unresolved_criteria", {}).get("items", ())),
        tuple(progress.get("unresolved_outputs", {}).get("items", ())), True, 1_024,
    )
    remaining_wait = max(0, int(budgets.get("remaining_wait_ms", 0)))
    observation = CompactObservationDomain(
        subject_ids, modalities, assurances, max(0, int(budgets.get("remaining_observations", 0))),
    )
    paging = CompactPagingDomain(
        bool(actions.get("has_more")), str(actions.get("next_cursor") or ""),
        str(actions.get("active_query") or ""), str(actions.get("active_target_filter") or ""),
        str(actions.get("active_relevance_filter") or ""),
        tuple(str(item) for item in actions.get("available_filters", ())),
    )
    budget = CompactBudgetDomain(remaining_wait, min(60_000, remaining_wait), True)
    action_domain = CompactActionDomain(tuple(projected), len(actions.get("options", ())), truncated)
    missing = tuple(str(key) for key, value in task.get("public_inputs", {}).items() if value is None)
    return CompactDecisionGuideV2(
        SCHEMA_VERSION, COMPACT_CONTRACT_V2_PROFILE_VERSION, str(context.get("context_id") or ""),
        action_domain, observation, paging, completion, budget,
        _contracts(action_domain, observation, paging, completion, budget, missing), 0, truncated,
    )


def _contracts(actions, observation, paging, completion, budget, missing):
    common = ("type", "context_id")
    return (
        _contract("select_action", bool(actions.actions), (*common, "action_id", "parameters", "destination_id"), {
            "action_id": "@action_domain.items.action_id", "parameters": "@selected.required_parameter_names",
            "destination_id": "@selected.visible_destination_ids|empty",
        }),
        _contract("request_observation", observation.remaining_observations > 0 and bool(observation.modalities),
                  (*common, "subject_id", "modality", "required_assurance", "reason"), {
                      "subject_id": "@observation_domain.subject_ids", "modality": "@observation_domain.modalities",
                      "required_assurance": "@observation_domain.assurance_levels", "reason": "text:1..500",
                  }),
        _contract("request_action_page", bool(paging.next_cursor or paging.available_filters),
                  (*common, "query", "target_id", "relevance_role", "cursor"), {
                      "query": "@paging_domain.query", "target_id": "@paging_domain.target_id",
                      "relevance_role": "@paging_domain.relevance_role", "cursor": "@paging_domain.next_cursor",
                  }),
        _contract("ask_user", True, (*common, "question", "requested_fields"), {
            "question": "text:1..1000", "requested_fields": missing or "explicit-public-missing-only",
        }),
        _contract("propose_done", True, (*common, "claimed_criteria", "evidence_refs", "result_summary", "unresolved_items"), {
            "claimed_criteria": "@completion_domain.criterion_ids", "evidence_refs": "@completion_domain.evidence_refs",
            "result_summary": "text:1..1024", "unresolved_items": (),
        }),
        _contract("wait", budget.remaining_wait_ms > 0, (*common, "reason", "max_wait_ms"), {
            "reason": "text:1..500", "max_wait_ms": "1..@budget_domain.per_decision_max_wait_ms",
        }),
        _contract("abort", True, (*common, "reason", "category"), {
            "reason": "text:1..500", "category": ("policy", "safety", "unsupported", "no_progress", "user_request"),
        }),
    )


def _contract(decision_type, usable, required, domains):
    return CompactDecisionContract(decision_type, usable, tuple(required), domains, True)


def _action_guide(option: dict[str, object]) -> CompactActionGuideV2:
    destinations, schema = option.get("destinations", {}), option.get("parameter_schema", {})
    destination_items = destinations.get("items", ()) if isinstance(destinations, dict) else ()
    required = schema.get("required", ()) if isinstance(schema, dict) else ()
    return CompactActionGuideV2(
        str(option.get("action_id") or ""), str(option.get("semantic_action") or ""),
        str(option.get("target_id") or ""), str(option.get("target_label") or ""),
        tuple(str(item.get("destination_id") or "") for item in destination_items if isinstance(item, dict)),
        tuple(str(item) for item in required) if isinstance(required, list) else (),
    )


def _evidence_refs(world) -> tuple[str, ...]:
    return _unique((
        *(item.get("fact_ref", "") for item in world.get("facts", {}).get("items", ())),
        *(item.get("evidence_ref", "") for item in world.get("artifact_summaries", {}).get("items", ())),
    ))


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if item))


def _with_guide_bytes(guide: CompactDecisionGuideV2) -> CompactDecisionGuideV2:
    for _ in range(4):
        size = len(serialize_compact_decision_guide_v2(guide).encode())
        if size == guide.guide_bytes:
            return guide
        guide = replace(guide, guide_bytes=size)
    raise ValueError("compact v2 guide size did not stabilize")
