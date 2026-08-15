# Target Runtime topology T0 consumer and test inventory

Date: 2026-08-15

Status: `T0_COMPLETE / T1_COMPLETE / T2_COMPLETE / T3_READY`

## Scope and method

This inventory is the deletion authority for the topology plan. It does not
move, delete or re-export production code. The scan covered:

- all Python files below `src/affordance_runtime`, `tests` and `scripts`;
- static `import` and `from ... import ...` edges parsed with the Python AST;
- dynamic imports, path assertions and constructor calls found with `rg`;
- root package exports, `pyproject.toml` console scripts and every root CLI
  subcommand;
- target, external-smoke, external-breadth and model-conformance benchmark
  composition roots;
- the legacy Coordinator, staged Runtime and legacy benchmark roots;
- production test helpers and the three root-level test support modules.

The inventory is repository-bounded. There is no in-repository consumer of the
root public API beyond tests. Hypothetical out-of-repository callers do not
authorize compatibility aliases under the topology plan.

The reachability roots used for classification were:

```text
target product:
  target_cli, target_composition, target_runtime_client,
  agent.composition, agent.runtime, agent.loop, agent.session

active target benchmark:
  benchmarks.target_loop.runner
  benchmarks.external_smoke.live_runner
  benchmarks.external_breadth.runner
  benchmarks.model_conformance.loop_attempt
  benchmarks.model_conformance.runtime_decision_matrix

legacy executable:
  composition, coordinator, runtime_client
  benchmarks.adaptive_routing, benchmarks.browsergym,
  benchmarks.browsergym_compatibility_episode,
  benchmarks.browsergym_episode_runner, benchmarks.composition,
  benchmarks.generalization, benchmarks.generalization_rollout,
  benchmarks.local, benchmarks.task_planning
```

Dynamic imports were checked separately because a static import closure cannot
prove their absence. Filename age, line count and test coverage were not used
as deletion evidence.

## Causal result

The topology ambiguity is one ownership problem, not four independent naming
problems:

```text
mixed root CLI/API
  -> exposes target and staged Runtime as peers
  -> keeps legacy benchmark commands executable
  -> keeps legacy tests as public-contract consumers

pass-through target wrappers
  -> obscure the actual TargetRuntime -> AgentLoop -> AgentRunSession spine

benchmark-owned BrowserGym implementation
  -> makes active product surface code depend on MiniWoB manifest policy
  -> prevents a clean surfaces -> world/actions/execution dependency direction
```

The sole target lifecycle after cutover is:

```text
TargetRuntime -> AgentLoop -> AgentRunSession
```

`AgentEpisodeRunner` has no unique state or transition: its two methods only
forward to `AgentLoop.start` and `AgentRunSession.run_until_pause`.
`TargetRuntimeClient` has no unique authority either: admission belongs to
`TargetRuntime.intake`, start/user-input belong to `TargetRuntime`, and
confirmation belongs to `AgentRunSession`. Both are `DELETE_WITH_OWNER` in T1.

## Public API and command disposition

| Current surface | Consumers | Replacement | Disposition | Slice |
|---|---|---|---|---|
| `affordance_runtime.__init__` target exports | target API tests only | target-only root façade | `REWRITE` | T1 |
| root `ActionContract`, planner, `RunRequest`, `RunResult`, `RuntimeClient`, `LegacyRuntimeClient`, `UnifiedAffordance`, `UnifiedObservation` exports | root API tests only; no production/benchmark imports through the root façade | public target task/runtime/session results and stable world/action projections only | `DELETE_WITH_OWNER` | T1/T3 |
| installed `affordance-runtime = affordance_runtime.cli:main` | package console entry | target product command in `app.cli` | `REWRITE` | T1 |
| `target-run` | `tests/test_target_cli.py`, README/current entrypoint docs | becomes the sole product `run` contract without an alias | `REWRITE` | T1 |
| legacy `run` | `cli.run_scenario`, pricing/settings/export reference fixtures and CLI tests | target natural-language run | `DELETE_WITH_OWNER` | T1/T3 |
| `serve-fixture`, `baseline`, legacy `benchmark`, `benchmark-task-planning`, `benchmark-adaptive-routing`, `benchmark-browsergym`, `benchmark-browsergym-generalist`, `evolve` | old local/Coordinator benchmark code and historical evidence commands | historical evidence retained as documents; no executable legacy runtime | `DELETE_WITH_OWNER` | T1/T3 |
| ScreenSpot, WorkArena preflight, WebArena-Verified, WASP and provider-preflight commands | isolated benchmark/provider utilities | separate benchmark entrypoint | `KEEP_MOVE` | T1/T4 |
| `benchmarks.target_loop`, `external_smoke`, `external_breadth`, current `model_conformance` CLIs | active target benchmark/evidence workflows | separate benchmark entrypoint consuming target public API | `KEEP_MOVE` | T1/T2 |

`src/affordance_runtime/__main__.py` remains only as the product console-module
forwarder and is `REWRITE`; it must not dispatch benchmark or legacy commands.

## Target façade and loop files

| Current path | Active consumers | Target replacement | Disposition | Replacement invariant/test | Slice |
|---|---|---|---|---|---|
| `agent/composition.py` | target composition and three active benchmark callers | `app/composition.py`, sole `TargetRuntime` constructor | `KEEP_MOVE` | exactly one production constructor; benchmark callers use public composition | T1/T4 |
| `agent/runtime.py` | target client/composition | `app/runtime.py` | `KEEP_MOVE` | façade owns intake/start/run/user-input | T1/T4 |
| `agent/loop.py` | runtime/session and focused tests | `agent/loop.py` | `KEEP_MOVE` | sole observe/decide/admit/execute/evaluate loop | T1 |
| `agent/session.py` | loop control helpers and focused tests | `agent/session.py` | `KEEP_MOVE` | sole continuation/confirmation/user-input handle | T1 |
| `agent/episode_runner.py` | `agent.runtime` plus direct tests | methods fold into `AgentLoop`/`TargetRuntime` | `DELETE_WITH_OWNER` | no production constructor or import remains | T1 |
| `target_runtime_client.py` | target CLI/composition/root exports and four tests | result value moves to `app/result.py`; methods fold into façade/session | `DELETE_WITH_OWNER` | intake/run/continuation properties retested at façade | T1 |
| `target_composition.py` | target CLI/root API | `app/composition.py` | `REWRITE` | one environment-backed product composition | T1/T4 |
| `target_cli.py` | mixed root CLI | `app/cli.py` | `KEEP_MOVE` | deterministic target CLI witness | T1/T4 |
| `browser_thread_session.py` | target CLI/browser composition | `surfaces/dom` lifecycle owner or `app` adapter assembly | `KEEP_MOVE` | browser thread remains surface-private | T1/T4 |

Active benchmarks do not construct `AgentLoop`, `AgentEpisodeRunner` or
`TargetRuntime` directly. They call `agent.composition.compose_target_runtime`.
The only source `TargetRuntime(...)` constructor is that composition owner.

## Legacy production deletion set

The following 108 non-benchmark modules are reachable from the declared legacy
roots and not reachable from the target product/active target benchmark roots.
Their disposition is `DELETE_WITH_OWNER` in T3 unless an earlier T1 deletion is
specified above. Their supported target replacements are the existing
`agent`, `world`, `execution`, `evaluation`, `task`, `risk`, `confirmation` and
`model_policy` owners; historical staged call order has no replacement test.

```text
action_admission.py
action_choice_authority.py
action_choice_builder.py
action_choice_catalog.py
action_choice_generation.py
action_choice_generation_support.py
action_contract_authority.py
action_contract_builder.py
action_effect_classifier.py
action_outcome_flow.py
action_selection.py
action_semantics.py
active_perception.py
active_perception_flow.py
active_step_scope.py
approval_contracts.py
artifacts.py
async_bridge.py
canonical_observation_builder.py
choice_contracts.py
choice_presentation.py
collection_window.py
composition.py
contract_execution_loop.py
coordinator.py
decision_constraints.py
dispatch_lifecycle.py
environment.py
evaluation_audit.py
evolution.py
execution_phase.py
executors.py
failure_envelope.py
fixtures.py
generalist_planner.py
high_risk_effect_policy.py
intent_compiler.py
interaction_grounding.py
legacy_criteria_evidence.py
material_binding_policy.py
model_recovery.py
observation_store.py
output_materialization.py
perception_phase.py
perception_session.py
planner_context.py
planner_context_recovery.py
planner_model_orchestrator.py
planner_schema_recovery.py
planners.py
planning.py
planning_contracts.py
planning_phase.py
planning_request.py
planning_request_serializer.py
progress_evaluation.py
progress_observation.py
progress_phase.py
progress_skill.py
recovery_coordinator.py
recovery_evaluation.py
recovery_owner_dispatcher.py
recovery_phase.py
recovery_protocol.py
recovery_trace_projection.py
reference_scenarios.py
routing.py
runtime.py
runtime_client.py
runtime_committer.py
runtime_evidence.py
runtime_loop_phase.py
runtime_result_phase.py
runtime_state_projection.py
safety.py
scope_authorization.py
semantic_audit.py
semantic_compilers.py
source_context.py
source_envelope.py
stage_protocol.py
state_kernel.py
step_choice_flow.py
step_choice_planner.py
task_plan_flow.py
task_plan_generators.py
task_plan_lifecycle.py
task_plan_progress.py
task_plan_progress_flow.py
task_planner.py
task_planning_trigger.py
task_skill_progress.py
task_skills.py
task_source_references.py
task_spec_authority.py
trace.py
transaction_materialization.py
verification/loop_evaluator.py
verification/open_semantic.py
verification/predicates.py
verification/providers/__init__.py
verification/providers/artifact.py
verification/providers/resource.py
verification/providers/structural.py
verification/step_completion.py
verification/task_completion.py
verification_report_adapter.py
visual_contracts.py
```

The following files were in the original seed scan but are empty or isolated
compatibility leaves and are also `DELETE_WITH_OWNER`: `artifact_phase.py`,
`compatibility_planner_algorithms.py`, `compatibility_semantic_compilers.py`,
`conformance.py`, `harness_learning.py`, `integrations/local.py`,
`planner_adapters.py`, `planning_request_builder.py`,
`proposal_recovery_policy.py`, `recovery_state_projection.py`,
`recovery_evolution.py`, `recovery_trace_commit.py`, `task_pipeline.py`, and
`task_plan_contracts.py` at package root. The similarly named target package
contracts under `task/` are different owners and remain.

Shared modules found in both closures are not deletion-authorized by
reachability alone. In particular:

- `contracts.py`, `grounding.py`, `simplified_runtime_contracts.py`,
  `unified_grounding.py` and `unified_observation.py` are `REWRITE`: migrate any
  still-supported public values to their target package owner, then delete the
  root legacy module; no re-export shim remains.
- `browser_session.py` is `KEEP_MOVE` into the DOM/browser surface lifecycle.
- `adapters/dom.py`, `adapters/som.py`, `adapters/wot.py` and
  `adapters/wot_security.py` are `REWRITE`: migrate remaining target consumers
  into `surfaces/*`, then delete `adapters/`.
- target-owned modules already below `agent/`, `world/`, `execution/`,
  `evaluation/`, `task/`, `risk/`, `confirmation/`, `model_boundary/`,
  `model_policy/` and `surfaces/` are `KEEP_MOVE`; legacy imports into them are
  removed when the deleting owner is cut over.

## Legacy benchmark disposition

These historical executable owners are `DELETE_WITH_OWNER` in T3. Their JSON
reports and evidence documents remain immutable records; executable Python is
not required to read those records:

```text
benchmarks/adaptive_routing.py
benchmarks/browsergym.py
benchmarks/browsergym_action_schema.py
benchmarks/browsergym_compatibility_episode.py
benchmarks/browsergym_dom.py
benchmarks/browsergym_encoder.py
benchmarks/browsergym_episode_runner.py
benchmarks/browsergym_matrix.py
benchmarks/browsergym_miniwob_source.py
benchmarks/browsergym_observer.py
benchmarks/browsergym_protocol.py
benchmarks/browsergym_types.py
benchmarks/composition.py
benchmarks/generalization.py
benchmarks/generalization_evidence.py
benchmarks/generalization_rollout.py
benchmarks/local.py
benchmarks/metrics.py
benchmarks/miniwob.py
benchmarks/runner.py
benchmarks/spec.py
benchmarks/suites.py
benchmarks/task_planning.py
benchmarks/visual.py
```

`benchmarks/__init__.py` is `KEEP_MOVE` because active benchmark packages still
need the namespace; it exports no legacy runtime.

## BrowserGym reusable-surface split

The active BrowserGym code is not a simple directory move. The exact
disposition is:

| Current file(s) below `benchmarks/external_smoke` | Disposition | Target owner |
|---|---|---|
| `browsergym_acquisition.py`, `browsergym_backend.py`, `browsergym_binding.py`, `browsergym_currentness.py`, `browsergym_diagnostics.py`, `browsergym_entity_identity.py`, `browsergym_execution.py`, `browsergym_projection.py`, `browsergym_semantic_profile.py`, `browsergym_semantics.py`, `browsergym_visual_disambiguation.py`, `browsergym_visual_projection.py` | `KEEP_MOVE` | `surfaces/browsergym` |
| `browsergym_environment.py` | `REWRITE` | split generic BrowserGym `WorldEnvironment` into `surfaces/browsergym`; keep MiniWoB task-id/seed/manifest factory in benchmark composition |
| `browsergym_verifier.py` | `REWRITE` | surface-owned typed source snapshot/lineage; MiniWoB reward/done interpretation remains benchmark evaluator policy |
| `browsergym_inventory.py` | `REWRITE` | package/version/primitive inventory under surface conformance; fixed `REVIEWED_TASK_IDS` remains in benchmark manifest |
| `browsergym_action_evaluator.py` | `DELETE_WITH_OWNER` | callers import product `ProductionActionEvaluator` directly |
| `environment.py` | `REWRITE` | benchmark evaluator contracts remain benchmark-owned; generic surface contracts move out |
| remaining `external_smoke` manifest, admission, runners, reporting, pacing, contracts and CLI | `KEEP_MOVE` | benchmark harness/reporting |

The split is required because `BrowserGymMiniWobEnvironment.open()` currently
imports `REVIEWED_TASK_IDS` and rejects tasks outside that fixed manifest. That
admission is valid benchmark policy but cannot live in a reusable product
surface. T2 must inject admitted task identity and keep the surface ignorant of
case lists. This is an owner split, not a compatibility layer.

Production consumers to switch in T2 are:

- `benchmarks/external_smoke/{adapter_conformance,adapter_reporting,environment,live_reporting,live_runner}.py`;
- `benchmarks/external_breadth/{coverage_probe,runner,semantic_inventory_targeted}.py`;
- every internal import among the BrowserGym files listed above.

Lexical/path consumers that AST import scanning alone does not cover are
`tests/architecture/test_target_runtime_composition.py`,
`tests/architecture/test_set_objective_generalization_redlines.py`,
`tests/test_import_order_regression.py` and
`tests/test_semantic_inventory_architecture.py`; all are `REWRITE` in T2.

## Test and fixture disposition

### Thin target wrapper consumers — `REWRITE` in T1

Every direct `AgentEpisodeRunner` test below keeps its behavioral invariant but
uses `AgentLoop.start/run`, `TargetRuntime`, or `AgentRunSession` according to
the tested boundary:

```text
test_action_evaluation_lineage.py
test_action_paging.py
test_agent_decision_context.py
test_agent_loop.py
test_agent_progress_loop.py
test_browsergym_local_progress_regression.py
test_browsergym_m46b_verifier_conformance.py
test_browsergym_verifier.py
test_confirmation_continuation.py
test_confirmation_reselection.py
test_control_feedback_runtime_integration.py
test_control_transition.py
test_control_transition_failures.py
test_dom_agent_loop_e2e.py
test_dynamic_semantic_task_progression.py
test_dynamic_tool_runtime_integration.py
test_live_model_policy_smoke.py
test_m2_model_boundary_closure.py
test_model_backed_agent_policy.py
test_model_policy_admission.py
test_model_policy_http_bridge.py
test_model_policy_ollama_bridge.py
test_model_policy_runtime_integration.py
test_model_port_decision_bridge.py
test_negative_claim_coverage_gate.py
test_observation_acquisition_lifecycle.py
test_session_snapshot_authority.py
test_surface_symmetry_matrix.py
test_task_evaluation_loop_policy.py
test_task_evaluation_validation.py
test_terminal_session_immutability.py
test_unified_source_orchestration.py
test_visual_agent_loop_e2e.py
test_visual_agent_loop_negatives.py
test_world_evidence_validation.py
test_wot_agent_loop_e2e.py
test_wot_agent_loop_negatives.py
```

`tests/test_target_runtime_client.py` is `REWRITE` as the façade lifecycle
suite. `tests/test_target_cli.py`, `tests/test_reference_target_pricing.py` and
`tests/test_reference_target_settings.py` are `REWRITE` against the same
façade; the client class itself is not retained for the tests.

### Legacy-only test consumers

The static graph found 89 test files directly importing the legacy-only
production set. These six are `REWRITE` because their invariant remains in the
target topology:

```text
architecture/test_runtime_redlines.py
test_dom_document_projection.py
test_reference_target_pricing.py
test_reference_target_settings.py
test_task_api.py
test_visual_contracts.py
```

The remaining direct consumers are `DELETE_WITH_OWNER`; target-owned action,
world, continuation, evaluation and surface suites already own the supported
replacement invariants:

```text
test_action_authority.py
test_action_choice_catalog.py
test_action_progress_index.py
test_active_perception.py
test_active_perception_coordinator.py
test_active_perception_flow.py
test_active_step_scope.py
test_adaptive_routing_benchmark.py
test_approval_contracts.py
test_authoritative_device_route.py
test_benchmark_metrics.py
test_benchmark_runner.py
test_browsergym_adapter.py
test_browsergym_adaptive_metrics.py
test_browsergym_encoder.py
test_browsergym_episode_runner.py
test_browsergym_observer.py
test_browsergym_report.py
test_canonical_observation_builder.py
test_collection_window.py
test_compatibility_semantic_compilers.py
test_container_conformance.py
test_contract_execution_loop.py
test_contracts.py
test_coordinator.py
test_criteria.py
test_criterion_evidence_runtime.py
test_cross_surface_coordinator.py
test_decision_constraints.py
test_evaluation_audit.py
test_evolution.py
test_evolution_replay.py
test_executors.py
test_failure_envelope.py
test_failure_owner_flow.py
test_generalization.py
test_generalization_evidence.py
test_generic_perception_coordinator.py
test_harness_learning.py
test_intent_compiler.py
test_local_benchmark_mainline.py
test_loop_evaluator.py
test_model_recovery.py
test_p4_c0_product_containment.py
test_p4_c1_truthful_facts.py
test_p4_c2_context_capability_provenance.py
test_p4_c3_transaction_materialization.py
test_p4_c4_dispatch_lifecycle.py
test_p4_c5_cutover.py
test_p5_0e_hardening.py
test_perception_session.py
test_planner_model_orchestrator.py
test_planner_response_contracts.py
test_planning.py
test_planning_request.py
test_pricing_gold_path.py
test_progress_stage_protocol.py
test_proposal_recovery_policy.py
test_r8_architecture_boundaries.py
test_recovery.py
test_recovery_coordinator.py
test_recovery_evolution.py
test_recovery_phase.py
test_recovery_trace_projection.py
test_routing.py
test_runtime_evidence.py
test_safety_approval.py
test_scope_authorization.py
test_source_context_and_semantic_audit.py
test_source_envelope.py
test_task_completion_evaluator.py
test_task_pipeline_multistage.py
test_task_plan_generators.py
test_task_plan_progress.py
test_task_planning_benchmark.py
test_task_skill_coordinator.py
test_task_skills.py
test_task_spec_authority.py
test_trace_writer.py
test_typed_runtime_deltas.py
test_uncertain_effect_coordinator.py
test_unified_fallback.py
test_verification_conditions.py
```

### BrowserGym surface tests — `KEEP_MOVE` or `REWRITE` in T2

The following tests remain, move under surface/conformance ownership and update
imports to `surfaces.browsergym`: `browsergym_adapter_support.py`,
`test_browsergym_active_capture_conformance.py`,
`test_browsergym_canonical_semantics.py`, `test_browsergym_currentness.py`,
`test_browsergym_execution.py`, `test_browsergym_m46a_currentness_conformance.py`,
`test_browsergym_m46b_verifier_conformance.py`, `test_browsergym_verifier.py`,
`test_browsergym_vision_escalation.py`, `test_browsergym_visual_binding.py`,
`test_browsergym_world_projection.py`, `test_grounded_tools_v2.py`,
`test_interaction_capability_onboarding.py`,
`test_miniwob_breadth_oracle_isolation.py`, `test_regular_lattice_semantics.py`
and `test_semantic_inventory_targeted.py`.

`test_browsergym_action_evaluator.py` is `REWRITE` to import the product
evaluator directly. `test_browsergym_adapter_readiness.py` and
`test_browsergym_dependency_inventory.py` are `REWRITE` so package capability
checks are surface conformance while task IDs remain benchmark manifest tests.
`test_browsergym_local_progress_regression.py` is already in the T1 wrapper
rewrite set and then follows the T2 import move.

### Test fixtures/support

| Current helper | Consumers | Disposition | Target |
|---|---|---|---|
| `src/affordance_runtime/testing/legacy_static_environment.py` | `tests/test_static_environment.py`, `tests/test_action_batch.py` | `DELETE_WITH_OWNER` | no legacy environment API |
| `src/affordance_runtime/testing/static_environment.py` | target loop/model integration tests and target benchmark support | `REWRITE` | test fake moves to `tests/support/agent`; benchmark simulation owns its explicit fixture under benchmark support |
| `src/affordance_runtime/testing/failure_injection.py` | migrated-environment tests | `KEEP_MOVE` | `tests/support/world` |
| `tests/target_agent_loop_support.py` | target loop/evaluation tests | `KEEP_MOVE` | `tests/support/agent` |
| `tests/model_policy_support.py` | model policy tests | `KEEP_MOVE` | `tests/support/model` |
| `tests/browsergym_adapter_support.py` | BrowserGym surface tests | `KEEP_MOVE` | `tests/support/surfaces/browsergym` |

No production core imports `affordance_runtime.testing`; active benchmark
modules currently do, so T2 must remove those imports before the production
`testing` package is deleted.

## Script disposition

The nine scripts with direct legacy-only imports are
`browsergym_bridge_smoke.py`, `chromium_smoke.py`, `generalization_smoke.py`,
`run_browsergym_generalist_smoke.py`, `run_g5_runtime_rollout.py`,
`run_generalist_local_e2e.py`, `run_intent_compilation.py`,
`run_m85_live_conflict.py` and `run_m85_live_visual_drag.py`. They are all
`DELETE_WITH_OWNER`; their historical evidence remains.

`run_step13_visual_gate.py`, `run_miniwob_verifier_14.py` and current target
benchmark CLIs are `KEEP_MOVE` under benchmark scripts, with BrowserGym imports
updated in T2. `check_evidence.py`, report comparison, isolated conformance and
provider-policy utilities are `KEEP_MOVE` when they do not construct a runtime.
`recovery_cascade_evolution.py` and `classify_planner_failures.py` are
`DELETE_WITH_OWNER` with the legacy recovery/planner evidence path.

## Architecture test changes by slice

| Test | Current truth | Required disposition |
|---|---|---|
| `architecture/test_target_runtime_composition.py` | correctly forbids benchmark loop construction, but names root target wrappers and benchmark-owned BrowserGym path | `REWRITE` in T1/T2 for `app` and `surfaces/browsergym` |
| `architecture/test_runtime_redlines.py` | protects old contracts/Coordinator details | replace with physical absence/import redlines in T3 |
| `test_target_core_boundaries.py` | target core direction is valid | `KEEP_MOVE`; extend after T1/T2 |
| `test_browsergym_oracle_isolation.py` | forbids alternate loop construction | `KEEP_MOVE`; update surface path in T2 |
| documentation/manifest governance | current-doc ownership is valid | `KEEP_MOVE`; add this evidence record |

T1 must add redlines for one public façade/composition/loop/session path and
physical absence of the two pass-through wrappers. T2 must add the
`surfaces/browsergym` owner boundary and forbid product surface code below
`benchmarks`. T3 must assert physical absence of every deleted module rather
than preserve import-compatible aliases.

## Deletion sequence and exit

| Slice | Files/consumers switched before deletion | Planned deletion |
|---|---|---|
| T1 | root exports/CLI, target product and benchmark composition callers, wrapper tests | `TargetRuntimeClient`, `AgentEpisodeRunner`, mixed CLI exports and legacy product command exposure |
| T2 | active benchmark BrowserGym imports and surface/conformance tests | benchmark-path reusable implementation and action-evaluator alias after owner split |
| T3a | root CLI legacy command handlers, old benchmark modules, scripts and tests | Coordinator/composition/runtime-client cluster and historical executable benchmarks |
| T3b | remaining staged planning/perception/execution/progress/recovery imports and tests | phase, planner, recovery, transaction and compatibility clusters listed above |
| T4 | all imports/tests/docs of surviving files | physical owner moves only; no semantic compatibility shims |

T0 has no unresolved file bucket. It does identify one mandatory implementation
split: BrowserGym surface mechanics and MiniWoB manifest/verifier policy cannot
move as one file owner. This does not block T1. It blocks claiming T2 complete
until the split and its conformance tests are atomic.

T2 completed that exact split. The implementation and deletion record is
[Target Runtime topology T2 — BrowserGym surface cutover](2026-08-15-target-runtime-topology-t2-surface-cutover.md).

This inventory does not admit new interaction actions, StateFact closure or
effect-authority closure. The known broad `activate` structural-delta evaluator
behavior remains outside topology claims and continues to block new action
families.
