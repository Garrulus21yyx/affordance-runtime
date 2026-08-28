from __future__ import annotations

import argparse

from affordance_runtime.benchmarks import cli


def _command_names() -> frozenset[str]:
    action = next(
        item
        for item in cli.build_parser()._actions
        if isinstance(item, argparse._SubParsersAction)
    )
    return frozenset(action.choices)


def test_benchmark_cli_exposes_only_retained_independent_commands() -> None:
    assert _command_names() == {
        "benchmark-screenspot",
        "benchmark-screenspot-grounder",
        "write-visual-capability-manifest",
        "write-supervised-gui-acceptance-manifest",
        "validate-supervised-gui-fixtures",
        "preflight-supervised-gui-shadow",
        "benchmark-workarena-preflight",
        "prepare-webarena-verified-subset",
        "evaluate-webarena-verified",
        "prepare-wasp-subset",
        "provider-preflight-ollama",
        "write-webarena-verified-w0-manifest",
        "preflight-webarena-verified-w0",
    }


def test_deleted_runtime_benchmark_commands_are_unparseable() -> None:
    for command in (
        "serve-fixture",
        "baseline",
        "benchmark",
        "benchmark-task-planning",
        "benchmark-adaptive-routing",
        "benchmark-browsergym",
        "benchmark-browsergym-generalist",
        "evolve",
    ):
        try:
            cli.build_parser().parse_args([command])
        except SystemExit as exc:
            assert exc.code == 2
        else:  # pragma: no cover - parser must fail closed
            raise AssertionError(f"deleted command remains parseable: {command}")
