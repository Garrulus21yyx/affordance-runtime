"""One ref-free typed identity for public GUI attempts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import SemanticTarget, WorldObservation
from affordance_runtime.world.public_semantic_digest import public_page_semantic_digest


@dataclass(frozen=True)
class PublicAttemptSignature:
    operation: str
    page_semantic_digest: str
    target_semantic_digest: str
    destination_semantic_digest: str
    parameter_digest: str

    def __post_init__(self) -> None:
        if not self.operation.strip() or len(self.operation) > 80:
            raise ValueError("attempt signature operation is invalid")
        for value in (
            self.page_semantic_digest,
            self.target_semantic_digest,
            self.destination_semantic_digest,
            self.parameter_digest,
        ):
            if value and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)):
                raise ValueError("attempt signature digest is invalid")


def public_attempt_signature(
    operation: str,
    target_id: str,
    destination_id: str,
    parameters: Mapping[str, object],
    world: WorldObservation,
) -> PublicAttemptSignature:
    targets = {item.target_id: item for item in world.targets}
    return PublicAttemptSignature(
        operation,
        public_page_semantic_digest(world),
        _target_digest(targets.get(target_id), targets),
        _target_digest(targets.get(destination_id), targets),
        _digest(to_json_compatible(parameters)),
    )


def _target_digest(
    target: SemanticTarget | None,
    targets: Mapping[str, SemanticTarget],
) -> str:
    if target is None:
        return ""
    context: list[tuple[str, str]] = []
    current = target
    seen: set[str] = set()
    while len(context) < 4:
        parent_id = str(current.relations.get("parent_id", ""))
        if not parent_id or parent_id in seen or parent_id not in targets:
            break
        seen.add(parent_id)
        current = targets[parent_id]
        if current.label.strip() or current.role.strip():
            context.append((current.role.casefold(), current.label.strip()))
    return _digest(
        {
            "role": target.role.casefold(),
            "label": target.label.strip(),
            "context": tuple(context),
        }
    )


def _digest(value: object) -> str:
    canonical = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
