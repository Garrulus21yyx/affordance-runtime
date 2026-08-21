# run5 Manager-mode and bounded cleanup convergence

Status: implemented_verified_non_closed

## Constraints

- Preserve the existing dirty worktree and unrelated changes.
- No real provider calls, BrowserGym live runs, Task-7 witness, or W1b/W2 cohort.
- No commit or push.
- Keep one internal `ManagerDecision`, one `MissionSupervisor`, one GUI loop, and one Binder.
- Maximum honest status is non-closed with W1b live verification pending.

## Steps

1. [done] Read all required repository policy, architecture/benchmark docs, and run5 evidence including trace and case result.
2. [done] Map current Manager schema/adapter/repair, MissionSupervisor/Evidence admission, and benchmark lifecycle owners.
3. [done] Implement mode-specific model-visible Manager schemas and lowering, Manager-only request configuration/trace, and prompt update.
4. [done] Rename `AuditBoundary` to `EvidenceBoundary` without aliases or split paths; update production/tests/docs.
5. [done] Implement bounded non-blocking cleanup, primary-failure-preserving projection, lifecycle status, and pre-cleanup durable snapshot.
6. [done] Add required counterexample/property/regression tests.
7. [done] Run provider-free focused suites, relevant integration/regression, full pytest, Ruff, and diff check.
8. [done] Run bounded independent fresh-context audit and reconcile findings.

## Files changed by this plan

- `.codex-plans/run5-manager-cleanup-convergence.md` (created)

## Evidence log

- Existing dirty worktree recorded before edits with `git status --short`.
- Required policy/docs/run5 run, summary, case, and complete trace read before product edits.
- Run5 trace confirms universal `ManagerDecisionModel` on both attempts, initial 2048-token reasoning exhaustion, and repair lowering conflict; case projection confirms cleanup masked `manager_failure`.
- Focused Manager/Supervisor/EvidenceBoundary/cleanup/BrowserGym-owner gate: 110 passed.
- Relevant mission, target-loop runtime, and BrowserGym regression gate: 361 passed, 3 skipped.
- Final full provider-free suite after audit remediation: 1388 passed, 19 skipped.
- `python -m ruff check src tests` and `git diff --check`: passed.
- Independent fresh-context audit: PASS after repairing one test-fixture evidence ref and one stale G5 status row; no architecture blocker remained.
