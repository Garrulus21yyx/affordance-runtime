# Gate 4 vertical conservation — attempt 2

Status: stopped_not_admitted; gate_2_readmitted_after_repair; gate_3_admitted; overall_reopened_non_closed

## Goal

Prove the ordered request and response conservation contracts through the real provider-free production path:
`TargetRuntime → CoreAgentLoop → ModelBackedAgentPolicy → PydanticAIGroundedDecisionPort → PydanticAI Agent →
Recording FunctionModel`, including annotated media, sparse Catalog relations, two-turn continuation, private
permutations, and final request-capacity coordinates. This attempt adds tests/support, plan, and documentation only
unless the production contract is falsified, in which case it stops under the user-specified protocol.

## Baseline and constraints

- Baseline HEAD: `c98c688b48a6dcf3b1d67fa6034bfaba177ad9d4`.
- Initial worktree: only `?? output/`; preserve it without modification, staging, or commit.
- Gate 0–3 admitted; Gate 4 pending; overall reopened/non-closed.
- Preserve `.codex-plans/gate4-vertical-conservation.md` as the aborted first-attempt falsification record.
- No real provider, live benchmark, Task7 replay, or external GUI side effect.
- Tests must traverse production owners; no hand-built Envelope/Catalog as vertical closure evidence and no
  test-specific production branch.
- Default modification scope is tests, test support, this plan, and the two authority documents. Any production
  falsification stops the gate; do not compensate in CoreLoop, bridge, Catalog, recorder, probe, or fixtures.

## Positive contract

- Ordered delivered fragment/media route union equals Manifest routes; Catalog rows equal Manifest routes plus frozen
  Store continuations; Envelope tools/media equal the frozen Catalog/delivery; recorder input equals the Envelope
  model-boundary projection.
- A recorder-selected call must be accepted by the provider-visible schema, resolve to exactly one current Catalog
  row, preserve the public route through `SelectAction`, and bind the row's current private binding.
- Actual annotated marks jointly conserve unary, source-only/destination-only binary, evidence-only, and unavailable
  cases without deriving routes from marks or leaking private lineage.
- Sparse relational schemas admit exactly the unique resolver relation, including per-route parameter domains and
  nontrivial public labels/variants.
- Store continuation commits through CoreLoop and exposes the next ordered suffix on the next real provider turn,
  without public cursor leakage, repetition, skipping, or ghost tools.
- Private identity/enumeration/resolver permutations leave public order, delivery, schema, Envelope identity/cost,
  and recorder input unchanged; public semantic or route changes change the appropriate identity.
- RequestAdmission uses one input coordinate, one output reserve, one complete-request sum, and the reserve-aware
  effective input limit; rejected requests never reach the recorder.

## Steps

1. [failed] Map existing Gate 0–3 production-path fixtures and run the first missing real annotated case. The
   evidence-only actual-mark case falsified Gate 2 before later Gate 4 assertions were added.
2. [blocked] Add the main vertical production-path test(s) for ordered request/response conservation and private
   non-reflow.
3. [blocked] Add annotated production-path cases and sparse Catalog equivalence properties.
4. [blocked] Add the two-turn continuation production-path sequence, stale/zero-prefix/no-ghost cases, and exact
   ordered inventory-union assertions.
5. [blocked] Add private-permutation and public-change identity/cost/physical-input properties.
6. [blocked] Add/extend capacity-coordinate assertions through the final admitted/rejected recorder boundary.
7. [completed] Run the first real production-path Gate 4 case; it falsified Gate 2, so stop and
   record owner/gate/input/actual/expected evidence.
8. [not_run] Full pytest, Ruff, compileall, diff check, and later production negative searches are not closure evidence
   after the mandatory stop.
9. [completed] Update `docs/architecture.md`, `docs/benchmark.md`, and
   `.codex-plans/c10-joint-delivery-packing.md` with reopened status and falsification evidence.
10. [not_run] Do not create `test: prove vertical model route conservation`; Gate 4 is not implemented.

## Files produced or modified

- `.codex-plans/gate4-vertical-conservation-attempt2.md` — this persistent attempt record.
- `.codex-plans/c10-joint-delivery-packing.md` — historical Gate 2 reopening and Gate 4 attempt-2 stop status.
- `docs/architecture.md` — owner-level causal model and current status.
- `docs/benchmark.md` — provider-free falsification evidence and execution-order status.

## Evidence log

- Baseline verified before modification: required HEAD and only `?? output/`.
- All six mandated source/status/plan files read completely before implementation.
- Concrete input: one real `WorldObservation` contained the ordinary executable shared toggle plus an in-frame
  screenshot grounding region for a visible read-only target `read-only-note`. The canonical projection assigned the
  latter `N1`. The request traversed `TargetRuntime/CoreAgentLoop → ModelBackedAgentPolicy → TurnPacker →
  ModelTurnDelivery/Manifest → CanonicalProviderEnvelope → PydanticAI Agent → Recording FunctionModel` with
  multimodal delivery enabled.
- Actual output: Runtime completed its unrelated executable action; recorder calls=`1`; recorder physical input
  equalled `Envelope.model_boundary_projection()`; one JPEG media record was physically attached, but it contained
  `marks=()`, `operand_roles=()`, and `route_deltas=()`. The Manifest contained only the unrelated
  `(activate,E1,"")` route.
- Expected Gate 2/Gate 4 output: the actual in-frame read-only annotation remains an evidence-only mark in the attached
  media with no operand role and no route delta. It must not disappear merely because it is not an action operand.
- Immediate mechanism: `GroundingProjection.project` computes `marked_targets` from `offered` action operands before
  annotation; `AgentImageMark` additionally accepts only executable `E*` refs. A read-only target is therefore removed
  before `bind_image_action_routes`, so the production path cannot express the documented evidence-only-mark case.
- Classification: Gate 2 media-fragment/GroundingProjection owner defect, not a Gate 4 vertical-composition defect.
  Producer: `GroundingProjection`; consumers: `bind_image_action_routes`, `ModelTurnDelivery`, `DeliveryManifest`,
  `CanonicalProviderEnvelope`. The violated positive invariant is that actual annotation marks and action-route roles
  are separate relations: an actual evidence-only mark may have zero route roles, while routes remain authorized only
  by exact route deltas.
- Stop protocol applied immediately. No later Gate 4 assertions, focused/full/static closure runs, production repair,
  test compensation, or completion commit were performed. No real provider, live benchmark, or Task7 replay ran.

Post-stop status: Gate 2 was subsequently repaired and re-admitted by a fresh provider-free review from `27e85efe`.
This Gate 4 attempt remains stopped/not admitted and was not resumed.
