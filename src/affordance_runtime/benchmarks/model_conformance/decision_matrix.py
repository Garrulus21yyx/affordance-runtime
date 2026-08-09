"""Fixed public-context cases for compact decision behavior diagnostics."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.source_profile import ObservationAssurance, assurance_satisfies

DECISION_VARIANTS = (
    "select_action",
    "request_observation",
    "request_action_page",
    "ask_user",
    "propose_done",
    "wait",
    "abort",
)


@dataclass(frozen=True)
class DecisionPayloadExpectation:
    expected_variant: str
    exact_fields: Mapping[str, object]
    allowed_domains: Mapping[str, tuple[object, ...]]
    collection_item_domains: Mapping[str, tuple[object, ...]]
    numeric_bounds: Mapping[str, tuple[int, int]]
    required_nonblank_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "exact_fields", freeze_json(self.exact_fields))
        object.__setattr__(self, "allowed_domains", freeze_json(self.allowed_domains))
        object.__setattr__(self, "collection_item_domains", freeze_json(self.collection_item_domains))
        object.__setattr__(self, "numeric_bounds", freeze_json(self.numeric_bounds))
        object.__setattr__(self, "required_nonblank_fields", tuple(self.required_nonblank_fields))
@dataclass(frozen=True)
class DecisionMatrixCase:
    case_id: str
    expected_variant: str
    serialized_context: str
    expected_payload: Mapping[str, object]
    expectation: DecisionPayloadExpectation
    correct_action_index: int | None = None
    correct_destination_index: int | None = None

    def __post_init__(self) -> None:
        if self.expected_variant not in DECISION_VARIANTS:
            raise ValueError("matrix case requires a canonical decision variant")
        object.__setattr__(self, "expected_payload", freeze_json(self.expected_payload))
def build_seven_decision_cases(serialized_context: str) -> tuple[DecisionMatrixCase, ...]:
    base = _context(serialized_context)
    context_id = str(base["context_id"])
    option = base["actions"]["options"][0]
    action_id = str(option["action_id"])
    destinations = option.get("destinations", {}).get("items", [])
    destination_id = str(destinations[0]["destination_id"]) if destinations else ""
    capability = base["world"]["observation_capabilities"][0]
    criterion_ids = tuple(
        str(item["criterion_id"])
        for item in base["task"].get("success_criteria", {}).get("items", [])
    )
    fact_refs = _fact_refs(base)
    payloads = (
        ("select", "select_action", {
            "type": "select_action", "context_id": context_id,
            "action_id": action_id, "parameters": {}, "destination_id": destination_id,
        }),
        ("observe", "request_observation", {
            "type": "request_observation", "context_id": context_id,
            "subject_id": str(option["target_id"]),
            "modality": capability["modality"],
            "required_assurance": capability["assurance"], "reason": "refresh current evidence",
        }),
        ("page", "request_action_page", {
            "type": "request_action_page", "context_id": context_id,
            "query": "", "target_id": "", "relevance_role": "", "cursor": "cursor:next",
        }),
        ("ask", "ask_user", {
            "type": "ask_user", "context_id": context_id,
            "question": "Which required value should be used?", "requested_fields": ["value"],
        }),
        ("done", "propose_done", {
            "type": "propose_done", "context_id": context_id,
            "claimed_criteria": list(criterion_ids), "evidence_refs": list(fact_refs[:1]),
            "result_summary": "Current evidence supports completion.", "unresolved_items": [],
        }),
        ("wait", "wait", {
            "type": "wait", "context_id": context_id,
            "reason": "allow the asynchronous state to settle", "max_wait_ms": 10,
        }),
        ("abort", "abort", {
            "type": "abort", "context_id": context_id,
            "reason": "the requested operation is unsupported", "category": "unsupported",
        }),
    )
    cases = []
    for name, variant, payload in payloads:
        context = _decision_context(base, variant)
        cases.append(DecisionMatrixCase(
            name, variant, _serialize(context), payload,
            _payload_expectation(variant, payload, context),
        ))
    return tuple(cases)
def build_multi_action_case(
    serialized_context: str,
    *,
    action_count: int,
    correct_index: int,
) -> DecisionMatrixCase:
    if action_count not in {8, 16} or not 0 <= correct_index < action_count:
        raise ValueError("multi-action matrix admits fixed 8/16 action profiles")
    context = _context(serialized_context)
    template = context["actions"]["options"][0]
    options = []
    for index in range(action_count):
        option = copy.deepcopy(template)
        option["action_id"] = f"public-action-{index + 1}"
        option["target_id"] = f"public-target-{index + 1}"
        option["target_label"] = f"Candidate {index + 1}"
        option["description"] = (
            "Matches the declared task objective" if index == correct_index
            else "Legal alternative that does not advance the declared objective"
        )
        options.append(option)
    context["actions"]["options"] = options
    context["actions"]["total_count"] = action_count
    context["actions"]["page_size"] = action_count
    context["task"]["instruction"] = (
        f"Choose the only candidate that matches the declared objective: Candidate {correct_index + 1}."
    )
    selected = options[correct_index]
    destinations = selected.get("destinations", {}).get("items", [])
    destination_id = str(destinations[0]["destination_id"]) if destinations else ""
    payload = {
        "type": "select_action", "context_id": context["context_id"],
        "action_id": selected["action_id"], "parameters": {},
        "destination_id": destination_id,
    }
    return DecisionMatrixCase(
        f"actions-{action_count}-correct-{correct_index + 1}",
        "select_action",
        _serialize(context),
        payload,
        _payload_expectation("select_action", payload, context),
        correct_action_index=correct_index,
    )
def build_destination_case(
    serialized_context: str,
    *,
    destinations: int,
    correct_index: int = 0,
    similar_ids: bool = False,
) -> DecisionMatrixCase:
    if destinations not in {0, 1, 2} or (destinations and not 0 <= correct_index < destinations):
        raise ValueError("destination matrix admits zero, one or two destinations")
    context = _context(serialized_context)
    option = context["actions"]["options"][0]
    option["target_id"] = "public-id-target" if similar_ids else "public-target"
    items = [
        {"destination_id": f"public-id-destination-{index + 1}", "label": f"Destination {index + 1}"}
        for index in range(destinations)
    ]
    option["destination_required"] = bool(items)
    option["destinations"] = {
        "items": items, "total_count": len(items), "truncated": False,
    }
    context["task"]["instruction"] = (
        "Activate the target without a destination."
        if not items else f"Activate the target using Destination {correct_index + 1}."
    )
    destination_id = str(items[correct_index]["destination_id"]) if items else ""
    payload = {
        "type": "select_action", "context_id": context["context_id"],
        "action_id": option["action_id"], "parameters": {}, "destination_id": destination_id,
    }
    return DecisionMatrixCase(
        (
            f"destinations-{destinations}-correct-{correct_index + 1 if items else 0}"
            f"{'-similar-ids' if similar_ids else ''}"
        ),
        "select_action",
        _serialize(context),
        payload,
        _payload_expectation("select_action", payload, context),
        correct_action_index=0,
        correct_destination_index=correct_index if items else None,
    )
def _context(serialized_context: str) -> dict[str, Any]:
    value = json.loads(serialized_context)
    if not isinstance(value, dict):
        raise ValueError("matrix AgentContext must be an object")
    return value


def _serialize(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fact_refs(context: Mapping[str, object]) -> tuple[str, ...]:
    world = context.get("world", {})
    targets = world.get("targets", {}).get("items", []) if isinstance(world, dict) else []
    facts = tuple(
        str(fact["fact_ref"])
        for target in targets if isinstance(target, dict)
        for fact in target.get("facts", {}).get("items", []) if isinstance(fact, dict)
    )
    global_facts = world.get("facts", {}).get("items", []) if isinstance(world, dict) else []
    artifacts = world.get("artifact_summaries", {}).get("items", []) if isinstance(world, dict) else []
    return (*facts, *(str(item["fact_ref"]) for item in global_facts), *(str(item["evidence_ref"]) for item in artifacts))


def _decision_context(base: dict[str, Any], variant: str) -> dict[str, Any]:
    context = copy.deepcopy(base)
    task = context["task"]
    actions = context["actions"]
    progress = context["progress"]
    if variant == "request_observation":
        task["instruction"] = "Request a fresh structural observation before taking any action."
        actions["options"] = []
        actions["total_count"] = 0
        actions["page_size"] = 0
    elif variant == "request_action_page":
        task["instruction"] = "Retrieve the next action page because the required action is not visible."
        actions["options"] = []
        actions["total_count"] = 1
        actions["page_size"] = 0
        actions["truncated"] = True
        actions["has_more"] = True
        actions["next_cursor"] = "cursor:next"
    elif variant == "ask_user":
        task["instruction"] = "A required value is missing. Ask the user for the field named value."
        task["public_inputs"] = {}
        actions["options"] = []
        actions["total_count"] = 0
        actions["page_size"] = 0
    elif variant == "propose_done":
        task["instruction"] = "The current validated evidence satisfies the task; propose completion."
        progress["validated_task_status"] = "complete"
        progress["unresolved_criteria"] = {"items": [], "total_count": 0, "truncated": False}
        actions["options"] = []
        actions["total_count"] = 0
        actions["page_size"] = 0
    elif variant == "wait":
        task["instruction"] = "Wait briefly for the asynchronous state change before observing again."
        actions["options"] = []
        actions["total_count"] = 0
        actions["page_size"] = 0
    elif variant == "abort":
        task["instruction"] = (
            "This task is explicitly unsupported and cannot be completed by any available "
            "action, observation, wait, or user input. Terminate safely without claiming completion."
        )
        actions["options"] = []
        actions["total_count"] = 0
        actions["page_size"] = 0
        context["world"]["observation_capabilities"] = []
        context["decision_mode"] = "recover"
        progress["validated_task_status"] = "blocked"
        progress["unresolved_criteria"] = {
            "items": ["unsupported"], "total_count": 1, "truncated": False,
        }
    return context


def decision_matches_expectation(
    decision: object,
    expectation: DecisionPayloadExpectation,
) -> bool:
    actual = {"type": _decision_variant(decision), **to_json_compatible(vars(decision))}
    if actual["type"] != expectation.expected_variant:
        return False
    for field, expected in expectation.exact_fields.items():
        if actual.get(field) != to_json_compatible(expected):
            return False
    for field, domain in expectation.allowed_domains.items():
        if actual.get(field) not in to_json_compatible(domain):
            return False
    for field, domain in expectation.collection_item_domains.items():
        value = actual.get(field)
        if not isinstance(value, list) or any(item not in to_json_compatible(domain) for item in value):
            return False
    for field, bounds in expectation.numeric_bounds.items():
        value = actual.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not bounds[0] <= value <= bounds[1]:
            return False
    return all(
        isinstance(actual.get(field), str) and bool(actual[field].strip())
        for field in expectation.required_nonblank_fields
    )


def _payload_expectation(variant, payload, context) -> DecisionPayloadExpectation:
    exact = {"type": variant, "context_id": payload["context_id"]}
    allowed: dict[str, tuple[object, ...]] = {}
    collections: dict[str, tuple[object, ...]] = {}
    numeric: dict[str, tuple[int, int]] = {}
    nonblank: tuple[str, ...] = ()
    if variant == "select_action":
        exact.update({key: payload[key] for key in ("action_id", "parameters", "destination_id")})
    elif variant == "request_observation":
        allowed["subject_id"] = tuple(dict.fromkeys([
            *(item["target_id"] for item in context["world"]["targets"]["items"]),
            *(item["target_id"] for item in context["actions"]["options"]),
        ]))
        capabilities = tuple(context["world"].get("observation_capabilities", ()))
        allowed["modality"] = tuple(dict.fromkeys(item["modality"] for item in capabilities))
        offered = tuple(item["assurance"] for item in capabilities)
        allowed["required_assurance"] = tuple(
            item.value for item in ObservationAssurance
            if any(assurance_satisfies(candidate, item) for candidate in offered)
        )
        nonblank = ("reason",)
    elif variant == "request_action_page":
        exact.update({key: payload[key] for key in ("query", "target_id", "relevance_role", "cursor")})
    elif variant == "ask_user":
        collections["requested_fields"] = tuple(payload["requested_fields"])
        exact["requested_fields"] = payload["requested_fields"]
        nonblank = ("question",)
    elif variant == "propose_done":
        exact["unresolved_items"] = payload["unresolved_items"]
        collections["claimed_criteria"] = tuple(
            item["criterion_id"] for item in context["task"]["success_criteria"]["items"]
        )
        collections["evidence_refs"] = _fact_refs(context)
        nonblank = ("result_summary",)
    elif variant == "wait":
        remaining = int(context.get("budgets", {}).get("remaining_wait_ms", 0))
        numeric["max_wait_ms"] = (1, min(60_000, remaining))
        nonblank = ("reason",)
    else:
        allowed["category"] = ("policy", "safety", "unsupported", "no_progress", "user_request")
        nonblank = ("reason",)
    return DecisionPayloadExpectation(variant, exact, allowed, collections, numeric, nonblank)


def _decision_variant(decision: object) -> str:
    return {
        "SelectAction": "select_action", "RequestObservation": "request_observation",
        "RequestActionPage": "request_action_page", "AskUser": "ask_user",
        "ProposeDone": "propose_done", "Wait": "wait", "Abort": "abort",
    }.get(type(decision).__name__, "")
