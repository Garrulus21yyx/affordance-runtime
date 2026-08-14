# Atomic Agent Memory Slice (`8f33d8a`)

Date: 2026-08-14  
Implementation: `8f33d8a`  
Status: `IMPLEMENTED / PUSHED / LIVE_NOT_RUN / GENERALIZATION_OPEN`

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

These checks verify the contract and unchanged execution ownership. No live
five-case benchmark has been run at this implementation SHA, so task-quality
improvement is not claimed. The next validation must use an evidence directory
outside the repository and record whether memory is non-empty and evolves
across turns. If the prior set/aggregation failures remain, the admitted next
step is causal trace analysis and stop—not a task-specific patch or an
immediate critic.
