# Step 12 Unified Source Orchestration Implementation

Status: `IMPLEMENTED_PROPERTY_AND_INTEGRATION_VERIFIED / STEP_13_VISUAL_BINDING_NEXT`

Scope boundary: implement Step 12 only. `VisualRegionBinding` and benchmark
capability expansion remain Step 13 and are not part of this plan.

## Work items

1. `done` — inspect and close typed pre-acquisition offer/result contracts.
2. `done` — add pure bounded `ObservationOrchestrator` selection.
3. `done` — add pure deterministic `WorldFusion` with explicit correspondence,
   provenance, conflicts and typed gaps.
4. `done` — integrate selection/fusion into thin `UnifiedWorldEnvironment`,
   including optional failure and shared acquisition ownership.
5. `done` — extract deterministic route ranking into `RouteSelector` and add
   bounded safe reroute for eligible `NOT_SENT` outcomes.
6. `done` — extract route-free `GroundingProjection` and make marks depend only
   on media actually emitted in the provider request.
7. `done` — verify selection, failure, fusion, conflict, grounding, authority,
   reroute, freshness and shared-capture properties plus focused integrations.
8. `done` — align implementation status/evidence and stop before Step 13.

## Modified/created files

- `docs/superpowers/plans/2026-08-12-step12-unified-source-orchestration-implementation.md`
  — durable execution state and verification record.
- `src/affordance_runtime/world/{acquisition,observation_orchestrator,fusion,route_selector,orchestrator}.py`
  — typed offers/results, bounded selection, pure fusion, route selection and thin coordination.
- `src/affordance_runtime/model_boundary/grounding_projection.py`
  — route-free E-ref/media/mark projection over exactly emitted media.
- `src/affordance_runtime/agent/execution_cycle.py`
  — one fresh revalidation and one bounded zero-dispatch reroute continuation.
- `tests/test_unified_source_orchestration.py`
  — deterministic DOM/Visual/WoT selection, fusion, grounding and reroute witnesses.

## Verification record

- Step-12 focused properties/integrations: `11 passed`.
- Existing Step-11/source/currentness focused regression: `51 passed`.
- Repository suite: `2317 passed, 27 skipped`.
- Ruff: passed.
- No Step-13 BrowserGym visual execution binding was added.
