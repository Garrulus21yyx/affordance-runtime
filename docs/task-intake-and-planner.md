# Task Intake and Generalist Planner Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** source intake, TaskSpec admission, TaskPlan generation, and bounded model planning
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## 1. Boundary

```text
natural-language interpretation
≠ accepted user authorization
≠ execution plan
≠ current legal action space
≠ concrete action transaction
≠ task completion
```

The model proposes. Runtime-owned authorities admit, bind, gate, evaluate, and
commit.

The semantic-authority rule is:

```text
single semantic admission
+ bounded contextual rereading
+ no downstream authority expansion
```

## 2. Default source path

`SourceEnvelopeBuilder` always creates one lightweight immutable envelope with
request identity/digest, caller/conversation revision, and attachment/target/
profile references. It does not split clauses or construct claim, coverage, or
obligation graphs.

`SourceAnchor` selectively binds material fields. Recipient, amount, account,
file, external destination, destructive target, forbidden effect, and
approval-related constraint prefer exact legal source spans. Ordinary low-risk
fields may bind a whole-request anchor.

Page observations cannot become user authority sources.

## 3. MinimalIntentProposal and SemanticAudit

The model returns an untrusted `MinimalIntentProposal` containing objective,
input/effect/constraint/forbidden-effect proposals, success proposal, source
anchor references, and ambiguities. It contains no accepted task identity,
steps, selector, capability, approval, or completion state.

`SemanticAudit` runs only for configured risk, irreversible/external effects,
multiple authority sources, attachment/profile authorization, material source
conflict, or material-field ambiguity. It may pass, veto, or request
clarification. It cannot add effects, alter success, grant capability, or repair
an invalid proposal into a ready TaskSpec.

## 4. TaskSpecAuthority

TaskSpecAuthority validates and freezes:

- explanatory objective and input bindings;
- one flat canonical `TaskRequirement` table;
- allowed-effect, constraint, preference, forbidden-effect, success, and output references to canonical requirement IDs;
- typed success expression and stable required OutputSpecs with materialization/source-binding policies;
- risk policy;
- `source_envelope_ref` and `source_binding_digest`.

TaskSpec has no steps, current UI facts, action family, selector/coordinate,
claim/obligation graph, evidence instances, or completion flags.

TaskSpec revision is allowed only for user clarification/modification or a
policy/authorization change that requires reconfirmation. Observation, failure,
replan, or Planner preference cannot revise TaskSpec.

## 5. Semantic Authority Boundary

`TaskSpecAuthority` is the only Task Meaning Write Barrier. Raw language
visibility does not grant semantic authority.

`SourceContextProjector` may produce an immutable `SourceContextView` containing
only accepted `AnchoredExcerpt` values, their existing requirement/criterion
IDs, and an optional non-authoritative summary. Its authority is always
`context_only`.

Allowed readers are:

- Task Planner, only when bounded source pragmatics materially help milestone decomposition;
- OpenSemanticResolver, only for the exact excerpts linked to an existing OpenSemanticCriterion;
- ClarificationComposer, only to phrase a question for a typed ambiguity or `TaskSpecGap`.

They cannot create requirements, effects, constraints, capability, success
semantics, or TaskSpec revisions. Missing admitted semantics returns
`TaskSpecGap` or clarification. Step Choice Planner normally receives no source
context. Action choice construction, grounding/predicate resolution, contract
binding, gates, execution, evaluation, completion, and commit receive no raw
request or SourceContextView.

Bounded proposal repair occurs before admission and replaces the untrusted
proposal; it never creates a second accepted meaning.

## 6. Task planning horizon

Task Planner consumes an immutable TaskPlanningRequest containing TaskSpec,
bounded canonical-observation projection, verified progress/bindings, recent
typed failures, assumptions, and budgets. When explicitly required, it may also
receive the bounded read-only SourceContextView described above. It proposes
`StepSpec` milestones; every Step carries `requirement_refs`, and effectful
Steps also carry `effect_authorization_refs`.

TaskPlanAuthority validates identity, dependencies, criterion fidelity,
observation/state basis, canonical requirement/effect traceability,
authorization compatibility, and digest. Semantic value dependencies use typed
Input/Binding/Value refs; execution ordering uses only `StepSpec.depends_on`.
The accepted
TaskPlan stores `StepSpec` directly and can be replaced without changing
TaskSpec. It is a Milestone Graph, never an intake obligation graph.

## 7. Active-step choice horizon

For the active step, Runtime first builds the complete legal
`ActionChoiceCatalog` from TaskSpec/TaskPlan/progress/current canonical
observation/effective capability/policy. Model presentation limits are not
Catalog inputs.

```text
0 choices → typed deterministic failure owner
1 choice  → Runtime selects
N choices → bounded ChoicePage → Step Choice Planner
```

Step Choice Planner may select only a displayed choice ID, request next page,
apply a sealed typed refinement, ask, or defer. It cannot invent action,
binding, selector, coordinate, backend, capability, or approval.

Each `ChoicePresentation` includes bounded target label/role, destination,
relevant current state, requirement/effect refs, evidence refs, conflict, risk,
and generation reason codes. It excludes selector, coordinate, locator,
backend handle, approval token, hidden IDs, and unrestricted source text.

## 8. Selection and ActionContract

ActionSelectionValidator checks current Catalog/page membership and identity.
ActionContractBuilder routes canonical bindings and produces one immutable,
expiring transaction. Task authority, capability, approval, and freshness/
preflight gates run after binding and before execution.

## 9. Planner finish and required outputs

Planner FinishProposal is only `FinalVerificationRequested`. Initial state may
already satisfy a `STATE_HOLDS` task without an action. Plan exhaustion and
Planner finish never imply TaskCompleted. TaskCompleted additionally requires
every required OutputSpec to be materialized and source-bound when its policy
requires lineage; Planner prose cannot substitute for structured output.

## 10. Typed intake/planning outcomes

- clarification required;
- TaskSpecGap discovered by bounded contextual reasoning;
- proposal rejected or bounded repair required;
- planning infeasible or stale;
- perception coverage/state required;
- invalid/unpresented choice;
- capability/approval denied;
- final evidence insufficient.

Generic error strings are diagnostics, not control ownership.

The previous extraction-era document is archived at
[maintained-pre-consolidation/task-intake-and-planner.md](archive/superseded-2026-08-05/maintained-pre-consolidation/task-intake-and-planner.md).
