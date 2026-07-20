"""Screenshot-derived visual grounding benchmark over real Chromium pixels."""

from __future__ import annotations

import hashlib
import io
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast
from urllib.request import Request, urlopen

from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.contracts import ActionContract
from affordance_runtime.executors import VisualExecutor
from affordance_runtime.fixtures import create_fixture_server


@dataclass(frozen=True)
class VisualGroundingRun:
    profile: str
    seed: int
    success: bool
    detected_bbox: list[int]
    screenshot_sha256: str
    screenshot_path: str
    receipt: dict[str, Any]


def detect_magenta_region(png_bytes: bytes) -> list[int]:
    """Ground the target from screenshot pixels without DOM coordinates."""

    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    matching: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = cast(tuple[int, int, int], image.getpixel((x, y)))
            if red >= 180 and green <= 80 and blue >= 180:
                matching.append((x, y))
    if len(matching) < 200:
        raise ValueError(f"magenta detector found only {len(matching)} pixels")
    min_x = min(x for x, _ in matching)
    max_x = max(x for x, _ in matching)
    min_y = min(y for _, y in matching)
    max_y = max(y for _, y in matching)
    return [min_x, min_y, max_x - min_x + 1, max_y - min_y + 1]


def run_visual_grounding_suite(
    output_dir: Path,
    *,
    cases: tuple[tuple[str, int], ...] = (
        ("train", 0),
        ("train", 1),
        ("train", 2),
        ("heldout", 101),
        ("heldout", 102),
    ),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    runs: list[VisualGroundingRun] = []
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        for profile, seed in cases:
            _post_json(f"{base_url}/api/reset", {"profile": profile, "seed": seed})
            screenshot_path = output_dir / f"visual-{profile}-seed-{seed}.png"
            with BrowserSession.launch(f"{base_url}/visual") as session:
                snapshot = session.capture(screenshot_path=str(screenshot_path))
                png = screenshot_path.read_bytes()
                bbox = detect_magenta_region(png)
                affordance = SomAdapter().parse(
                    [{"bbox": bbox, "label": "pixel-detected-magenta-target", "action": "click", "confidence": 1.0}],
                    environment_revision=snapshot.observation.environment_revision,
                    screenshot_ref=str(screenshot_path),
                    snapshot_id=snapshot.observation.snapshot_id,
                    page_revision=snapshot.observation.page_revision,
                )[0]
                contract = ActionContract.from_affordance(
                    affordance,
                    intent="activate screenshot-grounded magenta target",
                    backend="visual",
                )
                receipt = VisualExecutor(session).execute(contract, snapshot.observation)
                state = _get_json(f"{base_url}/api/state")
            runs.append(
                VisualGroundingRun(
                    profile,
                    seed,
                    receipt.success and bool(state["visual_clicked"]),
                    bbox,
                    hashlib.sha256(png).hexdigest(),
                    str(screenshot_path),
                    asdict(receipt),
                )
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    distinct_boxes = len({tuple(run.detected_bbox) for run in runs})
    report: dict[str, Any] = {
        "suite_version": "visual-grounding-v1",
        "detector": "screenshot_pixel_threshold_magenta_v1",
        "uses_dom_coordinates": False,
        "runs": [asdict(run) for run in runs],
        "success_rate": sum(run.success for run in runs) / len(runs),
        "distinct_detected_boxes": distinct_boxes,
        "acceptance_errors": [],
    }
    if not all(run.success for run in runs):
        report["acceptance_errors"].append("one or more visual grounding cases failed")
    if distinct_boxes != len(runs):
        report["acceptance_errors"].append("visual cases did not produce distinct detected boxes")
    (output_dir / "visual-grounding-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    markdown = [
        "# Real Visual Grounding Report",
        "",
        "- Detector: screenshot pixel threshold (magenta), not DOM coordinates",
        f"- Runs: `{len(runs)}`",
        f"- Distinct detected boxes: `{distinct_boxes}`",
        f"- Success rate: `{report['success_rate']:.4f}`",
        f"- Acceptance: `{'PASS' if not report['acceptance_errors'] else 'FAIL'}`",
        "",
    ]
    (output_dir / "visual-grounding-report.md").write_text("\n".join(markdown), encoding="utf-8")
    return report


def _post_json(url: str, value: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(value).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=3) as response:  # noqa: S310 - local fixture only
        return json.loads(response.read())


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=3) as response:  # noqa: S310 - local fixture only
        return json.loads(response.read())
