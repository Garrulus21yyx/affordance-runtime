# P5-M0.1 AgentContext implementation review

## Execution plan

- `M0.1-A` — `done`
  - Canonical owners: task contracts and model-boundary projection; AgentLoop remains orchestration-only.
  - Inputs: `TaskGoal`, task/material definitions, action parameter schemas, turn/evidence data, existing loop collaborators.
  - Outputs: bounded public projections, canonical evidence references, behavior-preserving execution-cycle extraction, architecture gates.
  - Forbidden responsibilities: model calls, context construction, paging, source classification, evidence entailment, surface-specific behavior.
- `M0.1-B` — `done`
  - Canonical owners: intent context, context budgets/views/builder, typed decisions, session revision state and decision control.
  - Inputs: authoritative runtime state, current observation/action space, optional intent context, evaluator outcomes.
  - Outputs: immutable disposable `AgentContext`, stable `ContextIdentity`, typed decisions, stale/replay zero-call admission.
  - Forbidden responsibilities: runtime authority, binding storage, long-horizon planning, semantic adjudication, targeted provider selection.
- `M0.1-C` — `done`
  - Canonical owners: observation source profiles, relevance policy, internal action pager, final context integration.
  - Inputs: legal/current internal action space, explicit local-objective hints, observation source metadata, typed page requests.
  - Outputs: truthful source summaries, deterministic relevance/ranking/paging, current-page admission, integration evidence and docs.
  - Forbidden responsibilities: legality/risk changes, action execution, semantic fusion, confirmation dominance, provider fallback.

## Status attestation

- remote_ci_attestation: unavailable

## Implementation status

- P5-M0.1 AgentContext: `CLOSED`
- ContextIdentity/stale decision: `CLOSED`
- IntentContext: `CLOSED_FOR_BOUNDED_CONTEXT_ONLY`
- LocalObjective relevance: `CLOSED_FOR_CURRENT_EXPLICIT_HINT_PROFILE`
- action paging: `CLOSED_FOR_DETERMINISTIC_PAGER`
- source assurance: `CLOSED_FOR_DOM_VISUAL_WOT_PROFILES`
- targeted observation provider selection: `DEFERRED`
- confirmation dominance: `NOT_STARTED`; exact semantic-subject equality remains current
- model-backed AgentPolicy: `NOT_STARTED`
- production model evaluators: `NOT_STARTED`
- external benchmark: `BLOCKED`
- default cutover: `NOT_READY`

The implementation remains on the non-default target path. It does not add a
provider SDK, criterion semantic entailment, semantic fusion, ActionBatch,
long-horizon planning, a durable context store, or new legacy-core authority.

## Runtime behavior closed

- Runtime rebuilds a disposable immutable AgentContext each policy turn from
  current task, observation, action space/page, progress and pending revisions.
- Every typed decision carries `context_id`; stale or replayed decisions make
  zero executor and surface-probe calls. BoundActionRequest retains the accepted
  context ID and is checked immediately before execution.
- Intent, task, model-world, progress, pending, budget, history and action-page
  projections are bounded and private-route-free; total serialized context size
  has a fixed 64 KiB default cap with truthful truncation metadata.
- Relevance runs only after TaskGoal legality/currentness and never changes
  Internal ActionSpace membership. The deterministic pager supports exact
  target/role filters and bounded case-insensitive public query.
- DOM, Visual and WoT expose structural, visual and environment-state quality
  profiles respectively. These profiles do not grant effects, lower risk or
  bypass confirmation.
- RequestObservation validates an offered modality/assurance capability and
  currently performs a full fresh observation. Wait uses an injectable clock
  boundary and fresh observation. ProposeDone resolves current evidence and
  re-enters validated TaskEvaluator control.

## Validation

- M0.1-A focused/affected suites: `52 passed`
- M0.1-B focused/affected suites: `188 passed`
- M0.1-C focused/regression suite: `77 passed`
- complete local suite, two complementary no-deselect file batches:
  `761 passed` + `624 passed` = `1385 passed`
- literal single-process `pytest -q`: executed twice; the host SIGKILLed the
  process at approximately 72–73% without a pytest failure. Two unrelated Rod
  Chromium renderers predating this run each retained approximately 1 GiB RSS;
  they were inspected but not terminated because they are outside repository scope.
- required DOM E2E: `1 passed`
- required Visual E2E: `1 passed`
- required WoT E2E: `1 passed`
- required surface symmetry matrix: `7 passed`
- required confirmation continuation: `8 passed`
- required target-core boundaries: `8 passed`
- required local benchmark mainline with `--runxfail`: `1 passed`
- `ruff check src tests`: passed
- `mypy src`: passed (`272` source files; two pre-existing unchecked-body notes)
- `git diff --check`: passed
- smart-room `docker compose ... config`: passed

## Changed-file ledger

- This review and plan file.
- M0.1-A: task/material contracts, public projection and schema projection, evidence namespace,
  execution-cycle extraction, focused projection/evidence/architecture tests.
- M0.1-B: intent context, projection budgets and byte cap, model world/progress/pending/budget
  views, context identity/builder, action-space identity, typed decisions, recurrent policy loop,
  stale/replay guard, request context binding, fake wait boundary, and migrated consumers.
- M0.1-C: source profiles, source summaries/capabilities, explicit-hint relevance,
  deterministic action pager, current-page admission, page/context freshness,
  cross-surface context symmetry, documentation and final regression evidence.
