# Trace and Evaluation Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** trace events, evidence locations, typed evaluation, external evaluation, and replay

The acquisition, output, dispatch/effect, checkpoint, and strict-replay clauses
below include target contracts spanning future hardening and not-yet-started P5-R
recovery. They are acceptance constraints, not an assertion that every type or
persistence path is already implemented.

Only final-contract hash identity, stale zero-call, receipt/effect separation,
verifier-backed completion and no-blind-retry formed the P4 semantic gate; that
MVP gate is now closed and P5 admission is unblocked. Permit/fencing/context/
collateral/manifest clauses are future hardening, not P5 blockers.

## 1. Trace rule

Trace records committed Runtime facts in causal order. It is an offline
consumer of authoritative transitions, not a completion or recovery owner.

Each event carries run/task identity, relevant revision/epoch/contract refs,
event type, typed payload, causal parent refs, timestamp/sequence, and artifact
refs. Raw user request content is not copied by default; SourceEnvelope refs,
hashes, and lengths preserve identity without broad disclosure.

Action-near events always project final contract hash, typed transport/effect
state and approval status. When an extended scenario enables them, events may
also project opaque context/surface/coordinate/lease/attempt/permit refs. Refs and
digests provide causality; they do not turn historical data into live authority.

## 2. Trace privacy and truthful acquisition

Trace follows data minimization. Cookies, tokens, credentials, clipboard
contents, secrets, unredacted typed input, and live browser/app/window handles
are never trace payloads or checkpoint fields. Raw screenshots, video, DOM/AX
trees, OCR text, network bodies, and sensitive output values are referenced by
digest and access-controlled artifact ref only when policy requires retention;
the default trace projection is bounded and redacted. Artifact storage and
trace access obey explicit encryption, access, redaction, and retention policy.

Each observation event records adapter/version, attempted source and
`scope_ref`, limits/budgets, item count, truncation/error, and adapter-owned
`SourceCoverage`. Redaction or omission from trace is not evidence that
acquisition was complete. Missing/malformed coverage remains `UNKNOWN`; neither
the trace projector nor `CanonicalObservationBuilder` may synthesize
`COMPLETE` from the presence of facts, candidates, or an artifact ref.

## 3. Transport, effect, step, and task are distinct

| Layer | Question | Result |
|---|---|---|
| transport | can Runtime prove whether the send boundary was crossed? | typed `ExecutionReceipt` with `NOT_SENT`, `SENT`, or `SENT_UNKNOWN`; provider acknowledgement remains receipt detail |
| action effect | did this exact attempt's expected effect occur? | `NOT_OCCURRED`, `OCCURRED`, or `STILL_UNCERTAIN` plus CriterionEvaluation |
| step | does StepSpec.completion hold? | CriterionEvaluation |
| task | does full TaskSpec.success and required-output closure hold with constraints/rechecks? | TaskCompletionEvaluation |

Every normal and exceptional Executor exit must return a typed receipt. If the
Runtime cannot prove the send boundary was not crossed, recovery derives
`SENT_UNKNOWN`, never `NOT_SENT`. `SENT` or a provider
acknowledgement proves only transport; `OCCURRED` and `NOT_OCCURRED` both
require effect/risk-specific assurance bound to attempt, transaction, contract,
resource/version, idempotency identity, and backend-request identity when
available.

No result substitutes for another. A boolean backend `success`, toast, plan
exhaustion, final prose, or external reward is not effect truth or
TaskCompleted.

## 4. Criterion policy

Each criterion leaf uses the minimum orthogonal policy:

```text
SatisfactionMode     = STATE_HOLDS | ACTION_CAUSED
EvidenceValidityMode = CURRENT_OBSERVATION | RECENT_ACTION | DURABLE | FINAL_RECHECK
AssuranceLevel       = WEAK | STRUCTURAL | AUTHORITATIVE
```

Status is one of `SATISFIED`, `UNSATISFIED`, `UNKNOWN`, `STALE`, `CONFLICT`,
`UNSUPPORTED`, or `ERROR`. No evidence means UNKNOWN; disabled evaluation never
creates synthetic PASSED.

`RECENT_ACTION` is valid only for `ACTION_CAUSED` with required causal lineage.
It proves that a bounded Runtime-owned ActionOutcome caused an effect in the
past; it never proves that the state still holds. Current state needs a separate
`STATE_HOLDS + CURRENT_OBSERVATION` leaf. `FINAL_RECHECK` requires authoritative
source, strength, and assurance.

## 5. Evidence locations

1. Current observation evidence stays in canonical UnifiedObservation.
2. Contract-bound causality stays in a bounded RecentActionOutcome index.
3. Artifact hash, resource/version, transaction ID, external final recheck, or
   human confirmation may enter the small DurableEvidenceStore.

Only durable evidence crosses observation epochs. Historical current-state
evidence is admitted only when the criterion validity mode explicitly permits
it.

## 6. Providers and admission

DOM, AX, visual/SVG, WoT property state, API/device, artifact, network,
external, and optional model/human providers extract evidence with source,
freshness, assurance, and observed value metadata. Typed predicate evaluators
own operators.

WOT_ACTION_RESULT is a contract-bound receipt/outcome that records dispatch
and, when qualified, recent causal evidence. It cannot complete a criterion or
task by itself. A state-holds criterion still needs fresh
`WOT_PROPERTY_STATE`/API/device evidence, and a high-risk external effect still
needs the declared authoritative `FINAL_RECHECK` or human confirmation.

EvidenceAdmissionPolicy decides whether an evidence record is usable for one
typed criterion ID. It does not own AllOf/AnyOf/root completion semantics.
ModelVerifier provides evidence only; model-only evidence cannot complete
high-risk external effects.

The canonical operator vocabulary and phase-specific provider coverage are
separate. The first mechanical baseline covers equals, contains, prefix/suffix,
between, exists/absent, selected/checked, changed, and Boolean composition.
Registered operators without a qualified provider return `UNSUPPORTED`; they
do not fall back to description matching or automatic model approval.

## 7. Output materialization and task completion

RuntimeCommitter may emit TaskCompleted only when TaskCompletionEvaluator
returns:

```text
TaskSpec.success root == SATISFIED
AND no required constraint violation
AND no unresolved external effect
AND all required FINAL_RECHECK completed
AND all required outputs are materialized and source-bound when required
```

Each required OutputSpec has a stable output ID and typed materialization
criterion. Output results are part of TaskCompletionEvaluation. Planner prose,
an unstructured final summary, or a satisfied environment state cannot replace
a required structured output or its source binding.

`OutputSpec` declares what is required; `OutputMaterialization` records what was
actually produced. The latter contains at least output/materialization and spec
refs, schema ID/version, typed value or protected artifact ref, content digest,
source refs, criterion refs, task/step/observation lineage, producer identity,
privacy classification, and redaction/retention policy refs. Sensitive values
remain in the governed artifact/value store while trace and checkpoint retain
only the authorized projection, ref, and digest.

Only a schema-valid, integrity-checked, policy-admitted
`OutputMaterialization` may populate the actual result namespace or satisfy a
required output. Expected-output metadata may be displayed separately, but
`OutputSpec`, a non-empty key, Planner prose, receipt, or trace payload cannot
be converted into `final_result`.

Evaluation runs on the initial canonical observation, completed active step,
new durable evidence, returned external recheck, plan exhaustion, Planner Finish
request, and immediately before every TaskCompleted commit.

## 8. Checkpoint projection

`RunCheckpoint` is a versioned recovery index over committed facts, not a
serialized Runtime or executable snapshot. Its bounded projection may include:

- run/task identity, schema/code/policy/profile/environment digests;
- admitted TaskSpec/TaskPlan/progress/ledger refs and digests, budgets, and
  trace head;
- `last_committed_observation_ref` and observation digest;
- sealed-contract ref/hash and approval request/grant audit refs/status;
- last attempt, dispatch-intent, transport, effect, clarification, and
  `OutputMaterialization` refs/digests.

It does not contain the canonical observation object graph, executable contract
payload, approval token, full `FinalDispatchAdmission`, `DispatchPermit`, credential, raw source/context,
`LiveSurfaceBinding`, `CoordinateBinding`, `SurfaceLease`, DOM/page/backend
handle, or physical-store implementation policy. On restore,
`last_committed_observation_ref` is explicitly historical: it supports audit,
dependency checks, and routing, but cannot prove current state, freshness,
context, coordinates, or task completion. Missing required identity/lifecycle
fields cause rejection; recovery does not infer them from an older schema.

Checkpoint creation is driven from the committed state snapshot. Persistence
may encode and atomically store that immutable projection, but cannot interpret
semantics or manufacture a transition. Resume validation only returns a typed
rejection/fresh-session/effect-reconciliation route; the routed domain owners
perform live work and RuntimeCommitter records its results.

## 9. External evaluation and claims

Benchmark oracles and rewards are stored separately from Runtime status. Reports
bind repository revision, dirty state, environment/assets, profile, provider,
budgets, seeds, missing/unrun episodes, Runtime result, external result, and
official-claim flag.

Historical evidence remains valid only for its exact identity. Replay may
diagnose or test a proposed generic fix; it cannot rewrite the original trace.

## 10. Strict replay

Published strict replay/release claims require exact repository/code revision and dirty-state identity,
contract/schema/policy/provider/evaluator versions and digests, environment and
asset versions, budgets/seeds, observation/evidence artifacts, session-context
requirements, and coordinate-transform inputs. A missing dependency, digest
mismatch, unavailable protected artifact, or incompatible schema rejects strict
replay; an approximate reconstruction must be labeled as a separate simulation,
not the original run.

Replay is diagnostic and append-only. It cannot rewrite committed events,
retroactively grant approval, change an effect settlement, or turn benchmark
reward into Runtime completion. It must not dispatch an effectful action into
the real external environment: use evidence-only evaluation or an explicitly
isolated simulator/sandbox. External benchmark/judge results remain separate
offline facts and cannot settle Runtime effect or task state.

The previous detailed document is archived at
[maintained-pre-consolidation/trace-and-evaluation.md](archive/superseded-2026-08-05/maintained-pre-consolidation/trace-and-evaluation.md).
