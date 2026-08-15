# Actor World Snapshot Convergence Design

> **Status:** single-source structure implemented; multi-source correspondence and dedup convergence open; live not run
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

The later multi-source audit exposes a separate boundary defect. Source
envelopes and source-local structures are retained, but the snapshot structure
renderer does not consistently apply the fusion-accepted source-to-canonical
correspondence. A corresponded structure node can therefore retain its place
in a source tree while losing the canonical entity's E-ref, facts and state.
The accepted `_canonical_maps()` result is currently not stored on
`WorldObservation`, so snapshot helpers reconstruct different subsets of it;
the fusion result sidecar and partly canonicalized source media do not provide
a single downstream identity owner.
Concatenating one complete forest per source would also repeat the same entity
when DOM, AX and visual providers agree. This document remains open for that
multi-source convergence even though the single-BrowserGym-source path is
implemented.

## SOTA alignment

BrowserGym exposes minimally altered DOM and AX trees, element-wise identifiers,
rendering attributes, and an aligned screenshot, leaving structure-preserving
filtering and formatting to the agent. AgentLab/WorkArena text agents retain
AX/HTML hierarchy and identifiers; their MiniWoB configuration benefits from
both HTML and AX. Mind2Web prunes large pages but retains each candidate's tag,
text, salient attributes, and parent/child context. UFO combines native UIA
control data with screenshots and explicitly re-annotates a smaller control set
when the full set becomes cluttered. OSWorld reports that screenshot, a11y and
SoM combinations are model-dependent and can add noise at high density.
OmniParser shows that established OCR/detection/caption models can provide
structured visual fallback when native structure is absent.

The common invariant is not “send every representation.” Runtime retains the
source observations and their lineage, aligns them to one current canonical
world, and sends the Actor a bounded view in which an actionable handle remains
joined to the structure that explains it. Agreeing DOM/AX/UIA/OCR/visual claims
are coalesced; novel or conflicting claims remain visible with provenance.
Tool availability does not delete or duplicate the object's world
representation.

Primary references:

- BrowserGym Ecosystem, TMLR 2025: <https://arxiv.org/abs/2412.05467>
- WorkArena / BrowserGym, ICML 2024: <https://proceedings.mlr.press/v235/drouin24a.html>
- Mind2Web, NeurIPS 2023: <https://arxiv.org/abs/2306.06070>
- UFO, NAACL 2025: <https://aclanthology.org/2025.naacl-long.26/>
- OSWorld, NeurIPS 2024: <https://arxiv.org/abs/2404.07972>
- OmniParser: <https://arxiv.org/abs/2408.00203>

## Reuse boundary

The repository does not implement source acquisition engines already supplied
by maintained open-source projects. BrowserGym/Playwright remain responsible
for browser DOM/AX extraction, iframe linkage, bounding boxes, screenshots and
browser actions. An admitted desktop surface should wrap pywinauto/UIA or the
platform accessibility API. Visual-only coverage should use a replaceable
OmniParser-compatible/OCR provider rather than a repository-owned detector.

Project code owns only the thin adapters, current identity/correspondence
acceptance, provenance/conflict-preserving fusion, ActionSpace authority and
bounded Actor projection. No DOM parser, AX merger, layout engine, OCR engine,
SoM renderer, device automation framework, graph database or parallel fusion
pipeline is introduced without a demonstrated upstream gap.

## Authority and dataflow

```text
SurfaceAdapter
  -> SurfaceObservation(s)                    source-local envelopes/lenses
  -> WorldFusion                              sole alignment/acceptance boundary
  -> WorldObservation                         authoritative canonical observed truth
  -> bounded internal ModelWorldView          ContextBuilder implementation input
  -> ActorWorldSnapshot                       sole Actor epistemic projection
       - one public node per retained canonical entity
       - primary structure plus novel complementary context
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
  -> ProviderCallNormalizer                    bounded wire/equivalence reconciliation;
                                                no world or snapshot read
  -> exact resolver                            private table only
  -> admission                                 still-current ActionSpace only
```

`ActorWorldSnapshot` answers what is currently observed. `ToolSpec` answers
what is currently callable. They share only current, observation-local public
refs. Neither owner prunes, derives, validates, or repairs the other.

All identities inside a `SurfaceObservation` remain source-local. `WorldFusion`
materializes its accepted mapping once as
`WorldObservation.entity_source_links`; every canonical fact/relation/media
view and the snapshot renderer consumes that link set. The old fusion-result
provenance sidecar becomes derived or is deleted. The snapshot binder never
reconstructs explicit correspondence, collision fallback or modality-specific
identity rules.

Maps, coverage and manifests use unique `source_observation_id` keys; `surface`
is only an adapter/capability attribute. Every retained source target receives
one typed link disposition (accepted equivalence, unmatched allocation,
rejected-proposal allocation, or conflicted-proposal allocation) with basis,
evidence and reason. Non-equivalence dispositions retain a distinct canonical
entity. Predicate acceptance is owned by the immutable fusion policy and is
source-permutation invariant; input order cannot select role, label or state.

## Snapshot contract

The snapshot is a disposable, bounded current-turn value. Internally it is a
graph so non-tree relations and multiple source lenses remain representable.
Its primary Actor rendering is a canonical ordered forest with compact source
lineage:

```json
{
  "snapshot_id": "snapshot:current",
  "documents": [
    {
      "source_refs": ["S1", "S2"],
      "modality": "structural",
      "roots": [
        {
          "ref": "E3",
          "role": "group",
          "label": "",
          "state": {},
          "facts": [],
          "source_refs": ["S1", "S2"],
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
7. Snapshot refs cannot authorize an action. A ref can participate in bounded
   call reconciliation only when the same value is already an emitted current
   tool selector or compiler-retained singleton reconciliation value; the
   reconciled exact call must still enter the private resolver and admission.
8. A source reports inventory coverage, rendering coverage, freshness, and
   semantic interpretation separately. Inventory completeness never means task
   semantic sufficiency.
9. Media belongs to the same snapshot and records whether it is available and
   attached. Bounding correspondence is advisory evidence only.
10. Traversal and byte limits fail closed with explicit truncation; retained
    action targets are pinned without deleting or rewriting their semantics.
11. One canonical entity appears at most once in Actor content even when
    several sources observe it; agreeing facts/relations appear once with
    aggregated evidence refs.
12. Every source-local target, structure semantic link, relation endpoint and
    media region uses the same fusion-accepted `entity_source_links`. Every
    retained source target has exactly one link. Unmatched content remains
    explicitly unmatched rather than receiving a guessed E-ref.
13. Complementary source structure is rendered only when it adds novel
    context, conflict, uncertainty or an unmatched entity. A source manifest
    and node `source_refs` retain agreeing lineage without repeating the full
    node/tree.

The current implementation keeps the public AX document separately from
semantic targets inside `SurfaceObservation`. Structure-only nodes receive no
binding and therefore cannot enter `ActionSpace`; semantic nodes carry an
explicit link to the current target and share its call-local E-ref in the Actor
snapshot. Other retained context nodes use non-callable N-refs. Each document
reports retained/total node counts and truthful truncation.

## Multi-source graph rendering

The model boundary must not expose the current flat `entities + facts +
relation strings` workspace or concatenate complete DOM, AX, OCR, SoM and tool
entity lists. ContextBuilder emits each retained canonical entity once, merges
accepted public facts and relations into that node, and aggregates source
evidence refs.

Source-native forests remain conserved inside `SurfaceObservation`. For Actor
rendering, `StructuralLensSelectionPolicy` selects one primary occurrence by
declared provenance/assurance, complete coverage, retained ancestor closure and
finally stable source-observation ID. Its ancestor closure and child order are
retained. Other lenses contribute only a canonical edge absent from the
primary, conflict/uncertainty, an unmatched entity, or ancestors required to
explain one of those. Repeated canonical nodes/edges/labels and alternate
source-only context are not novel; non-primary source-only context requires
explicit bounded lens widening. Non-tree relations
remain typed adjacent relations. If a parent is outside the bounded page, the
child becomes a page root with an explicit external-parent marker. Cycles and
ambiguous parentage fail typed rather than being guessed.

Equal canonical facts/relations from multiple sources render once with all
evidence refs. Conflicting values render once as bounded alternatives and do
not become duplicate entities. OCR/icon captions identical to a native label
are suppressed; novel or conflicting visual claims retain derived/model
provenance. Each capture is attached once, and any SoM overlay uses the same
current refs rather than introducing a second numbered entity vocabulary.
Raw/annotated/crop variants retain one upstream capture-group identity and
declared coordinate space; regions align only within that space or through an
accepted explicit transform. The provider mode selects one primary full-frame
variant rather than sending raw and annotated duplicates by default.

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
- a source correspondence rewrites target, structure, fact, relation, binding,
  destination and media-region endpoints consistently;
- same-surface multiple source instances keep distinct maps/coverage, and
  permuting source input leaves canonical values/conflicts/Actor output equal;
- invalid or conflicting alignment proposals retain distinct canonical
  entities with typed reasons rather than being dropped or guessed equal;
- A.1: two agreeing sources emit one Actor entity node carrying both source
  refs, without claiming that repeated fact/relation rows are already migrated;
- Step 15: agreeing fact/relation rows become one canonical claim carrying all
  evidence refs, with no projection-only dedup owner left behind;
- conflicting sources emit one entity with bounded typed alternatives;
- complementary source forests do not duplicate canonical nodes, while novel
  context and source-local parent/child order survive bounding;
- primary lens selection and complementary novelty are deterministic under
  equivalent source permutations and pagination;
- stale snapshot refs remain zero-dispatch;
- normalizer, resolver and admission do not read the snapshot;
- silent cross-tool reconciliation requires one current row and an identical
  authority-equivalence digest; ambiguous or non-equivalent cases produce a
  bounded model repair with zero dispatch;
- transition/history authority remains singular;
- structured-output failures retain bounded violation paths;
- existing singleton, semantic-grid, destination, and no-regression tests pass;
- held-out nested DOM and non-color duplicate-class cases pass without production
  branches.

Local implementation evidence at 2026-08-14: focused grounded-tool,
BrowserGym-world, vision-acquisition, observation-lifecycle, lattice, legacy
serialization, and model-policy tests pass. The later Wave-A full suite passes
with `2534 passed, 27 skipped`; Ruff and `mypy src` pass. That evidence covers
the current single-source rendering and does not prove the new multi-source
correspondence/dedup properties above. Per user direction, no live provider or
benchmark run was performed.
