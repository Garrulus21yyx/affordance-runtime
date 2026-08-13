# M4.6-E Set-objective de-specialization convergence plan

Date: 2026-08-13

Status: `CONVERGENCE_REOPENED / DUPLICATE_AUTHORITY_MIGRATION_REQUIRED`

## 2026-08-13 architecture-first correction

The attempted `TaskProgram` repair was reverted.  It duplicated whole-task
planning inside the benchmark short loop and then forced the model boundary to
carry a third task schema.  Its structured-output failures were symptoms of the
duplicated owner, not a reason to keep repairing that schema.

Repository review found three planning surfaces:

1. the retained default `TaskSpec -> TaskPlan<StepSpec> -> StateKernel/Coordinator`
   chain;
2. the target `TaskGoal -> optional TaskPlan<Milestone> -> VerifiedTaskState /
   ActiveObjective -> AgentLoopState` chain;
3. M4.6 short-loop `set / sequence / aggregate` ingress and the now-reverted
   `TaskProgram` wrapper.

The selected convergence path retains the admitted `TaskSpec` and canonical
`TaskPlan<StepSpec>` authority contracts, connects them to the target AgentLoop,
and does not import the old StateKernel/Coordinator execution core. M4.6 violated
that boundary by letting Catalog/model transport create planner-shaped semantic
state. The active work is to migrate the required set/sequence/aggregate algebra
into canonical plan steps and one step-execution reducer, then delete both the
temporary short-loop ingress and the displaced default execution chain at their
cutover boundary.

No further model schema tuning is allowed before that owner migration is
defined.  Projection schemas serialize canonical state; they do not define it.

The migration must also avoid an over-extended causal/provenance chain. Runtime
correctness requires only the admitted task/plan identity, active step identity,
current observation/action-space identity, one execution result, and validated
effect evidence. Model projections, tool catalogs, prompts, benchmark records,
and transition summaries are not additional causal authorities.

## Goal

Remove benchmark-shaped soft specialization from quantified GUI objectives. The
five MiniWoB witnesses remain regression evidence only. Runtime behavior must be
driven by admitted typed task semantics, current evidence obligations, persistent
set membership/effect state, and a fail-closed Catalog directive.

## Non-negotiable boundary

```text
Benchmark owns examples and evaluation.
Task authority owns semantic interpretation.
Evidence providers own bounded proposals.
Set Runtime state owns membership and obligations.
Catalog owns enforcement of the reducer directive.
Evaluators own effects and task completion.
```

Production behavior must not depend on benchmark case IDs, task slugs, English
keyword routing, arbitrary public-state string collisions, or witness-shaped DOM
appearance rules.

## Shared causal model

1. Set reduction is currently advisory: unresolved reductions collapse to an
   empty admitted-target tuple, which Catalog interprets as no filtering.
2. Set membership and effect obligations are reconstructed from a bounded model
   projection/history rather than owned by Runtime state.
3. Raw task prose is independently reinterpreted by Catalog and Vision routing.
4. BrowserGym color, repeated-leaf, and lattice observations are projected as
   task-ready facts without an explicit evidence-demand/admission boundary.
5. Fixed witnesses cover the successful shape but do not exercise paraphrase,
   distractor, zero-match, long-set, predicate-flip, or provider-conflict cases.
6. Live evidence at `1f32836` showed that typed establishment remained advisory:
   the policy could select a raw E-ref before any Runtime objective existed, so
   persistent membership and completion gates were never activated.

The authority invariant under repair is:

```text
semantic control enabled AND no admitted typed objective
=> zero effectful dispatch
```

Repeated live reopenings show that this invariant is necessary but not sufficient.
The remaining failures share one broader cause: semantic intent is admitted only
for entities already present in one observation, while provider recovery, future
selector resolution, derived values, scope enumeration, visual classification,
and task-semantic validation have separate or missing owners.  The bounded
contract under repair is therefore:

```text
Task semantic proposal
  -> independent semantic admission
  -> persistent typed objective/step/value plan
  -> fresh-observation selector resolution
  -> Runtime-owned candidate/value evidence obligations
  -> current ActionSpace + binding admission
  -> effect verification
  -> typed transition or fail-closed return to Agent
```

Provider recovery has exactly one owner per logical model request.  A provider
attempt receipt must distinguish a network dispatch from a local circuit
short-circuit.  Scope coverage is owned by a scope enumerator, never by a model
classifier.  Visual predicate providers classify a frozen candidate universe but
do not create action authority or declare completeness.

Entity selection now has one lifecycle independent of evidence modality:

```text
typed predicate + scope
  -> ScopeEnumerator candidate universe
  -> structural / derived / visual leaf evidence
  -> three-valued resolution
  -> unique current entity
  -> current ActionSpace and binding
```

Sequence steps, aggregate destinations and ordinary entity selection use this
same lifecycle. Vision changes the candidate/evidence source, not execution
authority.

## Work plan

| Step | Status | Change | Exit evidence |
|---|---|---|---|
| A | completed | Add explicit fail-closed set Catalog directive | Empty allowlist now means zero effectful actions; no-objective is represented separately |
| B | completed | Add Runtime-owned persistent set-objective state and typed transitions | More than 12 members, predicate flip, identity reorder, new candidates and E-ref renumbering preserve obligations |
| C | superseded/deleted | Remove typed objective establishment from action decisions | Canonical TaskPlan is now the only producer; Catalog and Vision do not parse task prose |
| D | completed | Introduce typed evidence obligations and demote visual routing | Set reducer projects evidence needs; visual acquisition routes typed needs derived from current facts |
| E | completed | Remove task-relative fields and witness-shaped provider publication | Deleted task predicate projection, keyword gate, universal parser and repeated-leaf exact-count scanner; color is generic `appearance.color_family` evidence |
| F | completed | Add property/metamorphic and integration tests | Capacity, missing fact, zero match, actionability, new candidate, history independence and de-specialization redlines pass |
| G | completed | Run focused suite, full suite, and real five-case regression gate | Full suite `2410 passed, 24 skipped`; live run `f57f758` completed all five with 3 successes and 2 typed provider-unavailable outcomes |
| H | superseded/deleted | Replace action-loop semantic ingress with pre-loop TaskSpec/TaskPlan admission | Without an admitted plan, semantic execution dispatches zero actions; the action loop has no objective-construction mode |
| I | superseded/deleted | Move public-fact selection out of action tools | The planner's discriminated execution transport maps once into typed `StepSpec.execution`; no exact-value action-tool enums remain |
| J | in_progress | Re-run the five live witnesses and held-out semantic-control cases | Grid, quantified shades, and aggregate value-entry witnesses completed; both pie witnesses established/executed their first objective then hit provider unavailable during successor ingress |
| K | superseded/deleted | Delete grounded objective transport | Grounded commands carry only current action/control choices; quantifiers, predicates and aggregates exist only in planner transport and admitted plan data |
| L | completed | Auto-advance only reducer-authorized singleton member continuations | No policy inference occurs for `execute_objective`; action ID and parameters remain Runtime-owned |
| M | completed | Make ProviderCallOrchestrator the sole transient recovery owner when enabled and expose attempt origin | Real `503 -> 200` integration emits two network attempts and one accepted logical response; quota/auth remains fail-closed |
| N | completed/replaced | Represent future work as dependent canonical TaskPlan steps | Each active `StepSpec.execution` retains a typed selector, never an E-ref; every fresh observation rebuilds selector resolution and current binding authority |
| O | completed | Add Runtime-owned AggregateObjective and value provenance | COUNT/SUM/MIN/MAX and filtered aggregates derive values only after complete source evidence; partial/unknown inputs cannot dispatch destination writes |
| P | completed | Close bounded compound predicate transport and typed comparisons | And/Or/Not plus Compare reach the Runtime without prose parsing or witness branches; unsupported depth/width/operators fail typed |
| Q | completed | Replace current-viewport/same-role candidate lists with ScopeEnumerator-owned universes | Snapshot viewport closure is domain-aware; larger scopes require an environment-owned enumerator and otherwise fail closed |
| R | completed | Wire VisualPredicateClassifier through evidence obligations | Set members, aggregate members/destinations and sequence selectors share visual-leaf classification without granting completeness or bindings |
| S | superseded/deleted from action policy | Use canonical intake semantic audit and TaskPlan admission | The action policy no longer owns an optional objective validator or any semantic installation path |
| T | in_progress | Run property/model/integration, held-out and real benchmark convergence gates | After authority cleanup, Ruff and full suite pass (`2418 passed, 27 skipped`); fresh real benchmark evidence remains required |
| U | completed | Remove the duplicate `TaskProgram` planner and its schema-repair path | Four public commits were reverted with audit-preserving revert commits; no TaskProgram source/test remains |
| V | completed | Publish one executable owner/producer/consumer/deletion map for task semantics through completion | `docs/task-execution-authority-map.md` names every owner and required deletion; the duplicate target TaskPlan was removed |
| W | completed | Migrate set/entity/aggregate semantics into the selected canonical task/frontier owner | executable semantics live directly on canonical `StepSpec`; one active step materializes the single `active_step_execution` state |
| X | implementation_completed_verification_open | Cut over callers and delete displaced contracts, tools, schemas, tests and docs | Dynamic objective tools/decisions/action payloads, parallel execution table, set-specific control projection and embedded sequence ingress are deleted |
| Y | in_progress | Replace schema-patch acceptance with authority/state-machine/boundary properties | CI now requires zero semantic constructors in action model policy and direct plan-step materialization; broader held-out/live gates remain |
| Z | completed | Remove projection-to-objective roundtrips and dynamic objective-establishment decisions | Runtime materializes current execution state from the admitted plan step; action policy returns only current action/control decisions |

## Archived pre-cutover live evidence

Run: `docs/evidence/runs/m4-6-e-semantic-tools-zhipu-f57f758/`

- `grid-coordinate`: success; typed coordinate objective selected E24 and used structural identity execution.
- `click-shades`: success; five distinct blue members settled, followed by a separately admitted Submit objective.
- `visual-addition`: success; parameterized fill objective followed by a separately admitted Submit objective.
- both pie witnesses: first `+` objective established and executed correctly; successor ingress ended with typed provider-unavailable before the visible `0` objective could be admitted.
- No point grounder or visual binding obtained execution authority.

This evidence was produced by the deleted dynamic-objective path. It remains a
historical diagnostic witness and is not acceptance evidence for the current
TaskSpec/TaskPlan cutover. Fresh live revalidation is required.

## Active implementation scope

This convergence now includes provider recovery ownership, future-resolvable
selector sequences, aggregate provenance, multi-scope universe ownership, bounded
normalized compound predicates/comparisons, production visual classification,
and independent semantic admission.  None may be simulated with task names,
prose keywords, candidate-count heuristics, singleton-action semantic guesses, or
benchmark-specific branches.

## Falsifiable exit criteria

- One transient owner per logical provider call; receipts reconcile logical,
  network, local-circuit, schema-repair, and fallback counts.
- Every automated physical action is authorized by an admitted current step,
  freshly resolved selector, current binding, and current ActionSpace.
- Future steps contain selectors and postconditions, never future identities or
  coordinates; unsupported or ambiguous resolution returns a typed outcome.
- Aggregate destination values carry a digest of a complete candidate universe,
  per-member extracted values, operator, format, and evaluator evidence.
- Compound predicates and comparison operators are bounded, typed, and
  three-valued; unknown is never silently false.
- Scope completeness has one Runtime owner and remains separate from predicate
  classification and actionability.
- Visual classification is called only for unresolved visual leaves and cannot
  create bindings, coordinates, or completeness claims.
- Semantic admission rejects under-specified, contradicted, authority-expanding,
  or unsupported proposals before effectful dispatch.
- Generated/held-out dynamic menus, compound predicates, mixed scopes,
  aggregates, visual-only concepts, provider failure/recovery, and stale-state
  transitions pass without adding case-shaped production branches.
- The real five-case run is rerun and recorded, but is regression evidence rather
  than the sole closure proof.

## Explicit non-goals

- No event-sourcing framework or generalized workflow platform.
- No replacement of BrowserGym/Playwright DOM execution authority.
- No point-grounding mainline.
- No attempt to prove open-world absolute completeness.
- No case-by-case apple/color/grid/task-slug branches.

## Files changed

- `task/set_objective_state.py` owns persistent membership, effects, evidence
  obligations, capacity and typed failure.
- `agent/state.py`, `agent/decisions.py`, `agent/decision_control.py` admit and
  advance typed set semantics without reconstructing history.
- `model_boundary/context*.py`, `model_policy/set_objective_catalog.py`, and
  `model_policy/grounded_tool_catalog.py` project and enforce explicit control
  directives, generic objective tools and bounded E-ref assessment batches.
- `world/vision_escalation.py` derives/routes typed current-evidence needs and
  no longer reads task prose.
- BrowserGym backend/projection removes repeated-leaf exact-count promotion and
  task-relative predicate fields; regular lattice remains a task-independent
  fail-closed evidence provider.
- Architecture, state-machine, held-out and integration regressions are under
  `tests/architecture/` and the focused set/grounding suites.
