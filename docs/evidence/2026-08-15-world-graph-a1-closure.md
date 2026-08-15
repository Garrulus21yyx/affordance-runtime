# Wave A.1 multi-source observed-world graph closure

Date: 2026-08-15

Status: `WORLD_GRAPH_A.1_REPAIR_IMPLEMENTED / PROPERTY_VERIFIED /
INDEPENDENT_FRESH_CONTEXT_REVIEW_PASSED / A.1_CLOSURE_ADMITTED /
A.2_ADMITTED_NOT_STARTED / STATEFACT_CUTOVER_PARTIAL /
ACTIVATE_EFFECT_AUTHORITY_OPEN / NEW_INTERACTION_ACTIONS_NOT_ADMITTED /
LIVE_NOT_RUN`

> This record preserves what the original offline gate established. A fresh
> independent audit subsequently produced counterexamples outside that gate,
> so the original `WORLD_GRAPH_A.1_COMPLETE` claim was withdrawn. The repair
> evidence and later independent closure attestation below supersede that
> original claim without rewriting its history.

## Implemented scope

The existing owner chain is now closed without adding a second world model:

```text
SurfaceAdapter
  -> immutable source-local SurfaceObservation
  -> WorldFusion
  -> one canonical WorldObservation
  -> ActorWorldSnapshot / independent ActionSpace
```

`source_observation_id` is the source-instance key for manifests, coverage,
fusion maps, currentness, ordering and source membership. Surface, modality,
profile, acquisition root and coverage remain immutable attributes of that
instance. Duplicate source IDs, phantom manifests and mixed source/canonical
envelopes fail closed.

Adapters/providers emit only `EntityAlignmentProposal` values between two
`SourceEntityEndpoint`s. The intended contract is that `WorldFusion` decides
each proposal, accepts legal equivalence components, isolates
rejected/conflicted endpoints, deterministically allocates canonical IDs, and
emits exactly one `EntitySourceLink` per retained source target. The audit found
that the implementation currently has no proposal-level decision value and can
aggregate rejected proposal evidence/confidence into an accepted endpoint
link. The link collection remains the intended sole rewrite map, but its
lineage cannot be treated as closed until repaired.

The immutable fusion predicate/profile registry applies symmetric consensus to
role, label and currently supported state predicates. Unknown profiles or
families fail closed; disagreement produces typed conflicts and removes the
disputed ordinary state/fact value. This slice does not coalesce equal fact rows
because that remains Step 15 scope.

BrowserGym structured, visual and disambiguation producers retain source-local
identities. Canonical media preserves upstream capture group, variant,
dimensions and coordinate space. Variants of one capture are grouped
deterministically for grounding, and endpoint alignment across distinct
coordinate spaces is rejected unless a future typed transform contract is
explicitly admitted.

The Actor projection consumes `entity_source_links`, emits at most one E-ref
per canonical entity, aggregates `source_refs`, and renders one bounded primary
lens plus only mechanically novel, conflicted or unmatched complementary
context. Native forest child order and ancestor closure are preserved under
bounds, and retained/total/truncation metadata reports the actual lens payload.

## Displaced paths

The following old authorities are removed rather than shimmed:

- adapter-authored `EntityCorrespondence` with a premature canonical target;
- `FusedEntityProvenance` and `WorldFusionResult.entity_provenance` sidecar;
- surface-keyed world coverage and fusion/currentness maps;
- Actor correspondence and collision-fallback reconstruction;
- source-envelope media rewritten into the canonical identity domain;
- provider-side regrouping or identity fusion.

Architecture redlines prevent these owners from returning and prevent action or
provider packages from importing observation-alignment authority.

## Property evidence

Unit, integration, conformance and architecture properties verify:

- source permutation invariance for links, conflicts and Actor payload;
- simultaneous same-surface source instances without manifest, coverage or lens loss;
- one link per retained source target and deterministic complete-component IDs;
- accepted equivalence deduplication plus typed unmatched, rejected and conflicted retention;
- one accepted map for fact, binding, destination, relation, structure and media rewrites;
- rejection of mixed domains, duplicate sources and undeclared profiles;
- canonical E-ref/state/fact retention for corresponded structure nodes;
- one Actor entity node with aggregated source refs, ancestor closure and native child order;
- complementary lenses that do not repeat the complete primary tree;
- capture variant selection and coordinate-space rejection independent of source order;
- truthful projection bounds/truncation and provider serialization without re-fusion;
- unchanged ActionSpace, binding, flat tool schema, currentness and dispatch behavior;
- no newly produced interaction family.

## Verification

- focused world graph, identity, structure, media and Actor tests: passed;
- source permutation/property tests: passed;
- architecture redlines and affected surface conformance: passed;
- full pytest: `1621 passed, 27 skipped`;
- Ruff (`ruff check src tests`): passed;
- repository-standard mypy (`mypy src`): passed, 335 source files;
- `git diff --check`: passed;
- clean isolated wheel build: passed;
- wheel installed outside the worktree with declared dependencies available;
  new graph contracts import successfully and removed
  `EntityCorrespondence` / `FusedEntityProvenance` exports are absent.

No live benchmark was run.

## Reopening evidence

The independent audit falsified five distinct boundary properties:

1. a valid and an invalid proposal involving the same endpoint can yield an
   accepted link whose evidence/confidence includes the invalid proposal;
2. endpoint-level link dispositions cannot represent exactly one result for
   every proposal;
3. `WorldObservation` construction accepts forged link sets including
   within-source many-to-one allocation, wrong acquisition roots, and
   authority-inconsistent accepted-link evidence;
4. projecting multiple sources that contain targets but no structure can fail
   the Actor forest retained-node invariant because a per-document fallback is
   compared with a global target count;
5. a supported identity-bearing relation that references an unknown
   source-local endpoint raises a bare `ValueError` instead of returning typed
   `FusionStatus.INCONCLUSIVE` with `unresolved_source_relation`.

These counterexamples share an incomplete acceptance boundary, but they do not
have one implementation owner. The repair therefore preserves the existing
chain and assigns the defects to fusion adjudication, fusion output contracts,
`WorldObservation` construction, Actor projection, and source/fusion
normalization respectively. The executable repair contract is in
[the A.1 plan](../plans/2026-08-15-world-graph-a1.md).

## Closure repair evidence

The repair separates proposal outcome from final allocation. Fusion emits one
immutable `EntityAlignmentDecision` for every retained proposal, forms graph
edges only from accepted decisions, then allocates canonical components and
emits one allocation-only `EntitySourceLink` for each retained endpoint.
Rejected/conflicted evidence and confidence remain solely on their proposal
decision and cannot enter an accepted component or link.

`WorldObservation` now rejects missing/phantom endpoints, uncovered canonical
targets, links to absent targets, within-source many-to-one allocation,
source/link root disagreement, empty or inconsistent equivalent roots,
duplicate/missing decisions, proposal basis/evidence/confidence mismatch,
incoherent disposition/reason pairs, and link components or allocation kinds
inconsistent with accepted decisions. Tests that formerly used
`dataclasses.replace()` to append canonical targets were migrated to modify a
source-local envelope and pass it through `WorldFusion`; no construction
backdoor or compatibility constructor was retained.

Decision semantic truth has one production owner: `WorldFusion`. The
`WorldObservation` constructor validates structural conservation between the
retained proposals, decisions, accepted components and links; it deliberately
does not repeat role, acquisition, endpoint or coordinate-space adjudication.
An architecture redline rejects any other production call site that constructs
`EntityAlignmentDecision` or `WorldObservation`. Consequently, a test-only
caller with direct constructor access can manufacture a structurally coherent
but semantically false rejected decision; that is outside the admitted production
construction boundary and is not claimed to be detected by `WorldObservation`.

The fusion boundary preflights the currently supported identity-bearing
relations (`parent_id`, `child_ids`, `label_for_id`). An unresolved endpoint
returns `FusionStatus.INCONCLUSIVE` with `unresolved_source_relation`; the
general typed relation framework remains Step 15 scope. The Actor fallback now
derives each structure-free document's retained and total counts from that
document's actual nodes.

Current offline verification:

- focused A.1 unit/integration/architecture command: `47 passed`;
- documentation governance: `15 passed`;
- full pytest: `1632 passed, 27 skipped`;
- Ruff: passed;
- repository mypy: passed, 335 source files;
- `git diff --check`: passed;
- live benchmark: not run.

No compatibility read, dual write, shadow link provenance, provider-side
alignment, or second correspondence map remains.

## Independent closure attestation

An independent fresh-context review passed after the repair. It rechecked the
shared causal model and the bounded A.1 exit properties: proposal-level outcome
conservation, accepted-only component lineage, accepted-world construction
invariants, deterministic typed failure for unresolved supported relations,
per-document structure-free Actor accounting, owner uniqueness, and the absence
of compatibility identity paths. No new production branch was required for a
held-out case.

The admitted status is therefore
`INDEPENDENT_FRESH_CONTEXT_REVIEW_PASSED / A.1_CLOSURE_ADMITTED /
A.2_ADMITTED_NOT_STARTED`. The verification commands below are rerun at the
closure commit boundary; live benchmark execution remains explicitly outside
this attestation.

## Remaining boundaries

- `STATEFACT_CUTOVER_PARTIAL`: this slice does not complete facts-only state or
  Step 15 canonical fact/relation evidence coalescing.
- `ACTIVATE_EFFECT_AUTHORITY_OPEN`: activate false-positive authority remains a
  later Wave B issue.
- `NEW_INTERACTION_ACTIONS_NOT_ADMITTED`: no scroll, press-key, focus, drag or
  hover producer, binding or tool was added.
- `SemanticDelta`, new benchmark cases, AgentLoop changes, graph databases,
  event stores and alternate Actor projections remain out of scope.
