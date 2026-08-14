# Atomic Agent Memory Slice (`8f33d8a`)

Date: 2026-08-14  
Implementation: `8f33d8a`  
Status: `IMPLEMENTED / VALID_DIAGNOSTIC_1_OF_5 / STOPPED_AFTER_FAILURE / GENERALIZATION_OPEN`

## Outcome

Grounded action selection no longer offers memory as an optional tool. Every
grounded model response must atomically contain:

```text
current public action/control decision + complete next bounded advisory memory
```

The model still makes one call per policy turn. After the response's context is
admitted as current, `AgentLoop` installs the attached memory and routes the
same decision through the existing Runtime path. The next disposable
`AgentContext` injects the stored memory alongside the current Unified World,
bounded interaction history and previous tool result.

## Authority and topology

- Memory is model-authored, bounded to 12 typed
  `pending | in_progress | completed` items and scoped to one run.
- It creates no separate decision turn, environment step, ActionSpace option,
  E-ref, private binding or dispatch.
- It cannot filter legal actions, assert task completion or override the
  authoritative evaluator.
- Stale responses install neither their action nor their memory.
- Grounded-tools explicitly declares `attached_working_memory`; protocols that
  do not return this envelope do not claim the capability.
- The optional `update_checklist` tool and `UpdateWorkingMemory` decision are
  deleted. No planner, critic, classifier, benchmark rule or second execution
  chain was introduced.

For a chosen action, memory reflects evidence from the current observation; it
must not mark the intended effect completed until a fresh observation confirms
it. Missing memory is a schema violation, and native tool-call repair returns
the bounded public field path `parameters.memory` to the same model operation.

## Verification before push

- focused protocol, working-memory, model-policy and visual-binding suite:
  `75 passed`;
- affected AgentLoop, DOM, Visual, WoT, composition and CLI suite:
  `92 passed`;
- `mypy src`: no issues in 497 source files;
- Ruff source/touched-test check: passed;
- `git diff --check`: passed.

These checks verify the contract and unchanged execution ownership.

## Default-4.1V live diagnostic

One frozen five-witness run completed from clean head
`d5242213089955dae8bf7e9d8cd5d59bb78df272`, whose product implementation is
`8f33d8a` plus documentation only. The output was written outside the repository
and the resulting evidence is valid:

```text
completed: 5/5
success: 1/5
outcomes: 1 success, 3 task_failed, 1 case_timeout
model: glm-4.1v-thinking-flashx
perception: structure-first.v1
protocol: grounded_tools.v2
```

The run proves that the new topology is exercised: all 12 completed policy
turns returned non-empty attached memory. It does not show a task-quality gain.

| Case | Outcome | Memory/action evidence |
|---|---|---|
| grid coordinate | task failed | memory correctly said `(1,-2)`, while the repaired action selected a public entity whose state was `(2,-1)` |
| pie/no-delay | success | memory changed from expanding the menu to clicking label `0`; both actions agreed |
| multi-target color | timeout | five distinct public blue entities were selected, but each memory contained only the next click and never retained the completed set or terminal condition |
| pie | task failed | second memory still said “Expand the pie menu” while the same response clicked `Y`; target argument repair occurred |
| visual addition | task failed | memory stored only “type total” then “press Submit”; it never stored the derived numeric result or supporting members before terminal submission |

The compact response also regressed provider/schema alignment. The 12 completed
turns accumulated 14 schema-repair counts: one initial structured-output repair
per completed turn plus two target-argument repairs. The prior optional-tool
diagnostic had zero schema or argument repairs across 15 turns. The current run
made 27 provider attempts; the color-set case timed out after five valid
actions. This is not an environment or binding failure, but the timeout cannot
be attributed solely to semantic memory quality because repair latency is a
separate contributing cause.

## Causal conclusion and stop boundary

Mandatory presence and next-context injection are now closed. They are not the
same as causal task-state control. In the current single sample, the model
authors memory and action concurrently, so the just-authored memory does not
govern the current action. On later turns the model often replaces memory with
a one-step action description instead of maintaining completed, remaining and
derived task facts. Runtime correctly validates both typed outputs but has no
authority to decide their open semantic consistency.

This is the first direct actor-memory contradiction, so a semantic consistency
stage is now evidence-justified as an experiment. A full independent critic is
not yet the smallest warranted change. If work resumes, compare the same model
under a two-call AgentPolicy-internal topology—state update first, then action
conditioned on that state—while retaining the single existing Runtime execution
chain. First simplify and measure the response schema, because every completed
turn currently required repair. Do not add task rules, deterministic semantic
guards or another Runtime path.

Per the stop instruction, no production or prompt change and no rerun follows
this failure analysis. The archived evidence is
[`runs/p5-m4-6-e-atomic-memory-five-witness-d524221/`](runs/p5-m4-6-e-atomic-memory-five-witness-d524221/).
