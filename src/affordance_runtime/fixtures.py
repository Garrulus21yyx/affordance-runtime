"""Resettable local SaaS fixture used by the benchmark gold paths."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

PRICING_DATA: dict[str, dict[str, Any]] = {
    "pro": {"users": 25, "projects": 100, "support": "business-hours"},
    "enterprise": {"users": "unlimited", "projects": "unlimited", "support": "24/7"},
}
EXPORT_CONTENT = b"report_id,total\nR-001,42\n"
EXPORT_SHA256 = hashlib.sha256(EXPORT_CONTENT).hexdigest()


def pricing_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Fixture Pricing</title></head>
  <body>
    <main>
      <h1>Plans</h1>
      <article id="pro" data-plan="pro" data-visible="false" data-users="25" data-projects="100" data-support="business-hours">
        <h2>Pro</h2><button id="show-pro" onclick="showPlan('pro')">Show Pro limits</button>
        <dl hidden><dt>Users</dt><dd>25</dd><dt>Projects</dt><dd>100</dd><dt>Support</dt><dd>Business hours</dd></dl>
      </article>
      <article id="enterprise" data-plan="enterprise" data-visible="false" data-users="unlimited" data-projects="unlimited" data-support="24/7">
        <h2>Enterprise</h2><button id="show-enterprise" onclick="showPlan('enterprise')">Show Enterprise limits</button>
        <dl hidden><dt>Users</dt><dd>Unlimited</dd><dt>Projects</dt><dd>Unlimited</dd><dt>Support</dt><dd>24/7</dd></dl>
      </article>
    </main>
    <script>
      function showPlan(id) {
        const plan = document.getElementById(id);
        plan.dataset.visible = 'true';
        plan.querySelector('dl').hidden = false;
      }
    </script>
  </body>
</html>"""


def settings_html(current: str, perturbations: set[str]) -> str:
    button_id = "enable-notifications-v2" if "selector_drift" in perturbations else "enable-notifications"
    disabled = " disabled" if "async_button_state" in perturbations else ""
    modal = (
        '<div id="blocking-modal" role="dialog"><p>Confirm fixture notice</p>'
        '<button id="dismiss-modal" onclick="document.getElementById(\'blocking-modal\').remove()">Dismiss</button></div>'
        if "blocking_modal" in perturbations
        else ""
    )
    enable_script = (
        "setTimeout(() => document.querySelector('button[onclick=\"saveSetting()\"]').disabled = false, 150);"
        if "async_button_state" in perturbations
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Fixture Settings</title></head>
<body data-setting="{current}"><main>
  <h1>Notification settings</h1>
  <p id="current-setting">Notifications: {current}</p>
  {modal}
  <button id="{button_id}" onclick="saveSetting()"{disabled}>Enable notifications</button>
  <p id="save-status"></p>
</main><script>
{enable_script}
async function saveSetting() {{
  const response = await fetch('/api/settings', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{notifications: 'enabled'}})}});
  if (!response.ok) {{ document.getElementById('save-status').textContent = 'Transient error'; return; }}
  const value = await response.json();
  document.body.dataset.setting = value.notifications;
  document.getElementById('current-setting').textContent = 'Notifications: ' + value.notifications;
  document.getElementById('save-status').textContent = 'Saved';
}}
</script></body></html>"""


def reports_html() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Fixture Reports</title></head>
<body><main>
  <h1>Reports</h1>
  <a id="export-report" href="/api/export" download="report.csv">Export report</a>
</main></body></html>"""


@dataclass
class LocalSaasState:
    settings: dict[str, Any] = field(default_factory=lambda: {"notifications": "disabled"})
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    perturbations: set[str] = field(default_factory=set)
    download_delay_ms: int = 0
    settings_failures_remaining: int = 0

    def reset(self) -> None:
        self.settings = {"notifications": "disabled"}
        self.audit_log.clear()
        self.perturbations.clear()
        self.download_delay_ms = 0
        self.settings_failures_remaining = 0

    def configure_perturbations(self, names: list[str]) -> None:
        self.perturbations = set(names)
        self.download_delay_ms = 250 if "delayed_download" in self.perturbations else 0
        self.settings_failures_remaining = 1 if "transient_settings_error" in self.perturbations else 0


def make_handler(state: LocalSaasState) -> type[BaseHTTPRequestHandler]:
    class LocalSaasHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path == "/pricing":
                self._send(200, pricing_html().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/settings":
                self._send(
                    200,
                    settings_html(str(state.settings["notifications"]), state.perturbations).encode("utf-8"),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/reports":
                self._send(200, reports_html().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/pricing":
                self._json(200, PRICING_DATA)
                return
            if path == "/api/health":
                self._json(200, {"ok": True})
                return
            if path == "/api/state":
                self._json(200, {"settings": state.settings, "audit_log": state.audit_log})
                return
            if path == "/api/export":
                if state.download_delay_ms:
                    time.sleep(state.download_delay_ms / 1_000.0)
                state.audit_log.append({"effect": "report.export", "sha256": EXPORT_SHA256})
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", 'attachment; filename="report.csv"')
                self.send_header("X-Content-SHA256", EXPORT_SHA256)
                self.send_header("Content-Length", str(len(EXPORT_CONTENT)))
                self.end_headers()
                self.wfile.write(EXPORT_CONTENT)
                return
            self._json(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path == "/api/reset":
                state.reset()
                self._json(200, {"ok": True})
                return
            if path == "/api/perturbations":
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                state.configure_perturbations([str(item) for item in payload.get("names", [])])
                self._json(200, {"names": sorted(state.perturbations)})
                return
            if path == "/api/settings":
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                value = str(payload.get("notifications") or "")
                if value not in {"enabled", "disabled"}:
                    self._json(400, {"error": "invalid_setting"})
                    return
                if state.settings_failures_remaining > 0:
                    state.settings_failures_remaining -= 1
                    state.audit_log.append({"effect": "settings.write.failed", "reason": "injected_transient_error"})
                    self._json(503, {"error": "transient"})
                    return
                state.settings["notifications"] = value
                state.audit_log.append({"effect": "settings.write", "notifications": value})
                self._json(200, {"notifications": value})
                return
            self._json(404, {"error": "not_found"})

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def _json(self, status: int, value: Any) -> None:
            self._send(status, json.dumps(value, sort_keys=True).encode("utf-8"), "application/json")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return LocalSaasHandler


def create_fixture_server(host: str = "127.0.0.1", port: int = 3000) -> ThreadingHTTPServer:
    state = LocalSaasState()
    return ThreadingHTTPServer((host, port), make_handler(state))


def serve_fixture(host: str = "127.0.0.1", port: int = 3000) -> None:
    server = create_fixture_server(host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
