# Open-status reconciliation and held-out Task8

Goal: reconcile the current maintained status without changing production behavior, then run one untouched held-out
W1b Task8 and use its native evaluator plus typed trace as the next generalization witness.

Constraints:

- Do not modify history, cursor, ToolReturn, World, Binder, BrowserGym, Monitor, or other production code during the
  status audit.
- Treat `TaskGoal -> GoalCompiler request` and `TaskGoal -> AgentContext.task` as the only lexical-admission contract.
- Treat BrowserGym dispatch, typed stability/acquisition outcome, fresh World, StepResult, and native evaluator as
  separate owner facts; success on one path does not prove unsupported paths.
- Do not specialize production behavior for Task8 or use its task text, site, expected answer, fixed ref, or task ID.
- Use the official native evaluator as the correctness authority; trace metrics are process/efficiency evidence.
- Keep `output/` untouched.

Steps:

1. **done — Reconcile open claims.** Trace every current open-status statement to its originating witness,
   current owner contract, tests, and later live evidence. Classify each as open, closed-for-bounded-path, or stale.
   Files: this plan, read-only source/tests/traces.
   Result: Planner lexical admission was historical C12; Task7 run2 supplies two live-pressure compactions; Task27
   run2 and Task266 run37 supply the bounded BrowserGym acquisition witnesses. Only held-out breadth/stability remains.
2. **done — Update maintained truth.** Edit only `docs/architecture.md` and `docs/benchmark.md` to remove stale
   Planner/compaction claims and state the bounded BrowserGym status precisely. Verify docs and focused owner gates.
   Result: `221 passed / 3 skipped` across complete focused TaskGoal, GoalCompiler, policy projection, CoreLoop,
   BrowserGym acquisition/currentness, real-backend active capture, and PydanticAI history suites; diff check passes.
3. **in_progress — Commit the audit separately.** Commit only the plan/docs if the audit changes maintained truth; do not
   include `output/` or production code.
4. **pending — Run held-out Task8 once.** Reuse `.env`, the fixed BrowserGym interpreter, the project service/profile,
   and the existing W1b runner. Persist formal evidence and inspect the full trace after completion.
5. **pending — Decide the next cohort.** If Task8 succeeds, select 3–5 untouched cases and report the fixed cohort
   before running it. If Task8 fails, classify environment/provider/case vs shared contract failure before any change.
6. **pending — Defer efficiency work.** Consider Task7 token optimization only after the held-out correctness cohort;
   keep it separate from any correctness repair.

Files modified so far:

- `.codex-plans/open-status-heldout-task8.md` — persistent audit/run plan.
- `docs/architecture.md` — reconciled bounded owner/live status.
- `docs/benchmark.md` — reconciled evaluation and held-out status.
