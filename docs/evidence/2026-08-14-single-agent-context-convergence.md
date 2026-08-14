# Single-AgentContext convergence evidence

Date: 2026-08-14

Status: `IMPLEMENTED / LOCALLY_VERIFIED / PUSHED_E7F9F46 / LIVE_NOT_RUN`

## Cause

The Runtime already built one bounded `AgentContext`, but grounded policy then
created a context-shaped `ToolPolicyView` and made a mandatory task-state model
call before the action call. The clean `cdb4bc9` run showed the consequence:
all seven initial updater responses violated the updater schema and four cases
stopped before action selection after repair also failed. This was not a
Unified World, DOM, E-ref, binding or executor defect. It was duplicated context
ownership plus an unnecessary semantic protocol gate.

## Implemented contract

```text
TaskGoal + current Unified World + progress/history/control state
                         │
                         ▼
                 canonical AgentContext
                         │
                         ▼
          one YAML-backed provider-message binder
                         │
                         ▼
          one model call chooses one current tool
                         │
                         ▼
      existing E-ref admission/private binding/execution/evaluation
```

- `AgentContext` is the only internal model-context owner.
- The grounded catalog contains only public current tool schemas and opaque
  Runtime bindings; it contains no view, memory or task-state projection.
- Valid grounded action selection performs one semantic model call. A bounded
  schema/argument repair corrects that same response and is not a planner.
- Original task, current world, verified/unresolved progress, chronological
  action/effect history, pending state, budgets and control feedback reach the
  model through one binder.
- DOM, visual and WoT facts continue to enter through the existing Unified
  World; no surface-specific cognition path was added.
- Internal entity/fact/action/binding identities do not cross the model
  boundary. Entities use `E*`; public evidence uses call-local `F*` refs.
- The objective proposal adapter retains a statically separate response type;
  no objective constructor was added to action tools.

## Removed

- mandatory task-state updater prompt, payload and repair diagnostics;
- `ToolPolicyView` as a second context-shaped owner;
- `AgentWorkingMemory`, `AgentPolicyTurn` and action-plus-memory response
  envelope;
- eager legacy AgentContext serialization on the grounded path.

## Verification so far

- focused grounded/policy/orchestrator tests: `30 passed`;
- Ruff: passed;
- mypy: passed across 497 source files;
- full repository suite: `2474 passed, 27 skipped`;
- clean wheel: v2 YAML prompt included; deleted working-memory module absent;
- benchmark: deliberately not run in this implementation slice.

The implementation is not a benchmark or generalization closure claim. The
next live run must use the default 4.1V profile; on failure, analysis stops the
slice rather than adding a benchmark/task-specific production branch.
