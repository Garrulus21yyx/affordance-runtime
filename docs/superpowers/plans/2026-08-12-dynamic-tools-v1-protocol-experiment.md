# Dynamic Tools v1 Protocol Experiment

Status: A/B_EXECUTED_INCONCLUSIVE — SELECTED_TOOL_ARGUMENT_REPAIR_OPEN

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
| Full repository validation | implemented | 2294 passed, 27 skipped; Ruff clean |
| Same-Zhipu two-case A/B | inconclusive | `p5-e-zhipu-dynamic-tools-ab-84a9466` |
| Selected-tool argument repair | implemented | same catalog/context/tool; one shared repair budget; focused tests |
| Targeted case-15 rerun | pending | fresh clean-SHA evidence |
| Fresh authority review | completed diagnostic | resolver authority remains unchanged |

## First A/B result

The clean-SHA `84a9466` run is valid execution evidence but not a valid
protocol-effect comparison:

- both arms completed two cases and each succeeded on `miniwob-60-31`;
- both arms failed `miniwob-60-15` before dispatch;
- the structured arm failed its decision package schema;
- the dynamic arm selected a known `act_02` but supplied `{}` where the
  catalog required `value: string`; the resolver correctly rejected it with
  zero dispatch;
- `comparison_valid=false` and the case-15 pair is inconclusive.

The archived aggregate token and latency fields omit failed-call usage because
the existing metadata projection only commits accepted call records. They may
describe the accepted case-31 path, but must not be interpreted as total
two-case arm cost.

The next bounded change is argument-only repair after a known tool fails its
declared input schema. It must retain the same catalog, context, and tool;
expose the selected `ToolSpec` schema plus a safe typed violation; consume the
same single repair budget used by outer-format repair; and return to the
existing resolver for final validation. It must not create a GUI turn,
decision, transition, dispatch, or guessed parameter value.

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
