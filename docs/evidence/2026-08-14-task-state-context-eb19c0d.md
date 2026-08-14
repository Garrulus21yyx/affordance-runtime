# Task-state context and action separation

Date: 2026-08-14

Implementation: `eb19c0d`

Status: `IMPLEMENTED / LIVE_SCHEMA_BLOCKED_AT_CDB4BC9 / STOPPED / GENERALIZATION_OPEN`

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
not establish task-quality improvement.

## Default-4.1V live diagnostic

The frozen five-witness diagnostic ran from clean exact head
`cdb4bc90a724ca73a48a5049fcfd66ba8af89580`, whose product implementation is
`eb19c0d` plus documentation only. The run completed 5/5 with valid evidence:

```text
success: 1/5
outcomes: 1 success, 4 structured_output_failure
provider/model: zhipu / glm-4.1v-thinking-flashx
perception: structure-first.v1
protocol: grounded_tools.v2
provider calls: 18
```

This result is blocked before a task-quality comparison. Across seven attempted
task-state updates, every initial response violated `GroundedTaskStatePayload`.
The bounded repair call recovered three updates and failed schema validation
again on four. Those four failures stopped policy execution before the actor
could choose another action:

| Case | Observed boundary |
|---|---|
| grid coordinate | repaired task state and actor action agreed on public `E38` at `(1,-2)`; success |
| pie/no-delay | first repaired state decomposed expand then select `0`; actor expanded; next updater failed after repair |
| blue set | first repaired state identified exactly `E5,E10,E12,E15,E16`; actor selected `E5`; next updater failed after repair |
| pie | initial updater failed after repair; actor was never called |
| visual addition | initial updater failed after repair; actor was never called |

The three admitted states are evidence that the new causal edge is exercised
and can express useful task semantics. They are not evidence that cross-turn
task state, aggregation or finalization is solved: the run did not reach those
checks. The prior 1/5 atomic-memory score and this 1/5 score therefore do not
measure the same failure boundary.

The updater repair prompt did receive the bounded, value-free schema violation
paths and codes. The benchmark trace persists only the repair count and final
typed `schema_error`, not the first and repaired violation paths. Consequently,
the immediate common cause is proven—systematic updater schema noncompliance—
while the exact recurring field-level mismatch is not observable from this
run. The visual-gate identity errors are downstream consequences of the policy
failing before dispatch, not an independent DOM or binding failure.

Per the stop instruction, no production or prompt repair and no rerun follows
this analysis. Raw evidence is archived at
[`runs/p5-m4-6-e-task-state-context-five-witness-cdb4bc9/`](runs/p5-m4-6-e-task-state-context-five-witness-cdb4bc9/).
