# M4.6-E Set-objective de-specialization convergence plan

Date: 2026-08-13

Status: `ARCHITECTURE_CONVERGED / IMPLEMENTED_NOT_LIVE_VERIFIED`

## 2026-08-13 architecture-first correction

The repository-wide review found two independent products and one accidental
duplicate inside the target loop:

1. the retained workflow `TaskSpec -> TaskPlan<StepSpec> -> Coordinator` chain;
2. the target GUI `TaskGoal -> observe -> ActionSpace -> AgentContext ->
   AgentDecision -> AgentLoop` chain;
3. an accidental target-loop `TaskFrontier / VerifiedTaskState /
   RequirementHypothesis / AgentDecisionPackage` semantic chain.

The third chain is deleted, not adapted. The target AgentLoop does not consume
workflow TaskSpec/TaskPlan and does not require an exact resource or GUI target
before its first observation. Sequence, set, and aggregate semantics now enter
only as one post-observation `EstablishLocalObjective` decision, share one
`local_objective_state` slot, and resolve their selectors against current world
evidence.

Provider adapters parse a response once into `AgentDecision`. The previous
typed-decision -> JSON -> second policy parse and internal predicate -> wire
predicate reverse codecs are removed. Projection schemas present current state;
they never become an authority or reconstruction path.

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

The repeated reopenings came from duplicate semantic owners and lossy boundary
round trips, not independent benchmark defects:

1. workflow planning contracts were imported into a GUI loop whose identities
   do not exist until observation;
2. frontier/hypothesis/objective-package state duplicated LocalObjective and
   made semantic ingress optional or pre-policy;
3. provider adapters resolved a tool to a typed package, serialized it, and a
   second policy parser interpreted it again;
4. documentation still named the deleted chain as current authority, inviting
   the same coupling to be reintroduced;
5. fixed witnesses did not expose these owner/projection defects until live
   provider and successor-observation paths exercised them.

The authority invariants are:

```text
no current LocalObjective
=> zero effectful dispatch

LocalObjective established
=> every authorized entity/action is resolved from the current observation

fresh observation
=> old entity/action/E-ref/binding resolution is stale and recomputed
```

The bounded contract is:

```text
current AgentContext
  -> one typed LocalObjective decision
  -> persistent typed local objective state
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
| C | implemented, verification open | Remove multiple objective-specific action decisions | Target AgentLoop has one rolling LocalObjective contract; TaskPlan is not its producer |
| D | completed | Introduce typed evidence obligations and demote visual routing | Set reducer projects evidence needs; visual acquisition routes typed needs derived from current facts |
| E | completed | Remove task-relative fields and witness-shaped provider publication | Deleted task predicate projection, keyword gate, universal parser and repeated-leaf exact-count scanner; color is generic `appearance.color_family` evidence |
| F | completed | Add property/metamorphic and integration tests | Capacity, missing fact, zero match, actionability, new candidate, history independence and de-specialization redlines pass |
| G | completed | Run focused suite, full suite, and real five-case regression gate | Full suite `2410 passed, 24 skipped`; live run `f57f758` completed all five with 3 successes and 2 typed provider-unavailable outcomes |
| H | deleted as invalid | Replace action-loop semantic ingress with pre-loop TaskSpec/TaskPlan admission | Removed: workflow exact-resource authority cannot precede GUI discovery in AgentLoop |
| I | implemented, verification open | Put selector/predicate semantics behind one LocalObjective decision contract | AgentContext remains disposable; no fact-specific schema owner or projection roundtrip |
| J | in_progress | Re-run the five live witnesses and held-out semantic-control cases | Grid, quantified shades, and aggregate value-entry witnesses completed; both pie witnesses established/executed their first objective then hit provider unavailable during successor ingress |
| K | implemented, verification open | Converge grounded objective transport on the single LocalObjective contract | Grounded policy exposes objective establishment before effectful actions; Runtime assigns objective/scope/step IDs |
| L | reopened | Auto-advance only reducer-authorized singleton member continuations | Reconnect after LocalObjective admission; action ID and parameters remain Runtime-owned |
| M | completed | Make ProviderCallOrchestrator the sole transient recovery owner when enabled and expose attempt origin | Real `503 -> 200` integration emits two network attempts and one accepted logical response; quota/auth remains fail-closed |
| N | implemented, verification open | Keep future-resolvable selectors in rolling LocalObjective state | Every fresh observation rebuilds selector resolution and current binding authority; no future E-ref or DOM ID |
| O | completed | Add Runtime-owned AggregateObjective and value provenance | COUNT/SUM/MIN/MAX and filtered aggregates derive values only after complete source evidence; partial/unknown inputs cannot dispatch destination writes |
| P | completed | Close bounded compound predicate transport and typed comparisons | And/Or/Not plus Compare reach the Runtime without prose parsing or witness branches; unsupported depth/width/operators fail typed |
| Q | completed | Replace current-viewport/same-role candidate lists with ScopeEnumerator-owned universes | Snapshot viewport closure is domain-aware; larger scopes require an environment-owned enumerator and otherwise fail closed |
| R | completed | Wire VisualPredicateClassifier through evidence obligations | Set members, aggregate members/destinations and sequence selectors share visual-leaf classification without granting completeness or bindings |
| S | deleted as invalid for AgentLoop | Use workflow intake semantic audit and TaskPlan admission | AgentLoop no longer invokes workflow intake/planning before the first policy turn |
| T | in_progress | Run property/model/integration, held-out and real benchmark convergence gates | Current architecture suite `2383 passed, 24 skipped`; fresh live evidence is still required |
| U | completed | Remove the duplicate `TaskProgram` planner and its schema-repair path | Four public commits were reverted with audit-preserving revert commits; no TaskProgram source/test remains |
| V | completed | Publish one executable owner/producer/consumer/deletion map | The map now separates target AgentLoop from the transactional TaskSpec/TaskPlan workflow |
| W | completed for deterministic architecture gate | Converge set/entity/aggregate semantics into one LocalObjective lifecycle | One `local_objective_state` reducer slot; no TaskPlan dependency |
| X | completed | Delete displaced contracts, tools, projections, tests and docs | Pre-loop planner/frontier/hypothesis/package paths and their current-authority documentation are deleted or retired pointers |
| Y | completed for deterministic architecture gate | Replace schema-patch acceptance with authority/state-machine/boundary properties | CI forbids pre-observation target/frontier authority, duplicate state slots, reverse objective codecs and policy-level raw-response parsing; live gate remains separate |
| Z | completed | Remove projection-to-objective and decision roundtrips | LocalObjective is admitted from the current typed decision; every provider adapter returns `ResolvedModelDecision`; projections retain no reconstruction authority |

## Archived pre-cutover live evidence

Run: `docs/evidence/runs/m4-6-e-semantic-tools-zhipu-f57f758/`

- `grid-coordinate`: success; typed coordinate objective selected E24 and used structural identity execution.
- `click-shades`: success; five distinct blue members settled, followed by a separately admitted Submit objective.
- `visual-addition`: success; parameterized fill objective followed by a separately admitted Submit objective.
- both pie witnesses: first `+` objective established and executed correctly; successor ingress ended with typed provider-unavailable before the visible `0` objective could be admitted.
- No point grounder or visual binding obtained execution authority.

This evidence was produced by the deleted dynamic-objective path. It remains a
historical diagnostic witness and is not acceptance evidence for the current
LocalObjective convergence. Fresh live revalidation is required.

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

- `task/local_objective.py` is the single variant-dispatch owner for establish,
  refresh, completion, action authorization and action parameters.
- `task/set_objective_state.py` owns persistent membership, effects, evidence
  obligations, capacity and typed failure.
- `agent/state.py`, `agent/decisions.py`, `agent/decision_control.py` admit and
  advance the one LocalObjective lifecycle without reconstructing history.
- `model_policy/spec.py` owns the one typed LocalObjective codec; grounded tools
  project that schema directly instead of maintaining a second schema.
- Deleted AgentLoop workflow-plan preparation, execution-control projection and
  the unused open-dict LocalObjective hint contract.
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
