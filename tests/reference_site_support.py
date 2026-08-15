"""Test-owned HTTP fixture for retained target-runtime acceptance witnesses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def pricing_html(seed: int = 0, profile: str = "train") -> str:
    suffix = "" if seed == 0 and profile == "train" else f"-{profile}-{seed}"
    return f"""<!doctype html><html lang="en"><body><main><h1>Plans</h1>
<article data-plan="pro"><h2>Pro</h2>
<button id="show-pro{suffix}" onclick="showPlan('pro')" data-runtime-operation="interaction.reveal@v1"
 data-runtime-effect-class="interaction_only" data-runtime-externality="local"
 data-runtime-reversibility="reversible" data-runtime-source-assurance="structural"
 data-runtime-risk="low">Show Pro limits</button>
<dl hidden><dt>Users</dt><dd>25</dd><dt>Projects</dt><dd>100</dd><dt>Support</dt><dd>Business hours</dd></dl></article>
<article data-plan="enterprise"><h2>Enterprise</h2>
<button id="show-enterprise{suffix}" onclick="showPlan('enterprise')" data-runtime-operation="interaction.reveal@v1"
 data-runtime-effect-class="interaction_only" data-runtime-externality="local"
 data-runtime-reversibility="reversible" data-runtime-source-assurance="structural"
 data-runtime-risk="low">Show Enterprise limits</button>
<dl hidden><dt>Users</dt><dd>Unlimited</dd><dt>Projects</dt><dd>Unlimited</dd><dt>Support</dt><dd>24/7</dd></dl></article>
</main><script>function showPlan(id) {{ const plan=document.querySelector('[data-plan="'+id+'"]'); plan.querySelector('dl').hidden=false; }}</script></body></html>"""


def settings_html(current: str) -> str:
    return f"""<!doctype html><html lang="en"><body><main><h1>Notification settings</h1>
<p id="current-setting">Notifications: {current}</p>
<button id="enable-notifications" onclick="saveSetting()" data-runtime-operation="resource.update@v1"
 data-runtime-effect-class="update" data-runtime-externality="local"
 data-runtime-reversibility="reversible" data-runtime-source-assurance="structural"
 data-runtime-risk="medium">Enable notifications</button>
<script>async function saveSetting() {{ const response=await fetch('/api/settings', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{notifications:'enabled'}})}}); const value=await response.json(); document.getElementById('current-setting').textContent='Notifications: '+value.notifications; }}</script>
</main></body></html>"""


@dataclass
class ReferenceSiteState:
    settings: dict[str, str] = field(default_factory=lambda: {"notifications": "disabled"})


def create_reference_server() -> ThreadingHTTPServer:
    state = ReferenceSiteState()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/pricing":
                self._send(200, pricing_html().encode(), "text/html; charset=utf-8")
            elif path == "/settings":
                self._send(200, settings_html(state.settings["notifications"]).encode(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(200, {"settings": state.settings})
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/settings":
                self._json(404, {"error": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            value = str(payload.get("notifications") or "")
            if value not in {"enabled", "disabled"}:
                self._json(400, {"error": "invalid_setting"})
                return
            state.settings["notifications"] = value
            self._json(200, {"notifications": value})

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _json(self, status: int, value: object) -> None:
            self._send(status, json.dumps(value, sort_keys=True).encode(), "application/json")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)
