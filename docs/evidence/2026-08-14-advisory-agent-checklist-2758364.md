# Advisory Agent Checklist Slice (`2758364`)

Date: 2026-08-14  
Implementation: `275836498b64fd33b7c89b1327a2f5b38ed84678`  
Status: `IMPLEMENTED_NOT_BENCHMARK_VALIDATED`

## Why this slice exists

The clean default-model run at `90c3997` showed one direct grounding success
and four failures concentrated in sequence choice, completed-set continuity,
aggregation and finalization judgment. Runtime already exposed the relevant
Unified World and executed every selected structural action correctly. The
remaining hypothesis is therefore narrower than “add a planner” or “add a
critic”: the recurrent policy loses its model-authored task state because every
turn starts from a fresh disposable request and only a compressed event history
survives.

[GlassBrowser](https://github.com/lzw12w/glass-browser) provides a useful small
reference point. Its actor remains a simple tool-using loop, but provider-native
message history and a durable todo checklist preserve cognitive continuity.
It does not require an independent critic for that basic mechanism. Its public
benchmark evidence should not be read as proof of equivalent full multi-step
task success; the relevant architectural lesson here is the checklist owner and
loop topology, not its score.

## Implemented topology

```text
TaskGoal + current Unified World + prior checklist
                    |
                    v
          existing GroundedActionAdapter
             /                  \
 update_checklist          environment tool
        |                         |
        v                         v
AgentLoopState advisory     existing Runtime chain
full replacement only       resolve -> admit -> bind -> execute
        |
        +------ fresh disposable AgentContext ------+
```

`update_checklist` is a typed `UpdateWorkingMemory` control. It replaces at
most 12 bounded `pending | in_progress | completed` items. The replacement:

- produces no BrowserGym/environment step;
- creates no ActionSpace option, action ID, E-ref binding or dispatch request;
- cannot filter or authorize Runtime actions;
- cannot assert task completion or override evaluation;
- is scoped to one `AgentLoopState` and projected back as explicitly advisory
  context on the next policy call.

The next model call still uses the existing grounded action adapter and the
existing Runtime execution chain. No task classifier, second planner, candidate
generator, semantic critic, arithmetic/color/count handler or benchmark branch
was added.

## Protocol closure

The protocol capability sets now remain exact:

- structured-package retains its existing seven-decision algebra;
- dynamic-tools retains select/observe/page controls;
- grounded-tools additionally declares `update_working_memory`;
- the primary benchmark composition requires that grounded capability and
  fails before execution if it is absent.

This avoids claiming checklist support for adapters that cannot emit it.

## Verification before push

- focused checklist/grounded/composition/parser suite: `98 passed`;
- affected architecture/model-boundary/control suite: `146 passed`;
- Ruff on every touched source and test file: passed;
- `mypy src`: passed across 497 source files;
- `git diff --check`: passed.

These checks prove the control and authority boundary, not task-performance
improvement.

## Next falsification step

Run the frozen five-case cohort with the default
`glm-4.1v-thinking-flashx` against a clean commit containing this slice. Inspect
first whether the model uses `update_checklist`, whether a following call takes
an environment action, and whether the checklist evolves coherently. Then
compare task outcomes with the prior clean 1/5 run.

If the model ignores the checklist or repeatedly rewrites it without acting,
stop and analyze prompt/tool-use alignment. If it maintains a coherent
checklist but still chooses actions that contradict it, that is the first
evidence for considering a bounded semantic critic. A critic is not admitted
before that boundary is observed.
