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

`SourceAnchor` is a selective provenance primitive, not a span quota. Ordinary
low-risk fields may bind a whole-request anchor. Material admission uses one of
four typed forms:

- `DIRECT_USER_EXPLICIT`: the typed value deterministically occurs in the current request; no character offset is required;
- `EXACT_SOURCE_EXCERPT`: an indirect unstructured attachment/email/web/profile value has a field-matched exact anchor;
- `TYPED_EXTERNAL`: a structured ingress value binds a versioned source and typed field path;
- `USER_CONFIRMED`: a later explicit user confirmation binds a versioned conversation confirmation record.

Page observations cannot become user authority sources. The same rule applies
to email, PDF, DOM, AX, OCR, screenshot, notification, memory/skill, and tool
output. Exact anchors prove lineage only; they do not prove field completeness
and do not grant capability, approval, policy, TaskSpec revision, control flow,
grounding, an ActionContract, or completion. An observation-derived value may
enter an effectful field only when the admitted TaskSpec explicitly permits that
typed source-to-field flow.

`MaterialBindingPolicy`, composed inside `TaskSpecAuthority`, checks each
external/irreversible effect independently: SEND requires recipient +
destination/channel + content/file; PAYMENT requires payee/account + amount +
currency; DELETE requires target + scope; SHARE requires principal + resource +
permission. One unrelated FILE or AMOUNT anchor cannot satisfy another field.

## 3. MinimalIntentProposal and SemanticAudit

The model returns an untrusted `MinimalIntentProposal` containing objective,
input/effect/constraint/forbidden-effect proposals, success proposal, source
anchor references, and ambiguities. It contains no accepted task identity,
steps, selector, capability, approval, or completion state.

`SemanticAudit` runs only for configured risk, irreversible/external effects,
multiple authority sources, attachment/profile authorization, material source
conflict, abnormal interpretation, or material-field ambiguity. Ordinary
effect-specific field completeness belongs to `MaterialBindingPolicy`, not the
audit. The audit may pass, veto, or request
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

The P0-E production bridge stores admitted `material_bindings` directly on the
current TaskSpec shape so later stages cannot recover them from prose. P3 folds
those values into canonical `TaskRequirement`/`InputBinding` payloads and keeps
only stable binding references plus the digest; it must not introduce a second
material registry or a legacy round-trip.

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
The accepted TaskPlan stores `StepSpec` directly and can be replaced without changing
TaskSpec. It is a Milestone Graph, never an intake obligation graph.

Requirement-ID membership is necessary but not sufficient. TaskPlanAuthority
applies deterministic typed semantic subsumption (`StepSpec ⊑
CanonicalRequirement`) over operation, effect class, subject/target,
destination, material parameter values, externality/reversibility, element
function and task usage, completion criterion, and required-output relation.
The result is ALLOW, DENY, or UNPROVEN; a plan cannot use a valid read
requirement ID to authorize delete, send, payment, or another broader action.
This evaluator reuses the existing canonical requirement table and is not a
second obligation graph or a whole-program theorem prover.

Replaceable does not mean replan every loop. Runtime reuses a still-feasible
active plan and may install a direct deterministic milestone without a model
call. Task Planner is called only for a typed `NO_CURRENT_PLAN`,
`PLAN_EXHAUSTED_TASK_INCOMPLETE`, `STEP_INFEASIBLE`, `ASSUMPTION_DISPROVED`,
`ENVIRONMENT_BOUNDARY_CHANGED`, or explicit policy/budget trigger. Every model
TaskPlanningRequest carries that trigger.

## 7. Active-step choice horizon

For the active step, Runtime first builds the complete legal
`ActionChoiceCatalog` from TaskSpec/TaskPlan/progress/current canonical
observation/effective capability/policy. Model presentation limits are not
Catalog inputs.

Effective capability is the intersection of the frozen
provider/model/tool-schema descriptor, environment adapter support, product
policy, and current user grant. Unknown actions, missing required safety
features, or provider-schema version/digest drift fail closed. Provider safety
or schema acceptance cannot create local Runtime authority. Product profiles
retain all safety gates; benchmark-only ablations use a separate composition and
cannot be selected by the production planner.

Complete means logically complete, not necessarily eagerly materialized. Small
Catalogs may hold every ActionChoice directly; large Catalogs may use immutable
lazy/indexed/query-backed membership. `count`, `contains`, `get`, deterministic
page/query results, rejection semantics, and digest must remain identical for
the same canonical inputs regardless of materialization or model page size.

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
`ActionTransactionMaterializer` routes canonical bindings and produces one
complete executable contract, including the final payload. It freezes that
contract before task/policy/capability and approval evaluate it. Final preflight
checks snapshot/page/target/expiry; Executor then consumes the same immutable
hash. Any reject or stale result makes zero Executor calls. Extended context,
coordinate, descriptor, permit/CAS/fencing and credential late-binding contracts
are scenario-triggered future hardening, not P4/P5 blockers.

`replace()` and partial preflight patching of a sealed contract are forbidden.
Any observation, surface generation, route, target, parameter, coordinate,
provider schema, capability, provenance, verifier, or risk change requires full
rematerialization, a new digest, and renewed admission/approval. Current
production dispatches primitive transactions only; batch/macro remains
plan-level and deferred.

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

## 11. Selective SOTA and complexity boundary

Planning adopts typed actions, partial-observation semantics, and
trusted-control versus untrusted-data separation; capability/coordinate identity
is added when an adapter needs it. AgentDojo/WASP utility and attack metrics and
OSWorld-V2 collateral probes are future release profiles only; they do not
enter planner context or confer execution authority.

The planner rejects prompt-only authorization, provider safety as local
authority, model-generated selectors/coordinates, generic success as effect
truth, and benchmark reward as completion. Enforcement remains narrow and
typed inside the modular monolith; it does not introduce a general taint
platform, planner microservices, another semantic registry, or theorem proving.

The previous extraction-era document is archived at
[maintained-pre-consolidation/task-intake-and-planner.md](archive/superseded-2026-08-05/maintained-pre-consolidation/task-intake-and-planner.md).
