# Runtime R8 Planner Model Orchestrator Containment Evidence

Date: 2026-07-22

Status: planner model/schema orchestration slice complete; R8 remains in
progress.

## Boundary

`planner_model_orchestrator.py` now owns the provider-neutral mechanics of one
Generalist model turn:

- the model-authored candidate data schema and dynamic initial/repair schemas;
- one structured initial generation followed by a bounded repair loop;
- preservation of the original system/user messages and same PlannerContext
  across repairs;
- redacted semantic-validation exhaustion;
- a mandatory reservation hook immediately before every provider call;
- generic action-to-target schema projection, including semantic drag
  destination constraints.

The collaborator is stateless. `GeneralistLMPlanner` still owns the exact
Prompt and `ModelConfig`, cumulative call count and maximum-call budget,
compiler-before-model fallback order, semantic issue classification and target
narrowing, candidate-to-`PlannerProposal` binding, model-call trace attachment,
and final planner-context trace payload. Coordinator and StateKernel are
untouched, so this creates no new authoritative state writer.

The public `PlannerProposalCandidate` remains available from
`generalist_planner.py` and inherits the provider-neutral data schema while
retaining its existing runtime-binding method. Compatibility wrappers preserve
the existing `_initial_candidate_schema` and `_repair_candidate_schema` test
surface. A complete JSON Schema comparison against the prior field declaration
is equal, including required fields, aliases, bounds, enum values, defaults,
and extra-field rejection.

No Prompt text/version, context-policy version, schema name, dynamic schema
class name, model configuration, repair count, model-call counting point,
semantic error string, repair message, proposal binding, provider behavior, or
trace field changed. No backend syntax, benchmark/task-family branch, selector,
coordinate, service, queue, or distributed state was introduced.

## Runtime-first evidence

Direct provider-neutral tests use only a structured `ModelPort` fixture and a
generic typed affordance context. They prove:

- a valid candidate binds after exactly one reserved provider call;
- an invalid target is repaired once with the exact four-message sequence on
  the same context and a narrowed dynamic schema;
- semantic repair exhaustion raises a redacted `StructuredModelError` and does
  not return an invalid proposal;
- a provider-side structured-schema failure propagates without an invented
  repair;
- every attempted call first reserves budget, and repair stops before a second
  provider call when the cumulative budget is exhausted;
- the public candidate inheritance preserves the provider schema fields.

Existing generic DOM, cross-surface Coordinator, compiler, and intent
compilation tests cover the integrated path without BrowserGym. The shared
source boundary test continues to reject BrowserGym/MiniWoB vocabulary.

No benchmark was run for this internal containment slice. Behavioral
equivalence, provider neutrality, and ownership are proven by direct and full
Runtime gates; benchmark scores cannot substitute for those claims.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused orchestrator/generalist/compiler/cross-surface/boundary tests: 88
  passed;
- full repository tests: 494 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 84 source files: passed;
- `git diff --check`: passed.

The Generalist planner fell from 2,481 to 2,288 lines. The extracted
orchestrator is 344 lines, including candidate and constrained-schema models.

## Remaining R8 work

- review whether the remaining semantic algorithms form one cohesive owner or
  require a further non-mechanical module boundary;
- split BrowserGym observer, encoder, episode runner, and report adapter;
- migrate selected bindings toward tagged payloads and finish the ownership and
  trace-schema audit.
