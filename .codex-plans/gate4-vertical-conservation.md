# Gate 4 vertical conservation execution

Status: aborted_not_admitted; gate_2_reopened; gate_3_reopened; overall_reopened_non_closed

## Goal

Prove, through the existing production `TargetRuntime/CoreAgentLoop` path and the Gate 0 Recording FunctionModel,
that one fresh World conserves its public projection, actually delivered route relation, Catalog/schema/resolver,
canonical provider envelope, capacity coordinates, returned tool call, and final private binding. Extend the same proof
through a two-turn continuation and an actually attached annotated-media case. This gate adds tests/support and status
evidence by default; an owner contract falsification stops the gate rather than authorizing compensation.

## Constraints

- Baseline HEAD `ca8dfdbf85a37d64f6868f23dd9cc95cbd845359`; Gate 0–3 admitted by the Gate 4 authorization.
- Preserve untracked `output/`; never modify, stage, or commit it.
- No real provider, live benchmark, Task7 replay, external token counter, or GUI side effect.
- No second World, ref allocator, Manifest, request builder, Binder, loop, cursor authority, or test-only production branch.
- If a Gate 1–3 owner is falsified, identify the gate/owner/input/output/invariant, reopen it, stop Gate 4, and do not
  commit a Gate-4-complete change.

## Steps

1. [completed] Build a read-only producer/consumer/conservation matrix and audit active token-breakdown consumers.
2. [failed] A real annotated production turn falsified Gate 2 media route/operand-role conservation; Gate 4 stopped.
3. [pending] Extend the recorder return through Catalog resolver, `SelectAction`, Binder, and stale/invalid failures.
4. [pending] Extend the real two-turn continuation and multimodal production-path cases through Envelope/recorder.
5. [pending] Add generated private-permutation, sparse-route/schema, label/variant, and capacity-coordinate properties.
6. [pending] Run focused, C8–C12/architecture, full, Ruff, compileall, diff, and production negative searches.
7. [completed] Record the Gate 2/Gate 3 diagnostic contract falsifications in architecture, benchmark, and plans.
8. [pending] No Gate 4 completion commit is permitted while the falsified owners remain reopened.

## Files produced or modified

- `.codex-plans/gate4-vertical-conservation.md` — this persistent execution record.

## Evidence log

- Baseline HEAD and worktree: exact required revision; only `?? output/` before this plan was created.
- Mandated current documents and historical Gate 0–2 C10 plan checkpoints plus Gate 3 plan read completely.

## Producer / consumer / conservation matrix

| Value / transition | Authoritative producer | Production consumers crossed by Gate 4 | Conserved fact |
| --- | --- | --- | --- |
| fresh `WorldObservation` | `SurfaceAdapter`/`UnifiedWorldEnvironment` acquisition | `CoreAgentLoop`, `WorldDeliveryIndex`, `ActionSpaceBuilder` | one current GUI generation; private observation/source identity is not public input |
| `CanonicalPublicWorldProjection` | `CanonicalPublicWorldProjection.build` called by `CoreAgentLoop._canonical_world_for` | `ContextBuilder`, grounding, delivery, effects, Manifest/Catalog lineage | sole E/N/F/R allocation and public order |
| complete `ActionSpace` | `ActionSpaceBuilder` | canonical projection, action recall/plan, action admission and Binder | complete legal semantic route relation remains Runtime-private until delivery |
| `ObservationDeliveryStore` | CoreLoop-owned initial value and `Store.reduce`/`RunState.apply` transitions | `ContextBuilder`, `ActionDeliveryPlan`, continuation capability/resolver | inventories, exact private offsets, currentness and continuation transitions |
| `ActionDeliveryPlan` | `ContextBuilder` from World/ActionSpace/Store | `TurnPacker`, `build_model_turn_delivery` | pure ordered obligations and one foreground; no cursor mutation |
| `ModelTurnDelivery` + `DeliveryManifest` | `TurnPacker` via `build_model_turn_delivery` | Catalog compiler, Envelope binder, trace diagnostics | exact admitted text/media plus ordered union of fragment/actual-mark route deltas |
| `PerTurnToolCatalog` | `compile_grounded_action_catalog` from Manifest rows + frozen Store capabilities | Envelope tools, normalizer, unique resolver | schema language equals exact resolver relation; no complete-ActionSpace rescan |
| `CanonicalProviderEnvelope` | `CanonicalProviderEnvelopeBinder` | `RequestAdmission`, PydanticAI typed codec, attempt transcript | one physical request identity: instruction, canonical user text, media, tools, settings, output contract |
| admitted request/cost | `RequestAdmission` over that envelope | `TurnPacker`, bridge diagnostics | input total, separate reserve, complete request total, and effective input limit share one coordinate contract |
| physical provider request | PydanticAI codec from admitted envelope | Gate 0 `FunctionModel` recorder | ordered messages/parts, bytes/MIME, tools/schema/strictness/settings/output equal `model_boundary_projection()` |
| returned tool call | Recording `FunctionModel` | PydanticAI deferred-call parser, normalizer, Catalog resolver | one schema-admitted call selects exactly one current resolver row |
| `SelectAction` | Catalog row resolver | `ActionSpace.admit`, risk/currentness, `ActionBinder` | operation/source/destination/business parameters remain unchanged while private IDs appear only internally |
| `BoundActionRequest` | `ActionBinder.bind_for_execution` | fake/in-memory environment executor | current private binding resolved only after semantic admission; no binding data returns to model input |

### Capacity consumer audit

At the stop revision, `estimated_total_tokens` was active input cost; `output_reserve_tokens` was the separate reserve;
`complete_request_tokens` was their sum; `admission_limit` was the effective input limit. The fields
`prefit_estimated_total_tokens`, `full_candidate_tokens`, and `lens_candidate_tokens` have no candidate producer: all
three are assigned the same complete-request total. The only production consumer compares `full_candidate_tokens`
against input-only `estimated_total_tokens` in the WebArena diagnostic. They are old-chain ghost metrics and will be
deleted at `ModelRequestBreakdown` plus that consumer, with no probe-side conversion, during the reopened Gate 3
diagnostic-owner repair rather than as a Gate 4 compensation. Gate 3 now names the live value
`estimated_input_tokens`; the old names remain in this historical falsification record only.

### Stop evidence

A provider-free real production turn crossed `TargetRuntime/CoreAgentLoop → ModelBackedAgentPolicy → TurnPacker →
ModelTurnDelivery/Manifest → CanonicalProviderEnvelope → PydanticAI Agent → Recording FunctionModel`, using a JPEG
screenshot with one in-frame current grounding region. Annotation correctly produced PNG bytes and an actual `E1`
mark. The frozen values were:

```text
Manifest.action_routes = [(activate, E1, "")]
CanonicalMediaRecord.marks = [(E1, (1, 1, 5, 5))]
CanonicalMediaRecord.operand_roles = [E1]
```

The media value has no route delta and `operand_roles` contains a ref rather than a source/destination role. The
current implementation creates route-free marks in `GroundingProjection`, filters them later by Manifest routed refs
in `build_model_turn_delivery`, and derives Envelope operand roles as the mark refs. This violates the Gate 2 positive
contract that actual media carries its route delta and operand role at generation, including destination-only marks.
No production repair or compensating test was made.
