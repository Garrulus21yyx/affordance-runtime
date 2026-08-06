"""Immutable logical action-choice membership, digest, query, and paging."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Protocol

from affordance_runtime.choice_contracts import (
    ActionChoice,
    CatalogRef,
    CatalogSlice,
    ChoiceBuildReport,
)
from affordance_runtime.immutable import to_json_compatible


class CatalogMembership(Protocol):
    def count(self) -> int: ...
    def contains(self, choice_id: str) -> bool: ...
    def get(self, choice_id: str) -> ActionChoice | None: ...
    def page(self, cursor: str | None, size: int) -> CatalogSlice: ...


class _Membership:
    def __init__(self, choices: tuple[ActionChoice, ...]) -> None:
        self._choices = choices
        self._index = {choice.choice_id: choice for choice in choices}

    def count(self) -> int:
        return len(self._choices)

    def contains(self, choice_id: str) -> bool:
        return choice_id in self._index

    def get(self, choice_id: str) -> ActionChoice | None:
        return self._index.get(choice_id)

    def page(self, cursor: str | None, size: int) -> CatalogSlice:
        if size < 1:
            raise ValueError("catalog page size must be positive")
        offset = int(cursor or 0)
        values = self._choices[offset : offset + size]
        following = offset + len(values)
        return CatalogSlice(values, str(following) if following < len(self._choices) else None)


class _LazyMembership(_Membership):
    def __init__(self, factory: Callable[[], tuple[ActionChoice, ...]]) -> None:
        self._factory = factory
        self._loaded: _Membership | None = None

    def _value(self) -> _Membership:
        if self._loaded is None:
            self._loaded = _Membership(self._factory())
        return self._loaded

    def count(self) -> int:
        return self._value().count()

    def contains(self, choice_id: str) -> bool:
        return self._value().contains(choice_id)

    def get(self, choice_id: str) -> ActionChoice | None:
        return self._value().get(choice_id)

    def page(self, cursor: str | None, size: int) -> CatalogSlice:
        return self._value().page(cursor, size)


@dataclass(frozen=True)
class ActionChoiceCatalog:
    catalog_id: str
    catalog_digest: str
    task_revision: int
    plan_revision: int
    state_version: int
    observation_ref: str
    active_step_id: str
    membership: CatalogMembership
    build_report: ChoiceBuildReport

    @classmethod
    def from_choices(
        cls,
        *,
        task_revision: int,
        plan_revision: int,
        state_version: int,
        observation_ref: str,
        active_step_id: str,
        choices: tuple[ActionChoice, ...],
        build_report: ChoiceBuildReport | None = None,
        realization: str = "eager",
    ) -> "ActionChoiceCatalog":
        ordered = tuple(sorted(choices, key=lambda item: item.choice_id))
        if len({item.choice_id for item in ordered}) != len(ordered):
            raise ValueError("catalog choice IDs must be unique")
        payload = {
            "task_revision": task_revision,
            "plan_revision": plan_revision,
            "state_version": state_version,
            "observation_ref": observation_ref,
            "active_step_id": active_step_id,
            "choices": [
                {
                    "choice_id": item.choice_id,
                    "action_kind": item.action_kind.value,
                    "target_id": item.target_id,
                    "target_label": item.target_label,
                    "destination_id": item.destination_id,
                    "destination_label": item.destination_label,
                    "parameters": to_json_compatible(item.parameters),
                    "criteria": item.criterion_ids,
                    "requirements": item.requirement_refs,
                    "effects": item.effect_refs,
                    "effectful": item.effectful,
                    "risk": item.risk,
                    "role": item.role.value,
                    "authority_proof": (
                        item.action_authority_proof.proof_digest if item.action_authority_proof else ""
                    ),
                }
                for item in ordered
            ],
            "rejections": [
                (
                    item.target_id,
                    item.action_kind.value if item.action_kind else None,
                    item.status.value,
                    item.reason_codes,
                )
                for item in (build_report.rejections if build_report else ())
            ],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if realization == "lazy":
            membership: CatalogMembership = _LazyMembership(lambda: ordered)
        elif realization in {"eager", "indexed"}:
            membership = _Membership(ordered)
        else:
            raise ValueError("unsupported catalog realization")
        report = build_report or ChoiceBuildReport(0, len(ordered))
        return cls(
            f"catalog:{digest}", digest, task_revision, plan_revision, state_version,
            observation_ref, active_step_id, membership, report,
        )

    @property
    def ref(self) -> CatalogRef:
        return CatalogRef(self.catalog_id, self.catalog_digest, self.observation_ref)

    @property
    def count(self) -> int:
        return self.membership.count()

    def contains(self, choice_id: str) -> bool:
        return self.membership.contains(choice_id)

    def get(self, choice_id: str) -> ActionChoice | None:
        return self.membership.get(choice_id)

    def page(self, cursor: str | None, size: int) -> CatalogSlice:
        return self.membership.page(cursor, size)
