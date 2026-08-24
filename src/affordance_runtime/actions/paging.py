"""Runtime-private deterministic filtering and paging of Internal ActionSpace."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from fractions import Fraction

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

PUBLIC_ACTION_LABEL_MAX_CHARS = 240

_ROLE_ORDER = {
    ActionRelevanceRole.DIRECT: 0,
    ActionRelevanceRole.ENABLING: 1,
    ActionRelevanceRole.INFORMATION: 2,
    ActionRelevanceRole.OTHER: 3,
}

ACTION_CANDIDATE_REASON_VOCABULARY = frozenset(
    {
        "exact_label",
        "lexical_match",
        "path_match",
        "role_compatible",
        "state_ready",
        "repeated_penalty",
        "already_satisfied_penalty",
        "risk_penalty",
        "effect_penalty",
    }
)

_OPERATION_ROLES = {
    "activate": frozenset(
        {
            "button",
            "checkbox",
            "link",
            "menuitem",
            "radio",
            "switch",
            "tab",
            "treeitem",
        }
    ),
    "type_text": frozenset({"combobox", "searchbox", "textbox"}),
    "select_option": frozenset({"combobox", "listbox", "option"}),
    "check": frozenset({"checkbox", "menuitemcheckbox", "switch"}),
    "uncheck": frozenset({"checkbox", "menuitemcheckbox", "switch"}),
    "read": frozenset({"cell", "document", "gridcell", "row", "status", "table"}),
}
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_LEXICAL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "use",
        "with",
    }
)


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
class ActionReranker:
    """Non-authoritative ordering over an already admitted recall set."""

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
    ) -> tuple[RankedActionCandidate, ...]:
        roles = roles or {}
        states = states or {}
        functional_paths = functional_paths or {}
        explicit_query = canonical_action_query(query)
        intent = explicit_query or _normalize_text(" ".join((instruction, *objectives, *done_when)))
        intent_tokens = _tokens(intent)
        token_cache: dict[str, frozenset[str]] = {intent: intent_tokens}
        fuzzy_token_scores: dict[str, float] = {}

        def tokens(value: str) -> frozenset[str]:
            cached = token_cache.get(value)
            if cached is None:
                cached = _tokens(value)
                token_cache[value] = cached
            return cached

        scored: list[tuple[float, str, str, str, int, object, tuple[str, ...]]] = []
        for ordinal, option in enumerate(options):
            action_id = str(getattr(option, "action_id", ""))
            target_id = str(getattr(option, "target_id", ""))
            operation = str(getattr(option, "operation", "") or getattr(option, "semantic_action", "")).casefold()
            if not action_id or not target_id or not operation:
                continue
            label = _normalize_text(labels.get(target_id, ""))
            role = _normalize_text(roles.get(target_id, ""))
            path = tuple(value for item in functional_paths.get(target_id, ()) if (value := _normalize_text(item)))
            state = states.get(target_id, {})
            reasons: list[str] = []
            score = 0.0

            label_tokens = tokens(label)
            path_text = " ".join(path)
            path_tokens = tokens(path_text)
            exact_label = bool(
                label
                and (label == explicit_query or (label in intent and label_tokens and label_tokens <= intent_tokens))
            )
            if exact_label:
                score += 8.0
                reasons.append("exact_label")
            lexical = _lexical_score(intent_tokens, (*label_tokens, *tokens(operation), *tokens(role)))
            # Fuzzy matching belongs to an explicit bounded action query.  A
            # full task instruction is broad semantic context, not a request
            # to compare every current control token pairwise.
            fuzzy = (
                _fuzzy_score(
                    intent_tokens,
                    label_tokens,
                    token_scores=fuzzy_token_scores,
                )
                if explicit_query
                else 0.0
            )
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

            scored.append(
                (
                    -score,
                    path_text,
                    label,
                    operation,
                    ordinal,
                    option,
                    tuple(dict.fromkeys(reasons)),
                )
            )
        result = []
        for rank, item in enumerate(sorted(scored), 1):
            option = item[5]
            result.append(
                RankedActionCandidate(
                    str(getattr(option, "action_id", "")),
                    str(getattr(option, "target_id", "")),
                    item[3],
                    rank,
                    -item[0],
                    item[6],
                )
            )
        return tuple(result)


@dataclass(frozen=True)
class ActionRecallPartition:
    """Query matches plus the excluded current non-match inventory."""

    prioritized: tuple[object, ...] = ()
    remainder: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        prioritized = tuple(self.prioritized)
        remainder = tuple(self.remainder)
        prioritized_ids = tuple(str(getattr(item, "action_id", "")) for item in prioritized)
        remainder_ids = tuple(str(getattr(item, "action_id", "")) for item in remainder)
        if any(not item for item in (*prioritized_ids, *remainder_ids)) or len(
            set((*prioritized_ids, *remainder_ids))
        ) != len(prioritized_ids) + len(remainder_ids):
            raise ValueError("action recall partitions must be disjoint current actions")
        object.__setattr__(self, "prioritized", prioritized)
        object.__setattr__(self, "remainder", remainder)

    @property
    def ordered(self) -> tuple[object, ...]:
        return self.prioritized + self.remainder


@dataclass(frozen=True)
class ActionRecallSet:
    """Deterministic query filter over the complete current ActionSpace."""

    def include(
        self,
        options,
        *,
        labels: Mapping[str, str],
        roles: Mapping[str, str] | None = None,
        functional_paths: Mapping[str, tuple[str, ...]] | None = None,
        query: str = "",
        focused_target_ids: frozenset[str] = frozenset(),
        viewport_target_ids: frozenset[str] = frozenset(),
    ) -> tuple[object, ...]:
        partition = self.partition(
            options,
            labels=labels,
            roles=roles,
            functional_paths=functional_paths,
            query=query,
            focused_target_ids=focused_target_ids,
            viewport_target_ids=viewport_target_ids,
        )
        return partition.prioritized if canonical_action_query(query) else partition.ordered

    def partition(
        self,
        options,
        *,
        labels: Mapping[str, str],
        roles: Mapping[str, str] | None = None,
        functional_paths: Mapping[str, tuple[str, ...]] | None = None,
        query: str = "",
        focused_target_ids: frozenset[str] = frozenset(),
        viewport_target_ids: frozenset[str] = frozenset(),
    ) -> ActionRecallPartition:
        normalized_query = canonical_action_query(query)
        if not normalized_query:
            return ActionRecallPartition(tuple(options), ())
        roles = roles or {}
        functional_paths = functional_paths or {}
        query_tokens = _literal_tokens(normalized_query)
        role_terms = query_tokens & frozenset(
            token
            for option in options
            for token in _literal_tokens(roles.get(str(getattr(option, "target_id", "")), ""))
        )
        operation_terms = query_tokens & frozenset(
            token
            for option in options
            for token in _literal_tokens(
                getattr(option, "operation", "") or getattr(option, "semantic_action", "")
            )
        )
        target_terms = query_tokens - role_terms - operation_terms
        prioritized: list[tuple[tuple[Fraction, int, int, int], int, object]] = []
        remainder: list[object] = []
        for option in options:
            target_id = str(getattr(option, "target_id", ""))
            operation = _normalize_text(getattr(option, "operation", "") or getattr(option, "semantic_action", ""))
            label = _normalize_text(labels.get(target_id, ""))
            role = _normalize_text(roles.get(target_id, ""))
            path = tuple(_normalize_text(item) for item in functional_paths.get(target_id, ()))
            label_tokens = _literal_tokens(label)
            role_tokens = _literal_tokens(role)
            operation_tokens = _literal_tokens(operation)
            path_tokens = _literal_tokens(" ".join(path))
            exact = bool(label and _bounded_phrase_match(label, normalized_query))
            # Current ActionSpace role/operation vocabulary supplies dynamic
            # query facets; no task/site keyword table is involved.  Remaining
            # target words must hit public label/path.  Keep every genuine
            # match so explicit recall does not become a Runtime subgoal selector.
            if not role_terms <= role_tokens or not operation_terms <= operation_tokens:
                remainder.append(option)
                continue
            target_tokens = label_tokens | path_tokens
            target_overlap = target_terms & target_tokens
            if target_terms:
                if not target_overlap:
                    remainder.append(option)
                    continue
                coverage = Fraction(len(target_overlap), len(target_terms))
            elif role_terms or operation_terms or exact:
                coverage = Fraction(1, 1)
            else:
                remainder.append(option)
                continue
            structural_priority = (
                0
                if target_id in focused_target_ids
                else 1
                if target_id in viewport_target_ids
                else 2
            )
            prioritized.append(
                (
                    (
                        coverage,
                        int(exact),
                        len(target_overlap),
                        len(role_terms) + len(operation_terms),
                    ),
                    structural_priority,
                    option,
                )
            )
        return ActionRecallPartition(
            tuple(
                item
                for _, _, item in sorted(
                    prioritized,
                    key=lambda pair: (
                        -pair[0][0],
                        -pair[0][1],
                        -pair[0][2],
                        -pair[0][3],
                        pair[1],
                        _public_option_order(pair[2], labels, roles, functional_paths),
                    ),
                )
            ),
            tuple(remainder),
        )


def rank_delivery_descriptors(
    descriptors: tuple[tuple[str, str, tuple[str, ...]], ...],
    *,
    intent: str,
) -> tuple[str, ...]:
    """Rank public descriptors with the same lexical primitives as ActionCandidates."""

    intent_text = _normalize_text(intent)
    intent_tokens = _tokens(intent_text)
    scored: list[tuple[float, str]] = []
    for identity, label, structural_context in descriptors:
        normalized_label = _normalize_text(label)
        label_tokens = _tokens(normalized_label)
        structural = " ".join(_normalize_text(item) for item in structural_context)
        score = _lexical_score(intent_tokens, (*label_tokens, *_tokens(structural))) * 5.0
        if normalized_label and normalized_label in intent_text:
            score += 8.0
        scored.append((-score, identity))
    return tuple(identity for _, identity in sorted(scored))


def delivery_descriptor_matches(intent: str, label: str, structural_context: tuple[str, ...] = ()) -> bool:
    normalized_intent = _normalize_text(intent)
    normalized_label = _normalize_text(label)
    intent_tokens = _tokens(normalized_intent)
    descriptor_tokens = (*_tokens(normalized_label), *(_tokens(" ".join(structural_context))))
    return bool(
        normalized_label
        and normalized_label in normalized_intent
        or _lexical_score(intent_tokens, descriptor_tokens) > 0
    )


def canonical_action_query(query: str) -> str:
    """Return the sole bounded query semantics used by action paging."""

    if not isinstance(query, str):
        raise TypeError("action page query must be text")
    if len(query) > PUBLIC_ACTION_LABEL_MAX_CHARS:
        raise ValueError("action page query exceeds the public label/query bound")
    return _normalize_text(query)


@dataclass(frozen=True)
class InternalActionPage:
    page_id: str
    action_space_id: str
    visible_action_ids: tuple[str, ...]
    visible_destinations: tuple[tuple[str, tuple[str, ...]], ...]
    total_count: int
    visible_route_count: int
    has_more: bool
    cursor: str = ""
    next_cursor: str = ""
    offset: int = 0
    query: str = ""
    relevance: tuple[tuple[str, ActionRelevance], ...] = ()
    objective_digest: str = "objective:none"

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_action_ids", tuple(self.visible_action_ids))
        destinations = tuple((action_id, tuple(items)) for action_id, items in self.visible_destinations)
        object.__setattr__(self, "visible_destinations", destinations)
        object.__setattr__(self, "relevance", tuple(self.relevance))
        if (
            self.offset < 0
            or self.visible_route_count < len(self.visible_action_ids)
            or self.total_count < self.offset + self.visible_route_count
        ):
            raise ValueError("internal action page counts are inconsistent")
        if self.has_more != (self.total_count > self.offset + self.visible_route_count):
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
class ActionDiscoveryMatch:
    """One public target/verb record returned by current action discovery."""

    target_ref: str
    label: str
    role: str
    operation: str
    destination_refs: tuple[str, ...] = ()
    match_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "destination_refs", tuple(self.destination_refs))
        object.__setattr__(self, "match_kinds", tuple(self.match_kinds))
        if not self.target_ref or not self.role or not self.operation:
            raise ValueError("discovery match requires public target, role, and operation")
        if len(set(self.destination_refs)) != len(self.destination_refs):
            raise ValueError("discovery destinations must be unique")


@dataclass(frozen=True)
class ActionDiscoveryResult:
    """Typed public output owned by action discoverability, never CoreLoop."""

    matches: tuple[ActionDiscoveryMatch, ...]
    query: str
    source_coverage: str
    result_coverage: str
    unmatched_terms: tuple[str, ...] = ()
    suggested_next: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "matches", tuple(self.matches))
        if self.query != canonical_action_query(self.query):
            raise ValueError("discovery query must be canonical")
        if self.source_coverage not in {"complete", "partial", "unavailable"}:
            raise ValueError("discovery source coverage is invalid")
        if self.result_coverage not in {"complete", "partial", "empty"}:
            raise ValueError("discovery result coverage is invalid")
        object.__setattr__(self, "unmatched_terms", tuple(self.unmatched_terms))

    def to_public_value(self) -> dict[str, object]:
        return {
            "kind": "empty" if not self.matches else "page",
            "matches": _public_discovery_rows(self.matches),
            "searched_domain": "executable_controls",
            "source_scope": "current_action_space",
            "source_coverage": self.source_coverage,
            "result_scope": "query" if self.query else "base_inventory",
            "result_coverage": self.result_coverage,
            "query": self.query,
            "unmatched_terms": self.unmatched_terms,
            "suggested_next": self.suggested_next,
        }


def _public_discovery_rows(matches: tuple[ActionDiscoveryMatch, ...]) -> tuple[Mapping[str, object], ...]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    for item in matches:
        key = (item.target_ref, item.label, item.role)
        row = grouped.setdefault(
            key,
            {
                "target_ref": item.target_ref,
                "label": item.label,
                "role": item.role,
                "verbs": [],
                "match_kinds": [],
            },
        )
        row["verbs"].append(item.operation)
        row["match_kinds"].extend(item.match_kinds)
    return tuple(
        {
            **row,
            "verbs": tuple(dict.fromkeys(row["verbs"])),
            "match_kinds": tuple(dict.fromkeys(row["match_kinds"])),
        }
        for row in grouped.values()
    )


@dataclass(frozen=True)
class ActionPager:
    # Count is a protocol page bound. Whole-request bytes are owned later by
    # RequestAdmission.
    page_size: int = 32
    relevance_policy: ActionRelevancePolicy = ActionRelevancePolicy()

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 128:
            raise ValueError("action page size must be within [1, 128]")

    def page(
        self,
        action_space: ActionSpace,
        objective: ActionObjective | None = None,
        *,
        query: str = "",
        labels: Mapping[str, str] | None = None,
        roles: Mapping[str, str] | None = None,
        states: Mapping[str, Mapping[str, object]] | None = None,
        functional_paths: Mapping[str, tuple[str, ...]] | None = None,
        focused_target_ids: frozenset[str] = frozenset(),
        viewport_target_ids: frozenset[str] = frozenset(),
        cursor: str = "",
        page_size: int | None = None,
        allowed_action_ids: frozenset[str] | None = None,
        authority_digest: str = "",
    ) -> InternalActionPage:
        query = canonical_action_query(query)
        labels = labels or {}
        limit = min(self.page_size, page_size or self.page_size)
        if limit <= 0:
            raise ValueError("paging limits must be positive")
        objective_digest = _objective_digest(objective, authority_digest)
        fingerprint = cursor_fingerprint(
            action_space.action_space_id,
            query,
            objective_digest,
            limit,
            tuple(sorted(allowed_action_ids)) if allowed_action_ids is not None else (),
        )
        offset = decode_cursor(cursor, fingerprint) if cursor else 0
        ranked = _ranked_options(
            action_space,
            objective,
            self.relevance_policy,
            query,
            labels,
            roles or {},
            states or {},
            functional_paths or {},
            focused_target_ids,
            viewport_target_ids,
            allowed_action_ids,
        )
        route_rows = _route_rows(ranked)
        if offset > len(route_rows):
            raise ValueError("action page cursor is outside the filtered route result")
        visible_routes = route_rows[offset : offset + limit]
        visible_by_action: dict[str, tuple[tuple[int, ActionOption, ActionRelevance], list[str]]] = {}
        for ranked_item, destination_id in visible_routes:
            action_id = ranked_item[1].action_id
            if action_id not in visible_by_action:
                visible_by_action[action_id] = (ranked_item, [])
            if destination_id:
                visible_by_action[action_id][1].append(destination_id)
        visible = tuple(item[0] for item in visible_by_action.values())
        visible_ids = tuple(visible_by_action)
        visible_destinations = tuple(
            (
                action_id,
                tuple(destinations) if ranked_item[1].destination_required else ranked_item[1].eligible_destination_ids,
            )
            for action_id, (ranked_item, destinations) in visible_by_action.items()
        )
        next_offset = offset + len(visible_routes)
        has_more = next_offset < len(route_rows)
        if has_more and not visible_routes:
            raise ValueError("action page budgets cannot represent the next option")
        next_cursor = encode_cursor(next_offset, fingerprint) if has_more else ""
        page_id = _page_id(
            action_space.action_space_id,
            visible_ids,
            visible_destinations,
            cursor,
            offset,
            query,
            objective_digest,
        )
        return InternalActionPage(
            page_id=page_id,
            action_space_id=action_space.action_space_id,
            visible_action_ids=visible_ids,
            visible_destinations=visible_destinations,
            total_count=len(route_rows),
            visible_route_count=len(visible_routes),
            has_more=has_more,
            cursor=cursor,
            next_cursor=next_cursor,
            offset=offset,
            query=query,
            relevance=tuple((item[1].action_id, item[2]) for item in visible),
            objective_digest=objective_digest,
        )

    def single_action_page(
        self,
        action_space: ActionSpace,
        objective: ActionObjective | None,
        action_id: str,
        destination_id: str = "",
    ) -> InternalActionPage:
        option = action_space.find(action_id)
        if option is None:
            raise ValueError("execution page action is absent from the current ActionSpace")
        if destination_id and destination_id not in option.eligible_destination_ids:
            raise ValueError("execution page destination is absent from the current ActionSpace")
        visible_destinations = (destination_id,) if destination_id else option.eligible_destination_ids
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
            objective_digest,
        )
        return InternalActionPage(
            page_id=page_id,
            action_space_id=action_space.action_space_id,
            visible_action_ids=(action_id,),
            visible_destinations=destinations,
            total_count=1,
            visible_route_count=1,
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
    objective_digest: str,
) -> str:
    payload = (
        action_space_id,
        cursor,
        offset,
        visible_ids,
        visible_destinations,
        canonical_action_query(query),
        objective_digest,
    )
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return f"action-page:{digest}"


def _ranked_options(
    action_space: ActionSpace,
    objective: ActionObjective | None,
    relevance_policy: ActionRelevancePolicy,
    query: str,
    labels: Mapping[str, str],
    roles: Mapping[str, str],
    states: Mapping[str, Mapping[str, object]],
    functional_paths: Mapping[str, tuple[str, ...]],
    focused_target_ids: frozenset[str],
    viewport_target_ids: frozenset[str],
    allowed_action_ids: frozenset[str] | None = None,
) -> list[tuple[int, ActionOption, ActionRelevance]]:
    ranked = [
        (index, option, relevance_policy.classify(option, objective))
        for index, option in enumerate(action_space.options)
        if (allowed_action_ids is None or option.action_id in allowed_action_ids)
    ]
    if query:
        partition = ActionRecallSet().partition(
            tuple(item[1] for item in ranked),
            labels=labels,
            roles=roles,
            functional_paths=functional_paths,
            query=query,
            focused_target_ids=focused_target_ids,
            viewport_target_ids=viewport_target_ids,
        )
        prioritized_ids = tuple(str(getattr(item, "action_id", "")) for item in partition.prioritized)
        remainder_ids = {str(getattr(item, "action_id", "")) for item in partition.remainder}
        by_id = {item[1].action_id: item for item in ranked}
        prioritized = [by_id[action_id] for action_id in prioritized_ids]
        # ``find_controls`` is a filter, not a query-biased full inventory.
        # Non-matches stay private in the current ActionSpace and are available
        # to a later, materially different query.
        assert remainder_ids.isdisjoint(prioritized_ids)
        return prioritized
    if objective is not None:
        ranked.sort(key=lambda item: (_ROLE_ORDER[item[2].role], -item[2].score, item[0]))
    return ranked


def _public_option_order(option, labels, roles, functional_paths) -> tuple[object, ...]:
    target_id = str(getattr(option, "target_id", ""))
    return (
        tuple(_normalize_text(item) for item in functional_paths.get(target_id, ())),
        _normalize_text(labels.get(target_id, "")),
        _normalize_text(roles.get(target_id, "")),
        _normalize_text(getattr(option, "operation", "") or getattr(option, "semantic_action", "")),
        json.dumps(to_json_compatible(getattr(option, "parameter_schema", {})), sort_keys=True, ensure_ascii=False),
    )


def _normalize_text(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())[:1000]


def _tokens(value: str) -> frozenset[str]:
    raw = tuple(_TOKEN.findall(value))
    values: set[str] = set()
    for item in raw:
        if len(item) >= 2 and item not in _LEXICAL_STOPWORDS:
            values.add(item)
            values.add(_stem(item))
    for size in (2, 3):
        for index in range(0, len(raw) - size + 1):
            joined = "".join(raw[index : index + size])
            if 4 <= len(joined) <= 24:
                values.add(_stem(joined))
    return frozenset(item for item in values if len(item) >= 3)


def _literal_tokens(value: str) -> frozenset[str]:
    """Token-boundary recall for explicit control discovery queries."""

    return frozenset(
        item
        for item in _TOKEN.findall(value)
        if len(item) >= 2 and item not in _LEXICAL_STOPWORDS
    )


def _bounded_phrase_match(left: str, right: str) -> bool:
    """Match an exact label/query phrase without substring leakage across words."""

    if left == right:
        return True
    for needle, haystack in ((left, right), (right, left)):
        start = haystack.find(needle)
        while start >= 0:
            end = start + len(needle)
            left_boundary = not needle[0].isalnum() or start == 0 or not haystack[start - 1].isalnum()
            right_boundary = (
                not needle[-1].isalnum()
                or end == len(haystack)
                or not haystack[end].isalnum()
            )
            if left_boundary and right_boundary:
                return True
            start = haystack.find(needle, start + 1)
    return False


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


def _fuzzy_score(
    intent: frozenset[str],
    label: frozenset[str],
    *,
    token_scores: dict[str, float] | None = None,
) -> float:
    if not intent or not label:
        return 0.0
    if token_scores is None:
        return max(SequenceMatcher(None, wanted, actual).ratio() for wanted in intent for actual in label)
    for actual in label:
        if actual not in token_scores:
            token_scores[actual] = max(
                SequenceMatcher(None, wanted, actual).ratio()
                for wanted in intent
            )
    return max(token_scores[actual] for actual in label)


def _state_flag(state: Mapping[str, object], *names: str) -> bool:
    wanted = {item.casefold() for item in names}
    return any(key.casefold().rsplit(".", 1)[-1] in wanted and value is True for key, value in state.items())


def _state_ready(operation: str, state: Mapping[str, object]) -> bool:
    if any(
        key.casefold().rsplit(".", 1)[-1] in {"disabled", "hidden"} and value is True for key, value in state.items()
    ):
        return False
    if any(
        key.casefold().rsplit(".", 1)[-1] in {"enabled", "visible"} and value is False for key, value in state.items()
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
    operation = str(getattr(option, "operation", "") or getattr(option, "semantic_action", "")).casefold()
    for outcome in outcomes[-4:]:
        prior_operation = str(getattr(outcome, "semantic_action", "")).casefold()
        target = getattr(outcome, "target", None)
        prior_label = _normalize_text(getattr(target, "label", ""))
        prior_role = _normalize_text(getattr(target, "role", ""))
        transition = getattr(outcome, "transition", {})
        no_progress = (
            isinstance(transition, Mapping)
            and str(transition.get("observed_change", "")).casefold() in {"unchanged", "no_effect", "regressed"}
        ) or str(getattr(outcome, "local_postcondition", "")).casefold() in {
            "unchanged",
            "no_effect",
            "unknown",
        }
        if no_progress and prior_operation == operation and prior_label == label and prior_role == role:
            return True
    return False


def _route_rows(
    ranked: list[tuple[int, ActionOption, ActionRelevance]],
) -> list[tuple[tuple[int, ActionOption, ActionRelevance], str]]:
    rows = []
    for item in ranked:
        option = item[1]
        if option.destination_required:
            rows.extend((item, destination_id) for destination_id in option.eligible_destination_ids)
        else:
            rows.append((item, ""))
    return rows


def _objective_digest(objective: ActionObjective | None, authority_digest: str = "") -> str:
    if objective is None and not authority_digest:
        return "objective:none"
    payload = (to_json_compatible(objective), authority_digest)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"objective:{digest}"
