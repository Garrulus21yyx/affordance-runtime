"""Deterministically emit the canonical Interaction Shell OpenAPI document."""

from __future__ import annotations

import json
from pathlib import Path

from .api import create_app


def main() -> None:
    app = create_app()
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    if len(operation_ids) != len(set(operation_ids)):
        raise RuntimeError("public FastAPI operation IDs must be unique")
    output = Path(__file__).resolve().parents[1] / "openapi.json"
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
