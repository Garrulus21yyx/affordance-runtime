# M4.6-E Set-objective de-specialization convergence plan

Date: 2026-08-13

Status: `ARCHITECTURE_REOPENED / BOUNDED_WITNESSES_PASS / GENERALIZATION_OPEN`

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

## Work plan

| Step | Status | Change | Exit evidence |
|---|---|---|---|
| A | completed | Add explicit fail-closed set Catalog directive | Empty allowlist now means zero effectful actions; no-objective is represented separately |
| B | completed | Add Runtime-owned persistent set-objective state and typed transitions | More than 12 members, predicate flip, identity reorder, new candidates and E-ref renumbering preserve obligations |
| C | completed | Route set semantics through typed model decisions | Main Agent establishes `FactEquals`/`VisualConcept` objectives explicitly; Catalog and Vision do not parse task prose |
| D | completed | Introduce typed evidence obligations and demote visual routing | Set reducer projects evidence needs; visual acquisition routes typed needs derived from current facts |
| E | completed | Remove task-relative fields and witness-shaped provider publication | Deleted task predicate projection, keyword gate, universal parser and repeated-leaf exact-count scanner; color is generic `appearance.color_family` evidence |
| F | completed | Add property/metamorphic and integration tests | Capacity, missing fact, zero match, actionability, new candidate, history independence and de-specialization redlines pass |
| G | in_progress | Run focused suite, full suite, and real five-case regression gate | Focused gate and full suite (`2398 passed, 27 skipped`) pass; clean-SHA live run remains required before verified closure |

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
