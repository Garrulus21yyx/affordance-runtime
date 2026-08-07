# Runtime R8 TaskPlanLifecycle Containment Evidence

Date: 2026-07-22

Status: first R8 internal-containment slice complete; R8 remains in progress.

## Boundary

Task-plan generation, bounded context construction, validation, async planner
resolution, replan eligibility, completion checks, and active-subgoal lookup
were previously embedded in `RunCoordinator`. They now live in the stateless
`TaskPlanLifecycle` collaborator.

The extraction does not introduce another state authority:

- `RunCoordinator` still owns the serial control loop and every transition;
- `StateKernel` remains the only mutable run-state implementation;
- `TaskPlanLifecycle` prepares immutable `TaskPlanTransition` values and reads
  current progress, but does not install, replace, activate, or complete plans;
- the existing `TaskPlannerPort`, `TaskPlanValidator`, budgets, Prompt, plan
  schema, trace event names/payloads, and verifier-backed completion rules are
  unchanged.

No benchmark adapter, task id, selector, backend handle, coordinate, provider,
or action-family rule was added. The new production module has no BrowserGym or
MiniWoB import and is exercised directly with a generic DOM fixture.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused lifecycle/planning/Coordinator/boundary tests: 41 passed;
- full repository tests: 473 passed;
- Ruff over `src` and `tests`: passed;
- mypy with the repository's optional-dependency boundary
  (`--ignore-missing-imports`) over 78 source files: passed;
- shared-runtime benchmark-vocabulary boundary: passed;
- `git diff --check`: passed.

Direct negative evidence proves that an asynchronously produced invalid plan is
classified by the existing validator and leaves `StateKernel.task_plan` and
`plan_progress` unset. Existing Coordinator integration tests continue to prove
serial plan activation, verifier-backed subgoal completion, replan lineage,
verified-evidence preservation, and unchanged trace ordering.

## Remaining R8 work

- extract `PerceptionSession`, `ContractExecutionLoop`, and `RecoveryHandler`
  without transferring state authority;
- split generalist planner context/LM orchestration from the existing typed
  semantic compiler registry;
- split BrowserGym observer, encoder, episode runner, and report adapter while
  preserving adapter-only protocol vocabulary;
- migrate selected binding payloads toward tagged types with compatibility and
  serialization tests.
