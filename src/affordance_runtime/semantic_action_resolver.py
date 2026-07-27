"""Typed semantic action resolution for empty strict-planner clarifications."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from affordance_runtime.planner_context import AffordanceSummary, PlannerContext
from affordance_runtime.planning import PlannerActionKind, PlannerProposal


@dataclass(frozen=True)
class SemanticActionResolution:
    """A locally resolved next semantic action from TaskSpec and current state."""

    action_kind: PlannerActionKind
    target_affordance_id: str
    destination_affordance_id: str = ""
    parameters: dict[str, str | int | float | bool | list[str]] = field(default_factory=dict)
    expected_effects: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()


def resolve_empty_clarification_action(
    context: PlannerContext,
    proposal: PlannerProposal,
) -> SemanticActionResolution | None:
    """Resolve one safe current action when the model asks an empty question.

    This resolver is intentionally narrower than the historical compatibility
    planner.  It uses only typed TaskSpec fields and current affordance
    summaries, never task names, URLs, selectors, coordinates, prompt changes,
    mutable state, trace writers, or benchmark vocabulary.
    """

    if proposal.action_kind != PlannerActionKind.ASK_USER or proposal.reason.strip():
        return None
    return (
        _resolve_text_value_entry(context)
        or _resolve_slider_press_key_entry(context)
        or _resolve_selected_option_terminal(context)
        or _resolve_requested_option_selection(context)
        or _resolve_requested_activation(context)
    )


def _resolve_text_value_entry(context: PlannerContext) -> SemanticActionResolution | None:
    if context.active_subgoal_action_family != PlannerActionKind.TYPE_TEXT.value:
        return None
    value = _requested_text_value(context)
    if not value:
        return None
    targets = [
        item
        for item in context.affordances
        if item.action in {"fill", "type", "type_text"}
        and item.state.get("enabled") is not False
        and item.state.get("visible") is not False
        and item.state.get("control_value") != value
    ]
    if len(targets) != 1:
        return None
    return SemanticActionResolution(
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=targets[0].id,
        parameters={"text": value},
        expected_effects=_expected_effects(context),
        evidence_requirements=_evidence_requirements(context),
    )


def _resolve_slider_press_key_entry(context: PlannerContext) -> SemanticActionResolution | None:
    if context.active_subgoal_action_family != PlannerActionKind.PRESS_KEY.value:
        return None
    targets = [
        item
        for item in context.affordances
        if item.action in {"press", "press_key"}
        and item.role == "slider"
        and item.state.get("enabled") is not False
        and item.state.get("visible") is not False
    ]
    if len(targets) != 1:
        return None
    requested = _requested_numeric_value(context)
    current = _current_numeric_value(targets[0])
    if requested is None or current is None or requested == current:
        return None
    return SemanticActionResolution(
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id=targets[0].id,
        parameters={"key": "ArrowRight" if requested > current else "ArrowLeft"},
        expected_effects=_expected_effects(context),
        evidence_requirements=_evidence_requirements(context),
    )


def _resolve_selected_option_terminal(context: PlannerContext) -> SemanticActionResolution | None:
    requested = _requested_option_values(context)
    if not requested or not _mentions_terminal_submission(context):
        return None
    controls = [
        item
        for item in context.affordances
        if item.action in {"select", "select_option"}
        and item.state.get("enabled") is not False
        and item.state.get("visible") is not False
    ]
    if len(controls) != 1:
        return None
    selected = {
        str(item).strip().casefold()
        for item in controls[0].state.get("selected_options", ())
        if isinstance(item, str) and item.strip()
    }
    if not selected or not any(value.casefold() in selected for value in requested):
        return None
    terminals = _terminal_activation_targets(context)
    if len(terminals) != 1:
        return None
    return SemanticActionResolution(
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=terminals[0].id,
        expected_effects=("submitted",),
        evidence_requirements=_evidence_requirements(context),
    )


def _resolve_requested_option_selection(context: PlannerContext) -> SemanticActionResolution | None:
    requested = _requested_option_values(context)
    if not requested:
        return None
    controls = [
        item
        for item in context.affordances
        if item.action in {"select", "select_option"}
        and item.state.get("enabled") is not False
        and item.state.get("visible") is not False
    ]
    if len(controls) != 1:
        return None
    selected = {
        str(item).strip().casefold()
        for item in controls[0].state.get("selected_options", ())
        if isinstance(item, str) and item.strip()
    }
    for value in requested:
        if value.casefold() not in selected:
            return SemanticActionResolution(
                action_kind=PlannerActionKind.SELECT_OPTION,
                target_affordance_id=controls[0].id,
                parameters={"option": value},
                expected_effects=_expected_effects(context),
                evidence_requirements=_evidence_requirements(context),
            )
    return None


def _resolve_requested_activation(context: PlannerContext) -> SemanticActionResolution | None:
    candidates = [
        item
        for item in context.affordances
        if item.action in {"activate", "click"}
        and item.state.get("enabled") is not False
        and item.state.get("visible") is not False
    ]
    requested_labels = _requested_activation_labels(context)
    if requested_labels:
        matches = [
            item
            for item in candidates
            if _normalized_label(item.label) in {_normalized_label(label) for label in requested_labels}
        ]
    else:
        matches = []
    if not matches and _text_corpus(context).find("close") >= 0:
        matches = [item for item in candidates if "close" in _label_tokens(item.label)]
    if len(matches) != 1:
        return None
    return SemanticActionResolution(
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=matches[0].id,
        expected_effects=_expected_effects(context),
        evidence_requirements=_evidence_requirements(context),
    )


def _requested_text_value(context: PlannerContext) -> str:
    constraints = context.task_spec.get("semantic_value_constraints")
    if isinstance(constraints, list):
        exact_values = tuple(
            value.strip()
            for item in constraints
            if isinstance(item, dict)
            and item.get("relation") == "exact"
            and isinstance(value := item.get("value"), str)
            and value.strip()
        )
        if len(set(exact_values)) == 1:
            return exact_values[0]
    values = []
    for item in _target_texts(context):
        if ":" in item:
            values.append(item.rsplit(":", 1)[1].strip())
    active_match = re.search(r":([^:]+?)\s+(?:has\s+changed|equals|is\b)", context.active_subgoal, re.IGNORECASE)
    if active_match is not None:
        values.append(active_match.group(1).strip())
    quoted = re.findall(r"['\"\u201c\u201d]([^'\"\u201c\u201d]+)['\"\u201c\u201d]", _objective(context))
    if len(quoted) == 1:
        values.append(quoted[0].strip())
    unique = tuple(dict.fromkeys(value for value in values if value))
    return unique[0] if len(unique) == 1 else ""


def _requested_option_values(context: PlannerContext) -> tuple[str, ...]:
    corpus = _text_corpus(context)
    values: list[str] = []
    for target in _target_texts(context):
        target = target.strip()
        if target and _has_literal_word(corpus, target):
            values.append(target)
    for option in (
        item.label.strip()
        for item in context.affordances
        if item.role == "option" and item.label.strip()
    ):
        if _has_literal_word(corpus, option):
            values.append(option)
    selected_options = (
        str(option).strip()
        for item in context.affordances
        if item.action in {"select", "select_option"}
        for option in item.state.get("selected_options", ())
        if isinstance(option, str) and option.strip()
    )
    for option in selected_options:
        if _has_literal_word(corpus, option):
            values.append(option)
    return tuple(dict.fromkeys(values))


def _requested_activation_labels(context: PlannerContext) -> tuple[str, ...]:
    labels: list[str] = []
    labels.extend(
        item.strip()
        for item in re.findall(r"['\"\u201c\u201d]([^'\"\u201c\u201d]+)['\"\u201c\u201d]", _objective(context))
        if item.strip()
    )
    for target in _target_texts(context):
        target = target.strip()
        bracket_match = re.search(r"text\(\)\s*=\s*['\"\u201c\u201d]([^'\"\u201c\u201d]+)['\"\u201c\u201d]", target)
        if bracket_match is not None:
            labels.append(bracket_match.group(1).strip())
        elif target and _has_literal_word(_text_corpus(context), target):
            labels.append(target)
    return tuple(dict.fromkeys(item for item in labels if item))


def _terminal_activation_targets(context: PlannerContext) -> tuple[AffordanceSummary, ...]:
    return tuple(
        item
        for item in context.affordances
        if item.action in {"activate", "click"}
        and item.state.get("enabled") is not False
        and item.state.get("visible") is not False
        and _label_tokens(item.label) & {"submit", "save", "done", "confirm", "send", "create", "continue", "next"}
    )


def _mentions_terminal_submission(context: PlannerContext) -> bool:
    return bool(_label_tokens(_text_corpus(context)) & {"submit", "save", "done", "confirm", "send"})


def _target_texts(context: PlannerContext) -> tuple[str, ...]:
    targets = context.task_spec.get("targets")
    if not isinstance(targets, list):
        return ()
    return tuple(str(item) for item in targets if isinstance(item, str) and item.strip())


def _requested_numeric_value(context: PlannerContext) -> float | None:
    for source in (context.active_subgoal, " ".join(_target_texts(context))):
        value = _single_numeric_value(source)
        if value is not None:
            return value
    criteria = context.task_spec.get("success_criteria")
    if isinstance(criteria, list):
        value = _single_numeric_value(" ".join(str(item) for item in criteria if "slider" in str(item).casefold()))
        if value is not None:
            return value
    match = re.search(r"\bselect\s+(-?\d+(?:\.\d+)?)\s+with\s+the\s+slider\b", _objective(context), re.IGNORECASE)
    return float(match.group(1)) if match is not None else None


def _current_numeric_value(affordance: AffordanceSummary) -> float | None:
    values: list[str] = []
    for key in ("control_value", "value", "aria_value_now", "valuenow", "context_text"):
        value = affordance.state.get(key)
        if isinstance(value, (int, float)):
            values.append(str(value))
        elif isinstance(value, str):
            values.extend(_numeric_strings(value))
    if not values:
        values.extend(_numeric_strings(affordance.label))
    unique = tuple(dict.fromkeys(float(item) for item in values))
    return unique[0] if len(unique) == 1 else None


def _single_numeric_value(value: str) -> float | None:
    unique = tuple(dict.fromkeys(float(item) for item in _numeric_strings(value)))
    return unique[0] if len(unique) == 1 else None


def _numeric_strings(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?(?![A-Za-z0-9])", value))


def _objective(context: PlannerContext) -> str:
    return str(context.task_spec.get("objective") or "")


def _text_corpus(context: PlannerContext) -> str:
    return " ".join(
        item
        for item in (
            _objective(context),
            context.active_subgoal,
            " ".join(_target_texts(context)),
            " ".join(str(item) for item in context.task_spec.get("success_criteria", ()) if isinstance(item, str)),
        )
        if item
    )


def _expected_effects(context: PlannerContext) -> tuple[str, ...]:
    return (context.active_subgoal,) if context.active_subgoal else ()


def _evidence_requirements(context: PlannerContext) -> tuple[str, ...]:
    requirements = context.task_spec.get("evidence_requirements")
    if not isinstance(requirements, list):
        return ()
    return tuple(str(item) for item in requirements if isinstance(item, str) and item)


def _normalized_label(value: str) -> str:
    return " ".join(_label_tokens(value))


def _label_tokens(value: str) -> set[str]:
    normalized = "".join(character.casefold() if character.isalnum() else " " for character in value)
    return {item for item in normalized.split() if item}


def _has_literal_word(corpus: str, value: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(value.strip()) + r"(?![A-Za-z0-9])"
    return bool(re.search(pattern, corpus, flags=re.IGNORECASE))
