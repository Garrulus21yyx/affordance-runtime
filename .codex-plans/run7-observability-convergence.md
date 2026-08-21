# Run7 observability convergence

Status: in_progress

## Goal

Converge terminal-result durability and observability into two non-competing chains:

- TaskEvaluator -> OfficialOutcomeCheckpoint -> SQLiteRunResultStore -> rebuildable JSON
- Runtime typed events -> local JSONL -> read-only Langfuse/OpenTelemetry

## Constraints

- Preserve the dirty worktree and existing SQLite result-store work.
- Do not change Runtime, World, Binder, or TaskEvaluator authority.
- Do not add DBOS, Temporal, Prefect, a second outcome store, or a control loop.
- Do not expose full World, screenshot data, private bindings, selectors, or large snapshots remotely.

## Steps

1. [done] Audit current owners, dependencies, event contracts, and official SDK integration.
2. [done] Remove finally-based evaluator inference and replace the large primary snapshot with a bounded typed event.
3. [done] Make checkpoint identity/status storage-neutral and keep JSON explicitly rebuildable from SQLite.
4. [done] Use official PydanticAI instrumentation for model/tool spans; keep only project-owned Runtime/lifecycle spans in the read-only Langfuse sink, with recursive privacy and size bounds.
5. [done] Update focused tests and architecture/benchmark contracts.
6. [done] Run focused provider-free tests and one provider-free trace witness.
7. [done] Full pytest, Ruff, diff-check, and the bounded fresh-context re-audit passed.
8. [pending] Run one live case only after explicit live authorization; credentials and the real remote trace audit now pass.

## Files

- `src/affordance_runtime/agent/observability.py`
- `src/affordance_runtime/benchmarks/target_loop/instrumentation.py`
- `src/affordance_runtime/benchmarks/target_loop/outcome_checkpoint.py`
- `src/affordance_runtime/benchmarks/target_loop/reporting.py`
- `src/affordance_runtime/benchmarks/target_loop/result_store.py`
- `src/affordance_runtime/benchmarks/target_loop/runner.py`
- `tests/unit/agent/test_observability.py`
- `tests/benchmarks/runtime/test_target_loop_lifecycle_failures.py`
