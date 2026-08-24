# Public Result Delivery Convergence Plan

Goal: replace both lossy result paths with one standard call-correlated tool-result lifecycle:
`typed external tool call -> Runtime execution -> ObservationDeliveryStore inventory -> TurnPacker atomic selection ->
PydanticAI ToolReturn/DeferredToolResults under the original tool_call_id -> physical provider request`, while keeping
one Store, one packer, one Envelope, and one CoreAgentLoop. Workspace retains receipts only.

Status: implementation/provider-free acceptance at `a20fce29` was falsified by independent review of `2a0ce38c`.
The pending-call committed Store suppresses the same-step GUI-effect `advance` transition. Work stops and returns only
to the provider-protocol / `ObservationDeliveryStore.reduce` ownership boundary. The normative replacement is now
frozen in `docs/architecture.md` and its acceptance in `docs/benchmark.md`: policy retains the official PydanticAI
pending exchange, the existing typed AgentDecision/StepResult algebra owns execution truth, and the Store reducer
alone constructs the next Store.
Live and cohort execution remain stopped.

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

7. **done — Independent fresh-context review: falsified**
   - Read-only review of the full causal surface and evidence. Any falsification gets its own commit and stops work.

8. **pending — Request authorization for one held-out witness (not eligible)**
   - Only after steps 1-7 pass. Bounded cohort remains stopped.

## Revised standard tool-result migration

9. **done — Verify standard transport APIs and current bridge lifecycle**
   - Confirm installed PydanticAI DeferredToolRequests/DeferredToolResults/ToolReturn contracts and physical message
     behavior; compare official PydanticAI, MCP, OpenAI computer-use, and browser-use primary sources.
   - Trace every supported local tool result producer by return type and original tool_call_id.

10. **done — Freeze type-driven result algebra and deletion map**
   - Define `PublicEvidenceResult | ExecutionReceipt | ToolFailed | FinalResponse` ownership and unsupported outcomes.
   - Delete tool-name classification and ordinary `latest_public_results` user-context injection from the target design.

11. **done — Implement standard call-correlated result return**
   - Store/Packer retain project-specific inventory/currentness/atomic selection.
   - Bridge returns admitted public records as ToolReturn/DeferredToolResults paired to the original call ID; private
     cursor/lineage/digests remain metadata.
   - Workspace and recent trajectory retain only receipt/summary lineage.

12. **done — Reverify all producer types and physical requests**
   - Generated producer-completeness properties, call-ID conservation, typed failures, pagination/currentness,
     exact records/capacity, Recording FunctionModel, full/static/negative checks.

13. **done — Independent fresh review falsified the acceptance**
   - A committed pending-call Store currently bypasses the sole GUI-effect `advance` transition. Stop and return only
     to the Store merge owner; no live.

14. **done — Freeze provider-protocol / delivery-state convergence design**
   - PydanticAI owns pending call/history/result pairing; policy returns the existing immutable call-correlated
     AgentDecision and no Store snapshot.
   - StepResult owns the existing typed result/receipt/failure and execution/World facts; do not add a duplicate outcome
     wrapper.
   - `ObservationDeliveryStore.reduce(previous, step)` composes effect, result, continuation, discovery, failure, and
     novelty exactly once and is the only next-Store constructor.
   - Record the complete deletion map, reuse boundary, composition matrix, and non-goals in the two current authority
     docs. This plan tracks work only and does not override them.

15. **done — Close the existing call/result algebra and reducer composition properties**
   - Reuse AgentDecision.tool_call_id, StepResult, existing typed local results/receipts/failures, and official
     PydanticAI message/deferred-result types; add only an exhaustive pure projection function where required.
   - Add generated legal combinations of pending exchange, GUI effect, public evidence, continuation, discovery, and
     typed failure. Keep production behavior unchanged until the cutover can remain green.
   - Commit this verified scaffold independently.
   - Files: `src/affordance_runtime/agent/tool_result_projection.py`,
     `tests/unit/agent/test_tool_result_projection.py`.

16. **completed — Atomic production cutover with snapshot/cursor ownership split**
   - Migrate policy, Catalog resolver, CoreLoop, StepResult, Store, RunState, Workspace/Monitor, TurnPacker, Envelope
     codec, and trace consumers together.
   - Delete whole-Store return fields, Store pending-call/outcome fields, manual mapping history reconstruction,
     caller-side merges, and generic result-body projections.
   - Do not add a replacement state machine, Store, packer, provider transport, or benchmark/site branch.
   - Commit only after focused production-path and existing suites are green.
   - Falsification witness: the first admitted `action_results_next_page` capability is produced from the
     `AgentContext` delivery-planning Store, while `RunState.delivery_store` still has no corresponding inventory.
     The committed reducer therefore returns `unsupported` for a capability that the exact admitted Catalog accepted.
   - Observed: provider-free vertical test
     `test_gate_2_two_turn_production_path_advances_store_and_records_new_suffix_routes` failed in
     `ObservationDeliveryStore.reduce` with `committed continuation is unsupported` after 883 passing tests and 18
     skips in the same run. Expected: every continuation accepted from the exact admitted turn is reducible exactly
     once against the authoritative previous Store without a whole-Store handoff.
   - Producer/owner/consumer gap: `ContextBuilder/build_action_delivery_plan` produces the inventory/capability for
     `ModelTurnDelivery` and Catalog resolution; `ObservationDeliveryStore.reduce` owns the next Store; CoreLoop and
     RunState consume that transition. The frozen contract does not state how the admitted per-turn inventory becomes
     an authoritative reducer input before currentness validation. No nearby fallback or guessed fix was added.
   - Evidence: `evidence/acceptance/provider-protocol-delivery-state-cutover-falsification-20260824.json`.
   - Resolution supplied 2026-08-24: `ActionDeliveryPlan` owns the immutable per-turn inventory snapshot and admitted
     continuation capabilities; `ObservationDeliveryStore` owns only persistent cursor progress and real temporal
     evidence. Catalog binds a capability directly to the admitted Plan row, and the reducer validates its
     inventory key/offset/World/action/result lineage before committing only cursor progress. ContextBuilder no longer
     replaces the persistent Store with an `ActionDeliveryPlanningResult.store`, and the Catalog does not require
     inventory installation in Store. Rebuilding the next Plan against fresh World/ActionSpace either reapplies the
     cursor to matching lineage or fails typed stale/reset.

17. **in_progress — Normalize continuation identity with one complete key**
   - Replace the unlineaged `requested_continuation_scope` duplicate with a typed complete continuation key shared by
     cursor progress and foreground request.
   - Make `for_world` total over every lineaged Store field before any identity return, and clear foreground whenever
     its keyed cursor does not survive.
   - Promote a Plan obligation only when its complete inventory key equals the requested foreground key; any
     world/action/result/order change starts at offset zero and normal priority.
   - Verify with generated Store-field normalization/key mutation properties plus same-World and changed-World
     vertical witnesses. No live/provider execution.

18. **completed — Provider-free vertical acceptance and evidence commit**
   - Run the real `ModelBackedAgentPolicy → CoreAgentLoop → Store.reduce → RunState.apply → Recording FunctionModel`
     paths for the generated composition matrix.
   - Run focused/full/Ruff/compileall/diff and production negative searches; persist a revision-bound evidence artifact.
   - Commit verification/status independently from implementation.

18. **pending — Independent fresh-context exit review**
   - Read-only review from the committed revision. Any falsification stops immediately, records its owner and witness,
     and leaves live/cohort stopped.

19. **pending — Request authorization for one held-out witness**
   - Eligible only after steps 15–18 pass. One Task 21 witness precedes any bounded cohort.

## Explicit non-goals

- No new Memory, pager, packer, Manager, semantic judge, VLM fallback, CoreLoop branch, or second Envelope authority.
- No `_MAX_DEPTH`, string-length, record-count, or Task21-specific threshold patch.
- No live/provider call before explicit post-review authorization.
- No GoalCompiler/semantic-judge ModelPort migration or visual-specialist restructuring in this convergence; those are
  separately scoped simplification candidates and cannot delay return to the GUI benchmark.

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
- `evidence/acceptance/public-result-fresh-review-falsification-20260824.json` — independent `list_regions` ingestion falsification; returns work to the Store owner.
- `evidence/acceptance/call-correlated-tool-results-provider-free-20260824.json` — revision-bound standard deferred-result acceptance.
- `evidence/acceptance/call-correlated-tool-results-fresh-review-falsification-20260824.json` — committed-Store/effect-transition merge falsification.
