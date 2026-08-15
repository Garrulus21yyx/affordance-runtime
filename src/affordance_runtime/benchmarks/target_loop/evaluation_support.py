"""Dynamic output and local-HTTP semantic fixed-case support."""

import hashlib
import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.model.evaluator import ModelPortSemanticCriterionJudge
from affordance_runtime.model.providers.port import ModelConfig, OpenAICompatibleModelPort
from affordance_runtime.task import EvaluationSpec, RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


@dataclass
class OutputEnvironment(StaticEnvironment):
    output_path: Path = field(default_factory=Path)

    async def close(self):
        self.output_path.unlink(missing_ok=True)


def output_case_parts():
    descriptor, path_text = tempfile.mkstemp(prefix="affordance-m3-", suffix=".txt")
    os.close(descriptor)
    path = Path(path_text)
    path.write_text("benchmark report", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    value = {"path": str(path), "sha256": digest}
    environment = OutputEnvironment(
        (_output_world("output:before", None), _output_world("output:after", value)),
        (ActionResult("*", DispatchStatus.SENT, "dom", True),), output_path=path,
    )
    task = TaskGoal(
        "dynamic-output", "Export report", allowed_effects=("report_exported",),
        success_criteria=({"id": "ready", "subject_id": "report:1", "predicate": "ready", "value": True},),
        requested_outputs=("report",), risk_profile=RiskProfile.LOW,
        evaluation_spec=EvaluationSpec({"criterion": "ready"}, required_output_integrity={"report": value}),
    )
    return task, environment


def _output_world(identity: str, artifact) -> WorldObservation:
    target = SemanticTarget("report:1", "document", "report", {"ready": True})
    fact = StateFact(f"fact:{identity}:ready", target.target_id, "ready", True, identity)
    binding = _binding(identity, target.target_id, "activate", "report_exported")
    artifacts = {"report": artifact} if artifact is not None else {}
    source = SurfaceObservation(
        identity, "dom", f"revision:{identity}", ObservationSourceProfile.dom(),
        (target,), (fact,), (binding,), artifacts=artifacts,
    )
    return WorldObservation(identity, (target,), (fact,), (binding,), {"dom": CoverageState.COMPLETE}, sources=(source,))


def semantic_task() -> TaskGoal:
    return TaskGoal(
        "dynamic-report", "Create a clear report", allowed_effects=("report_created",),
        success_criteria=({
            "id": "quality", "adjudicator": "semantic", "kind": "semantic_rubric",
            "rubric": "The report is clear and contains a conclusion.",
            "evidence_scope_target_ids": ["report:1"],
        },), risk_profile=RiskProfile.LOW,
    )


def semantic_world(identity: str, present: bool) -> WorldObservation:
    generator = SemanticTarget("generator:1", "button", "generate")
    targets, facts = [generator], []
    if present:
        targets.append(SemanticTarget("report:1", "content", "report"))
        facts.append(StateFact(f"fact:{identity}:report", "report:1", "content", "Clear conclusion", identity))
    binding = _binding(identity, generator.target_id, "activate", "report_created", surface="static")
    source = SurfaceObservation(
        identity, "static", f"revision:{identity}", ObservationSourceProfile.dom(),
        tuple(targets), tuple(facts), (binding,),
    )
    return WorldObservation(identity, tuple(targets), tuple(facts), (binding,), {"static": CoverageState.COMPLETE}, sources=(source,))


def _binding(identity, target_id, action, effect, *, surface="dom") -> ActionBinding:
    return ActionBinding(
        f"binding:{identity}", identity, identity, f"revision:{identity}", f"fingerprint:{identity}",
        target_id, target_id, surface, surface, action, "click", "local_reversible", (effect,),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"private_route": "omitted"}, risk=ActionRisk.LOW,
    )


@dataclass
class SemanticHttpFixtureEnvironment(StaticEnvironment):
    server: ThreadingHTTPServer | None = field(default=None, init=False)
    thread: threading.Thread | None = field(default=None, init=False)
    http_requests: int = field(default=0, init=False)

    def start_server(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                owner.http_requests += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                request = json.loads(body["messages"][1]["content"])
                evidence = request["evidence_catalog"]["items"][0]["evidence_ref"]
                proposal = {"proposals": [{"criterion_id": "quality", "status": "satisfied", "evidence_refs": [evidence], "reason": "fixture proposal"}]}
                content = json.dumps(proposal)
                payload = json.dumps({"id": "semantic:fixture", "choices": [{"message": {"content": content}}], "usage": {"total_tokens": 12}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                del format, args

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    async def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


def semantic_environment() -> SemanticHttpFixtureEnvironment:
    environment = SemanticHttpFixtureEnvironment(
        (semantic_world("semantic:before", False), semantic_world("semantic:after", True)),
        (ActionResult("*", DispatchStatus.SENT, "static", True),),
    )
    environment.start_server()
    return environment


def semantic_evaluator(environment: SemanticHttpFixtureEnvironment) -> ProductionTaskEvaluator:
    assert environment.server is not None
    port = OpenAICompatibleModelPort(
        f"http://127.0.0.1:{environment.server.server_port}", "fixture-key",
        "fixture-model", "local-fixture", "local-http",
    )
    config = ModelConfig(
        timeout_s=1.0, rate_limit_retries=0, transient_retries=0,
        prompt_version="p5-m3-fixture",
    )
    return ProductionTaskEvaluator(ModelPortSemanticCriterionJudge(port, config, 2.0))
