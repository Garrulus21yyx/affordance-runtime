# TaskPlan Authority Call-Site Audit

> Baseline: `8445747f0d734b3998b88edb204e099edf58d259`
> Slice: `TPA-1`
> Status: current read-only inventory
> Production behavior change: none

## Purpose

This inventory freezes the current TaskPlan generation, validation, replacement,
commit, storage, recovery, CLI, integration, and benchmark surfaces before TPA-2
and TPA-3 change the Step Planner input boundary. It records facts, not the target
implementation.

## Current lifecycle

```text
TaskPlanLifecycle.build_context
  -> TaskPlannerPort.plan
  -> TaskPlan
  -> TaskPlanValidator.validate
  -> TaskPlanFlow / TaskPlanCommitPreparation
  -> RunCoordinator
  -> StateKernel.install_task_plan or replace_task_plan
```

The current decision owner is the composition of `TaskPlanLifecycle` and
`TaskPlanValidator`. The future `TaskPlanAuthority` does not yet have production
authority.

## Generation and construction inventory

| Symbol | Module | Current role | Creates TaskPlan | Target owner | Migration |
|---|---|---|---:|---|---|
| `TaskPlannerPort.plan` | `task_planning.py` | public legacy plan producer contract | indirect | `TaskPlanGeneratorPort.generate` | TPA-4/5 |
| `TaskObligationOutcomeCompiler.compile` | `task_planning.py` | canonical obligation-to-subgoal rule compiler | yes | rule draft generator | TPA-5 |
| `RuleTaskPlanner.plan` | `task_planning.py` | rule producer/router delegate | indirect | rule draft generator | TPA-5 |
| `LLMTaskPlanner.plan` | `task_planning.py` | provider generation, repair, authority binding | yes | LLM draft generator | TPA-5 |
| `PlanningRouter.plan` | `task_planning.py` | chooses rule or complex planner | indirect | generator router | TPA-5 |
| `synthetic_task_plan` | `task_planning.py` | legacy flat-plan constructor | yes | Runtime no-plan/implicit-step policy | TPA-6/10 |
| `PricingTaskPlanner.plan` | `planners.py` | reference-app plan producer | yes | reference draft generator | TPA-5/8 |
| `_CountingPlanner.plan` | `benchmarks/task_planning.py` | benchmark wrapper around a TaskPlannerPort | no | compatibility instrumentation | TPA-5/8 |

The executable AST baseline permits direct `TaskPlan(...)` construction only in:

```text
planners.py:PricingTaskPlanner
task_planning.py:TaskObligationOutcomeCompiler
task_planning.py:LLMTaskPlanner
task_planning.py:synthetic_task_plan
```

## Admission and application inventory

| Symbol | Reads | Writes | Current decision/commit role | Target |
|---|---|---|---|---|
| `TaskPlanLifecycle.propose_initial` | TaskSpec, StateKernel, BrowserSnapshot, budget | none | invokes producer and validator | TaskPlanAuthority request preparation |
| `TaskPlanLifecycle.propose_replacement` | current plan/progress, evidence, state identity | none | invokes producer, carries completed subgoals, validates | revision authority preparation |
| `TaskPlanLifecycle.evaluate_replacement` | plan/progress, current environment, budgets | none | current replan trigger policy | RecoveryPolicy plus feasibility issue |
| `TaskPlanLifecycle.completed` | plan and completed subgoal IDs | none | legacy completion predicate | compatibility only after TPA-10 |
| `TaskPlanValidator.validate` | plan, TaskSpec, state/version/context | none | structural, lineage, coverage, safety, feasibility mix | composed TaskPlanAuthority policies |
| `TaskPlanFlow.prepare` | TaskSpec, state, snapshot, budget | none | chooses initial/replacement preparation | TaskPlanApplicationFlow |
| `TaskPlanCommitPreparation` | accepted flow result | none | trace/commit projection | retained application projection |
| `RunCoordinator.run_sync` | typed preparation and current state | StateKernel and trace | only production plan committer | retained |
| `StateKernel.install_task_plan` | accepted-looking TaskPlan identity | plan/progress/version | invariant-enforcing storage mutation | accepted-plan-only storage |
| `StateKernel.replace_task_plan` | replacement identity and completed definitions | plan/progress/version | invariant-enforcing replacement mutation | accepted-plan-only storage |

## Production commit caller baseline

The only production calls are:

```text
coordinator.py: state.replace_task_plan(task_plan)
coordinator.py: state.install_task_plan(task_plan)
```

Tests and fixtures call these methods directly to establish state, but no other
production module may do so. The architecture test fails if this allowlist grows.

## Replan trigger inventory

| Source | Current output | Current effect | Target boundary |
|---|---|---|---|
| `TaskPlanLifecycle.should_replan` | boolean | replacement when active action budget exhausted | RecoveryPolicy decision |
| `TaskPlanLifecycle.evaluate_replacement` | `TaskPlanReplacementDecision` | unavailable family, already-satisfied, unsupported state | typed issue; already-satisfied becomes progress verification |
| `TaskPlanFlow` current-state discard compatibility | replacement preparation | can remove an already-satisfied entry from a replacement plan | retire after verified progress path |
| `ProposalRejectionRecoveryPolicy` | `REPLAN_STEP` or abort | recovery command availability | retained trigger only |
| `RecoveryCoordinator` | `REPLAN_STEP` / `REPLAN_TASK` commands | typed recovery plan | cannot carry a new plan |
| Coordinator recovery branch | applies recovery delta/re-entry | may return to planning | TaskPlanAuthority revision request in TPA-7 |

## CLI, integration, and benchmark wiring

| Wiring surface | Current TaskPlan producer/configuration | Migration gate |
|---|---|---|
| `cli.py` | `PricingTaskPlanner` or `PlanningRouter` passed to Coordinator | explicit generator/authority/step-planner injection in TPA-8 |
| `task_pipeline.py` | replaces default router with `LLMTaskPlanner` for model-backed complex plans | draft generator wiring in TPA-5/8 |
| `benchmarks/browsergym_episode_runner.py` | `PlanningRouter(complex_planner=LLMTaskPlanner(model))` | normal Runtime authority path only |
| `benchmarks/task_planning.py` | rule/LLM profile selection plus counting wrapper | compatibility benchmark instrumentation |
| local/reference benchmarks | configure Step Planner and optional Task Planner | must not admit or commit plans |

## Current invariants to preserve

- A replacement uses a new plan ID and version and names its superseded plan.
- Verified completed subgoal definitions are carried forward unchanged.
- StateKernel validates task identity, state/version lineage, and completed-step preservation.
- Task Planner output cannot directly mutate StateKernel or write trace.
- RunCoordinator remains the only production install/replace caller.
- Benchmark reward, receipt success, and Planner prose do not admit a TaskPlan.

## TPA-2/3 deletion gates

This audit remains current until:

1. all standard Step Planner triple signatures are removed in TPA-3;
2. all TaskPlan producers return `TaskPlanDraft` in TPA-5;
3. `TaskPlanAuthority` owns initial admission in TPA-6 and replacement admission in TPA-7;
4. the executable baselines are reduced in the same revision as each migration.
