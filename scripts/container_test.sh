#!/usr/bin/env bash
set -euo pipefail

test "$(id -u)" -ne 0
python -m pytest -q
python -m ruff check src tests scripts
python -m mypy src
python -m build
