# Runtime R8 PlannerContextBuilder Containment Evidence

Date: 2026-07-22

Status: generalist-planner context slice complete; R8 remains in progress.

## Boundary

The bounded planner input model and construction policy now live in
`planner_context.py`:

- `AffordanceSummary`, `PlannerContext`, and `PlannerLimits`;
- explicit `PlannerContextBuilder` plus the compatible
  `build_planner_context` function;
- semantic-target inventory projection and permitted semantic action kinds;
- untrusted text/state/affordance/artifact bounds;
- current-revision satisfied-target memory;
- one relevant execution/verification/recovery failure summary.

`GeneralistLMPlanner` still owns model calls, Prompt/schema repair, proposal
binding, and the exact semantic compiler/constraint ordering. Existing
non-private imports of the context models, limits, and compatibility function
from `generalist_planner` remain valid. Internal helper tests now import their
actual owner module.

No Prompt version, context-policy version, field, bound, ranking rule, action
mapping, compiler, model budget, or provider behavior changed. The generalist
planner fell from 2,985 to 2,617 lines; the extracted builder is shared Runtime
code with no BrowserGym/MiniWoB vocabulary.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused context/generalist/compiler/boundary tests: 77 passed;
- full repository tests: 485 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 82 source files: passed;
- `git diff --check`: passed.

Direct generic tests prove bounded visible text, artifacts, accepted knowledge,
and affordance count; preservation of observed action families under a small
inventory budget; semantic permitted-action projection; absence of selector
and backend-handle fields; equality of the compatibility function and explicit
builder; and fail-closed rejection of a legacy envelope without `TaskSpec`.

## Remaining R8 work

- separate generalist LM invocation/schema repair from semantic rule functions;
- move default generic compiler rule registration out of the planner module
  while preserving rule order and evidence declarations;
- split BrowserGym observer, encoder, episode runner, and report adapter;
- migrate selected bindings toward tagged payloads and finish ownership audit.
