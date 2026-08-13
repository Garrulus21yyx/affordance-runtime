# Canonical Agent Authority Cutover Execution Record

> **Status:** IN_PROGRESS
> **Target:** [Canonical GUI Agent Execution Architecture](../task-execution-authority-map.md)
> **Started:** 2026-08-13

## Goal and constraints

Replace the recurrent Agent-created LocalObjective ingress with the repository's
admitted TaskSpec -> TaskPlan<StepSpec.execution> -> StepExecutionState ->
ActionChoiceCatalog chain. Preserve the action-only Agent interface, current
observation rebinding, risk/execution/evaluation boundaries, and benchmark
neutrality. Delete the displaced production path instead of maintaining a
compatibility execution core.

## Canonical comparison

| Required question | Answer |
|---|---|
| Primary stages | task/plan admission, active-step execution, current choices, Agent decision |
| Single semantic owner | admitted TaskPlan<StepSpec.execution> |
| Affected invariants | one semantic owner; action-only Agent; semantic persistence/physical rebinding; one active execution-state slot |
| Authoritative inputs | TaskGoal/request, admitted TaskSpec, current WorldObservation, admitted TaskPlan |
| Typed outputs | PlanProposal/admitted TaskPlan, StepExecutionState, ActionChoiceCatalog, action/control AgentDecision |
| Consumers | AgentLoop composition, ContextBuilder, grounded action-tool catalog, admission, reducers/evaluators |
| Agent algebra change | yes: delete semantic-state constructor; retain action/control variants |
| Projection authoritative | no |
| Deleted path | EstablishLocalObjective decision/tools, Agent-origin local_objective_state, codecs/projectors/tests/docs |
| Unsupported behavior | typed planning/evidence/selector failures with zero dispatch |

## Execution steps

| Step | Status | Deliverable / evidence |
|---|---|---|
| 1. Repository-wide call graph and owner inventory | completed | existing TaskSpec/TaskPlan/step reducers reused; duplicate recurrent producer identified |
| 2. Freeze failing properties for action-only Agent and plan-produced step state | completed | architecture, decision-schema, catalog, selector-refresh tests |
| 3. Compose TaskSpec/TaskPlan authority into target AgentLoop | completed | explicit `AgentTaskPlanPreparerPort`; no capability hidden on AgentPolicy |
| 4. Connect active StepSpec -> StepExecutionState -> current action page/tools | completed | single `active_step_execution`; fresh-observation refresh; retained current mapping |
| 5. Remove recurrent LocalObjective decision/tool/projection path | completed | decision, codec, tool, state, facade and evidence naming removed from production |
| 6. Run focused, architecture, integration, and full regression tests | completed | focused 111 passed; full 2382 passed/27 skipped |
| 7. Run fresh five-case real benchmark and inspect per-case evidence | pending | exact run artifact |
| 8. Reconcile docs/status and closure claim | completed | implementation candidate recorded; live/generalization closure remains open |

## Files changed

- `agent/task_plan_preparation.py`, `agent/loop.py`, `agent/state.py`
- `task/execution_control.py`, `agent/step_execution_evidence.py`
- recurrent decision/model schema and grounded action-tool boundary
- benchmark composition and Step-13 runner wiring
- architecture/status/tests and this execution record

## Findings and plan revisions

- The reducers already re-resolved semantic selectors on fresh observations;
  the shared cause was the recurrent Agent being allowed to create their
  persistent semantic input.
- Planning is an explicit AgentLoop collaborator. It is not attached to or
  discovered through AgentPolicy.
- Evidence source differences do not create a second lifecycle. DOM/derived/
  visual results install into the same active step reducer state.
- Runtime retains its current internal action page and private mapping; the
  grounded tool catalog is a disposable action-only projection. It does not
  serialize and reconstruct task semantics.
- Prior five-case results apply to `f3ca2df`. They do not verify this working
  candidate; Step 7 remains open until a fresh persisted run completes.
