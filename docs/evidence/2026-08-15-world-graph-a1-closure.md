# Wave A.1 multi-source observed-world graph closure

Date: 2026-08-15

Status: `WORLD_GRAPH_A.1_COMPLETE / STATEFACT_CUTOVER_PARTIAL / ACTIVATE_EFFECT_AUTHORITY_OPEN / NEW_INTERACTION_ACTIONS_NOT_ADMITTED / LIVE_NOT_RUN`

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
`SourceEntityEndpoint`s. `WorldFusion` validates proposals, accepts legal
equivalence components, isolates rejected/conflicted endpoints,
deterministically allocates canonical IDs from the sorted complete component,
and emits exactly one `EntitySourceLink` per retained source target. That link
collection is the only mapping used to rewrite targets, facts, bindings,
destinations, relations, structure semantic links, media regions and source
membership.

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

## Remaining boundaries

- `STATEFACT_CUTOVER_PARTIAL`: this slice does not complete facts-only state or
  Step 15 canonical fact/relation evidence coalescing.
- `ACTIVATE_EFFECT_AUTHORITY_OPEN`: activate false-positive authority remains a
  later Wave B issue.
- `NEW_INTERACTION_ACTIONS_NOT_ADMITTED`: no scroll, press-key, focus, drag or
  hover producer, binding or tool was added.
- `SemanticDelta`, new benchmark cases, AgentLoop changes, graph databases,
  event stores and alternate Actor projections remain out of scope.
