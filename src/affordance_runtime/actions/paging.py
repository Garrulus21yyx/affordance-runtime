"""Runtime-private deterministic filtering and paging of Internal ActionSpace."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher

from affordance_runtime.actions.admission import (
    AdmissionContractOwner,
    AdmissionIssue,
    AdmissionIssueCode,
)
from affordance_runtime.actions.relevance import (
    ActionObjective,
    ActionRelevance,
    ActionRelevancePolicy,
    ActionRelevanceRole,
)
from affordance_runtime.actions.space_contracts import (
    ActionOption,
    ActionSpace,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.page_cursor import cursor_fingerprint, decode_cursor, encode_cursor

_ROLE_ORDER = {
    ActionRelevanceRole.DIRECT: 0,
    ActionRelevanceRole.ENABLING: 1,
    ActionRelevanceRole.INFORMATION: 2,
    ActionRelevanceRole.OTHER: 3,
}

ACTION_CANDIDATE_REASON_VOCABULARY = frozenset({
    "exact_label",
    "lexical_match",
    "path_match",
    "role_compatible",
    "state_ready",
    "newly_revealed",
    "repeated_penalty",
    "already_satisfied_penalty",
    "risk_penalty",
    "effect_penalty",
})

_OPERATION_ROLES = {
    "activate": frozenset({
        "button", "checkbox", "link", "menuitem", "radio", "switch", "tab", "treeitem",
    }),
    "type_text": frozenset({"combobox", "searchbox", "textbox"}),
    "select_option": frozenset({"combobox", "listbox", "option"}),
    "check": frozenset({"checkbox", "menuitemcheckbox", "switch"}),
    "uncheck": frozenset({"checkbox", "menuitemcheckbox", "switch"}),
    "read": frozenset({"cell", "document", "gridcell", "row", "status", "table"}),
}
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_LEXICAL_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "use", "with",
})


@dataclass(frozen=True)
class RankedActionCandidate:
    """One deterministic rank over an already legal ActionOption."""

    action_id: str
    target_id: str
    operation: str
    rank: int
    score: float
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.action_id or not self.target_id or not self.operation or self.rank < 1:
            raise ValueError("ranked action candidate identity is invalid")
        if any(item not in ACTION_CANDIDATE_REASON_VOCABULARY for item in self.reasons):
            raise ValueError("ranked action candidate reason is outside the closed vocabulary")


@dataclass(frozen=True)
class ActionCandidateRanker:
    """Pure shared ordering for automatic delivery and explicit action search."""

    fuzzy_threshold: float = 0.86

    def rank(
        self,
        options,
        *,
        labels: Mapping[str, str],
        roles: Mapping[str, str] | None = None,
        states: Mapping[str, Mapping[str, object]] | None = None,
        functional_paths: Mapping[str, tuple[str, ...]] | None = None,
        query: str = "",
        instruction: str = "",
        objectives: tuple[str, ...] = (),
        done_when: tuple[str, ...] = (),
        recent_outcomes: tuple[object, ...] = (),
        require_match: bool = False,
    ) -> tuple[RankedActionCandidate, ...]:
        roles = roles or {}
        states = states or {}
        functional_paths = functional_paths or {}
        explicit_query = _normalize_text(query[:120])
        intent = explicit_query or _normalize_text(
            " ".join((instruction, *objectives, *done_when))
        )
        intent_tokens = _tokens(intent)
        scored: list[tuple[float, str, str, str, str, tuple[str, ...]]] = []
        for option in options:
            action_id = str(getattr(option, "action_id", ""))
            target_id = str(getattr(option, "target_id", ""))
            operation = str(
                getattr(option, "operation", "") or getattr(option, "semantic_action", "")
            ).casefold()
            if not action_id or not target_id or not operation:
                continue
            label = _normalize_text(labels.get(target_id, ""))
            role = _normalize_text(roles.get(target_id, ""))
            path = tuple(
                value for item in functional_paths.get(target_id, ())
                if (value := _normalize_text(item))
            )
            state = states.get(target_id, {})
            reasons: list[str] = []
            score = 0.0

            label_tokens = _tokens(label)
            path_text = " ".join(path)
            path_tokens = _tokens(path_text)
            exact_label = bool(label and (
                label == explicit_query
                or (label in intent and label_tokens and label_tokens <= intent_tokens)
            ))
            if exact_label:
                score += 8.0
                reasons.append("exact_label")
            lexical = _lexical_score(intent_tokens, (*label_tokens, *_tokens(operation), *_tokens(role)))
            fuzzy = _fuzzy_score(intent_tokens, label_tokens)
            if lexical or fuzzy >= self.fuzzy_threshold:
                score += lexical * 3.0 + fuzzy * 2.0
                reasons.append("lexical_match")
            path_overlap = _lexical_score(intent_tokens, path_tokens)
            if path_overlap:
                score += path_overlap * 5.0
                reasons.append("path_match")
            if role in _OPERATION_ROLES.get(operation, frozenset()):
                score += 1.0
                reasons.append("role_compatible")
            if _state_ready(operation, state):
                score += 0.5
                reasons.append("state_ready")
            if _state_flag(state, "changed", "newly_revealed"):
                score += 0.75
                reasons.append("newly_revealed")
            if _state_flag(state, "selected", "active", "checked", "pressed"):
                score -= 0.75
                reasons.append("already_satisfied_penalty")
            if _repeated_without_progress(option, label, role, recent_outcomes):
                score -= 3.0
                reasons.append("repeated_penalty")
            risk = str(getattr(option, "risk", "")).casefold()
            if risk in {"medium", "high", "irreversible"}:
                score -= {"medium": 0.25, "high": 0.75, "irreversible": 1.5}[risk]
                reasons.append("risk_penalty")
            effect = str(getattr(option, "effect_category", "")).casefold()
            if effect in {"external", "irreversible"}:
                score -= 0.5 if effect == "external" else 1.0
                reasons.append("effect_penalty")

            matched = any(item in reasons for item in (
                "exact_label", "lexical_match", "path_match",
            ))
            if require_match and not matched:
                continue
            scored.append((
                -score,
                path_text,
                label,
                operation,
                action_id,
                tuple(dict.fromkeys(reasons)),
            ))
        result = []
        for rank, item in enumerate(sorted(scored), 1):
            option = next(
                candidate for candidate in options
                if str(getattr(candidate, "action_id", "")) == item[4]
            )
            result.append(RankedActionCandidate(
                item[4],
                str(getattr(option, "target_id", "")),
                item[3],
                rank,
                -item[0],
                item[5],
            ))
        return tuple(result)


def canonical_action_query(query: str) -> str:
    """Return the sole bounded query semantics used by action paging."""

    if not isinstance(query, str):
        raise TypeError("action page query must be text")
    return query[:120].casefold()


@dataclass(frozen=True)
class InternalActionPage:
    page_id: str
    action_space_id: str
    visible_action_ids: tuple[str, ...]
    visible_destinations: tuple[tuple[str, tuple[str, ...]], ...]
    total_count: int
    has_more: bool
    cursor: str = ""
    next_cursor: str = ""
    offset: int = 0
    query: str = ""
    target_id: str = ""
    relevance_role: ActionRelevanceRole | None = None
    relevance: tuple[tuple[str, ActionRelevance], ...] = ()
    objective_digest: str = "objective:none"

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_action_ids", tuple(self.visible_action_ids))
        destinations = tuple((action_id, tuple(items)) for action_id, items in self.visible_destinations)
        object.__setattr__(self, "visible_destinations", destinations)
        object.__setattr__(self, "relevance", tuple(self.relevance))
        if self.offset < 0 or self.total_count < self.offset + len(self.visible_action_ids):
            raise ValueError("internal action page counts are inconsistent")
        if self.has_more != (self.total_count > self.offset + len(self.visible_action_ids)):
            raise ValueError("internal action page continuation is inconsistent")
        if self.has_more != bool(self.next_cursor):
            raise ValueError("has_more requires a usable next cursor")
        if len(set(self.visible_action_ids)) != len(self.visible_action_ids):
            raise ValueError("internal action page IDs must be unique")
        if tuple(action_id for action_id, _ in destinations) != self.visible_action_ids:
            raise ValueError("internal action page destinations must bind every visible action")
        if any(len(set(items)) != len(items) for _, items in destinations):
            raise ValueError("internal action page destination IDs must be unique")
        if self.page_id != _page_id(
            self.action_space_id,
            self.visible_action_ids,
            destinations,
            self.cursor,
            self.offset,
            self.query,
            self.target_id,
            self.relevance_role,
            self.objective_digest,
        ):
            raise ValueError("internal action page identity does not bind its exact projection")

    def relevance_for(self, action_id: str) -> ActionRelevance | None:
        return next((item for candidate, item in self.relevance if candidate == action_id), None)

    def visible_destination_ids(self, action_id: str) -> tuple[str, ...]:
        return next((items for candidate, items in self.visible_destinations if candidate == action_id), ())

    def selection_issue(self, action_id: str, destination_id: str = "") -> AdmissionIssue | None:
        if action_id not in self.visible_action_ids:
            return AdmissionIssue(
                AdmissionIssueCode.ACTION_OUTSIDE_CURRENT_PAGE,
                ("actions",),
                AdmissionContractOwner.CURRENT_ACTION_PAGE,
                {"offered_action_ids": self.visible_action_ids},
                {"action_id_offered": False},
            )
        if destination_id and destination_id not in self.visible_destination_ids(action_id):
            return AdmissionIssue(
                AdmissionIssueCode.DESTINATION_OUTSIDE_CURRENT_PAGE,
                ("destination_id",),
                AdmissionContractOwner.CURRENT_ACTION_PAGE,
                {"offered_destination_ids": self.visible_destination_ids(action_id)},
                {"destination_id_offered": False},
            )
        return None


@dataclass(frozen=True)
class ActionPager:
    # Normal GUI slices are admitted by the byte budget, not split into tiny
    # fixed pages.  The count remains only a defensive upper bound.
    page_size: int = 128
    relevance_policy: ActionRelevancePolicy = ActionRelevancePolicy()
    max_projected_bytes: int = 24 * 1024

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 128:
            raise ValueError("action page size must be within [1, 128]")
        if self.max_projected_bytes <= 0:
            raise ValueError("action page byte budget must be positive")

    def page(
        self,
        action_space: ActionSpace,
        objective: ActionObjective | None = None,
        *,
        query: str = "",
        target_id: str = "",
        relevance_role: ActionRelevanceRole | str | None = None,
        labels: Mapping[str, str] | None = None,
        roles: Mapping[str, str] | None = None,
        states: Mapping[str, Mapping[str, object]] | None = None,
        functional_paths: Mapping[str, tuple[str, ...]] | None = None,
        cursor: str = "",
        page_size: int | None = None,
        max_destinations_per_option: int = 16,
        max_targets: int = 64,
        allowed_action_ids: frozenset[str] | None = None,
        authority_digest: str = "",
    ) -> InternalActionPage:
        query = canonical_action_query(query)
        role = ActionRelevanceRole(relevance_role) if relevance_role else None
        labels = labels or {}
        limit = min(self.page_size, page_size or self.page_size)
        if limit <= 0 or max_destinations_per_option <= 0 or max_targets <= 0:
            raise ValueError("paging limits must be positive")
        objective_digest = _objective_digest(objective, authority_digest)
        fingerprint = cursor_fingerprint(
            action_space.action_space_id,
            query,
            target_id,
            role,
            objective_digest,
            limit,
            max_destinations_per_option,
            max_targets,
            tuple(sorted(allowed_action_ids)) if allowed_action_ids is not None else (),
        )
        offset = decode_cursor(cursor, fingerprint) if cursor else 0
        ranked = _ranked_options(
            action_space,
            objective,
            self.relevance_policy,
            query,
            target_id,
            role,
            labels,
            roles or {},
            states or {},
            functional_paths or {},
            allowed_action_ids,
        )
        if offset > len(ranked):
            raise ValueError("action page cursor is outside the filtered result")
        visible = _select_page_slice(
            ranked,
            offset,
            limit,
            max_destinations_per_option,
            max_targets,
            self.max_projected_bytes,
        )
        visible_ids = tuple(item[1].action_id for item in visible)
        visible_destinations = tuple(
            (item[1].action_id, item[1].eligible_destination_ids[:max_destinations_per_option])
            for item in visible
        )
        next_offset = offset + len(visible)
        has_more = next_offset < len(ranked)
        if has_more and not visible:
            raise ValueError("action page budgets cannot represent the next option")
        next_cursor = encode_cursor(next_offset, fingerprint) if has_more else ""
        page_id = _page_id(
            action_space.action_space_id,
            visible_ids,
            visible_destinations,
            cursor,
            offset,
            query,
            target_id,
            role,
            objective_digest,
        )
        return InternalActionPage(
            page_id=page_id,
            action_space_id=action_space.action_space_id,
            visible_action_ids=visible_ids,
            visible_destinations=visible_destinations,
            total_count=len(ranked),
            has_more=has_more,
            cursor=cursor,
            next_cursor=next_cursor,
            offset=offset,
            query=query,
            target_id=target_id,
            relevance_role=role,
            relevance=tuple((item[1].action_id, item[2]) for item in visible),
            objective_digest=objective_digest,
        )

    def single_action_page(
        self,
        action_space: ActionSpace,
        objective: ActionObjective | None,
        action_id: str,
        destination_id: str = "",
        *,
        max_destinations_per_option: int = 16,
    ) -> InternalActionPage:
        option = action_space.find(action_id)
        if option is None:
            raise ValueError("execution page action is absent from the current ActionSpace")
        if destination_id and destination_id not in option.eligible_destination_ids:
            raise ValueError("execution page destination is absent from the current ActionSpace")
        visible_destinations = (
            (destination_id,)
            if destination_id
            else option.eligible_destination_ids[:max_destinations_per_option]
        )
        objective_digest = _objective_digest(objective)
        destinations = ((action_id, visible_destinations),)
        relevance = self.relevance_policy.classify(option, objective)
        page_id = _page_id(
            action_space.action_space_id,
            (action_id,),
            destinations,
            "",
            0,
            "",
            "",
            None,
            objective_digest,
        )
        return InternalActionPage(
            page_id=page_id,
            action_space_id=action_space.action_space_id,
            visible_action_ids=(action_id,),
            visible_destinations=destinations,
            total_count=1,
            has_more=False,
            relevance=((action_id, relevance),),
            objective_digest=objective_digest,
        )


def _page_id(
    action_space_id: str,
    visible_ids: tuple[str, ...],
    visible_destinations: tuple[tuple[str, tuple[str, ...]], ...],
    cursor: str,
    offset: int,
    query: str,
    target_id: str,
    role: ActionRelevanceRole | None,
    objective_digest: str,
) -> str:
    payload = (
        action_space_id,
        cursor,
        offset,
        visible_ids,
        visible_destinations,
        canonical_action_query(query),
        target_id,
        role.value if role else "",
        objective_digest,
    )
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return f"action-page:{digest}"


def _ranked_options(
    action_space: ActionSpace,
    objective: ActionObjective | None,
    relevance_policy: ActionRelevancePolicy,
    query: str,
    target_id: str,
    role: ActionRelevanceRole | None,
    labels: Mapping[str, str],
    roles: Mapping[str, str],
    states: Mapping[str, Mapping[str, object]],
    functional_paths: Mapping[str, tuple[str, ...]],
    allowed_action_ids: frozenset[str] | None = None,
) -> list[tuple[int, ActionOption, ActionRelevance]]:
    ranked = [
        (index, option, relevance_policy.classify(option, objective))
        for index, option in enumerate(action_space.options)
        if (allowed_action_ids is None or option.action_id in allowed_action_ids)
        and (not target_id or option.target_id == target_id)
    ]
    if role is not None:
        ranked = [item for item in ranked if item[2].role == role]
    if query:
        shared_order = ActionCandidateRanker().rank(
            tuple(item[1] for item in ranked),
            labels=labels,
            roles=roles,
            states=states,
            functional_paths=functional_paths,
            query=query,
            require_match=True,
        )
        order = {item.action_id: item.rank for item in shared_order}
        ranked = [item for item in ranked if item[1].action_id in order]
        ranked.sort(key=lambda item: order[item[1].action_id])
    if objective is not None:
        ranked.sort(key=lambda item: (_ROLE_ORDER[item[2].role], -item[2].score, item[0]))
    return ranked


def _normalize_text(value: object) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", str(value)).casefold().split()
    )[:1000]


def _tokens(value: str) -> frozenset[str]:
    raw = tuple(_TOKEN.findall(value))
    values: set[str] = set()
    for item in raw:
        if len(item) >= 2 and item not in _LEXICAL_STOPWORDS:
            values.add(item)
            values.add(_stem(item))
        if len(item) >= 8:
            values.update((item[:4], item[-4:]))
    for size in (2, 3):
        for index in range(0, len(raw) - size + 1):
            joined = "".join(raw[index : index + size])
            if 4 <= len(joined) <= 24:
                values.add(_stem(joined))
    return frozenset(item for item in values if len(item) >= 3)


def _stem(value: str) -> str:
    if len(value) > 6 and value.endswith("ing"):
        return value[:-3]
    if len(value) > 5 and value.endswith("ers"):
        return value[:-3]
    if len(value) > 4 and value.endswith("s"):
        return value[:-1]
    return value


def _lexical_score(intent: frozenset[str], candidate) -> float:
    values = frozenset(candidate)
    if not intent or not values:
        return 0.0
    return len(intent & values) / max(1, len(values))


def _fuzzy_score(intent: frozenset[str], label: frozenset[str]) -> float:
    if not intent or not label:
        return 0.0
    return max(
        SequenceMatcher(None, wanted, actual).ratio()
        for wanted in intent
        for actual in label
    )


def _state_flag(state: Mapping[str, object], *names: str) -> bool:
    wanted = {item.casefold() for item in names}
    return any(
        key.casefold().rsplit(".", 1)[-1] in wanted and value is True
        for key, value in state.items()
    )


def _state_ready(operation: str, state: Mapping[str, object]) -> bool:
    if any(
        key.casefold().rsplit(".", 1)[-1] in {"disabled", "hidden"} and value is True
        for key, value in state.items()
    ):
        return False
    if any(
        key.casefold().rsplit(".", 1)[-1] in {"enabled", "visible"} and value is False
        for key, value in state.items()
    ):
        return False
    if operation == "type_text" and any(
        key.casefold().rsplit(".", 1)[-1] in {"editable", "readonly"}
        and (value is False if key.casefold().endswith("editable") else value is True)
        for key, value in state.items()
    ):
        return False
    return True


def _repeated_without_progress(option, label: str, role: str, outcomes: tuple[object, ...]) -> bool:
    operation = str(
        getattr(option, "operation", "") or getattr(option, "semantic_action", "")
    ).casefold()
    for outcome in outcomes[-4:]:
        prior_operation = str(getattr(outcome, "semantic_action", "")).casefold()
        target = getattr(outcome, "target", None)
        prior_label = _normalize_text(getattr(target, "label", ""))
        prior_role = _normalize_text(getattr(target, "role", ""))
        transition = getattr(outcome, "transition", {})
        no_progress = (
            isinstance(transition, Mapping)
            and str(transition.get("observed_change", "")).casefold()
            in {"unchanged", "no_effect", "regressed"}
        ) or str(getattr(outcome, "local_postcondition", "")).casefold() in {
            "unchanged", "no_effect", "unknown",
        }
        if no_progress and prior_operation == operation and prior_label == label and prior_role == role:
            return True
    return False


def _select_page_slice(
    ranked: list[tuple[int, ActionOption, ActionRelevance]],
    offset: int,
    limit: int,
    max_destinations: int,
    max_targets: int,
    max_bytes: int,
) -> list[tuple[int, ActionOption, ActionRelevance]]:
    visible: list[tuple[int, ActionOption, ActionRelevance]] = []
    projected_bytes = 0
    pinned_targets: set[str] = set()
    for item in ranked[offset : offset + limit]:
        option_bytes = _projected_option_weight(item[1], max_destinations)
        if option_bytes > max_bytes:
            raise ValueError("single action option exceeds the page byte budget")
        option_targets = {item[1].target_id, *item[1].eligible_destination_ids[:max_destinations]}
        if len(pinned_targets | option_targets) > max_targets or projected_bytes + option_bytes > max_bytes:
            break
        visible.append(item)
        projected_bytes += option_bytes
        pinned_targets.update(option_targets)
    return visible


def _projected_option_weight(option: ActionOption, max_destinations: int) -> int:
    payload = (
        option.action_id,
        option.semantic_action,
        option.target_id,
        option.effect_category,
        to_json_compatible(option.parameter_schema),
        option.description,
        option.semantic_effects,
        option.risk,
        option.destination_required,
        option.eligible_destination_ids[:max_destinations],
        option.observation_barrier,
    )
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _objective_digest(objective: ActionObjective | None, authority_digest: str = "") -> str:
    if objective is None and not authority_digest:
        return "objective:none"
    payload = (to_json_compatible(objective), authority_digest)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"objective:{digest}"
