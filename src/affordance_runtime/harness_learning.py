"""Canonical trace validation and backend-neutral semantic skill extraction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from affordance_runtime.immutable import freeze_json
from affordance_runtime.task_skills import (
    TaskSkillMiner,
    TaskSkillPayload,
    VerifiedSemanticStep,
    VerifiedSemanticTrace,
    quarantine_task_skill,
)

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


class CanonicalTraceError(ValueError):
    """The persisted trace cannot support offline learning."""


@dataclass(frozen=True)
class TraceMiningContext:
    task_family: str
    variant: str

    def validate(self) -> None:
        if not self.task_family.strip() or not self.variant.strip():
            raise CanonicalTraceError("trace mining requires task family and environment variant")


@dataclass(frozen=True)
class CanonicalTraceReport:
    path: str
    run_id: str
    source_digest: str
    runtime_version: str
    contract_schema_version: str
    event_count: int
    verified_contract_ids: tuple[str, ...]
    terminal_event: str

    def digest(self) -> str:
        value = {
            "schema_version": "canonical-trace-report-v1",
            "run_id": self.run_id,
            "source_digest": self.source_digest,
            "runtime_version": self.runtime_version,
            "contract_schema_version": self.contract_schema_version,
            "event_count": self.event_count,
            "verified_contract_ids": self.verified_contract_ids,
            "terminal_event": self.terminal_event,
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CanonicalTrace:
    report: CanonicalTraceReport
    rows: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(freeze_json(row) for row in self.rows))


@dataclass(frozen=True)
class CanonicalTraceValidator:
    """Validate a complete, ordered, causal runtime JSONL trace."""

    def validate(self, path: Path) -> CanonicalTrace:
        encoded = path.read_bytes()
        if not encoded.strip():
            raise CanonicalTraceError("canonical trace is empty")
        source_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        rows: list[Mapping[str, Any]] = []
        for line_number, line in enumerate(encoded.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CanonicalTraceError(f"invalid JSONL at line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise CanonicalTraceError(f"trace row {line_number} must be an object")
            rows.append(value)
        if not rows:
            raise CanonicalTraceError("canonical trace has no events")

        run_id = _required_string(rows[0], "run_id")
        runtime_version = _required_string(rows[0], "runtime_version")
        contract_schema_version = _required_string(rows[0], "contract_schema_version")
        known_ids: set[str] = set()
        ancestors: dict[str, set[str]] = {}
        event_types: list[str] = []
        for sequence, row in enumerate(rows):
            if row.get("schema_version") != "1.0":
                raise CanonicalTraceError("unsupported persisted trace schema")
            if row.get("sequence") != sequence:
                raise CanonicalTraceError("trace sequence must be contiguous and ordered")
            if row.get("run_id") != run_id:
                raise CanonicalTraceError("trace rows contain mixed run ids")
            if row.get("runtime_version") != runtime_version:
                raise CanonicalTraceError("trace rows contain mixed runtime versions")
            if row.get("contract_schema_version") != contract_schema_version:
                raise CanonicalTraceError("trace rows contain mixed contract schema versions")
            event_id = _required_string(row, "event_id")
            if event_id in known_ids:
                raise CanonicalTraceError("trace event ids must be unique")
            parents = row.get("parent_event_ids")
            if not isinstance(parents, list) or not all(isinstance(item, str) for item in parents):
                raise CanonicalTraceError("trace parent ids must be a list of strings")
            missing = [item for item in parents if item not in known_ids]
            if missing:
                raise CanonicalTraceError("trace parent must exist earlier in the same trace")
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise CanonicalTraceError("trace event payload must be an object")
            known_ids.add(event_id)
            ancestors[event_id] = set(parents).union(*(ancestors[parent] for parent in parents))
            event_types.append(_required_string(row, "event_type"))

        if event_types[0] != "TaskCreated":
            raise CanonicalTraceError("canonical learning trace must start with TaskCreated")
        if (
            event_types[-1] != "TaskCompleted"
            or event_types.count("TaskCompleted") != 1
            or "TaskFailed" in event_types
            or "TaskAborted" in event_types
        ):
            raise CanonicalTraceError("canonical learning trace requires one successful terminal task")

        semantic_contract_order: list[str] = []
        semantic_contracts: set[str] = set()
        post_action_passes: set[str] = set()
        verified_outcomes: set[str] = set()
        contract_events: dict[str, str] = {}
        post_action_events: dict[str, str] = {}
        outcome_events: dict[str, str] = {}
        for row in rows:
            payload = _payload(row)
            if row["event_type"] == "ContractBuilt" and isinstance(payload.get("semantic_action"), dict):
                contract_id = _required_string(payload, "contract_id")
                if contract_id in semantic_contracts:
                    raise CanonicalTraceError("semantic contract ids must be unique")
                semantic_contract_order.append(contract_id)
                semantic_contracts.add(contract_id)
                contract_events[contract_id] = _required_string(row, "event_id")
            elif row["event_type"] == "PostActionEvaluated":
                contract_id = _required_string(payload, "contract_id")
                if payload.get("action_effect_status") != "passed":
                    continue
                evidence = payload.get("evidence")
                if not isinstance(evidence, list) or not evidence:
                    raise CanonicalTraceError("passed postcondition requires persisted verifier evidence")
                if not all(isinstance(item, dict) and item.get("passed") is True for item in evidence):
                    raise CanonicalTraceError("postcondition evidence must be independently passed")
                if not all(
                    item.get("strength") in {"strong", "authoritative"}
                    and isinstance(item.get("evidence_id"), str)
                    and item["evidence_id"]
                    and item.get("source") not in {"execution_receipt", "planner", "self_report"}
                    for item in evidence
                ):
                    raise CanonicalTraceError("learning requires strong independent postcondition evidence")
                post_action_passes.add(contract_id)
                post_action_events[contract_id] = _required_string(row, "event_id")
            elif row["event_type"] == "RouteOutcomeRecorded":
                if (
                    payload.get("status") == "verified_success"
                    and payload.get("verification_status") == "passed"
                    and payload.get("trainable") is True
                    and isinstance(payload.get("evidence_ids"), list)
                    and payload["evidence_ids"]
                ):
                    verified_outcomes.add(_required_string(payload, "contract_id"))
                    outcome_events[_required_string(payload, "contract_id")] = _required_string(row, "event_id")
        verified = semantic_contracts & post_action_passes & verified_outcomes
        if not semantic_contracts or verified != semantic_contracts:
            raise CanonicalTraceError("every semantic contract must have passed, trainable verification evidence")
        for contract_id in semantic_contract_order:
            contract_event = contract_events[contract_id]
            post_action_event = post_action_events[contract_id]
            outcome_event = outcome_events[contract_id]
            if contract_event not in ancestors[outcome_event] or outcome_event not in ancestors[post_action_event]:
                raise CanonicalTraceError("verified action lifecycle must preserve contract-to-evidence causality")

        report = CanonicalTraceReport(
            str(path),
            run_id,
            source_digest,
            runtime_version,
            contract_schema_version,
            len(rows),
            tuple(contract_id for contract_id in semantic_contract_order if contract_id in verified),
            event_types[-1],
        )
        return CanonicalTrace(report, tuple(rows))


@dataclass(frozen=True)
class CanonicalSemanticTraceExtractor:
    validator: CanonicalTraceValidator = CanonicalTraceValidator()

    def extract(self, path: Path, context: TraceMiningContext) -> VerifiedSemanticTrace:
        context.validate()
        trace = self.validator.validate(path)
        task_created = _payload(trace.rows[0])
        goal = _required_string(task_created, "goal")
        semantic_actions: dict[str, Mapping[str, Any]] = {}
        for row in trace.rows:
            if row["event_type"] != "ContractBuilt":
                continue
            payload = _payload(row)
            action = payload.get("semantic_action")
            if isinstance(action, Mapping):
                semantic_actions[_required_string(payload, "contract_id")] = action

        steps = tuple(
            self._step(semantic_actions[contract_id])
            for contract_id in trace.report.verified_contract_ids
        )
        return VerifiedSemanticTrace(
            trace_id=trace.report.run_id,
            task_family=context.task_family,
            variant=context.variant,
            objective=goal,
            steps=steps,
            source_digest=trace.report.source_digest,
            report_digest=trace.report.digest(),
        )

    @staticmethod
    def _step(action: Mapping[str, Any]) -> VerifiedSemanticStep:
        target = _mapping(action.get("target"), "semantic target")
        destination_value = action.get("destination")
        destination = _mapping(destination_value, "semantic destination") if destination_value is not None else {}
        parameters = action.get("parameters")
        if not isinstance(parameters, Mapping) or not all(isinstance(name, str) for name in parameters):
            raise CanonicalTraceError("semantic action parameters must be an object")
        verifier_plan = action.get("verifier_plan")
        if (
            not isinstance(verifier_plan, Sequence)
            or isinstance(verifier_plan, str)
            or not verifier_plan
            or not all(isinstance(item, Mapping) for item in verifier_plan)
        ):
            raise CanonicalTraceError("semantic action requires a typed verifier plan")
        postconditions = tuple(_verifier_postcondition(item) for item in verifier_plan)
        evidence_requirements = tuple(_verifier_requirement(item) for item in verifier_plan)
        return VerifiedSemanticStep(
            action_kind=_required_string(action, "action_kind"),
            target_role=_required_string(target, "role"),
            target_label=_required_string(target, "label"),
            parameters=tuple(sorted(parameters.items())),
            destination_role=str(destination.get("role", "")),
            destination_label=str(destination.get("label", "")),
            postconditions=postconditions,
            evidence_requirements=evidence_requirements,
        )


@dataclass(frozen=True)
class SemanticTraceCluster:
    cluster_id: str
    traces: tuple[VerifiedSemanticTrace, ...]


@dataclass(frozen=True)
class SemanticTraceClusterer:
    """Group independent canonical traces by backend-neutral action shape."""

    def cluster(self, traces: Iterable[VerifiedSemanticTrace]) -> tuple[SemanticTraceCluster, ...]:
        groups: dict[str, list[VerifiedSemanticTrace]] = {}
        for trace in traces:
            shape = {
                "family": trace.task_family.casefold().strip(),
                "steps": [
                    {
                        "action": step.action_kind,
                        "role": step.target_role.casefold().strip(),
                        "destination_role": step.destination_role.casefold().strip(),
                        "parameter_names": sorted(name for name, _ in step.parameters),
                        "postconditions": step.postconditions,
                        "evidence_requirements": step.evidence_requirements,
                    }
                    for step in trace.steps
                ],
            }
            encoded = json.dumps(shape, sort_keys=True, separators=(",", ":")).encode("utf-8")
            cluster_id = "sha256:" + hashlib.sha256(encoded).hexdigest()
            groups.setdefault(cluster_id, []).append(trace)
        return tuple(
            SemanticTraceCluster(cluster_id, tuple(items))
            for cluster_id, items in sorted(groups.items())
        )

    def mine(
        self,
        traces: Iterable[VerifiedSemanticTrace],
        *,
        skill_id: str,
        heldout_suite: str,
        negative_traces: Iterable[VerifiedSemanticTrace] = (),
    ) -> TaskSkillPayload:
        clusters = self.cluster(traces)
        eligible = [
            item
            for item in clusters
            if len(item.traces) >= 3 and len({trace.variant for trace in item.traces}) >= 2
        ]
        if len(eligible) != 1:
            raise CanonicalTraceError("mining requires exactly one eligible cross-variant semantic cluster")
        selected = eligible[0]
        payload = TaskSkillMiner().mine(selected.traces, skill_id=skill_id, heldout_suite=heldout_suite)
        if payload.schema_version != "1.1":
            raise CanonicalTraceError("canonical mining must produce digest-bound TaskSkill schema 1.1")
        negatives = tuple(negative_traces)
        if any(not trace.report_digest or not is_sha256_digest(trace.report_digest) for trace in negatives):
            raise CanonicalTraceError("negative examples must come from digest-bound canonical reports")
        payload = replace(
            payload,
            applicability=(
                f"task-family:{selected.traces[0].task_family.casefold().strip()}",
                f"semantic-shape:{selected.cluster_id}",
                f"minimum-variants:{len({trace.variant for trace in selected.traces})}",
            ),
            negative_examples=tuple(trace.report_digest for trace in negatives),
        )
        payload.validate()
        return payload


@dataclass(frozen=True)
class CanonicalTaskSkillProposal:
    payload: TaskSkillPayload
    artifact_id: str
    source_trace_digests: tuple[str, ...]
    source_report_digests: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalTaskSkillPipeline:
    """Extract, cluster, mine, and quarantine a candidate without activating it."""

    extractor: CanonicalSemanticTraceExtractor = CanonicalSemanticTraceExtractor()
    clusterer: SemanticTraceClusterer = SemanticTraceClusterer()

    def propose(
        self,
        sources: Iterable[tuple[Path, TraceMiningContext]],
        *,
        registry: Any,
        skill_id: str,
        heldout_suite: str,
        negative_sources: Iterable[tuple[Path, TraceMiningContext]] = (),
    ) -> CanonicalTaskSkillProposal:
        traces = tuple(self.extractor.extract(path, context) for path, context in sources)
        negatives = tuple(self.extractor.extract(path, context) for path, context in negative_sources)
        payload = self.clusterer.mine(
            traces,
            skill_id=skill_id,
            heldout_suite=heldout_suite,
            negative_traces=negatives,
        )
        artifact = quarantine_task_skill(payload, registry)
        return CanonicalTaskSkillProposal(
            payload,
            artifact.id,
            payload.source_trace_digests,
            payload.mining_report_digests,
        )


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(row.get("payload"), "trace payload")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalTraceError(f"{name} must be an object")
    return value


def _required_string(value: Mapping[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise CanonicalTraceError(f"{name} must be a non-empty string")
    return item


def _verifier_postcondition(value: Mapping[str, Any]) -> str:
    kind = _required_string(value, "kind")
    target = _required_string(value, "target")
    return f"{kind} verifies expected state for {target}"


def _verifier_requirement(value: Mapping[str, Any]) -> str:
    kind = _required_string(value, "kind")
    evidence_key = value.get("evidence_key")
    suffix = f" using {evidence_key}" if isinstance(evidence_key, str) and evidence_key else ""
    return f"independent {kind} evidence{suffix}"


def is_sha256_digest(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value))
