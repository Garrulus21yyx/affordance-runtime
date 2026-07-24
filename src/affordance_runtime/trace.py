"""Causal trace DAG for runtime runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any

from affordance_runtime.contracts import ACTION_CONTRACT_SCHEMA_VERSION


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
    runtime_version: str = "0.1.0"
    contract_schema_version: str = ACTION_CONTRACT_SCHEMA_VERSION
    environment_version: str = ""
    artifact_index: list[str] = field(default_factory=list)

    def add(self, kind: str, payload: dict[str, Any], *, parents: list[str] | None = None) -> TraceNode:
        parent_ids = parents or []
        known_ids = {node.id for node in self.nodes}
        unknown = [parent for parent in parent_ids if parent not in known_ids]
        if unknown:
            raise ValueError(f"trace parent does not exist: {unknown}")
        node = TraceNode(
            id=f"{kind}_{len(self.nodes):04d}",
            kind=kind,
            payload=payload,
            parents=parent_ids,
        )
        self.nodes.append(node)
        return node

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "runtime_version": self.runtime_version,
            "contract_schema_version": self.contract_schema_version,
            "environment_version": self.environment_version,
            "artifact_index": self.artifact_index,
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

    def event_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "schema_version": "1.0",
                "run_id": self.run_id,
                "runtime_version": self.runtime_version,
                "contract_schema_version": self.contract_schema_version,
                "environment_version": self.environment_version,
                "sequence": sequence,
                "event_id": node.id,
                "event_type": node.kind,
                "parent_event_ids": node.parents,
                "timestamp_s": node.timestamp_s,
                "state": node.payload.get("state", ""),
                "artifact_refs": node.payload.get("artifact_refs", []),
                "payload": node.payload,
            }
            for sequence, node in enumerate(self.nodes)
        ]


@dataclass(frozen=True)
class JsonlTraceWriter:
    path: Path

    def write(self, trace: TraceDag) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(row, sort_keys=True, default=str) for row in trace.event_rows()]
        self.path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return self.path

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
