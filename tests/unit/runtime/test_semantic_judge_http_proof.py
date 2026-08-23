import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator as _ProductionTaskEvaluator
from affordance_runtime.model.evaluator import ModelPortSemanticCriterionJudge
from affordance_runtime.model.providers.port import ModelConfig, OpenAICompatibleModelPort
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)
from tests.support.canonical_world import canonical_world


class ProductionTaskEvaluator(_ProductionTaskEvaluator):
    async def evaluate(self, task, observation):
        return await self.evaluate_with_projection(
            task, observation, canonical_world(observation)
        )


@dataclass
class JudgeBehavior:
    status: int = 200
    delay_s: float = 0.0
    malformed: bool = False
    invented: bool = False
    requests: list[dict[str, Any]] = field(default_factory=list)


def _serve(behavior: JudgeBehavior) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP hook
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            behavior.requests.append(body)
            if behavior.delay_s:
                time.sleep(behavior.delay_s)
            if behavior.status != 200:
                payload = json.dumps({"error": {"status": "fixture"}}).encode()
                self.send_response(behavior.status)
            else:
                request = json.loads(body["messages"][1]["content"])
                evidence_ref = "fact:invented" if behavior.invented else request["evidence_catalog"]["items"][0]["evidence_ref"]
                proposal = {
                    "proposals": [{
                        "criterion_id": request["criteria"][0]["criterion_id"],
                        "status": "satisfied",
                        "evidence_refs": [evidence_ref],
                        "reason": "bounded fixture proposal",
                    }]
                }
                content = "{" if behavior.malformed else json.dumps(proposal)
                payload = json.dumps({
                    "id": "semantic:http-fixture",
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
                }).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except BrokenPipeError:
                pass

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _world() -> WorldObservation:
    fact = StateFact("fact:report", "report:1", "content", "Clear report with conclusion", "source:report")
    source = SurfaceObservation(
        "source:report", "dom", "revision:1", ObservationSourceProfile.dom(),
        targets=(SemanticTarget("report:1", "content", "report", {"content": fact.value}),),
        facts=(fact,),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _task() -> TaskGoal:
    return TaskGoal(
        "semantic", "Review the report",
        success_criteria=({
            "id": "quality", "adjudicator": "semantic", "kind": "semantic_rubric",
            "rubric": "The report is clear and contains a conclusion.",
            "evidence_scope_target_ids": ["report:1"],
        },),
    )


def _judge(server: ThreadingHTTPServer, *, deadline: float = 2.0) -> ModelPortSemanticCriterionJudge:
    port = OpenAICompatibleModelPort(
        f"http://127.0.0.1:{server.server_port}", "fixture-private-key", "fixture-model",
        "local-semantic-fixture", "local-fixture",
    )
    config = ModelConfig(
        timeout_s=max(0.01, deadline * 0.9), rate_limit_retries=0, transient_retries=0,
        prompt_version="p5-m2-semantic-fixture",
    )
    return ModelPortSemanticCriterionJudge(port, config, deadline)


def _close(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_local_http_semantic_proposal_is_evidence_validated_and_runtime_composed() -> None:
    behavior = JudgeBehavior()
    server, thread = _serve(behavior)
    judge = _judge(server)
    try:
        result = asyncio.run(ProductionTaskEvaluator(judge).evaluate(_task(), _world()))
    finally:
        _close(server, thread)

    assert result.status == TaskEvaluationStatus.COMPLETE
    assert len(behavior.requests) == 1
    request = behavior.requests[0]
    assert [item["role"] for item in request["messages"]] == ["system", "user"]
    assert "task status" not in json.dumps(request["response_format"]).casefold()
    assert request["response_format"]["json_schema"]["strict"] is True
    assert judge.last_metadata is not None and judge.last_metadata.total_tokens == 40
    assert judge.last_metadata.rate_limit_retry_count == judge.last_metadata.transient_retry_count == 0
    captured = json.dumps(request).casefold()
    assert "fixture-private-key" not in captured
    for private in ("selector", "coordinate", "bbox", "href", "backend", "executor", "credential"):
        assert private not in request["messages"][1]["content"].casefold()


@pytest.mark.parametrize(
    "behavior",
    [JudgeBehavior(status=429), JudgeBehavior(status=500), JudgeBehavior(malformed=True), JudgeBehavior(invented=True), JudgeBehavior(delay_s=0.1)],
)
def test_local_http_semantic_failures_are_one_attempt_unknown_and_no_retry(behavior: JudgeBehavior) -> None:
    server, thread = _serve(behavior)
    deadline = 0.02 if behavior.delay_s else 2.0
    try:
        result = asyncio.run(ProductionTaskEvaluator(_judge(server, deadline=deadline)).evaluate(_task(), _world()))
    finally:
        _close(server, thread)

    assert len(behavior.requests) == 1
    assert result.status == TaskEvaluationStatus.UNKNOWN
