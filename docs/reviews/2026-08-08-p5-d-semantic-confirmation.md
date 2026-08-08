# P5-D Semantic Confirmation and Effect-Certainty Record

> **Lifecycle:** CURRENT REVISION-SCOPED IMPLEMENTATION RECORD
> **Start:** `codex/migrate-world-interaction-capabilities@d435250e25f1d1c07ffd0f2558affcbdba4983a3`
> **D0 commit:** `e01bd5d` (`refactor: close confirmation prerequisites`)
> **P5-D commit:** `feat: add semantic confirmation continuation` (this record is contained in that commit; its SHA is reported by the final Git evidence)
> **Remote CI attestation:** unavailable

## Closed scope

- Authority/status/queue/README truth now records P5-A1–A4 complete
  non-default, P5-B minimums complete for DOM/Visual full digest/WoT local HTTP
  JSON, P5-C1–C3 matrix proven, C4 fusion deferred, and small C5 state complete.
- Target action certainty is exactly `EFFECT_CONFIRMED`,
  `NO_EFFECT_CONFIRMED`, `UNKNOWN`, or `REJECTED`; the ambiguous target
  `NOT_VERIFIED` status was removed.
- `ActionResult` and `WotTransportResult` constructors enforce dispatch/status,
  success, and error invariants while permitting a sent HTTP/business failure.
- WoT validates property values against the finite TD schema before publishing
  facts, uses kind-qualified source-local target IDs, rejects unsupported HTTP
  routes/payloads before send, and maps unclassified effectful port exceptions
  to `SENT_UNKNOWN`. Effectful action rate limiting exists; property-read
  scheduling/rate limiting does not.
- `risk/` owns ALLOW/NEEDS_CONFIRMATION/BLOCK plus semantic subject hashing.
  The subject includes action, target, destination, normalized parameters,
  effects, Runtime risk, and consequence categories. It excludes observation,
  option, binding, selector, coordinate/bbox, href/method, backend,
  screenshot/TD digest, and all credential material.
- `confirmation/` owns typed request/decision contracts and semantic summaries.
  Decisions bind confirmation ID and subject ID; wrong, stale, denied, or reused
  decisions fail closed. There is at most one pending request per run.
- `AgentRunSession` is a single-process, single-task, single-environment
  continuation object. It has no serialization, durable ledger, database,
  global registry, approval token, signing, transaction, or cross-process resume.
- CONFIRM performs fresh observation, task evaluation, ActionSpace rebuild,
  semantic subject recomputation, and current-route binding. DOM selector,
  Visual region/point/screenshot identity, and WoT TD form/href can change while
  the confirmed semantic subject remains stable; the current route executes once.
- `NOT_SENT` does not consume confirmation and may fresh-rebind within budget.
  `SENT` and `SENT_UNKNOWN` consume it. `SENT_UNKNOWN + EFFECT_CONFIRMED`
  continues once; `SENT_UNKNOWN + NO_EFFECT_CONFIRMED` requires a new
  confirmation if policy selects the action again; `UNKNOWN` waits for the user
  with the unknown request retained and no duplicate attempt.
- DOM, Visual, and WoT use the same RiskPolicy, ConfirmationRequest,
  AgentRunSession, AgentLoop, deterministic policy, and task evaluator.
  Confirmation representations exclude all private routes and credentials.
- Architecture gates cover target core, risk, confirmation, Visual, and WoT:
  files above 350 lines and functions above 80 lines fail, as do forbidden
  adapter/agent/legacy/benchmark dependency directions.

## Status and exclusions

```text
DOM_single_surface: CLOSED
Visual_single_surface: CLOSED_FOR_FULL_DIGEST_PROFILE
WoT_single_surface: CLOSED_FOR_LOCAL_HTTP_JSON_SIMULATION
three_surface_deterministic_matrix: PROVEN
P5_D_semantic_confirmation: CLOSED
model_backed_target_policy: NOT_STARTED
new_loop_benchmark_harness: NOT_STARTED
semantic_fusion: NOT_STARTED
long_horizon: NOT_STARTED
ActionBatch: NOT_STARTED
external_benchmark: BLOCKED
default_cutover: NOT_READY
```

No model-backed AgentPolicy, production model evaluator composition, semantic
fusion, ActionBatch integration, long-range planning, external benchmark,
durable resume, authorization platform, default-path switch, merge, or old-core
deletion was performed. Exact validation commands and final HEAD are recorded
in the task's final Git evidence; external benchmark admission additionally
requires the model-backed target policy/evaluators, new-loop harness, and
exact-head remote CI evidence.
