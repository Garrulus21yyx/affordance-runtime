#!/usr/bin/env python3
"""Launch the frozen verifier diagnostic with child-only local configuration."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PINNED_PYTHON = Path("/home/yang/.venvs/affordance-browsergym-py312/bin/python")
MINIWOB_SOURCE = Path("/tmp/miniwob-plusplus")
MINIWOB_SOURCE_SHA = "7fd85d71a4b60325c6585396ec4f48377d049838"
_DOTENV_ASSIGNMENT = re.compile(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not _fixture_is_clean():
        return 1
    environment = _local_dotenv_environment(
        REPOSITORY_ROOT / ".env", dict(os.environ),
    )
    environment.update({
        "PYTHONPATH": str(REPOSITORY_ROOT / "src"),
        "MINIWOB_SOURCE_DIR": str(MINIWOB_SOURCE),
        "MINIWOB_URL": "file:///tmp/miniwob-plusplus/miniwob/html/miniwob/",
        "RUN_MINIWOB_VERIFIER_14_DIAGNOSTIC": "1",
    })
    command = (
        str(PINNED_PYTHON),
        "-m",
        "affordance_runtime.benchmarks.external_breadth.verifier_targeted_cli",
        "--profile",
        "MINIWOB_VERIFIER_14_TARGETED_DIAGNOSTIC",
        "--seed",
        "7",
        "--min-policy-call-interval-s",
        "7.5",
        "--output-dir",
        str(args.output_dir),
    )
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    ).returncode


def _fixture_is_clean() -> bool:
    try:
        sha = subprocess.run(
            ("git", "-C", str(MINIWOB_SOURCE), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ("git", "-C", str(MINIWOB_SOURCE), "status", "--short"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return sha == MINIWOB_SOURCE_SHA and not status


def _local_dotenv_environment(
    path: Path,
    inherited: dict[str, str],
) -> dict[str, str]:
    environment = dict(inherited)
    if not path.is_file():
        return environment
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _DOTENV_ASSIGNMENT.fullmatch(line)
        if match is None:
            continue
        name, value = match.groups()
        value = value.strip()
        if len(value) >= 2 and value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        environment.setdefault(name, value)
    return environment


if __name__ == "__main__":
    raise SystemExit(main())
