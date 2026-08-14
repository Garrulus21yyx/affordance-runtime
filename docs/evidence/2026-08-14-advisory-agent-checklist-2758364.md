# Advisory Agent Checklist Slice (`2758364`)

Date: 2026-08-14  
Implementation: `275836498b64fd33b7c89b1327a2f5b38ed84678`  
Status: `IMPLEMENTED / DIAGNOSTIC_RUN_COMPLETE / FORMAL_EVIDENCE_INVALID / CHECKLIST_NOT_EXERCISED`

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

## One default-model diagnostic at `b309c9d`

A single five-case run used default `glm-4.1v-thinking-flashx`, structure-first
perception and `grounded_tools.v2` at
`b309c9d10233be96082feb96e19ca3bc92290a84`. It completed all cases with raw
diagnostic outcomes of 3 success and 2 task failure, but
`run_evidence_valid=false`. The sole formal error was:

```text
git identity was dirty or changed during the arm
```

This was an invocation error: the new output directory was created inside the
repository, so the final identity gate correctly observed the runner's own
untracked evidence files. It is not a provider, GUI, schema or case-execution
failure. The raw traces are retained only as invalid diagnostic evidence and
must not be used as a benchmark improvement claim.

| Case | Raw outcome | Policy behavior |
|---|---|---|
| grid coordinate | success | one structural `SelectAction` |
| pie/no-delay | success | two structural `SelectAction` calls |
| multi-target color | task failed | seven structural actions; reactivated an entity while current public state exposed `selected=true`, then submitted |
| pie | success | two structural `SelectAction` calls |
| visual addition | task failed | filled, filled again after the public textbox value became `6`, then submitted an environment-rejected answer |

Across the cohort there were 15 policy calls, all 15 resolved as
`SelectAction`. There were zero `UpdateWorkingMemory` decisions, images,
argument violations or repairs. Every call's catalog included
`update_checklist`, but the model never selected it.

## Causal conclusion and stop boundary

This run does not validate or falsify checklist-assisted action quality because
the checklist mechanism was never exercised. It does falsify the weaker
assumption that merely offering an optional cognitive tool changes this
default policy topology. The 3/5 versus prior 1/5 cannot be attributed to the
new mechanism; both pie successes occurred without it and are consistent with
the already observed provider variance. The two residual failures remain at
the same semantic boundary as before: completed-set continuity and aggregate
answer validation.

An independent critic is still premature: no persisted checklist existed for
an actor to contradict. Work stops after this analysis. If resumed, the next
architecture choice must isolate one general variable that actually guarantees
cognitive continuity, for example a bounded policy-internal initial state
update or provider-native session memory. It must not infer complexity from
benchmark names, add task-family rules, or create a second execution path.

The raw invalid diagnostic is preserved at
[`../runs/p5-m4-6-e-advisory-checklist-five-witness-b309c9d/`](../runs/p5-m4-6-e-advisory-checklist-five-witness-b309c9d/).
