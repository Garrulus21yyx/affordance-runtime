# Public Result Delivery Convergence Plan

Goal: replace the lossy `local result -> Workspace exact values -> generic projection` path with one owner-preserving
`ObservationDeliveryStore -> TurnPacker -> ModelTurnDelivery -> physical provider request` path, while keeping one
Store, one packer, one Delivery, one Envelope, and one CoreAgentLoop.

Status: active; the owner migration is implemented and provider-free invariant verification is in progress.

## Steps

1. **done — Repository-wide relevant causal review**
   - Trace all local-result producers, Store state/transitions, Workspace copies, packer obligations/atoms, Delivery,
     binder, envelope, Monitor novelty, continuation, fresh-World invalidation, exceptional paths, evidence/docs/tests.
   - Record every authority and consumer; distinguish architecture, verification, environment, and acceptance defects.
   - Files: this plan only.

2. **done — Current primary-source comparison**
   - Compare atomic structured tool-result delivery and compaction behavior with current official provider/runtime
     practices; use only primary sources and label design inferences.

3. **done — Freeze bounded positive contract and migration map**
   - Define typed `PublicResultRecord`/inventory identity, currentness, atomicity, packing, suffix, oversized-record,
     admitted-novelty, failure, and temporal-order contracts.
   - Define physical deletions and affected consumers; no Task21/site/content specialization.

4. **done — Implement owner migration**
   - Store owns canonical records and continuation suffix.
   - Workspace retains lineage/summary only.
   - Existing TurnPacker admits complete public-result records into ModelTurnDelivery.
   - Binder/Envelope/Recording consume that same Delivery projection.
   - Monitor novelty derives from admitted records.

5. **done — Verify invariant properties and vertical production paths**
   - Deep mappings, long text, Unicode, 1/2/16/32 records, exact-fit/one-unit-over, pagination append/dedup,
     currentness, suffix conservation, provider physical equality, direct final response.
   - Focused, full pytest, Ruff, compileall, negative searches.

6. **done — Commit provider-free evidence/status**
   - Separate implementation and evidence/status commits; Overall remains non-closed and no live is run.

7. **pending — Independent fresh-context review**
   - Read-only review of the full causal surface and evidence. Any falsification gets its own commit and stops work.

8. **pending — Request authorization for one held-out witness**
   - Only after steps 1-7 pass. Bounded cohort remains stopped.

## Explicit non-goals

- No new Memory, pager, packer, Manager, semantic judge, VLM fallback, CoreLoop branch, or second Envelope authority.
- No `_MAX_DEPTH`, string-length, record-count, or Task21-specific threshold patch.
- No live/provider call before explicit post-review authorization.

## Produced files

- `.codex-plans/public-result-delivery-convergence.md` — persistent plan and progress authority for this task.
- `src/affordance_runtime/agent/context/observation_delivery.py` — typed record/inventory owner and lifecycle.
- `src/affordance_runtime/agent/context/action_candidate_projection.py` — existing-plan PUBLIC_RESULT obligation.
- `src/affordance_runtime/agent/context/model_turn_delivery.py` — frozen admitted result projection.
- `src/affordance_runtime/model/policy/grounded_policy_context.py` — exact physical public-result rendering.
- `src/affordance_runtime/agent/workspace.py` — summary/lineage-only event history.
- `src/affordance_runtime/agent/context/step_projection.py` — evidence bodies removed from recent trajectory.
- `src/affordance_runtime/agent/monitor.py` — model-visible admitted-prefix novelty identity.
- `evidence/acceptance/public-result-turn-packing-provider-free-20260824.json` — revision-bound provider-free acceptance.
