import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from target_agent_loop_support import (
    FirstOfferedActionPolicy,
    SharedStateActionEvaluator,
    SharedStateTaskEvaluator,
    run_immediate,
    shared_state_task,
)

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.surfaces.wot import WotDeploymentScope
from affordance_runtime.surfaces.wot.adapter import WotSurfaceAdapter
from affordance_runtime.surfaces.wot.transport import HttpWotTransport
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


class SharedStateHttpFixture:
    def __init__(self) -> None:
        self.expanded = False
        self.td_calls = 0
        self.property_calls = 0
        self.action_calls = 0


@contextmanager
def shared_state_server():
    state = SharedStateHttpFixture()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/td":
                state.td_calls += 1
                self._json(_td(self.server.server_address[1]))
                return
            if self.path == "/properties/expanded":
                state.property_calls += 1
                self._json(state.expanded)
                return
            self.send_error(404)

        def do_POST(self):
            if self.path == "/actions/enable":
                state.action_calls += 1
                state.expanded = True
                self._json({"enabled": True})
                return
            self.send_error(404)

        def _json(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}/td"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _td(port: int) -> dict:
    base = f"http://127.0.0.1:{port}"
    return {
        "id": "shared-state",
        "title": "Shared State",
        "base": base,
        "securityDefinitions": {"public": {"scheme": "nosec"}},
        "security": "public",
        "properties": {
            "expanded": {
                "type": "boolean",
                "readOnly": True,
                "forms": [{"href": "/properties/expanded", "op": "readproperty"}],
            }
        },
        "actions": {
            "enable": {
                "forms": [{"href": "/actions/enable", "op": "invokeaction"}]
            }
        },
    }


def test_real_http_wot_only_short_loop_completes_with_one_semantic_action() -> None:
    with shared_state_server() as (fixture, td_url):
        environment = UnifiedWorldEnvironment(
            (
                WotSurfaceAdapter(
                    HttpWotTransport(td_url),
                    deployment_scope=WotDeploymentScope.LOCAL_SIMULATION,
                ),
            )
        )
        task = shared_state_task()
        loop = AgentLoop(
            FirstOfferedActionPolicy(),
            SharedStateActionEvaluator(),
            SharedStateTaskEvaluator(),
        )

        result = run_immediate(AgentEpisodeRunner(loop).run(environment, task))

        assert result.status == AgentLoopStatus.DONE
        assert result.observation_count == 2
        assert result.execution_count == 1
        assert result.currentness_probe_count == 1
        assert len(result.turns) == 1
        assert result.turns[0].before_observation_id != result.turns[0].after_observation_id
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.COMPLETE
        assert fixture.td_calls == 3
        assert fixture.property_calls == 2
        assert fixture.action_calls == 1
        assert tuple(adapter.surface for adapter in environment.adapters) == ("wot",)
        assert "href" not in repr(result.turns)
        assert "credential" not in repr(result)
