# Dynamic Tools v1 Protocol Experiment

Status: IN_PROGRESS — bounded transport experiment

## Goal

Test whether a smaller, ephemeral tool-selection facade removes the exact
decision-schema blocker observed with `glm-4.1v-thinking-flashx`, without
creating a second action, execution, objective, or task authority.

```text
AgentContext + current ActionPage
  → ephemeral ToolCatalog
  → exactly one model proposal
  → catalog resolver
  → AgentDecisionPackage(NoObjectiveOperation, decision)
  → existing objective/action admission
  → existing confirmation/currentness/execution/evaluation
```

## Frozen scope

- Protocol ID: `dynamic_tools.v1`.
- First slice covers current action options and objective-neutral control tools.
- Runtime identities are hidden behind call-local opaque tool and destination
  references.
- Destination-required actions expose one bounded `destination_ref` enum; the
  catalog does not expand `option × destination`.
- The catalog is immutable and bound to the exact context, observation, action
  page, and action-space revision used to compile it.
- Resolver output always uses `NoObjectiveOperation`; it never mutates or
  clears the active objective.
- ActionSpace admission, current binding, risk, confirmation, dispatch,
  effect evaluation, task evaluation, and transition identity remain owned by
  existing Runtime components.
- Initial result feedback continues through the next `AgentContext`; no
  assistant/tool conversation history is introduced.

## Non-goals

- Toolifying objective or requirement-hypothesis production.
- Introducing objective-only policy turns.
- Creating ToolManager, ToolScheduler, tool ledger, or tool execution state.
- Treating provider call IDs as Runtime transition identity.
- Replacing current observation/action paging or backend acquisition semantics.
- Assuming native tool-call support from provider name alone.

## Closed outcomes

The model boundary accepts exactly one proposal. It returns typed failures for:

- zero proposals;
- multiple proposals;
- unknown tool name;
- invalid argument object;
- unknown or stale catalog identity;
- unknown destination reference;
- provider/schema/transport failure.

All rejected outcomes are zero-dispatch. Unsupported model profiles fail closed
or use the explicitly configured compact `{tool, args}` transport; they never
silently switch protocol.

## Work plan

| Step | Status | Evidence |
|---|---|---|
| Freeze authority, lifecycle, and A/B contract | implemented | this record |
| Provider-neutral ToolSpec/ToolCall contracts | implemented | source + contract tests |
| Pure catalog compiler and resolver | implemented | property/state tests |
| Compact transport and exact model routing | implemented | adapter tests |
| Policy integration and metrics/trace | implemented | integration tests |
| Full repository validation | implemented | 2289 passed, 27 skipped; Ruff clean |
| Same-Zhipu two-case A/B | pending | clean-SHA evidence |
| Fresh authority review | pending | review record |

## A/B gate

Both arms must use the same Zhipu model, cases, seed, screenshots, AgentContext,
requirement hypotheses, Runtime implementation, turn limits, and timeouts.

```text
structured_package.v2
vs
dynamic_tools.v1
```

Primary diagnostic metrics:

- valid proposal rate;
- zero/multiple/unknown proposal counts;
- argument and stale-catalog rejection counts;
- admitted decision count;
- GUI dispatch count;
- provider attempts and format repair count;
- catalog count/bytes and token/latency measurements.

Safety invariants remain required: invalid/stale calls are zero-dispatch;
confirmation behavior is unchanged; `SENT_UNKNOWN` is never replayed; and the
tool facade cannot amplify ActionSpace authority.

## Exit criteria

- Every resolved action maps bijectively to one current ActionOption and, when
  required, one current eligible destination.
- Resolver output passes through existing action/objective admission; direct
  execution is impossible.
- Catalogs from another context/observation/page deterministically fail before
  dispatch.
- Exactly-one proposal and bounded argument properties hold under generated
  invalid inputs.
- Full tests pass on a clean implementation SHA.
- Same-model A/B reports whether valid decisions and GUI dispatch improve from
  the structured-package baseline without safety regressions.
