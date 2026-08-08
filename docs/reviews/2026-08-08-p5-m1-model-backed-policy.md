# P5-M1 model-backed policy implementation

Date: 2026-08-08

## Scope and status

- P5-M0.1/M0.1.1: `CLOSED`
- P5-M1 model policy core: `CLOSED_FOR_INJECTED_STRUCTURED_MODEL_PORT`
- real provider profile: `NOT_STARTED`
- deterministic evaluators: `RETAINED`
- production model evaluators: `NOT_STARTED`
- semantic entailment: `NOT_STARTED`
- benchmark harness: `NOT_STARTED`
- external benchmark: `BLOCKED`
- default cutover: `NOT_READY`
- remote_ci_attestation: `unavailable`

## Implemented boundary

`ModelBackedAgentPolicy` serializes one disposable AgentContext as canonical
bounded JSON, sends one request through an injected `StructuredDecisionModelPort`,
and accepts only the strict SelectAction/RequestObservation/RequestActionPage/
AskUser/ProposeDone/Wait/Abort response union. Unknown fields, missing fields,
stale context IDs, malformed JSON and nested private execution parameters fail
as typed model failures. There is no automatic retry, raw response history, or
chain-of-thought persistence.

M1-0 additionally binds each InternalActionPage to its model-visible destination
slice, admits only the exact current continuation cursor, weights only visible
destinations, builds a coherent single-action execution page after confirmation,
projects only evaluation-evidence-backed verified facts, validates the finite
parameter-schema contract at construction, obscures intent source references,
and exposes remaining wait budget.

## Internal proof profile

The same policy class, canonical serializer and strict parser complete one-action
DOM, Visual and WoT local-simulation tasks. Scripted structured-response ports
also exercise paging, fresh observation, fake wait, ProposeDone validation,
stale context, hidden action/destination, malformed/private parameters, typed
provider failures, and Runtime-owned confirmation. The existing deterministic
ActionEvaluator, TaskEvaluator, RiskPolicy, confirmation and AgentLoop remain
the execution and completion authorities.

These are injected/local fixture proofs, not a real-model generalization claim.
Destination paging, targeted observation acquisition, provider retry platforms,
production model evaluators, semantic evidence entailment, confirmation
dominance, semantic fusion, long-horizon planning and ActionBatch remain deferred.

## Validation

- M1-0 focused admission/projection/confirmation suites: `142 passed`
- model-policy serializer/parser/policy focused suite: `17 passed`
- model-policy Runtime plus three-surface focused proof: `57 passed`
- exact collection: `1474 tests`
- deterministic file manifests: `173 = 87 + 86` files
- node-set proof: `1474 = 797 + 677`, intersection/missing/extra all `0`
- shard A: `797 passed`
- shard B: `677 passed`
- full pytest: `1474 passed`
- DOM model-policy E2E: `2 passed` including retained deterministic proof
- Visual model-policy E2E: `2 passed` including retained deterministic proof
- WoT model-policy E2E: `2 passed` including retained deterministic proof
- surface symmetry: `7 passed`
- confirmation continuation: `8 passed`
- target-core boundaries: `9 passed`
- legacy `--runxfail`: `1 passed`
- Ruff, mypy, diff check and smart-room compose config: passed

No external benchmark was run. Exact-head remote CI status was unavailable.
