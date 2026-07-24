"""Conservative task-scope decisions over current typed grounding evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping

from affordance_runtime.contracts import Observation, ScopeAuthorization, ScopeRelationKind
from affordance_runtime.grounding import GroundingCandidate, UnifiedAffordance


class ScopeRejectionKind(StrEnum):
    TARGET_OUT_OF_SCOPE = "target_out_of_scope"
    UNREQUESTED_EFFECT = "unrequested_effect"


@dataclass(frozen=True)
class ProposalScopeDecision:
    authorized: bool
    rejection: ScopeRejectionKind | None = None
    detail: str = ""
    authorization: ScopeAuthorization | None = None


_SCOPE_STOPWORDS = {
    "activate",
    "button",
    "click",
    "control",
    "field",
    "input",
    "item",
    "option",
    "select",
    "the",
    "this",
    "with",
}
_EFFECT_TERMS = {
    "add",
    "buy",
    "confirm",
    "create",
    "delete",
    "download",
    "open",
    "pay",
    "publish",
    "purchase",
    "remove",
    "save",
    "send",
    "submit",
    "update",
    "upload",
}
_GENERIC_ENTITY_TERMS = {
    "book",
    "contact",
    "entry",
    "file",
    "folder",
    "node",
    "page",
    "result",
    "search",
    "tree",
}
_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


@dataclass(frozen=True)
class ProposalScopeEvaluator:
    """Keep TaskSpec as authority while accepting bounded relational proof."""

    def evaluate(
        self,
        *,
        action_kind: str,
        target_id: str,
        target_label: str,
        target_role: str,
        parameters: Mapping[str, Any],
        objective: str,
        targets: tuple[str, ...],
        unified_affordances: tuple[UnifiedAffordance, ...],
        observation: Observation,
        selected_candidate: GroundingCandidate | None = None,
    ) -> ProposalScopeDecision:
        authorized_text = " ".join((objective, *targets))
        authorized_tokens = _scope_tokens(authorized_text)
        label_tokens = _scope_tokens(target_label)
        unrequested_effects = label_tokens.intersection(_EFFECT_TERMS) - authorized_tokens
        if unrequested_effects:
            return ProposalScopeDecision(
                False,
                ScopeRejectionKind.UNREQUESTED_EFFECT,
                ",".join(sorted(unrequested_effects)),
            )
        if not targets or target_role == "option" or not label_tokens:
            return ProposalScopeDecision(True)
        target_tokens = _scope_tokens(" ".join(targets))
        semantic_label_tokens = label_tokens - _EFFECT_TERMS
        semantic_authorized_tokens = (target_tokens | authorized_tokens) - _EFFECT_TERMS
        if not (
            target_tokens
            and semantic_label_tokens
            and semantic_label_tokens.isdisjoint(semantic_authorized_tokens)
        ):
            return ProposalScopeDecision(True)

        target = next(
            (item for item in unified_affordances if item.semantic_target_id == target_id),
            None,
        )
        candidates = self._candidate_pool(target, observation, selected_candidate)
        for candidate in candidates:
            relation = self._relational_match(
                action_kind=action_kind,
                parameters=parameters,
                objective=objective,
                targets=targets,
                authorized_text=authorized_text,
                target_tokens=target_tokens,
                unified_affordances=unified_affordances,
                candidate=candidate,
            )
            if relation is not None:
                return ProposalScopeDecision(
                    True,
                    authorization=_scope_authorization(relation, candidate),
                )
        return ProposalScopeDecision(
            False,
            ScopeRejectionKind.TARGET_OUT_OF_SCOPE,
            target_id,
        )

    @staticmethod
    def _candidate_pool(
        target: UnifiedAffordance | None,
        observation: Observation,
        selected_candidate: GroundingCandidate | None,
    ) -> tuple[GroundingCandidate, ...]:
        if selected_candidate is not None:
            return (selected_candidate,) if selected_candidate.is_current(observation) else ()
        if target is None:
            return ()
        return tuple(
            candidate
            for candidate in target.grounding_candidates
            if candidate.is_current(observation)
        )

    def _relational_match(
        self,
        *,
        action_kind: str,
        parameters: Mapping[str, Any],
        objective: str,
        targets: tuple[str, ...],
        authorized_text: str,
        target_tokens: set[str],
        unified_affordances: tuple[UnifiedAffordance, ...],
        candidate: GroundingCandidate,
    ) -> ScopeRelationKind | None:
        if self._semantic_values_are_authorized(action_kind, parameters, authorized_text):
            compatible_targets = [
                item
                for item in unified_affordances
                if action_kind in item.supported_actions
            ]
            if len(compatible_targets) == 1:
                return ScopeRelationKind.SEMANTIC_VALUE_UNIQUE_CONTROL
        evidence = candidate.scope_evidence
        if evidence is None:
            return None
        requested_positions = _requested_ordinals(" ".join((objective, *targets)))
        if evidence.collection_position in requested_positions:
            return ScopeRelationKind.ORDINAL_COLLECTION_ITEM
        entity_terms = target_tokens - _GENERIC_ENTITY_TERMS
        group_tokens = _scope_tokens(evidence.group_context)
        property_tokens = _scope_tokens(evidence.container_context)
        objective_tokens = _scope_tokens(objective) - target_tokens - _EFFECT_TERMS
        if (
            entity_terms
            and not entity_terms.isdisjoint(group_tokens)
            and property_tokens
            and not property_tokens.isdisjoint(objective_tokens)
        ):
            return ScopeRelationKind.ENTITY_PROPERTY
        return None

    @staticmethod
    def _semantic_values_are_authorized(
        action_kind: str,
        parameters: Mapping[str, Any],
        authorized_text: str,
    ) -> bool:
        parameter_name = {
            "type_text": "text",
            "select_option": "option",
        }.get(action_kind)
        if parameter_name is None:
            return False
        raw_value = parameters.get(parameter_name)
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not values or any(not isinstance(value, str) or not value.strip() for value in values):
            return False
        semantic_values = [value for value in values if isinstance(value, str)]
        normalized_authority = f" {_normalize_phrase(authorized_text)} "
        return all(
            f" {_normalize_phrase(value)} " in normalized_authority
            for value in semantic_values
        )


def _scope_authorization(
    relation: ScopeRelationKind,
    candidate: GroundingCandidate,
) -> ScopeAuthorization:
    evidence_payload = {
        "relation": relation.value,
        "candidate_id": candidate.candidate_id,
        "snapshot_id": candidate.observation_epoch_id,
        "target_fingerprint": candidate.target_fingerprint,
        "scope_evidence": asdict(candidate.scope_evidence) if candidate.scope_evidence is not None else None,
    }
    encoded = json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
    return ScopeAuthorization(
        relation=relation,
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.observation_epoch_id,
        target_fingerprint=candidate.target_fingerprint,
        evidence_digest=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        evidence_refs=candidate.evidence_refs,
    )


def _scope_tokens(value: str) -> set[str]:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("-", " ")
    tokens: set[str] = set()
    for token in re.findall(r"\w+", normalized.casefold(), flags=re.UNICODE):
        if len(token) <= 2 or token in _SCOPE_STOPWORDS:
            continue
        tokens.add(token)
        if len(token) > 4 and token.endswith("ed"):
            tokens.update((token[:-1], token[:-2]))
        if len(token) > 5 and token.endswith("ing"):
            tokens.add(token[:-3])
        if len(token) > 4 and token.endswith("s"):
            tokens.add(token[:-1])
    return tokens


def _normalize_phrase(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _requested_ordinals(value: str) -> set[int]:
    normalized = _normalize_phrase(value)
    numeric = {
        int(match.group(1))
        for match in re.finditer(r"\b(\d+)(?:st|nd|rd|th)\b", normalized)
        if int(match.group(1)) > 0
    }
    return numeric | {
        position
        for word, position in _ORDINAL_WORDS.items()
        if re.search(rf"\b{word}\b", normalized)
    }
