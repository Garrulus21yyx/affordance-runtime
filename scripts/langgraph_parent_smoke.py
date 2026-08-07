"""Run the real LangGraph parent against the external task protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from affordance_runtime.integrations.langgraph_parent import run_langgraph_parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_langgraph_parent(args.output)
    if report["pricing"]["status"] != "success":
        raise RuntimeError("LangGraph pricing flow failed")
    if report["export"]["preapproval_status"] != "waiting_approval":
        raise RuntimeError("LangGraph export bypassed approval")
    if report["export"]["status"] != "success":
        raise RuntimeError("LangGraph approved export failed")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
