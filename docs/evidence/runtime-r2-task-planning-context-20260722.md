# Runtime-first R2: Context-Rich Task Planning Evidence

Date: 2026-07-22

## Scope and boundary

R2 is implemented in the generic Runtime and reference application. It adds no
BrowserGym task-family rule and does not alter benchmark acceptance thresholds,
budgets, or oracles.

## Implemented contract

`TaskPlannerPort` receives a versioned, bounded `TaskPlanningContext` containing
the validated TaskSpec, current state and plan identity, a handle-free
environment/affordance summary, active/completed/failed subgoals, the criteria
evidence ledger, failure and recovery summaries, disproved assumptions, and
remaining budgets.

Initial plans must be version 1 with no predecessor. Every replacement must use
a new plan ID, increment `plan_version` by exactly one, and bind
`supersedes_plan_id` to the current plan. Verified subgoals and their definitions
cannot be removed or redefined. Trace events retain the planning context and
supersession chain.

The validator rejects selectors, raw coordinates, backend syntax, gesture
commands, approval tokens, and capability grants in plan text. The action
planner and ActionContract remain the executable and authority boundaries.

## Generic and negative evidence

- a failure/evidence-aware planner changes its replacement plan from the
  criteria evidence ledger and failure summary;
- verified progress survives from plan v1 into plan v2;
- stale, repeated, or incorrectly linked replacement plans are rejected;
- a replacement cannot redefine a verified SubgoalSpec;
- `PlanningRouter` retains the simple one-subgoal flat path;
- planning context contains semantic affordances but no selector, coordinate,
  backend, capability, or approval handle.

## Normal non-BrowserGym proof

The normal reference `run` entrypoint accepts `--task-planning` for pricing.
With the local fixture and real Chromium it completes:

```text
reveal-pro -> reveal-enterprise -> TaskCompleted
```

The independent final-DOM oracle confirms both plan cards are visible and their
values equal `PRICING_DATA`. This path uses `BrowserSession`, `RunCoordinator`,
`PricingTaskPlanner`, the ordinary action planner, ActionContracts, structural
post-verification, and criteria-bound Subgoal completion.

## Verification

```text
Python 3.12.3
pytest -q
423 passed

ruff check src tests scripts
All checks passed!

mypy --ignore-missing-imports src
Success: no issues found in 73 source files

task-planning ablation acceptance_errors: []
adaptive: short=true, long=true, task_success_rate=1.0
flat: short=true, long=false
always_plan: short=false, long=true
```

The ablation preserves its existing semantic oracle and acceptance rules; R2
does not soften or hard-code benchmark outcomes.

## Remaining work

R3 is next: generic task-aware perception orchestration. R4 and R5 remain open.
