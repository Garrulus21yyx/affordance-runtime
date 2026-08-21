# Phase 13 role-frequency convergence

Status: implementation complete; provider-free verification passed; live W1b pending/non-closed
Constraints: preserve unrelated worktree changes; do not run a live provider/benchmark unless requested; retain non-closed W1b status.

## Steps

1. [completed] Read the specified architecture/benchmark contracts and map all current finalizer owners, consumers, traces, metrics, tests, and standalone consumers.
2. [completed] Extend ManagerDecision/ManagerRoleRequest and prompt/model decoding for bounded direct terminal response plus evidence refs.
3. [completed] Implement the mechanical mission-owned FinalResponseBoundary and integrate it atomically into MissionSupervisor.
4. [completed] Remove the obsolete mission Finalizer/tool-envelope production path and replace observability/report metrics.
5. [completed] Add/update provider-free contract, regression, frequency, at-most-once, and no-ActionPolicy tests.
6. [completed] Run focused and broad verification, obsolete-symbol scans, diff review, and update docs without claiming live closure.

## Files changed by this task

- `.codex-plans/phase13-role-frequency-convergence.md` (plan tracking; updated for run10 reopening)
- `src/affordance_runtime/mission/{contracts,finalization,supervisor}.py` and mission exports
- `src/affordance_runtime/model/{mission_roles,policy}/` and Manager prompt
- `src/affordance_runtime/agent/` tracing/context and target-loop metrics
- focused mission/model/integration tests and architecture/benchmark status docs

## Notes

- The worktree is already dirty. Existing modifications are user-owned until proven otherwise and must not be overwritten.
- Run10 reopened the prior terminal contract: a correct direct business value was rejected by the Finalizer tool-envelope glue.
- Target exit state: direct ManagerReview -> mechanical boundary -> existing FinalResponse, provider-free verified, live W1b still pending/non-closed.
- Verification: focused owner/protocol suites passed; full `1332 passed, 19 skipped`; Ruff and `git diff --check` passed.
