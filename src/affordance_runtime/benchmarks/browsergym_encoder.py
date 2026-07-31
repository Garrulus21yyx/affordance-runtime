"""BrowserGym-only encoding of validated semantic contracts and gestures."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any

from affordance_runtime.benchmarks.browsergym_action_schema import BrowserGymAction
from affordance_runtime.benchmarks.browsergym_types import BROWSERGYM_BACKEND
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    GestureBinding,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.immutable import thaw_json_at_external_boundary
from affordance_runtime.planning import ContractBuilder, PlannerActionKind, PlannerProposal
from affordance_runtime.simplified_runtime_contracts import CollectionIntent, RelationIntent
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_planning import SubgoalOutcomeRelation, SubgoalSpec
from affordance_runtime.unified_grounding import source_affordance_for_candidate
from affordance_runtime.visual_contracts import VisualContractBinder


@dataclass
class BrowserGymContractBuilder(ContractBuilder):
    """Attach an externally selected typed BrowserGym action to a Core contract."""

    bindings: dict[str, BrowserGymAction] = field(default_factory=dict)

    def _route_verifier_kinds(
        self,
        semantic_target_id: str,
        snapshot: BrowserSnapshot,
    ) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [
                    *super()._route_verifier_kinds(semantic_target_id, snapshot),
                    "state_delta_or_terminal",
                ]
            )
        )

    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        contract = super().build(proposal, task_spec, state, snapshot)
        action = self.bindings.get(proposal.proposal_id)
        if action is None:
            raise ValueError(f"BrowserGym action binding is missing: {proposal.proposal_id}")
        return replace(
            contract,
            action=action.name,
            backend=BROWSERGYM_BACKEND,
            parameters={"action": asdict(action)},
            verifier_plan=browsergym_action_verifiers(action, snapshot),
            contract_hash="",
        )


@dataclass(frozen=True)
class BrowserGymGestureEncoder:
    """Translate a validated Core gesture binding to BrowserGym actions only."""

    def encode(self, binding: GestureBinding) -> BrowserGymAction:
        source_locator = binding.source.locator
        destination_locator = binding.destination.locator
        source_bid = str(source_locator.get("backend_handle") or "")
        destination_bid = str(destination_locator.get("backend_handle") or "")
        sortable = is_sortable_list_binding(binding)
        spatial_relation = bool(
            source_locator.get("relation_geometry") == "relative_size"
            and destination_locator.get("relation_geometry") == "relative_size"
        )
        calendar_range = (
            source_locator.get("calendar_endpoint") == "start"
            and destination_locator.get("calendar_endpoint") == "end"
        )
        same_calendar_slot = bool(calendar_range and source_bid and source_bid == destination_bid)
        if source_bid and destination_bid and not sortable and not calendar_range and not spatial_relation:
            return BrowserGymAction(
                "drag_and_drop",
                {"from_bid": source_bid, "to_bid": destination_bid},
            )
        source_box = viewport_box(source_locator.get("bbox"))
        destination_box = viewport_box(destination_locator.get("bbox"))
        if source_box is not None and destination_box is not None:
            to_x = destination_box[0] + destination_box[2] / 2
            to_y = destination_box[1] + destination_box[3] / 2
            from_y = source_box[1] + source_box[3] / 2
            if same_calendar_slot:
                from_y = source_box[1] + source_box[3] * 0.25
                to_y = destination_box[1] + destination_box[3] * 0.75
            if sortable:
                if destination_box[1] > source_box[1]:
                    to_y = destination_box[1] + destination_box[3] * 0.75
                elif destination_box[1] < source_box[1]:
                    to_y = destination_box[1] + destination_box[3] * 0.25
            arguments: dict[str, Any] = {
                "from_x": source_box[0] + source_box[2] / 2,
                "from_y": from_y,
                "to_x": to_x,
                "to_y": to_y,
            }
            if calendar_range and source_bid and destination_bid:
                arguments.update({"from_bid": source_bid, "to_bid": destination_bid})
            return BrowserGymAction("mouse_drag_and_drop", arguments)
        if source_bid and destination_bid:
            return BrowserGymAction(
                "drag_and_drop",
                {"from_bid": source_bid, "to_bid": destination_bid},
            )
        raise ValueError("BrowserGym drag encoding requires bids or viewport geometry")


@dataclass(frozen=True)
class BrowserGymPointEncoder:
    """Translate one current semantic point target to a BrowserGym action."""

    def encode(self, affordance: Affordance) -> BrowserGymAction:
        bid = str(affordance.locator.get("backend_handle") or "")
        if bid:
            return BrowserGymAction("click", {"bid": bid})
        box = viewport_box(affordance.locator.get("bbox"))
        if box is None:
            raise ValueError("BrowserGym point encoding requires a bid or viewport geometry")
        return BrowserGymAction(
            "mouse_click",
            {"x": box[0] + box[2] / 2, "y": box[1] + box[3] / 2},
        )

    def encode_contract(self, contract: ActionContract) -> BrowserGymAction:
        candidate = contract.grounding_candidate
        if candidate is None:
            raise ValueError("BrowserGym point contract requires a selected grounding candidate")
        bid = str(getattr(candidate.payload, "backend_handle", "") or "")
        if bid:
            return BrowserGymAction("click", {"bid": bid})
        point = thaw_json_at_external_boundary(contract.locator.get("point"))
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("BrowserGym point contract requires trusted viewport coordinates")
        return BrowserGymAction("mouse_click", {"x": float(point[0]), "y": float(point[1])})


@dataclass
class GeneralistBrowserGymContractBuilder(ContractBuilder):
    """Bind the common semantic vocabulary to typed BrowserGym actions."""

    gesture_encoder: BrowserGymGestureEncoder = field(default_factory=BrowserGymGestureEncoder)
    point_encoder: BrowserGymPointEncoder = field(default_factory=BrowserGymPointEncoder)
    visual_contract_binder: VisualContractBinder = field(default_factory=VisualContractBinder)

    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        contract = super().build(proposal, task_spec, state, snapshot)
        affordance = (
            source_affordance_for_candidate(
                contract.grounding_candidate,
                snapshot.affordance_model.affordances,
            )
            if contract.grounding_candidate is not None
            else next(
                item
                for item in snapshot.affordance_model.affordances
                if item.id == proposal.target_affordance_id
            )
        )
        if proposal.action_kind == PlannerActionKind.ACTIVATE:
            bid = str(affordance.locator.get("backend_handle") or "")
            if not bid:
                raise ValueError("Generalist BrowserGym binding requires an affordance bid")
            select_owner_bid = str(affordance.locator.get("select_owner_backend_handle") or "")
            select_option = str(affordance.locator.get("select_option") or "")
            if select_owner_bid and select_option:
                action = BrowserGymAction(
                    "select_option",
                    {"bid": select_owner_bid, "options": select_option},
                )
            else:
                direct_dom_control = bool(affordance.state.get("collection_action"))
                action = BrowserGymAction(
                    "click_no_navigation"
                    if affordance.state.get("href") == "#" or direct_dom_control
                    else "click",
                    {"bid": bid},
                )
        elif proposal.action_kind == PlannerActionKind.POINT_ACTIVATE:
            if contract.route_plan is None:
                raise ValueError("BrowserGym point target requires a unified grounding candidate")
            point_contract = self.visual_contract_binder.bind_point_activate(
                contract.route_plan,
                snapshot.observation,
                intent=proposal.subgoal or task_spec.objective,
                verifier_plan=(VerifierSpec("state_delta_or_terminal", "", True),),
                required_capabilities=contract.required_capabilities,
                risk=contract.risk,
                supersedes_contract_id=contract.supersedes_contract_id,
                source_contract_id=contract.source_contract_id,
                fallback_reason=contract.fallback_reason,
            )
            contract = replace(
                point_contract,
                expected_effects=contract.expected_effects,
                idempotency_key=contract.idempotency_key,
                compensation=contract.compensation,
                timeout_ms=contract.timeout_ms,
                contract_hash="",
            )
            action = self.point_encoder.encode_contract(contract)
        elif proposal.action_kind == PlannerActionKind.TYPE_TEXT:
            bid = str(affordance.locator.get("backend_handle") or "")
            if not bid:
                raise ValueError("Generalist BrowserGym binding requires an affordance bid")
            value = browsergym_fill_value(affordance.state, str(proposal.parameters["text"]))
            action = (
                BrowserGymAction("type_text_with_events", {"bid": bid, "text": value})
                if browsergym_requires_keyboard_events(affordance)
                else BrowserGymAction("fill", {"bid": bid, "value": value})
            )
        elif proposal.action_kind == PlannerActionKind.SELECT_OPTION:
            bid = str(affordance.locator.get("backend_handle") or "")
            if not bid:
                raise ValueError("Generalist BrowserGym binding requires an affordance bid")
            action = BrowserGymAction(
                "select_option",
                {"bid": bid, "options": proposal.parameters["option"]},
            )
        elif proposal.action_kind == PlannerActionKind.PRESS_KEY:
            bid = str(affordance.locator.get("backend_handle") or "")
            if not bid:
                raise ValueError("Generalist BrowserGym binding requires an affordance bid")
            action = BrowserGymAction(
                "press",
                {"bid": bid, "key_comb": str(proposal.parameters["key"])},
            )
        elif proposal.action_kind == PlannerActionKind.DRAG:
            drag_binding = contract.gesture_binding
            if drag_binding is None:
                raise ValueError("Generalist BrowserGym drag requires a core gesture binding")
            action = self.gesture_encoder.encode(drag_binding)
        else:
            raise ValueError(
                f"unsupported generalist BrowserGym semantic action: {proposal.action_kind.value}"
            )
        action.render()
        verifier_plan = browsergym_action_verifiers(action, snapshot)
        verifier_plan = declare_browsergym_active_subgoal_evidence(
            verifier_plan,
            proposal=proposal,
            state=state,
            action=action,
            affordance=affordance,
        )
        return replace(
            contract,
            action=action.name,
            backend=BROWSERGYM_BACKEND,
            parameters={"action": asdict(action)},
            verifier_plan=verifier_plan,
            contract_hash="",
        )

    def _available_executors(self, snapshot: BrowserSnapshot) -> frozenset[str]:
        del snapshot
        return frozenset({BROWSERGYM_BACKEND})

    def _route_verifier_kinds(
        self,
        semantic_target_id: str,
        snapshot: BrowserSnapshot,
    ) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [
                    *super()._route_verifier_kinds(semantic_target_id, snapshot),
                    "state_delta_or_terminal",
                ]
            )
        )


def viewport_box(value: Any) -> tuple[float, float, float, float] | None:
    """Validate one adapter-owned viewport rectangle."""

    value = thaw_json_at_external_boundary(value)
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x, y, width, height = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return None
    return x, y, width, height


def is_sortable_list_binding(binding: GestureBinding) -> bool:
    """Recognize the reusable DOM list-item gesture shape without task IDs."""

    source_selector = str(binding.source.locator.get("selector") or "").lower()
    destination_selector = str(binding.destination.locator.get("selector") or "").lower()
    source_id = str(
        getattr(binding.source, "candidate_id", "")
        or getattr(binding.source, "semantic_target_id", "")
        or getattr(binding.source, "id", "")
    ).lower()
    destination_id = str(
        getattr(binding.destination, "candidate_id", "")
        or getattr(binding.destination, "semantic_target_id", "")
        or getattr(binding.destination, "id", "")
    ).lower()
    return (source_selector.startswith("li") and destination_selector.startswith("li")) or (
        "dom_li_" in source_id and "dom_li_" in destination_id
    )


def browsergym_fill_value(affordance_state: dict[str, Any], semantic_value: str) -> str:
    """Translate semantic text to the value format required by native controls."""

    input_type = affordance_state.get("input_type")
    if input_type == "time":
        for time_format in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                return datetime.strptime(semantic_value.strip(), time_format).strftime("%H:%M")
            except ValueError:
                continue
        return semantic_value
    if input_type != "date":
        return semantic_value
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(semantic_value, date_format).date().isoformat()
        except ValueError:
            continue
    return semantic_value


def browsergym_requires_keyboard_events(affordance: Affordance) -> bool:
    """Use physical typing for a search control whose results depend on key events."""

    return (
        affordance.state.get("focused") is True
        and affordance.state.get("element_tag") == "input"
        and bool(re.search(r"\bsearch\b", affordance.label, re.IGNORECASE))
    )


def browsergym_action_verifiers(
    action: BrowserGymAction,
    snapshot: BrowserSnapshot,
) -> list[VerifierSpec]:
    """Encode action-specific postconditions from the pre-action snapshot."""

    verifier_plan = [VerifierSpec("evidence", "last_action_error", "")]
    action_bid = str(action.arguments.get("bid") or "")
    if action.name in {"fill", "type_text_with_events"}:
        verifier_plan.append(
            VerifierSpec(
                "dom_attribute",
                action_bid,
                {
                    "target_attribute": "bid",
                    "attribute": "value",
                    "value": str(action.arguments.get("value", action.arguments.get("text", ""))),
                },
            )
        )
    elif action.name == "select_option":
        selected_options = action.arguments["options"]
        verifier_plan.append(
            VerifierSpec(
                "control_state",
                action_bid,
                (
                    {"field": "selected_options", "value": selected_options}
                    if isinstance(selected_options, Sequence) and not isinstance(selected_options, (str, bytes))
                    else {"field": "value", "value": str(selected_options)}
                ),
            )
        )
    elif action.name == "press":
        previous = snapshot.observation.metadata.get("control_states", {})
        previous_state = previous.get(action_bid, {}) if isinstance(previous, Mapping) else {}
        is_scroll_region = (
            isinstance(previous_state, Mapping)
            and isinstance(previous_state.get("scroll_height"), (int, float))
            and isinstance(previous_state.get("client_height"), (int, float))
            and previous_state["scroll_height"] > previous_state["client_height"]
        )
        field_name = "scroll_top" if is_scroll_region else "aria_valuenow"
        previous_value = previous_state.get(field_name, "") if isinstance(previous_state, Mapping) else ""
        if previous_value in {None, ""} and isinstance(previous_state, Mapping):
            field_name = "context_text"
            previous_value = previous_state.get(field_name, "")
        verifier_plan.append(
            VerifierSpec(
                "control_state",
                action_bid,
                {"field": field_name, "changed_from": previous_value},
            )
        )
    elif action.name in {"click", "click_no_navigation"}:
        previous = snapshot.observation.metadata.get("control_states", {})
        previous_state = previous.get(action_bid, {}) if isinstance(previous, Mapping) else {}
        expanded = previous_state.get("aria_expanded") if isinstance(previous_state, Mapping) else None
        checked = previous_state.get("checked") if isinstance(previous_state, Mapping) else None
        if expanded in {"true", "false"}:
            verifier_plan.append(
                VerifierSpec(
                    "control_state",
                    action_bid,
                    {"field": "aria_expanded", "value": "false" if expanded == "true" else "true"},
                )
            )
        elif isinstance(checked, bool):
            verifier_plan.append(
                VerifierSpec(
                    "control_state",
                    action_bid,
                    {"field": "checked", "changed_from": checked},
                )
            )
        else:
            verifier_plan.append(VerifierSpec("state_delta_or_terminal", action_bid, True))
    elif action.name == "mouse_click":
        verifier_plan.append(VerifierSpec("state_delta_or_terminal", "", True))
    verifier_plan[-1] = replace(
        verifier_plan[-1],
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )
    return verifier_plan


def declare_browsergym_active_subgoal_evidence(
    verifier_plan: list[VerifierSpec],
    *,
    proposal: PlannerProposal,
    state: StateKernel,
    action: BrowserGymAction,
    affordance: Affordance,
) -> list[VerifierSpec]:
    """Declare exact adapter postconditions as active-subgoal evidence.

    Core remains responsible for attaching current criterion/requirement ids.
    This adapter declaration only states that its concrete backend verifier can
    prove the current typed outcome; ambiguous deltas remain terminal-only.
    """

    if not verifier_plan or state.task_plan is None or state.task_progress is None:
        return verifier_plan
    active_id = state.task_progress.active_subgoal_id
    active = next(
        (item for item in state.task_plan.subgoals if item.subgoal_id == active_id),
        None,
    )
    if (
        active is None
        or active.outcome is None
        or (
            active.action_family is not None
            and active.action_family.value != proposal.action_kind.value
        )
        or (
            not isinstance(active.interaction, RelationIntent)
            and not _browsergym_outcome_target_matches(active.outcome.subject, affordance)
        )
    ):
        return verifier_plan
    completed_click_progress = _browsergym_completed_click_progress_spec(
        action,
        relation=active.outcome.relation,
    )
    if completed_click_progress is not None:
        declared = list(verifier_plan)
        if declared and declared[-1].kind == "state_delta_or_terminal":
            declared[-1] = replace(declared[-1], strict=False)
        return [*declared, completed_click_progress]
    drag_progress = _browsergym_drag_progress_spec(action, active=active, affordance=affordance)
    if drag_progress is not None:
        return _append_authoritative_progress_spec(verifier_plan, drag_progress)
    slider_progress = _browsergym_slider_exact_progress_spec(
        action,
        verifier_plan[-1],
        active=active,
        proposal=proposal,
        state=state,
    )
    if slider_progress is not None:
        return _append_authoritative_progress_spec(verifier_plan, slider_progress)
    if not _browsergym_postcondition_proves_outcome(
        action,
        verifier_plan[-1],
        relation=active.outcome.relation,
        outcome_value=active.outcome.value,
        affordance=affordance,
        collection_intent=(
            active.interaction
            if isinstance(active.interaction, CollectionIntent)
            else None
        ),
    ):
        return verifier_plan
    declared = list(verifier_plan)
    declared[-1] = replace(
        declared[-1],
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )
    return declared


def _append_authoritative_progress_spec(
    verifier_plan: list[VerifierSpec],
    progress_spec: VerifierSpec,
) -> list[VerifierSpec]:
    """Keep action-effect checks from competing with an exact progress witness."""

    effect_only = [
        replace(item, progress_scope=ProgressEvidenceScope.NONE)
        if item.progress_scope != ProgressEvidenceScope.NONE
        else item
        for item in verifier_plan
    ]
    return [*effect_only, progress_spec]


def _browsergym_outcome_target_matches(subject: str, affordance: Affordance) -> bool:
    aliases = {
        "box": "input",
        "field": "input",
        "text": "input",
        "textbox": "input",
        "value": "input",
    }
    ignored = {
        "aria",
        "control",
        "current",
        "handle",
        "state",
        "ui",
    }

    def tokens(value: str) -> tuple[str, ...]:
        return tuple(
            aliases.get(token, token)
            for token in re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)
            if len(token) >= 3
            and not token.isdecimal()
            and token not in ignored
        )

    generic_tokens = {"input"}
    subject_tokens = tokens(subject)
    subject_specific_tokens = tuple(item for item in subject_tokens if item not in generic_tokens)
    target_tokens = tokens(" ".join((affordance.label, affordance.role)))
    target_specific_tokens = tuple(item for item in target_tokens if item not in generic_tokens)
    if subject_specific_tokens and not target_specific_tokens:
        return bool(set(subject_tokens) & set(target_tokens) & generic_tokens)
    match_tokens = subject_specific_tokens or subject_tokens
    return bool(match_tokens and target_tokens) and any(
        target == subject_token
        or (len(target) >= 4 and subject_token.startswith(target))
        or (len(subject_token) >= 4 and target.startswith(subject_token))
        for subject_token in match_tokens
        for target in target_tokens
    )


def _browsergym_completed_click_progress_spec(
    action: BrowserGymAction,
    *,
    relation: SubgoalOutcomeRelation,
) -> VerifierSpec | None:
    if action.name not in {"click", "click_no_navigation"}:
        return None
    if relation != SubgoalOutcomeRelation.IS_COMPLETED:
        return None
    action_bid = str(action.arguments.get("bid") or "")
    if not action_bid:
        return None
    return VerifierSpec(
        "observation_metadata",
        "active_control",
        action_bid,
        strict=False,
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )


def _browsergym_drag_progress_spec(
    action: BrowserGymAction,
    *,
    active: SubgoalSpec,
    affordance: Affordance,
) -> VerifierSpec | None:
    if action.name not in {"drag_and_drop", "mouse_drag_and_drop"}:
        return None
    if not isinstance(active.interaction, RelationIntent):
        return None
    backend_handle = str(affordance.locator.get("backend_handle") or "")
    if not backend_handle:
        return None
    expected: dict[str, object] | None = None
    if active.interaction.destination_ordinal is not None:
        expected = {
            "field": "collection_position",
            "value": active.interaction.destination_ordinal,
        }
    elif active.interaction.destination_offset is not None:
        position = affordance.state.get("collection_position")
        if isinstance(position, int):
            expected = {
                "field": "collection_position",
                "value": position + active.interaction.destination_offset,
            }
    elif active.interaction.source.relative_size == "smallest":
        expected = {"field": "inside_largest", "value": True}
    if expected is None:
        return None
    return VerifierSpec(
        "control_state",
        backend_handle,
        expected,
        strict=False,
        evidence_key=f"relation_state:{backend_handle}:{expected['field']}",
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )


def _browsergym_slider_exact_progress_spec(
    action: BrowserGymAction,
    verifier: VerifierSpec,
    *,
    active: SubgoalSpec,
    proposal: PlannerProposal,
    state: StateKernel,
) -> VerifierSpec | None:
    if action.name != "press" or verifier.kind != "control_state":
        return None
    expected = verifier.expected if isinstance(verifier.expected, Mapping) else {}
    field_name = str(expected.get("field") or "")
    if not field_name:
        return None
    target = _requested_slider_progress_value(active=active, proposal=proposal, state=state)
    if target is None:
        return None
    return VerifierSpec(
        "control_state",
        verifier.target,
        {"field": field_name, "value": target},
        strict=False,
        evidence_key=f"slider_target:{verifier.target}",
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )


def _requested_slider_progress_value(
    *,
    active: SubgoalSpec,
    proposal: PlannerProposal,
    state: StateKernel,
) -> str | None:
    if active.outcome is not None and active.outcome.value.strip():
        return active.outcome.value.strip()
    candidates = (
        active.outcome.subject if active.outcome is not None else "",
        active.objective,
        " ".join(active.success_criteria),
        " ".join(active.evidence_requirements),
        proposal.subgoal,
        " ".join(proposal.expected_effects),
        " ".join(proposal.evidence_requirements),
        state.goal,
    )
    for text in candidates:
        value = _single_slider_numeric_value(text)
        if value is not None:
            return value
    return None


def _single_slider_numeric_value(text: str) -> str | None:
    if not text or "slider" not in text.casefold():
        return None
    patterns = (
        r"\bselect\s+(-?\d+(?:\.\d+)?)\s+with\s+(?:the\s+)?slider\b",
        r"\bslider[_\s-]*value[_\s:-]*(-?\d+(?:\.\d+)?)\b",
        r"\bslider\b[^.;,\n]*\b(?:to|equals?|=|value)\s*(-?\d+(?:\.\d+)?)\b",
    )
    values = {
        match.group(1)
        for pattern in patterns
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    }
    return next(iter(values)) if len(values) == 1 else None


def _browsergym_postcondition_proves_outcome(
    action: BrowserGymAction,
    verifier: VerifierSpec,
    *,
    relation: SubgoalOutcomeRelation,
    outcome_value: str,
    affordance: Affordance,
    collection_intent: CollectionIntent | None = None,
) -> bool:
    expected = verifier.expected if isinstance(verifier.expected, Mapping) else {}
    normalized_outcome = browsergym_fill_value(affordance.state, outcome_value.strip())
    if action.name in {"fill", "type_text_with_events"} and verifier.kind == "dom_attribute":
        actual = str(expected.get("value", ""))
        return (
            relation
            in {
                SubgoalOutcomeRelation.EQUALS,
                SubgoalOutcomeRelation.HAS_CHANGED,
                SubgoalOutcomeRelation.MATCHES,
            }
            and bool(normalized_outcome)
            and actual == normalized_outcome
        ) or (
            relation == SubgoalOutcomeRelation.CONTAINS
            and bool(normalized_outcome)
            and normalized_outcome in actual
        )
    if action.name == "select_option" and verifier.kind == "control_state":
        options = action.arguments.get("options")
        selected = (
            [str(item) for item in options]
            if isinstance(options, Sequence) and not isinstance(options, (str, bytes))
            else [str(options)]
        )
        intended_members = (
            [str(item) for item in collection_intent.members.values]
            if collection_intent is not None
            else [normalized_outcome]
        )
        return bool(intended_members) and (
            (relation == SubgoalOutcomeRelation.IS_SELECTED and selected == intended_members)
            or
            (relation == SubgoalOutcomeRelation.EQUALS and selected == [normalized_outcome])
            or (relation == SubgoalOutcomeRelation.CONTAINS and normalized_outcome in selected)
            or (
                collection_intent is None
                and relation == SubgoalOutcomeRelation.IS_SELECTED
                and normalized_outcome in selected
            )
        )
    if action.name == "press" and verifier.kind == "control_state":
        return relation == SubgoalOutcomeRelation.HAS_CHANGED and "changed_from" in expected
    if action.name in {"click", "click_no_navigation"} and verifier.kind == "control_state":
        return (
            relation == SubgoalOutcomeRelation.IS_EXPANDED
            and expected.get("field") == "aria_expanded"
            and expected.get("value") == "true"
        ) or (
            relation
            in {
                SubgoalOutcomeRelation.HAS_CHANGED,
                SubgoalOutcomeRelation.IS_CHECKED,
            }
            and expected.get("field") == "checked"
            and "changed_from" in expected
        )
    return False
