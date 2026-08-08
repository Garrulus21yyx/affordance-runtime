# P5-M0 Model-Safe Policy and Evaluator Boundary Record

> **Lifecycle:** CURRENT REVISION-SCOPED IMPLEMENTATION RECORD
> **Start:** `codex/migrate-world-interaction-capabilities@d5a49734e6d01f54aaee31899459056a145d563f`
> **Implementation commit:** `refactor: add model-safe policy and evaluator boundaries` (this record is contained in that commit; final SHA is reported by Git evidence)
> **Remote CI attestation:** unavailable

## Closed scope

- AgentTaskView exposes bounded semantic task fields, stable criterion IDs,
  requested output IDs, and public material references. Secret-like inputs and
  private paths are redacted only in the model projection.
- AgentActionSpaceView contains opaque action IDs, semantic actions/targets,
  labeled semantic destinations, public parameter schemas, effects, risk, and
  barriers. It excludes eligible binding IDs, schema/observation identity,
  surface/backend/executor details, private routes, digests, and credentials.
  Internal ActionSpace remains the only admission authority.
- AgentTurnView exposes bounded semantic history and statuses without request,
  observation, backend, adapter-evidence, binding, or credential data.
  AgentPlanView exposes semantic milestones only. AgentPolicy now receives
  these views plus AgentWorldView, never TaskGoal/ActionSpace/Turn/TaskPlan.
- Destination IDs are nonblank, unique, sorted semantic IDs without private
  route markers. ActionBinding, ActionOption, AdmittedActionSelection,
  BoundActionRequest, and WorldObservation independently enforce membership
  and current destination-target existence.
- A LOW-risk, empty-effect `read` in the OBSERVATION category is legal for an
  effectful task without granting a business effect. READ_ONLY remains limited
  to that form; effect-bearing or elevated-risk reads do not gain the exception.
- WorldEvidenceIndex is immutable and observation-scoped. It indexes StateFact
  IDs and controlled `artifact:<source-observation>:<key>` refs, not artifact
  values. Blank, duplicate, oversized, secret-bearing, invented, or before-only
  action evidence refs fail closed against the fresh after observation.
- TaskEvaluation now binds task ID, observation ID, stable criterion proposals,
  completion evidence, and evaluated outputs. Resolved criterion statuses need
  current evidence. COMPLETE requires the complete required criterion set and
  deterministic validation; INCOMPLETE cannot claim all criteria satisfied.
- Requested outputs are unique and evidence-bound. The declared minimum
  EvaluationSpec integrity profile requires an explicit regular-file path and
  matching streamed SHA-256. Missing output/evidence/file, unsupported shape,
  or digest mismatch rejects COMPLETE; receipts do not replace file validation.
- ModelFailure and model evaluator input views are typed, bounded, provider
  neutral, and private-payload-free. No provider SDK or model call was added.
- DOM, Visual full-digest, and WoT local HTTP JSON use equivalent AgentTaskView
  and policy-facing semantic action/effect/risk vocabulary while private routes
  stay absent. Source-local target identities remain distinct because semantic
  fusion was not started; this is protocol symmetry, not model generalization.
- Target, model-boundary, evaluation, Visual, and WoT owners remain below the
  350-line file and 80-line function gates. Dependency tests reject concrete
  surface/executor/binder, benchmark, fixture, legacy-core, and reverse imports.

## Validation

Exact implementation-head validation includes the focused model/task/action/
destination/evidence/output suites, DOM/Visual/WoT E2E and symmetry suites,
documentation and architecture gates, the required legacy `--runxfail` test,
full pytest, Ruff, mypy, `git diff --check`, and smart-room compose config.
No external benchmark was run.

## Status and exclusions

```text
P5_D6_1: CLOSED
P5_M0_model_input_boundary: CLOSED
P5_M0_evaluator_trust_boundary: CLOSED
target_output_validation: CLOSED_FOR_DECLARED_MINIMUM
model_backed_AgentPolicy: NOT_STARTED
production_model_evaluators: NOT_STARTED
new_loop_benchmark_harness: NOT_STARTED
semantic_fusion: NOT_STARTED
long_horizon: NOT_STARTED
ActionBatch: NOT_STARTED
external_benchmark: BLOCKED
default_cutover: NOT_READY
```

The default product path remains the legacy Coordinator baseline. External
benchmark admission still requires M0, a model-backed target AgentPolicy,
production evaluator composition, a new-AgentLoop harness, and exact-head
remote CI. No transaction, event core, proof graph, ledger, durable resume,
registry, token platform, semantic fusion, cross-surface fallback, ActionBatch,
default cutover, merge, PR-state change, or old-core deletion was performed.
