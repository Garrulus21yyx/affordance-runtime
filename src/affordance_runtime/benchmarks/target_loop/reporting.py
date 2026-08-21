"""Compatibility entry points for SQLite-backed JSON report projection."""

from pathlib import Path

from affordance_runtime.benchmarks.target_loop.result_store import SQLiteRunResultStore


def write_case_report(result, output_dir: str | Path) -> None:
    """Commit one case payload to SQLite, then export its JSON projection."""

    root = Path(output_dir)
    store = SQLiteRunResultStore(root / "run-results.sqlite3")
    store.commit_case_report(result)
    store.export_case_report(result.case_id, root)


def write_run_report(
    result,
    output_dir: str,
    *,
    include_case_reports: bool = True,
) -> None:
    """Commit the suite payload to SQLite, then export rebuildable JSON."""

    root = Path(output_dir)
    store = SQLiteRunResultStore(root / "run-results.sqlite3")
    if include_case_reports:
        for result_item in result.cases:
            store.commit_case_report(result_item)
            store.export_case_report(result_item.case_id, root)
    store.commit_run_report(result)
    store.export_run_report(result.identity.run_id, root)
