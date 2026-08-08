# P5-M0.1.1 context operational closure

## Status attestation

- remote_ci_attestation: unavailable
- implementation path: non-default target AgentLoop
- default product path: unchanged retained Coordinator baseline

## Closed profile

- P5-M0.1 structure: `CLOSED`
- P5-M0.1.1 one-shot context epoch: `CLOSED`
- traversable action paging: `CLOSED_FOR_DETERMINISTIC_CURSOR_PAGER`
- context projection coherence: `CLOSED`
- LocalObjective relevance: `CLOSED_FOR_EXPLICIT_HINT_PROFILE`
- source assurance: `CLOSED_FOR_DOM_VISUAL_WOT_PROFILES`
- targeted provider acquisition: `DEFERRED`
- confirmation dominance: `NOT_STARTED`; exact semantic-subject equality remains current
- model-backed AgentPolicy: `NOT_STARTED`
- production evaluators: `NOT_STARTED`
- external benchmark: `BLOCKED`
- default cutover: `NOT_READY`

## Responsibility slices

- `M0.1.1-A`: context/session identity and narrow observation/state mutation
  owners accept current session state and previous observation identity; they
  emit a one-shot context ID or explicit fresh-observation failure. They do not
  own CAS, a registry, persistence, provider targeting or a StateKernel.
- `M0.1.1-B`: the Runtime-private deterministic pager and model-boundary action
  projection accept an Internal ActionSpace, explicit filters/objective and
  Runtime-issued cursor; they emit a traversable page and current-page-only
  bounded view. They do not execute or decide legality.
- `M0.1.1-C`: task/world projection, explicit-hint relevance, source profiles,
  decision/history projection and evidence-ref canonicalization emit truthful
  bounded public context. They do not change effects, risk, confirmation or
  completion authority.

## Runtime behavior

- Every actual `AgentPolicy.decide(context)` call advances a monotonic session
  generation. Page A → B → A cannot revive the first A context; stale and replayed
  decisions make zero executor and surface-probe calls.
- RequestObservation, Wait, binding/currentness refresh, confirmation refresh and
  post-action observation all reject reuse of the previous acquisition identity.
- `has_more` always carries a filter/objective/budget-bound opaque `next_cursor`.
  Current page identity binds cursor/offset, visible IDs, filters and relevance
  identity. Selection remains limited to the current page.
- Context budgets drive action count and destination truncation. Only current-page
  action schemas are projected, and current-page target/destination identities are
  pinned into ModelWorld.
- Task sections and per-target state/relations report truthful totals/truncation.
  Compaction preserves current-page targets, active objective, pending summaries
  and newest history before lower-priority context.
- Acquisition capability is independent of whether the current acquisition failed;
  assurance dominance is authoritative ≥ structural ≥ weak. Source summaries add
  current/stale freshness and conflict status without granting action authority.
- RequestObservation, RequestActionPage, AskUser, ProposeDone, Wait and Abort enter
  recurrent history only as bounded semantic summaries. Unicode fact/artifact
  identities use canonical value-free evidence refs.

## Explicit non-starts

No provider SDK, model-backed AgentPolicy, production model evaluator, semantic
entailment/fusion, targeted provider acquisition, confirmation dominance,
ActionBatch integration, long-horizon planner, benchmark harness, external
benchmark admission, default cutover or old-core deletion was started.

## Validation

- M0.1.1-A focused/architecture exit: `90 passed`
- M0.1.1-B focused/cross-surface exit: `79 passed`
- M0.1.1-C focused/architecture/documentation exit: `128 passed`
- exact collection: `1429 tests collected`
- explicit shard proof: A `715` IDs, B `714` IDs, union `1429`, intersection `0`
- explicit shard execution: A `715 passed`; B `714 passed`
- DOM E2E: `1 passed`
- Visual E2E: `1 passed`
- WoT E2E: `1 passed`
- surface symmetry: `7 passed`
- confirmation continuation: `8 passed`
- target core boundaries: `8 passed`
- required legacy `--runxfail`: `1 passed`
- `ruff check src tests`: passed
- `mypy src`: passed for `275` source files with two pre-existing unchecked-body notes
- `git diff --check`: passed
- smart-room Compose config: passed

The complete local suite was executed through the two proven complementary
explicit node-id manifests. No single-process full-suite pass is claimed.
Remote CI status is unavailable.
