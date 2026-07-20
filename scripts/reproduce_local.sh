#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
.venv/bin/pip install -e '.[dev,web,parent,visual]'
.venv/bin/playwright install chromium
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
.venv/bin/python -m build
.venv/bin/python scripts/chromium_smoke.py
.venv/bin/python scripts/langgraph_parent_smoke.py --output evidence/parent
.venv/bin/affordance-runtime benchmark --output evidence/benchmark --seeds 3
.venv/bin/affordance-runtime evolve \
  --benchmark-report evidence/benchmark/benchmark-report.json \
  --output evidence/evolution
.venv/bin/python scripts/generalization_smoke.py \
  --benchmark evidence/benchmark/benchmark-report.json \
  --output evidence/generalization
.venv/bin/python scripts/check_evidence.py \
  --benchmark evidence/benchmark/benchmark-report.json \
  --evolution evidence/evolution/evolution-report.json \
  --parent evidence/parent/langgraph-parent-report.json \
  --generalization evidence/generalization/generalization-report.json
