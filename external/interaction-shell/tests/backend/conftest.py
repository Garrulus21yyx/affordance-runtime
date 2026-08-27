from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
