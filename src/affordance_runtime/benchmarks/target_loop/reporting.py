"""Secret-free JSON benchmark report serialization."""

import json
from dataclasses import asdict
from pathlib import Path


def write_run_report(result, output_dir: str) -> None:
    root = Path(output_dir)
    cases = root / "cases"
    cases.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    _write(root / "run.json", payload)
    _write(root / "summary.json", {"identity": payload["identity"], "acceptance": payload["acceptance"], "rates": payload["rates"]})
    for item in payload["cases"]:
        _write(cases / f"{item['case_id']}.json", item)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
