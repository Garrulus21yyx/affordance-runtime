# Gate 2/4 action-route authority convergence

Status: implemented_provider_free_verified; gate_2_vertical_exit_review_pending; gate_4_exit_review_pending; overall_reopened_non_closed

## Baseline and purpose

- Baseline HEAD: `29177e80` (`test: record vertical route authorization falsification`).
- Initial worktree: only `?? output/`; preserve it without modification, staging, or commit.
- Attempt 3 proved that a single actual image mark could publish a complete binary route whose complementary operand
  was absent from the final text/media delivery. The failure was detected correctly by `ModelTurnDelivery` before any
  recorder/provider/GUI attempt.
- This migration closes that shared authority defect. It does not add a planner, manager, retry, test-only production
  branch, alternate route inference, or a second delivery authority.

## Positive owner contract

```text
VisualEvidenceFragment = exact image bytes + actual E/N marks + bounding boxes
ActionRouteFragment = operation + source + optional destination + complete public context + private resolver row

Canonical World + complete ActionSpace
  -> ActionDeliveryPlan owns complete atomic ActionRouteFragments
  -> TurnPacker admits bounded route-fragment prefixes and visual evidence independently
  -> Manifest.action_routes is exactly the admitted ActionRouteFragments
  -> ToolCatalog consumes only Manifest.action_routes
```

- A visual mark is evidence only. It neither authorizes nor infers a unary or binary route.
- A destination-required route is one atomic source/destination record. Its operation and both public operands are
  rendered and admitted together or omitted together.
- Media metadata contains only facts actually visible in the image. Resolver lineage remains private to the admitted
  route fragment and never enters media, provider physical content, public trace, or delivery identity.
- An unselected route remains absent from Manifest/Catalog even when either or both operands are marked; the existing
  continuation/find-controls mechanism remains its recovery path.

## Serial migration

1. [completed] Inventory and remove every media route/operand-role producer and consumer.
2. [completed] Rename/fix the existing DeliveryPlan atomic record as `ActionRouteFragment`, preserving its sole private
   resolver row and complete binary public context.
3. [completed] Make `ModelTurnDelivery` consume renderer/DeliveryPlan Manifest routes only; keep media as exact visual
   evidence and preserve E/N visibility in the Manifest without action authorization.
4. [completed] Replace the incorrect single-mark authorization tests with selected/unselected route properties covering
   unary, binary, E/N evidence-only marks, one/both/no marks, and cursor recovery.
5. [completed] Complete the real Runtime -> PydanticAI recorder -> schema -> resolver -> ActionSpace -> Binder vertical
   proof, sparse relation, continuation, permutation, and capacity conservation.
6. [completed] Run focused/full/static/architecture and negative searches, then update architecture/benchmark/C10 status.
7. [completed] Create one independent implementation commit only if the complete vertical exit passes; otherwise apply
   the stop protocol and leave Gate 2 vertical exit and Gate 4 pending/not admitted.

## Status discipline

During implementation the only permissible intermediate status is:

```text
Gate 2 owner implementation in progress/completed
Gate 2 vertical exit pending
Gate 4 pending
Overall reopened / non-closed
```

Gate 2 and Gate 4 may be admitted only together after the full vertical proof passes.

## Provider-free implementation evidence

- Focused Gate set: `184 passed, 2 skipped`.
- Full pytest: `1620 passed, 24 skipped, 1 warning`.
- Ruff, compileall, `git diff --check`, and production negative searches pass.
- Selected binary routes remain atomic with source-only, destination-only, both, or no actual image marks.
- Thirty-two actual E marks can include an unselected route without authorizing it; a real `find_controls` call then
  recovers the route into the next Envelope, whose schema-selected call resolves and binds the intended private target.
- Sparse multi-source/multi-destination schemas accept exactly the three existing adjacency rows and reject the missing
  Cartesian edge. Unary/multi-operation rows, duplicate short Unicode/punctuation labels, and per-route business
  parameter domains preserve schema acceptance iff exactly one private resolver row accepts the complete arguments.
- A real continuation sequence consumes every ordered owner route exactly once, exposes no ghost continuation after
  the suffix is exhausted, and keeps private cursor/action identities out of every recorded physical input.
- The final physical Envelope passes at exact input fit; one token below returns typed `context_capacity` with zero
  recorder/model attempts. Default capacity coordinates remain `62,904 + 4,096 = 67,000`.
- No real provider, live benchmark, or Task7 replay ran. A fresh independent exit review remains required before joint
  Gate 2/Gate 4 admission or any closure claim.
- The verified migration is committed independently as `test: prove vertical model route conservation`; the exact
  revision is recorded by Git and reported at handoff.
