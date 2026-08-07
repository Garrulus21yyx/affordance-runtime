import json
from pathlib import Path

import pytest

from affordance_runtime.evolution import EvolutionRegistry, EvolutionStatus
from affordance_runtime.harness_learning import (
    CanonicalSemanticTraceExtractor,
    CanonicalTaskSkillPipeline,
    CanonicalTrace,
    CanonicalTraceError,
    CanonicalTraceReport,
    CanonicalTraceValidator,
    SemanticTraceClusterer,
    TraceMiningContext,
)
from affordance_runtime.trace import JsonlTraceWriter, TraceDag


def test_canonical_trace_rows_are_deeply_immutable_from_source_rows() -> None:
    rows = [{"event": "TaskCreated", "payload": {"goal": "save"}}]
    report = CanonicalTraceReport(
        path="trace.jsonl",
        run_id="run",
        source_digest="sha256:" + "0" * 64,
        runtime_version="test",
        contract_schema_version="1.0",
        event_count=1,
        verified_contract_ids=(),
        terminal_event="TaskCompleted",
    )

    trace = CanonicalTrace(report, tuple(rows))
    rows[0]["payload"]["goal"] = "mutated"  # type: ignore[index]

    assert trace.rows[0]["payload"] == {"goal": "save"}
    with pytest.raises(TypeError):
        trace.rows[0]["payload"]["goal"] = "mutated"  # type: ignore[index]


def _write_trace(
    path: Path,
    *,
    run_id: str,
    label: str,
    value: str,
    terminal: str = "TaskCompleted",
) -> Path:
    trace = TraceDag(run_id, runtime_version="test-runtime", environment_version="layout")
    parent = trace.add("TaskCreated", {"state": "created", "goal": f"Set {label} to {value}"})
    parent = trace.add(
        "ContractBuilt",
        {
            "state": "preflight",
            "contract_id": f"contract-{run_id}",
            "semantic_action": {
                "action_kind": "type_text",
                "target": {"semantic_target_id": "semantic:name", "role": "textbox", "label": label},
                "destination": None,
                "parameters": {"text": value},
                "expected_effects": [],
                "verifier_plan": [
                    {
                        "kind": "control_state",
                        "target": "profile_name",
                        "expected": {"value": value},
                        "strict": True,
                        "evidence_key": "profile_name",
                        "criterion_ids": [],
                        "requirement_ids": [],
                    }
                ],
                "required_capabilities": ["settings.write"],
                "risk": "medium",
            },
        },
        parents=[parent.id],
    )
    parent = trace.add(
        "RouteOutcomeRecorded",
        {
            "state": "verifying",
            "contract_id": f"contract-{run_id}",
            "status": "verified_success",
            "verification_status": "passed",
            "trainable": True,
            "evidence_ids": [f"evidence-{run_id}"],
        },
        parents=[parent.id],
    )
    parent = trace.add(
        "PostActionEvaluated",
        {
            "state": "verifying",
            "contract_id": f"contract-{run_id}",
            "action_effect_status": "passed",
            "evidence": [
                {
                    "verifier_kind": "control_state",
                    "target": "profile_name",
                    "passed": True,
                    "source": "post_observation",
                    "expected": {"value": value},
                    "evidence_id": f"evidence-{run_id}",
                    "strength": "strong",
                }
            ],
        },
        parents=[parent.id],
    )
    trace.add(terminal, {"state": "done", "result": {"success": terminal == "TaskCompleted"}}, parents=[parent.id])
    return JsonlTraceWriter(path).write(trace)


def test_canonical_trace_extracts_digest_bound_backend_neutral_semantics(tmp_path: Path) -> None:
    path = _write_trace(tmp_path / "events.jsonl", run_id="profile-a", label="Name", value="Ada")

    extracted = CanonicalSemanticTraceExtractor().extract(
        path,
        TraceMiningContext("profile update", "layout-a"),
    )

    assert extracted.source_digest.startswith("sha256:")
    assert extracted.report_digest.startswith("sha256:")
    assert extracted.steps[0].target_role == "textbox"
    assert extracted.steps[0].target_label == "Name"
    assert extracted.steps[0].parameters == (("text", "Ada"),)
    assert extracted.steps[0].postconditions == (
        "control_state verifies expected state for profile_name",
    )
    assert "selector" not in json.dumps(extracted.steps[0].__dict__)


def test_canonical_trace_rejects_failed_or_unverified_and_broken_causality(tmp_path: Path) -> None:
    failed = _write_trace(
        tmp_path / "failed.jsonl",
        run_id="failed",
        label="Name",
        value="Ada",
        terminal="TaskFailed",
    )
    with pytest.raises(CanonicalTraceError, match="successful terminal"):
        CanonicalTraceValidator().validate(failed)

    path = _write_trace(tmp_path / "broken.jsonl", run_id="broken", label="Name", value="Ada")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]["parent_event_ids"] = ["future-event"]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(CanonicalTraceError, match="parent must exist earlier"):
        CanonicalTraceValidator().validate(path)


def test_cross_variant_cluster_mines_schema_11_with_source_and_report_digests(tmp_path: Path) -> None:
    extractor = CanonicalSemanticTraceExtractor()
    traces = tuple(
        extractor.extract(
            _write_trace(tmp_path / f"{run_id}.jsonl", run_id=run_id, label=label, value=value),
            TraceMiningContext("profile update", variant),
        )
        for run_id, variant, label, value in (
            ("profile-a", "layout-a", "Name", "Ada"),
            ("profile-b", "layout-b", "Full name", "Grace"),
            ("profile-c", "layout-a", "Name", "Lin"),
        )
    )

    payload = SemanticTraceClusterer().mine(
        traces,
        skill_id="profile.canonical-update",
        heldout_suite="profile-heldout-v2",
    )

    assert payload.schema_version == "1.1"
    assert payload.source_trace_digests == tuple(trace.source_digest for trace in traces)
    assert payload.mining_report_digests == tuple(trace.report_digest for trace in traces)
    assert payload.parameters[0].name == "step_1_target_label"
    assert payload.parameters[1].name == "step_1_text"


def test_cluster_does_not_merge_different_action_shapes(tmp_path: Path) -> None:
    extractor = CanonicalSemanticTraceExtractor()
    traces = [
        extractor.extract(
            _write_trace(tmp_path / f"trace-{index}.jsonl", run_id=f"trace-{index}", label="Name", value=value),
            TraceMiningContext("profile update", "layout-a" if index != 2 else "layout-b"),
        )
        for index, value in enumerate(("Ada", "Grace", "Lin"))
    ]
    incompatible = traces[0].__class__(
        trace_id="other-action",
        task_family="profile update",
        variant="layout-c",
        objective="Activate Save",
        steps=(traces[0].steps[0].__class__("activate", "button", "Save", postconditions=("saved",), evidence_requirements=("state",)),),
        source_digest=traces[0].source_digest,
        report_digest=traces[0].report_digest,
    )

    clusters = SemanticTraceClusterer().cluster((*traces, incompatible))

    assert sorted(len(cluster.traces) for cluster in clusters) == [1, 3]


def test_pipeline_quarantines_digest_bound_candidate_and_mines_negative_examples(tmp_path: Path) -> None:
    sources = tuple(
        (
            _write_trace(tmp_path / f"positive-{index}.jsonl", run_id=f"positive-{index}", label=label, value=value),
            TraceMiningContext("profile update", variant),
        )
        for index, variant, label, value in (
            (1, "layout-a", "Name", "Ada"),
            (2, "layout-b", "Full name", "Grace"),
            (3, "layout-a", "Name", "Lin"),
        )
    )
    negative = (
        (
            _write_trace(tmp_path / "negative.jsonl", run_id="negative", label="Nickname", value="Do not use"),
            TraceMiningContext("unrelated profile alias", "layout-c"),
        ),
    )
    registry = EvolutionRegistry()

    proposal = CanonicalTaskSkillPipeline().propose(
        sources,
        registry=registry,
        skill_id="profile.pipeline-update",
        heldout_suite="profile-heldout-v3",
        negative_sources=negative,
    )

    artifact = registry.artifacts[proposal.artifact_id]
    assert artifact.status == EvolutionStatus.QUARANTINED
    assert artifact.payload_digest == proposal.payload.digest()
    assert proposal.payload.negative_examples
    assert proposal.payload.applicability[0] == "task-family:profile update"
