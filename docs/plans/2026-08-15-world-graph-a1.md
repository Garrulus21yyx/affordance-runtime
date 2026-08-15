# Wave A.1 source-instance owner-spine plan

Status: `WORLD_GRAPH_A.1_REPAIR_IMPLEMENTED / PROPERTY_VERIFIED /
INDEPENDENT_FRESH_CONTEXT_REVIEW_PASSED / A.1_CLOSURE_ADMITTED /
A.2_ADMITTED_NOT_STARTED / STATEFACT_CUTOVER_PARTIAL /
ACTIVATE_EFFECT_AUTHORITY_OPEN / NEW_INTERACTION_ACTIONS_NOT_ADMITTED /
LIVE_NOT_RUN`

Baseline: `codex/migrate-world-interaction-capabilities@3c7e3606a01b6340006d8dfd3683efa9d587f029`

## Constraints

- Preserve the sole `TargetRuntime -> AgentLoop -> AgentRunSession` lifecycle.
- Converge the existing `SurfaceObservation -> WorldFusion -> WorldObservation
  -> ActorWorldSnapshot / ActionSpace` chain.
- Add no second world model, Actor projection, interaction family or live run.
- Leave StateFact facts-only cutover and activate effect authority open.
- Delete displaced APIs and maps; retain no compatibility or dual-write path.

## Owner inventory and decisions

- `world/contracts.py` owns source-local proposal endpoints, source-instance
  manifests, accepted entity links and canonical media.
- `world/fusion.py` is the sole alignment acceptance, canonical allocation,
  predicate conflict and source-to-canonical rewrite owner.
- BrowserGym structured/visual projections produce immutable source-local
  envelopes and proposals only.
- `agent/context/actor_world_snapshot.py` consumes accepted links for source
  membership and source structure lenses; it does not rebuild identity.
- `agent/context/grounding_projection.py` consumes canonical media and selects
  deterministic capture variants without pixel identity matching.
- ActionSpace, route selection and dispatch retain their independent legal
  action contracts, consulting source-instance identity only for currentness.
- Provider serialization consumes the completed Actor snapshot and flat tools;
  it cannot fuse, align or regroup world identity.

## Execution slices

1. Inventory all identity, coverage, structure, media and projection consumers.
2. Replace surface-keyed coverage and premature canonical correspondence with
   typed source-instance manifests, proposals and accepted links.
3. Rebuild fusion around deterministic components and one accepted rewrite map.
4. Migrate BrowserGym producers and evaluation/currentness consumers.
5. Implement the bounded primary/novel Actor lens and canonical media path.
6. Delete displaced exports, reconstruction and provenance authority.
7. Add invariant, property, integration, conformance and architecture gates.
8. Run full offline validation, wheel checks and align status/evidence.

The implementation established the intended owner spine, but an independent
post-closure audit falsified the closure claim. The prior verification did not
cover mixed valid/invalid proposals, forged accepted-world links, unresolved
relation endpoints, or the multi-source structure-free Actor fallback. The
historical result remains recorded in
[the reopened closure record](../evidence/2026-08-15-world-graph-a1-closure.md),
but it is not current closure evidence.

## Closure repair contract

The architecture is retained. The repair must not move all failures into
`WorldFusion`; each boundary keeps one responsibility:

| Defect | Sole owner | Required correction |
|---|---|---|
| rejected proposal evidence contaminates an accepted link | `WorldFusion` | build equivalence components and accepted-link lineage from accepted decisions only |
| one result per proposal is not representable | fusion contracts | add immutable proposal-level `EntityAlignmentDecision` |
| forged or inconsistent links can construct accepted truth | `WorldObservation` | validate complete, injective, acquisition-consistent source-to-canonical allocation |
| multiple sources without structure corrupt Actor forest counts | Actor projector | count retained nodes per document/source fallback, not against global visible targets |
| unresolved identity-bearing relation raises | source normalization / fusion boundary | preflight source-local endpoints and return typed `INCONCLUSIVE` with `unresolved_source_relation` |

Proposal adjudication and final allocation are different values:

```text
EntityAlignmentProposal
  -> exactly one EntityAlignmentDecision(accepted | rejected | conflicted)
  -> accepted decisions only form equivalence components
  -> exactly one EntitySourceLink per retained source endpoint
```

`EntityAlignmentDecision` records the outcome and evidence for one proposed
equivalence. `EntitySourceLink` records only where a source endpoint was
finally allocated (`equivalent` or `independent`). Rejected/conflicted proposal
evidence remains on its decision and must never be presented as support for an
accepted equivalence. The link does not duplicate proposal evidence or
confidence; diagnostics derive accepted lineage from decisions.

`WorldObservation` construction must verify all of the following:

- link endpoints exactly cover retained source targets, with no phantom or
  missing endpoint;
- every canonical target has link coverage and every link names an existing
  canonical target;
- source endpoint allocation is a total function and is injective within one
  source observation;
- endpoints merged as equivalent share the declared non-empty acquisition
  root;
- equivalent allocation is derivable only from accepted decision components,
  while independent allocation cannot masquerade as accepted correspondence.

A.1 closes only the currently supported identity-bearing relation keys:
`parent_id`, `child_ids`, and `label_for_id`. Their source-local endpoints are
prevalidated and rewritten through the one accepted link map. Unknown
endpoints fail closed as a typed fusion result; Step 15 remains the sole slice
that introduces the general typed relation vocabulary and provenance-bearing
`RelationClaim`.

## Repair exit criteria

Closure may be restored only when invariant/property tests prove:

1. every proposal has exactly one decision and every retained endpoint exactly
   one final link;
2. mixing valid and invalid proposals cannot change accepted-component
   evidence, confidence, identity, or canonical allocation;
3. forged, non-injective, wrong-root, phantom, or incomplete link sets cannot
   construct a `WorldObservation`;
4. unresolved supported relation endpoints return typed `INCONCLUSIVE` without
   a bare exception;
5. two or more structure-free sources produce a valid bounded Actor snapshot;
6. source/proposal permutation preserves decisions, links, canonical graph and
   Actor output;
7. existing currentness, ActionSpace, tool, dispatch, media-lineage and
   single-source behavior do not regress.

No new interaction family, StateFact cutover, general relation framework,
`SemanticDelta`, live benchmark, graph database, or alternate projection is
part of this repair.

## Repair implementation record

The repair preserves the original owner spine and now executes this single
identity flow:

```text
EntityAlignmentProposal
  -> one immutable EntityAlignmentDecision
  -> ACCEPTED decisions only form endpoint components
  -> deterministic canonical allocation
  -> one allocation-only EntitySourceLink per retained endpoint
```

`EntityAlignmentDecision` alone retains proposal disposition, basis, evidence,
confidence and reason. `EntitySourceLink` now contains only source endpoint,
canonical endpoint, acquisition root and `EQUIVALENT`/`INDEPENDENT`
allocation; the displaced link disposition/basis/evidence/confidence/reason
path is deleted.

`WorldObservation` construction verifies exact endpoint and canonical target
coverage, total and within-source-injective allocation, link/source root
agreement, non-empty consistent equivalent roots, one decision per retained
proposal, proposal evidence/confidence conservation, and equality between
accepted-decision components and final link components. Supported unresolved
`parent_id`, `child_ids`, and `label_for_id` relations now stop before rewrite
with `FusionStatus.INCONCLUSIVE / unresolved_source_relation`.

The structure-free Actor fallback counts the nodes actually retained in each
source document. It no longer compares a per-source document with the global
visible-target count.

`WorldFusion` is the sole production producer of `EntityAlignmentDecision` and
the sole production constructor of `WorldObservation`. The observation
constructor validates structural conservation and the closed
disposition/reason shape; it does not re-run role/root/endpoint/coordinate
adjudication. An architecture redline forbids a second production constructor
or decision producer. Direct test-only construction therefore cannot be cited
as proof that the observation constructor independently establishes semantic
decision truth.

Offline property evidence at the repair working tree:

- requested focused gate: `47 passed`;
- full pytest: `1632 passed, 27 skipped`;
- `ruff check src tests`: passed;
- `mypy src`: passed for 335 source files;
- `git diff --check`: passed;
- live benchmark: not run.

Implementation and local property verification are complete. Independent
fresh-context review passed against the repair exit properties and sole-owner
boundaries, so A.1 closure is admitted. This attestation does not widen the
slice into StateFact cutover, activate-effect authority, new interactions, or
live benchmark evidence; A.2 is admitted but not started at this boundary.
