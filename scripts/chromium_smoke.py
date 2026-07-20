"""Focused real-Chromium smoke used by CI and clean-checkout reproduction."""

from __future__ import annotations

import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from affordance_runtime.cli import run_pricing_baseline, run_scenario
from affordance_runtime.fixtures import create_fixture_server


def main() -> int:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        with TemporaryDirectory(prefix="affordance-runtime-smoke-") as directory:
            result = run_scenario(
                "pricing",
                f"{base_url}/pricing",
                Path(directory) / "artifacts",
                run_id="ci-pricing-smoke",
            )
            baseline = run_pricing_baseline(f"{base_url}/pricing")
        if result["status"] != "done" or baseline["status"] != "done":
            raise RuntimeError(f"Chromium smoke failed: runtime={result['status']} baseline={baseline['status']}")
        print("chromium_smoke=passed")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
