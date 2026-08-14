# Task-state context and action separation

Date: 2026-08-14

Implementation: `eb19c0d`

Status: `IMPLEMENTED / PUSHED / LIVE_NOT_RUN / GENERALIZATION_OPEN`

## Outcome

The previous mandatory atomic-memory response proved that memory was generated
and reinjected, but its valid default-4.1V diagnostic reached only 1/5. The
traces showed that concurrently sampled memory and action could contradict each
other, completed set membership was not retained, aggregate derivations were
absent, and every completed turn required structured-output repair.

`eb19c0d` replaces that response shape with one policy-internal causal sequence:

```text
TaskGoal + fresh Unified World + world transition + previous task state
                              |
                              v
                    task-state updater call
                              |
                              v
                     updated advisory state
                              |
         + clean current tools + same fresh Unified World
                              |
                              v
                         actor call
                              |
                              v
                existing Runtime action admission path
```

The two model calls may use the same configured provider and model. They create
no additional BrowserGym step, action authority, alternate executor or hidden
oracle.

## Contract changes

- `GroundedPolicyContextBinder` is the single model-message assembly owner.
- `prompts/grounded_agent.yaml` separately defines task-state, actor and dormant
  objective-proposer roles and is packaged in the wheel.
- The updater input explicitly distinguishes `current_unified_world`,
  `world_transition`, and `previous_agent_task_state`.
- The bounded task state contains goal, requirement items, derived facts,
  semantic next step, readiness and blockers.
- The actor receives the just-authored task state before choosing one tool.
- Action tools no longer contain or require `memory`; action fixtures therefore
  test actions, while context/task-state tests cover cognition state.
- Working memory is removed from the `supported_decisions` algebra because it is
  context, not a Runtime decision.
- Task-state structured-output repair returns only bounded, value-free schema
  violations to the updater and remains separate from action argument repair.

## Authority boundaries

World transition is a public Runtime projection of the observed result after
the previous decision. It is evidence, not an Agent inference. Task state is a
model-authored belief: it may decompose the goal, retain progress, calculate
derived facts and state blockers, but it cannot filter ActionSpace, name private
bindings, authorize execution or decide authoritative completion. Fresh public
world evidence wins when it conflicts with stored belief.

No benchmark case, task name, page string, selector, fixed action ID, fixed
output or task-family classifier was added. DOM, WoT and visual sources still
enter through SurfaceAdapters and the Unified World projection.

## Verification

- focused grounded/task-state/provider contracts: passed;
- broader model-protocol, visual binding, model-boundary and architecture
  contracts: 77/77 after the final old action-memory fixture was removed;
- local full suite on the implementation candidate: 2471 passed, 27 skipped;
- the one schema-budget witness exposed by the larger task-state context was
  converted from a fixed byte constant to a schema-relative compaction
  property and passed;
- final task-state lifecycle/repair/capability focus: 10/10;
- `ruff check src tests`: passed;
- `mypy src`: passed across 498 source files;
- wheel build: passed, with `grounded_agent.yaml` present in the artifact;
- `git diff --check`: passed.

These checks establish the contract and unchanged execution ownership. They do
not establish task-quality improvement. The next evidence is one exact-head
default-4.1V five-witness diagnostic after remote CI. If it fails, analyze the
state/action traces and stop; do not add a critic or task-specific branch.
