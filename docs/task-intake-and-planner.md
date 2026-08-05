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

- objective and input bindings;
- allowed effects and capability ceiling;
- hard constraints, preferences, and forbidden effects;
- typed success expression and requested outputs;
- risk policy;
- `source_envelope_ref` and `source_binding_digest`.

TaskSpec has no steps, current UI facts, action family, selector/coordinate,
claim/obligation graph, evidence instances, or completion flags.

TaskSpec revision is allowed only for user clarification/modification or a
policy/authorization change that requires reconfirmation. Observation, failure,
replan, or Planner preference cannot revise TaskSpec.

## 5. Task planning horizon

Task Planner consumes an immutable TaskPlanningRequest containing TaskSpec,
bounded canonical-observation projection, verified progress/bindings, recent
typed failures, assumptions, and budgets. It proposes `StepSpec` milestones.

TaskPlanAuthority validates identity, dependencies, criterion fidelity,
observation/state basis, authorization compatibility, and digest. The accepted
TaskPlan stores `StepSpec` directly and can be replaced without changing
TaskSpec. It is a Milestone Graph, never an intake obligation graph.

## 6. Active-step choice horizon

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

## 7. Selection and ActionContract

ActionSelectionValidator checks current Catalog/page membership and identity.
ActionContractBuilder routes canonical bindings and produces one immutable,
expiring transaction. Task authority, capability, approval, and freshness/
preflight gates run after binding and before execution.

## 8. Planner finish

Planner FinishProposal is only `FinalVerificationRequested`. Initial state may
already satisfy a `STATE_HOLDS` task without an action. Plan exhaustion and
Planner finish never imply TaskCompleted.

## 9. Typed intake/planning outcomes

- clarification required;
- proposal rejected or bounded repair required;
- planning infeasible or stale;
- perception coverage/state required;
- invalid/unpresented choice;
- capability/approval denied;
- final evidence insufficient.

Generic error strings are diagnostics, not control ownership.

The previous extraction-era document is archived at
[maintained-pre-consolidation/task-intake-and-planner.md](archive/superseded-2026-08-05/maintained-pre-consolidation/task-intake-and-planner.md).
