# Architecture

## Purpose

Affordance Runtime is a small orchestration layer around a GUI agent. Its distinctive capability is adaptive
multi-source observation: acquire a cheap structured view first, supplement it only when the task, grounding, or
verification evidence requires another source, and expose one fused semantic world to the model.

## One control flow

```text
                         TaskGoal
                            |
                            v
                  ObservationPolicy
               cheap sufficient sources
                            |
                            v
          DOM / AX / Visual / WoT / HTTP adapters
                            |
                            v
                       WorldFusion
                            |
                            v
                    WorldObservation
                       /          \
                      v            v
              ActionSpace      ContextBuilder
                      \            /
                       v          v
                       AgentPolicy
                            |
                            v
                    semantic decision
                            |
                            v
              admission -> binding -> execution
                            |
                            v
                 fresh post-action observation
                            |
                            v
              ActionEvaluation + TaskEvaluation
                            |
                            v
                        RunState
```

The loop is reactive. `WorldObservation` is current environment truth. The Runtime does not maintain a replayable
world history or infer a persistent semantic delta graph.

## Core contracts

### TaskGoal

The stable task contract: instruction, success criteria, allowed effects, requested outputs, risk profile, and loop
budget. Benchmark IDs and hidden oracle values never enter it.

### SurfaceAdapter

A source adapter owns source-specific acquisition and execution details. It publishes:

- observation offers: modality, assurance, purpose, and cost;
- normalized source observations;
- private action bindings;
- typed unavailable or failed acquisition;
- exact dispatch truth for actions it executes.

Adapters do not interpret the task, choose the next source, or decide task completion.

### ObservationPolicy and WorldFusion

The observation policy chooses the cheapest sufficient offers for a typed evidence need. A normal acquisition uses
one source and may add at most one complementary source. `WorldFusion` aligns accepted source observations and
produces one immutable `WorldObservation` with public semantic entities, facts, relations, conflicts, artifacts, and
private bindings.

Source selection and fusion are different responsibilities: selection decides what to acquire; fusion decides what
the acquired evidence supports.

### ActionSpace and binding

`ActionSpace` is derived from the current world. The model proposes only offered semantic actions and call-local
entity references. Runtime admission checks the current task boundary and risk policy. The binder resolves the
accepted semantic action to a current private route immediately before execution.

### AgentContext

The target model input contains only:

```text
goal
current public world
currently offered semantic actions and tools
recent semantic actions and their verified outcomes
```

Provider-specific prompts and tool schemas are serializations of this context, not authoritative state.
Step, observation, wait, token, and cost budgets remain private Runtime control. They affect termination and which
tools are currently offered; their counters are not model context.

### RunState and StepResult

In the simplified core, `RunState` is the only mutable run-control value:

```text
current_world
current_task_evaluation
last_step
status
remaining_steps
observation_count
execution_count
context_generation
recent_actions (at most four public summaries)
```

`remaining_steps` is Runtime-only. The loop decrements it and stops at zero; the model does not receive the number.
`recent_actions` is bounded disposable context, not environment authority or a replay log.

`StepResult` records what the next model turn needs to know about one policy outcome:

```text
decision
before-world
execution result, if any
fresh after-world, if acquired
action evaluation, if an action was dispatched
task evaluation
status after the step
confirmation request, if any
short feedback
```

It is not an aggregate root, event log, replay authority, or reconstruction format. Detailed provider timings and
debug data may be emitted as telemetry, but telemetry cannot re-enter Runtime control.

## Authority boundaries

| Question | Owner |
|---|---|
| What did a source observe? | SurfaceAdapter |
| Which sources are worth acquiring now? | ObservationPolicy |
| What is the current unified world? | WorldFusion / WorldObservation |
| What semantic action should be attempted? | AgentPolicy |
| Is the action legal and current? | Runtime admission and binder |
| What was physically dispatched? | Executing adapter |
| Did the action have the expected effect? | ActionEvaluator |
| Is the task complete? | TaskEvaluator |
| Continue, wait, ask, finish, or fail? | Core loop using typed outcomes |

## Closed run statuses

The core status algebra is `running`, `waiting_user`, `waiting_confirmation`, `done`, `blocked`, `cancelled`, and
`failed`. Known but unmigrated decision paths and unavailable capabilities stop with a status and bounded reason code.
An invalid policy implementation raises `TypeError`; failed initial acquisition raises `CoreLoopStartError`. Terminal
states are absorbing for the current run. Resume behavior is not yet migrated. Durable replay and cross-process
idempotency are outside the current scope.

## Migration status

The simplified loop is an explicit migration target, not yet the default CLI path. `TargetRuntime.run_core_task`
currently reuses the production environment, action-space builder, binder, risk policy, context builder, model policy,
and evaluators.

The low-risk `SelectAction` path is the first migrated vertical slice: admission, binding, one dispatch, fresh
observation, action/task evaluation, and a bounded public history window are connected. The next model turn sees the
semantic action, public parameters, dispatch truth, verified effect, task status, and evaluator reason. It does not see
the binding, selector, full world diff, or remaining budgets.

Pre-dispatch rejection remains fail-closed, and confirmation and user-input resume are not yet migrated.
`RequestActionPage` and `Wait` still stop with `decision_path_not_migrated`. Each later path must move with its own
contract test before the default runtime switches; until then, the legacy loop remains only as the behavior source.

## Non-goals

- event sourcing or a transition ledger;
- exact Python object-identity proofs across every phase;
- a generalized workflow or multi-agent engine;
- predictive GUI world models;
- benchmark-specific branches in product code;
- reconstructing Runtime state from reporting DTOs;
- production-grade persistence, distributed retries, or long-running orchestration.

## Change rule

A product change must improve a reusable contract or address a benchmark-observed shared cause. Adding an adapter
must not require changes to run control. Adding an action must not require changes to observation fusion. Adding a
benchmark must not change product behavior.
