"""Causal trace DAG for runtime runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass(frozen=True)
class TraceNode:
    id: str
    kind: str
    payload: dict[str, Any]
    parents: list[str] = field(default_factory=list)
    timestamp_s: float = field(default_factory=time)


@dataclass
class TraceDag:
    run_id: str
    nodes: list[TraceNode] = field(default_factory=list)

    def add(self, kind: str, payload: dict[str, Any], *, parents: list[str] | None = None) -> TraceNode:
        node = TraceNode(
            id=f"{kind}_{len(self.nodes):04d}",
            kind=kind,
            payload=payload,
            parents=parents or [],
        )
        self.nodes.append(node)
        return node

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind,
                    "parents": node.parents,
                    "timestamp_s": node.timestamp_s,
                    "payload": node.payload,
                }
                for node in self.nodes
            ],
        }

