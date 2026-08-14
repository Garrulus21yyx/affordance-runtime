# Actor World Snapshot Convergence Design

> **Status:** implemented locally; full static and regression verification passed; live not run
> **Baseline:** `cf20e78de16ce7263f3b2abc7ae1a5665ba888f5`
> **Scope:** existing `activate`, `type_text`, `select_option`, and `read`

## Problem statement

BrowserGym already supplies a structured DOM/AX observation, computed public
state, hierarchy, bounding geometry, and a screenshot aligned to the same
elements. The current grounded Actor boundary destroys that closure: it flattens
the public world into separate entity/fact/relation lists, removes every
actionable entity, removes every fact owned by an action candidate, and then
expects the independently compiled ToolSpec to replace those world facts. An
E-ref fallback ToolSpec only names legal current refs, so the Actor can lose the
mapping from each ref to its public state. Separately, a screenshot already
present in the structural observation is not transportable by the
structure-first profile unless an optional semantic visual provider first
creates a `visual` source.

The seed-7 field trace makes both failures concrete. `click-shades` has five
blue, four red, and three green actionable controls in the closed observation,
but the Actor receives only an undifferentiated E-ref enum. `visual-addition`
has two structurally observable groups containing eight and two blue leaf
nodes, but they are rendered as a flat list of generic E-refs and the aligned
screenshot is withheld.

## SOTA alignment

BrowserGym exposes minimally altered DOM and AX trees, element-wise identifiers,
rendering attributes, and an aligned screenshot, leaving structure-preserving
filtering and formatting to the agent. AgentLab/WorkArena text agents retain
AX/HTML hierarchy and identifiers; their MiniWoB configuration benefits from
both HTML and AX. Mind2Web prunes large pages but retains each candidate's tag,
text, salient attributes, and parent/child context. The common invariant is
that an actionable handle remains joined to the observation that explains the
object. Tool availability does not delete the object's world representation.

Primary references:

- BrowserGym Ecosystem, TMLR 2025: <https://arxiv.org/abs/2412.05467>
- WorkArena / BrowserGym, ICML 2024: <https://proceedings.mlr.press/v235/drouin24a.html>
- Mind2Web, NeurIPS 2023: <https://arxiv.org/abs/2306.06070>

## Authority and dataflow

```text
SurfaceAdapter
  -> WorldObservation                         authoritative observed truth
  -> bounded internal ModelWorldView          ContextBuilder implementation input
  -> ActorWorldSnapshot                       sole Actor epistemic projection
       - structure-preserving public nodes
       - inline public state and evidence
       - source/coverage manifest
       - aligned current media manifest
       - conflicts, uncertainty, traversal
       - canonical transition projections

ActionSpace
  -> closed action candidates
  -> GroundedToolCompiler
  -> public ToolSpec + private resolution      sole executable catalog

ActorWorldSnapshot + ToolSpec
  -> provider binder                           serialization only
  -> Actor
  -> exact resolver                            private table only
  -> admission                                 still-current ActionSpace only
```

`ActorWorldSnapshot` answers what is currently observed. `ToolSpec` answers
what is currently callable. They share only current, observation-local public
refs. Neither owner prunes, derives, validates, or repairs the other.

## Snapshot contract

The snapshot is a disposable, bounded current-turn value. Internally it is a
graph so non-tree relations remain representable. Its primary Actor rendering
is a source-preserving ordered forest:

```json
{
  "snapshot_id": "snapshot:current",
  "documents": [
    {
      "source_ref": "S1",
      "modality": "structural",
      "roots": [
        {
          "ref": "E3",
          "role": "group",
          "label": "",
          "state": {},
          "facts": [],
          "children": []
        }
      ]
    }
  ],
  "sources": [],
  "media": [],
  "conflicts": [],
  "unknowns": [],
  "traversal": null
}
```

Required invariants:

1. Every emitted node ref is unique in the current snapshot.
2. Parent/child order is preserved for every retained structural node.
3. Public role, label, state, and fact evidence are inline with their node.
4. Actionable and non-actionable nodes use the same world representation.
5. No node or fact is removed because a ToolSpec mentions the same ref or
   semantic value.
6. Route data, backend selectors, canonical target IDs, bindings, and action IDs
   never enter the snapshot.
7. Snapshot refs cannot authorize an action. Only exact ToolSpec parameters can
   enter the private resolver.
8. A source reports inventory coverage, rendering coverage, freshness, and
   semantic interpretation separately. Inventory completeness never means task
   semantic sufficiency.
9. Media belongs to the same snapshot and records whether it is available and
   attached. Bounding correspondence is advisory evidence only.
10. Traversal and byte limits fail closed with explicit truncation; retained
    action targets are pinned without deleting or rewriting their semantics.

The current implementation keeps the public AX document separately from
semantic targets inside `SurfaceObservation`. Structure-only nodes receive no
binding and therefore cannot enter `ActionSpace`; semantic nodes carry an
explicit link to the current target and share its call-local E-ref in the Actor
snapshot. Other retained context nodes use non-callable N-refs. Each document
reports retained/total node counts and truthful truncation.

## Structural rendering

The model boundary must not expose the current flat `entities + facts +
relation strings` workspace. ContextBuilder builds one ordered forest from
public parent/child relations and merges public facts into their subject node.
Non-tree relations remain typed adjacent relations. If a parent is outside the
bounded page, the child becomes a page root with an explicit external-parent
marker. Cycles and ambiguous parentage fail typed rather than being guessed.

The internal `ModelWorldView` may remain useful to evaluator and paging
consumers, but it is not a second Actor representation. Only the snapshot is
serialized on the grounded action path.

## Media and observation sources

A raw current screenshot is a BrowserGym observation capability independent of
semantic visual providers. Explicit visual observation attaches that screenshot
as a `visual` source with no targets, facts, bindings, or action authority.
Optional region proposers, disambiguators, predicate classifiers, and point
grounders may add typed public visual evidence, but they do not control whether
the screenshot exists or can be sent to a multimodal Actor.

The structure-first profile therefore has a closed transition:

```text
current structural snapshot + available raw screenshot
  -> Actor chooses observe_visual
  -> fresh snapshot contains structural + visual sources
  -> the aligned screenshot is attached to the next provider request

or

  -> typed visual_source_unavailable / no_information_gain
```

Capture success and Actor-visible evidence gain are distinct facts.

## Temporal context

No new interaction ledger is introduced. `ControlTransition` remains the owner
of decisions, dispatch, effects, and task evaluation. `last_transition` and
verified bounded history are projected against the current grounding index.
Unprovable cross-snapshot continuity is represented as unknown; it is not
guessed and cannot create an action.

## Provider validation telemetry

The provider adapter retains bounded, value-free `StructuredOutputViolation`
facts across original and repair attempts: validation stage, schema version,
violation code, public field path, repair attempted, and repair outcome. Raw
payload values remain absent. This telemetry is independent of world and action
authority.

## Deletions

The grounded Actor path deletes these responsibilities rather than replacing
them with another sidecar:

- binder-owned actionable-entity removal;
- candidate-owned fact removal;
- flat relationship-string reconstruction as the primary environment view;
- tool/world semantic deduplication;
- semantic visual provider as the gate for raw screenshot transport.

It does not add compiler coverage metadata, task-derived collections, a second
candidate projection, a progress ledger, a Submit guard, or benchmark-specific
semantic fields.

## Verification

Properties and representative witnesses must establish:

- E-ref fallback values join to exactly one current world node with all retained
  public state, including duplicate semantic classes;
- semantic ToolSpecs do not cause matching world facts to disappear;
- tree order and parent/child closure survive bounding and paging;
- current raw screenshots can be requested without a semantic visual provider;
- screenshot attachment never creates bindings or legal actions;
- stale snapshot refs remain zero-dispatch;
- resolver and admission do not read the snapshot;
- transition/history authority remains singular;
- structured-output failures retain bounded violation paths;
- existing singleton, semantic-grid, destination, and no-regression tests pass;
- held-out nested DOM and non-color duplicate-class cases pass without production
  branches.

Local implementation evidence at 2026-08-14: focused grounded-tool,
BrowserGym-world, vision-acquisition, observation-lifecycle, lattice, legacy
serialization, and model-policy tests pass; the full suite passes with `2512
passed, 27 skipped`; Ruff passes; `mypy src` passes. Per user direction, no live
provider or benchmark run was performed.
