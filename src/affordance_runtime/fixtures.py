"""Resettable local SaaS fixture used by the benchmark gold paths."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LOCAL_SAAS_FIXTURE_VERSION = "2.0.0"
PRICING_DATA: dict[str, dict[str, Any]] = {
    "pro": {"users": 25, "projects": 100, "support": "business-hours"},
    "enterprise": {"users": "unlimited", "projects": "unlimited", "support": "24/7"},
}
EXPORT_CONTENT = b"report_id,total\nR-001,42\n"
EXPORT_SHA256 = hashlib.sha256(EXPORT_CONTENT).hexdigest()


def _control_id(base: str, seed: int, profile: str) -> str:
    return base if seed == 0 and profile == "train" else f"{base}-{profile}-{seed}"


def _layout_fingerprint(seed: int, profile: str) -> str:
    payload = json.dumps(
        {
            "seed": seed,
            "profile": profile,
            "direction": "column-reverse" if (seed + (profile == "heldout")) % 2 else "column",
            "offset": (seed * 37 + (101 if profile == "heldout" else 0)) % 173,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def pricing_html(seed: int = 0, profile: str = "train") -> str:
    pro_button = _control_id("show-pro", seed, profile)
    enterprise_button = _control_id("show-enterprise", seed, profile)
    direction = "column-reverse" if (seed + (profile == "heldout")) % 2 else "column"
    distractor = '<button type="button">Contact sales</button>' if profile == "heldout" else ""
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Fixture Pricing</title><style>#plans {{display:flex;flex-direction:{direction};gap:12px}}</style></head>
  <body>
    <main>
      <h1>Plans</h1>
      {distractor}
      <section id="plans">
      <article id="pro" data-plan="pro" data-visible="false" data-users="25" data-projects="100" data-support="business-hours">
        <h2>Pro</h2><button id="{pro_button}" onclick="showPlan('pro')">Show Pro limits</button>
        <dl hidden><dt>Users</dt><dd>25</dd><dt>Projects</dt><dd>100</dd><dt>Support</dt><dd>Business hours</dd></dl>
      </article>
      <article id="enterprise" data-plan="enterprise" data-visible="false" data-users="unlimited" data-projects="unlimited" data-support="24/7">
        <h2>Enterprise</h2><button id="{enterprise_button}" onclick="showPlan('enterprise')">Show Enterprise limits</button>
        <dl hidden><dt>Users</dt><dd>Unlimited</dd><dt>Projects</dt><dd>Unlimited</dd><dt>Support</dt><dd>24/7</dd></dl>
      </article>
      </section>
    </main>
    <script>
      function showPlan(id) {{
        const plan = document.getElementById(id);
        plan.dataset.visible = 'true';
        plan.querySelector('dl').hidden = false;
      }}
    </script>
  </body>
</html>"""


def settings_html(current: str, perturbations: set[str], seed: int = 0, profile: str = "train") -> str:
    button_id = _control_id("enable-notifications", seed, profile)
    if "selector_drift" in perturbations:
        button_id = f"{button_id}-drift"
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
    heldout_notice = '<button type="button" id="settings-help">Settings help</button>' if profile == "heldout" else ""
    offset = (seed * 29 + (83 if profile == "heldout" else 0)) % 140
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Fixture Settings</title></head>
<body data-setting="{current}"><main style="margin-left:{offset}px">
  <h1>Notification settings</h1>
  <p id="current-setting">Notifications: {current}</p>
  {heldout_notice}
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


def reports_html(seed: int = 0, profile: str = "train") -> str:
    export_id = _control_id("export-report", seed, profile)
    distractor = '<a href="/api/health">Preview report</a>' if profile == "heldout" else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Fixture Reports</title></head>
<body><main>
  <h1>Reports</h1>
  {distractor}
  <a id="{export_id}" href="/api/export" download="report.csv">Export report</a>
</main></body></html>"""


def visual_html(seed: int = 0, profile: str = "train") -> str:
    left = 80 + ((seed * 97 + (211 if profile == "heldout" else 0)) % 720)
    top = 100 + ((seed * 53 + (137 if profile == "heldout" else 0)) % 360)
    width = 84 + (seed % 3) * 11
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Visual Grounding Fixture</title></head>
<body><main><h1>Visual target</h1><p>Activate the magenta rectangle.</p>
<button aria-label="" style="position:absolute;left:{left}px;top:{top}px;width:{width}px;height:44px;background:rgb(212,20,232);border:0;color:black" onclick="activateVisual()">GO</button>
<p id="visual-status">pending</p></main>
<script>async function activateVisual() {{ await fetch('/api/visual', {{method:'POST'}}); document.getElementById('visual-status').textContent='activated'; }}</script>
</body></html>"""


def conformance_html(*, visual: bool = False) -> str:
    action = "/api/conformance-visual" if visual else "/api/conformance-dom"
    style = (
        "position:absolute;left:220px;top:160px;width:180px;height:52px;"
        "background:rgb(212,20,232);border:0;color:black"
        if visual
        else ""
    )
    label = "GO" if visual else "Enable shared state"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Cross-Surface Conformance</title></head>
<body><main><h1>Reversible shared state</h1>
<button type="button" style="{style}" aria-label="{'' if visual else label}" onclick="enableSharedState()">{label}</button>
<p id="conformance-status">disabled</p>
</main><script>
function enableSharedState() {{
  const request = new XMLHttpRequest();
  request.open('POST', '{action}', false);
  request.send();
  document.getElementById('conformance-status').textContent = request.status === 200 ? 'enabled' : 'failed';
}}
</script>
</body></html>"""


@dataclass
class LocalSaasState:
    settings: dict[str, Any] = field(default_factory=lambda: {"notifications": "disabled"})
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    perturbations: set[str] = field(default_factory=set)
    download_delay_ms: int = 0
    settings_failures_remaining: int = 0
    seed: int = 0
    profile: str = "train"
    visual_clicked: bool = False
    conformance_enabled: bool = False

    def reset(self, *, seed: int = 0, profile: str = "train") -> None:
        if profile not in {"train", "heldout"}:
            raise ValueError(f"unsupported fixture profile: {profile}")
        self.settings = {"notifications": "disabled"}
        self.audit_log.clear()
        self.perturbations.clear()
        self.download_delay_ms = 0
        self.settings_failures_remaining = 0
        self.seed = seed
        self.profile = profile
        self.visual_clicked = False
        self.conformance_enabled = False

    def configure_perturbations(self, names: list[str]) -> None:
        self.perturbations = set(names)
        self.download_delay_ms = 250 if "delayed_download" in self.perturbations else 0
        self.settings_failures_remaining = 1 if "transient_settings_error" in self.perturbations else 0


def make_handler(state: LocalSaasState) -> type[BaseHTTPRequestHandler]:
    class LocalSaasHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path == "/pricing":
                self._send(200, pricing_html(state.seed, state.profile).encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/settings":
                self._send(
                    200,
                    settings_html(
                        str(state.settings["notifications"]), state.perturbations, state.seed, state.profile
                    ).encode("utf-8"),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/reports":
                self._send(200, reports_html(state.seed, state.profile).encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/visual":
                self._send(200, visual_html(state.seed, state.profile).encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/conformance":
                self._send(200, conformance_html().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/conformance-visual":
                self._send(200, conformance_html(visual=True).encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/pricing":
                self._json(200, PRICING_DATA)
                return
            if path == "/api/health":
                self._json(200, {"ok": True, "fixture_version": LOCAL_SAAS_FIXTURE_VERSION})
                return
            if path == "/api/conformance":
                try:
                    self._json(200, _conformance_state(state))
                except Exception as exc:
                    self._json(503, {"error": f"{type(exc).__name__}: {exc}"})
                return
            if path == "/api/state":
                self._json(
                    200,
                    {
                        "settings": state.settings,
                        "audit_log": state.audit_log,
                        "seed": state.seed,
                        "profile": state.profile,
                        "layout_fingerprint": _layout_fingerprint(state.seed, state.profile),
                        "visual_clicked": state.visual_clicked,
                    },
                )
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
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                try:
                    state.reset(seed=int(payload.get("seed", 0)), profile=str(payload.get("profile", "train")))
                except (TypeError, ValueError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(
                    200,
                    {
                        "ok": True,
                        "seed": state.seed,
                        "profile": state.profile,
                        "layout_fingerprint": _layout_fingerprint(state.seed, state.profile),
                    },
                )
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
            if path == "/api/visual":
                state.visual_clicked = True
                state.audit_log.append({"effect": "visual.activate", "seed": state.seed, "profile": state.profile})
                self._json(200, {"activated": True})
                return
            if path in {"/api/conformance-dom", "/api/conformance-visual"}:
                surface = "visual" if path.endswith("visual") else "dom"
                try:
                    _set_conformance_state(state, True, surface=surface)
                except Exception as exc:
                    self._json(503, {"error": f"{type(exc).__name__}: {exc}"})
                    return
                self._json(200, {"enabled": True, "surface": surface})
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


def _conformance_state(state: LocalSaasState) -> dict[str, Any]:
    control_url = os.environ.get("AFFORDANCE_WOT_CONTROL_URL", "").rstrip("/")
    if not control_url:
        return {"enabled": state.conformance_enabled, "oracle": "fixture-memory"}
    with urlopen(f"{control_url}/state", timeout=3.0) as response:  # noqa: S310 - configured local proof service
        payload = json.loads(response.read())
    return {"enabled": bool(payload["state"]["enabled"]), "oracle": "node-wot-control"}


def _set_conformance_state(state: LocalSaasState, enabled: bool, *, surface: str) -> None:
    control_url = os.environ.get("AFFORDANCE_WOT_CONTROL_URL", "").rstrip("/")
    if control_url:
        request = Request(
            f"{control_url}/set",
            data=json.dumps({"enabled": enabled, "source": surface}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3.0):  # noqa: S310 - configured local proof service
            pass
    else:
        state.conformance_enabled = enabled
    state.audit_log.append({"effect": "conformance.write", "enabled": enabled, "surface": surface})


def create_fixture_server(host: str = "127.0.0.1", port: int = 3000) -> ThreadingHTTPServer:
    state = LocalSaasState()
    return ThreadingHTTPServer((host, port), make_handler(state))


def serve_fixture(host: str = "127.0.0.1", port: int = 3000) -> None:
    server = create_fixture_server(host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
