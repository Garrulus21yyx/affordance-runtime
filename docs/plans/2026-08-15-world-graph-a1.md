# Wave A.1 source-instance owner-spine plan

Status: `COMPLETE`

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

All slices are complete. Detailed exit evidence and remaining boundaries are in
[the closure record](../evidence/2026-08-15-world-graph-a1-closure.md).
