# P5-D6.1 Confirmation and Evaluation Contract Completion

> **Lifecycle:** CURRENT REVISION-SCOPED IMPLEMENTATION RECORD
> **Start:** `codex/migrate-world-interaction-capabilities@e22c519cebd185abcb9c173bffeef8af80b0f18d`
> **Implementation commit:** `refactor: complete confirmation and evaluation contracts` (this record is contained in that commit; its SHA is reported by final Git evidence)
> **Remote CI attestation:** unavailable

## Closed contract scope

- Effective risk is the maximum of the TaskGoal floor and selected option risk,
  with `IRREVERSIBLE` above `HIGH`. It is the single risk used by assessment,
  subject identity, request presentation, and fresh-subject comparison.
  READ_ONLY still blocks effectful actions.
- Semantic destination now flows from policy selection through ActionSpace
  admission, admitted selection, ActionIntent, subject identity, confirmation,
  and fresh recomputation. Required and offered IDs are enforced. No drag,
  send, transfer, or other destination execution primitive was added.
- Confirmation presentation includes semantic action, target label and stable
  ID, optional destination label and stable ID, bounded semantic parameters,
  effects, effective risk, and consequences. Password/secret/token/credential/
  authorization/API-key-like fields are display-redacted. Exact unredacted
  semantic parameters remain bound by subject identity.
- Confirmation request repr hides its intent. Summary construction reads only
  secret-free semantic world context and never reads selector, coordinate,
  bbox, href, method, backend, screenshot/TD digest, security reference,
  credential, or an ActionBinding payload.
- DONE, CANCELLED, FAILED, and BLOCKED sessions are terminal and immutable.
  Repeated run/resolve calls return the original result without new observation,
  policy, probe, or execution work.
- After confirmation, an exact current semantic subject executes its current
  binding once. When no exact subject exists, Runtime clears approval and
  returns to policy on the already-fresh observation; it never selects
  `candidates[0]` or a fuzzy replacement.
- Every ActionEvaluation binds exact request, before-observation, and
  after-observation IDs. Confirmed effect and confirmed no-effect require
  authoritative evidence references. Coverage gaps remain UNKNOWN; reason text
  cannot substitute for evidence. Lineage mismatches fail before TaskEvaluator.
- TaskEvaluation control is explicit and uniform: COMPLETE → DONE,
  INCOMPLETE → policy, UNKNOWN → WAITING_USER, BLOCKED → BLOCKED.
  These rules apply initially, before policy, after confirmation reobservation,
  and after action evaluation.
- DOM, Visual full-digest, and WoT local HTTP JSON simulation retain one shared
  RiskPolicy, ConfirmationRequest, AgentRunSession, ActionEvaluation contract,
  task-evaluation policy, fresh-rebind behavior, and private-payload isolation.
- Target core, agent, evaluation, risk, confirmation, Visual, and WoT remain
  within the 350-line file and 80-line function gates. Import-boundary tests
  continue to reject concrete surface, legacy owner, and fixture dependencies.

## Validation

Validation at the implementation HEAD includes:

```text
pytest -q
pytest -q tests/test_risk_policy.py -vv
pytest -q tests/test_confirmation_contracts.py -vv
pytest -q tests/test_confirmation_continuation.py -vv
pytest -q tests/test_target_evaluation_certainty.py -vv
pytest -q tests/test_target_result_invariants.py -vv
pytest -q tests/test_dom_agent_loop_e2e.py -vv
pytest -q tests/test_visual_agent_loop_e2e.py -vv
pytest -q tests/test_wot_agent_loop_e2e.py -vv
pytest -q tests/test_surface_symmetry_matrix.py -vv
pytest -q tests/test_target_core_boundaries.py -vv
pytest -q tests/test_destination_contract.py -vv
pytest -q tests/test_confirmation_presentation.py -vv
pytest -q tests/test_terminal_session_immutability.py -vv
pytest -q tests/test_action_evaluation_lineage.py -vv
pytest -q tests/test_task_evaluation_loop_policy.py -vv
pytest -q tests/test_confirmation_reselection.py -vv
pytest -q tests/test_local_benchmark_mainline.py::test_settings_recovery_blocks_stale_dispatch_then_retries_verified_absence --runxfail
ruff check src tests
mypy src
git diff --check
docker compose -f environments/smart_room/docker-compose.yml config
```

No external full-agent benchmark was run.

## Status and exclusions

```text
P5_D_current_profile: CLOSED
P5_D6_1_contract_completion: CLOSED
destination_execution_primitives: NOT_STARTED
model_backed_target_policy: NOT_STARTED
production_model_evaluators: NOT_STARTED
new_loop_benchmark_harness: NOT_STARTED
semantic_fusion: NOT_STARTED
long_horizon: NOT_STARTED
ActionBatch: NOT_STARTED
external_benchmark: BLOCKED
default_cutover: NOT_READY
```

The default product path remains the legacy Coordinator baseline. D6.1 does not
admit external benchmarks: model-backed target AgentPolicy, production evaluator
composition, the new-AgentLoop benchmark harness, and exact-head remote CI are
still required. No registry, approval token, transaction, durable resume,
semantic fusion, fallback routing, default cutover, merge, or old-core deletion
was implemented.
