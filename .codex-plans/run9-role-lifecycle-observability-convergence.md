# Run9 role invocation, case lifecycle, and observability convergence

Status: completed_non_closed

## Goal

Close one shared seam:

`benchmark_case_started -> role ToolOutput invocation -> MissionSupervisor -> typed terminal result -> preliminary persistence -> bounded cleanup/report/flush -> benchmark_case_finished`

## Constraints

- Preserve the dirty worktree and existing user changes.
- Keep one MissionSupervisor, one CoreAgentLoop, one ModelInvocationResult, one SQLite authority, and one trace chain.
- Langfuse remains fail-open and read-only.
- No live provider, BrowserGym witness, task-7 replay, or W2 until provider-free gates and fresh audit pass.
- Do not retain the free-text JSON role path as a normal compatibility branch.

## Owners and steps

1. [completed] Audit role invocation, provider adapters, lifecycle state, result persistence, cleanup/report timeouts, and trace-root ownership.
2. [completed] Add shared `PydanticAIRoleInvoker` using strict ToolOutput and existing role Pydantic models; preserve ModelInvocationResult attempt evidence.
3. [completed] Remove manual role JSON repair/envelope/transcript coupling and update prompts/tests.
4. [completed] Add closed case lifecycle phases at owner boundaries and immediate terminal Manager failure return.
5. [completed] Persist preliminary case result before bounded cleanup; keep cleanup/report failures orthogonal.
6. [completed] Move Langfuse root to benchmark case start; demote CoreLoop start to a child event; add bounded fail-open flush.
7. [completed] Run focused provider-free and fault-injection tests, full pytest, Ruff, and diff-check.
8. [completed] Run bounded fresh-context architecture audit; do not run live unless it passes.

## Files expected

- `src/affordance_runtime/model/mission_roles.py`
- `src/affordance_runtime/model/policy/pydantic_ai_bridge.py` or a shared role invoker module
- `src/affordance_runtime/mission/supervisor.py`
- `src/affordance_runtime/benchmarks/target_loop/runner.py`
- `src/affordance_runtime/benchmarks/target_loop/result_store.py`
- `src/affordance_runtime/benchmarks/target_loop/instrumentation.py`
- `src/affordance_runtime/agent/observability.py`
- focused tests and maintained architecture/benchmark docs
