# Target default cutover consumer map

Status: evidence-backed migration inventory; not a default-cutover or deletion claim.

## Current entry ownership

| Consumer | Current owner | Migration disposition |
|---|---|---|
| root `affordance-runtime run` | legacy `run_scenario -> compose_run_coordinator -> RunCoordinator` | keep default in this slice; retarget reference scenarios before Phase 3 |
| public `RuntimeClient` | legacy `RunCoordinator` | retain as legacy compatibility until target client/default API is selected |
| root package target API | `compose_target_runtime -> TargetRuntime -> ThinTaskIntake -> AgentLoop` | explicit supported target entry; not yet default |
| `benchmarks/target_loop` | product `compose_target_runtime` with harness-only decorators | target/shared claim owner |
| `benchmarks/external_breadth` and current visual Step-13 gate | target-loop benchmark composition | target benchmark owner; live evidence remains profile-specific |
| legacy local SaaS / full-Coordinator BrowserGym commands | legacy benchmark/composition | historical or legacy acceptance only; cannot establish target closure |
| direct `RunCoordinator` scripts | legacy diagnostics | make explicitly legacy or delete with their causal owner during Phase 4 |

## Test ownership rule

- Tests importing `agent/task/world/model_boundary/model_policy` and protecting target invariants are target/shared.
- Tests whose subject is `compose_run_coordinator`, `RunCoordinator`, `RuntimeCommitter`, `StateKernel`, legacy planning stages, or legacy `RuntimeClient` are legacy unless the same invariant is independently owned by target tests.
- Benchmark report and frozen evidence readers remain historical/shared; they are not production runtime consumers.
- A legacy test is not migrated by renaming it. Its claim must either be protected through `compose_target_runtime`, retained as an explicitly historical contract, or deleted with the legacy behavior.

## Default-cutover blockers

1. Retarget or explicitly retire the root pricing/settings/export scenario acceptance paths.
2. Select and implement the target-default public client semantics; move the existing Coordinator client under an explicit legacy name/namespace.
3. Change root CLI `run` only after its environment adapter can implement `WorldEnvironment` without benchmark task routing.
4. Run a clean-SHA target-default held-out, multi-seed benchmark with a predeclared threshold.
5. Perform a fresh-context topology review showing that root API, CLI, and current benchmark resolve through the same product composition identity.

Until those conditions pass, deleting legacy production owners or their tests would be premature. Once they pass, remaining legacy consumer imports become a concrete deletion list rather than a reason to preserve two defaults.
