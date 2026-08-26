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
3. **done — Commit the audit separately.** Commit only the plan/docs if the audit changes maintained truth; do not
   include `output/` or production code.
   Result: committed as `eca4f13d docs: reconcile held-out benchmark status`.
4. **done — Run held-out Task8 once.** Reuse `.env`, the fixed BrowserGym interpreter, the project service/profile,
   and the existing W1b runner. Persist formal evidence and inspect the full trace after completion.
   Preparation: declared official case `79.8.2` in a held-out benchmark-only set before execution; 34 focused manifest/
   launcher tests pass. Full suite reports 1787 pass, 4 skip, the existing docs-governance failure, and three isolated
   wall-clock deadline tests that pass 3/3 on each of three immediate reruns.
   Result: run1 completed normally through one STOP and one native evaluation. All 34 policy decisions were valid
   single calls, with zero provider fallback, stale catalog, grounding gap, invalid arguments, or context rejection.
   The model derived that Pittsburgh International Airport is about 32 km from CMU and returned `SUCCESS` with an
   empty result list. The native evaluator rejected only that public response classification: the installed public
   `FinalAgentResponse` schema says an empty retrieval returns an empty array, while the official Task8 reference
   requires `NOT_FOUND_ERROR` with null data. This is an upstream benchmark-response contract conflict, not the stale
   Planner, compaction, BrowserGym acquisition, or Agent data-flow gap.
5. **done — Decide the next cohort.** If Task8 succeeds, select 3–5 untouched cases and report the fixed cohort
   before running it. If Task8 fails, classify environment/provider/case vs shared contract failure before any change.
   Result: classify as an external benchmark public-contract/evaluator-reference conflict. Do not run the cohort or
   change production Agent behavior until that response protocol is made unambiguous at its benchmark owner.
6. **pending — Defer efficiency work.** Consider Task7 token optimization only after the held-out correctness cohort;
   keep it separate from any correctness repair.

Files modified so far:

- `.codex-plans/open-status-heldout-task8.md` — persistent audit/run plan.
- `docs/architecture.md` — reconciled bounded owner/live status.
- `docs/benchmark.md` — reconciled evaluation and held-out status.
- `src/affordance_runtime/benchmarks/webarena_verified.py` — declared public held-out case identity in the benchmark
  manifest owner; no task content or evaluator answer enters Runtime.
- `src/affordance_runtime/benchmarks/target_loop/cases.py` — exposes the held-out declaration through the existing W1b
  runner and native evaluator.
- `tests/benchmarks/runtime/test_webarena_verified_benchmark.py` — freezes held-out manifest identity.
- `tests/benchmarks/runtime/test_target_loop_manifest_identity.py` — proves Task8 is selected by the existing suite.
