# ActionContract Digest Threat Model

> **Lifecycle:** CURRENT REFERENCE THREAT MODEL
> **Implementation scope:** existing ActionContract digest identity and approval-token binding
> **Target status:** legacy transactional-baseline analysis; not a target architecture contract

The unified-world target replaces the god `ActionContract` with semantic
`ActionIntent` plus a small observation-bound `BoundActionRequest`. It retains
request identity for stale/result lineage and semantic identity for human
confirmation, but it does not carry this document's wider
transaction/proof/trace digest model into the target core.

> **MVP scope:** trusted single-process, single-coordinator, serial execution. This
> model protects final-contract immutability and approval/execution hash equality;
> it does not claim malicious-insider, multi-worker, multi-tenant or hard-crash
> dispatch security.

## Boundary

`ActionContract.contract_hash` is the stable digest used to bind an accepted
Runtime action to approval, preflight, execution, typed evaluation, trace, and
recovery evidence. The digest is meaningful only if every hash-critical field is
deeply immutable before the hash is computed.

For the MVP final transaction, digest equality is paired with fresh
snapshot/page/target preflight. Extended execution-context, live-surface,
coordinate, capability-manifest and provenance fields are hash-critical only
when an admitted scenario actually uses them.

## Failure model

The pre-SAR-1 contract object was `frozen=True` only at the dataclass shell. Its
nested `dict` and `list` payloads could still be mutated through either:

- the original caller-owned objects passed into the constructor; or
- the public contract fields returned after construction.

That produced a stale-hash condition:

```text
contract_hash was computed over payload A
payload changed to payload B
contract_hash still identified payload A
compute_hash() now identified payload B
```

This is a correctness and security issue because approval tokens match
`contract_hash`.

The same class of failure occurs when code uses `replace()` or a partial
preflight patch to refresh proof/candidate identity while retaining an old
locator, route, payload, verifier, live surface, coordinate transform, provider
schema, or capability envelope. A hash over that newly mixed object only proves
that the inconsistent mixture was not subsequently modified; it does not prove
same-epoch or semantic consistency.

## Hash-critical fields

SAR-1 treats every present executable field as hash-critical. The MVP always
includes operation, target, final parameters/payload and freshness identity;
the extended fields below are conditional on the adapter/scenario:

- `locator`
- `parameters`
- `preconditions`
- `expected_effects`
- `verifier_plan`
- `required_capabilities`
- `fallback_backends`
- route, grounding, gesture, scope, snapshot/page/target identity fields
- idempotency, compensation, timeout, risk, backend, action, schema version
- execution-context requirement and live-surface generation/owner identity
- document/frame and source/destination coordinate spaces, screenshot/viewport,
  crop/scroll, DPR, zoom, scale, orientation, display/window origin, and
  transform digest
- provider/model/tool/action-schema descriptor identity/version/digest,
  adapter support, effective capability intersection, and current grant refs
- source provenance and trusted-control bindings for values that enter
  effectful fields, plus exact-contract approval requirements; the approval
  grant itself binds the completed contract hash externally
- the deterministic, secret-free RouteBinding: canonical unsigned
  target/destination resource encoding, schema/encoder/route-policy and
  application-payload digests, opaque credential scope, principal/audience, and
  closed late-binding policy digest

Analytics-only data must not be added to `ActionContract`. It belongs in trace
or artifact records.

`verifier_plan` is the current implementation-era field name recorded by this
threat model. The target contract replaces provider planning with typed
`evaluation_requirements`; the immutability and stale-hash rule is unchanged.

## Sealed transaction closure

The target construction path is:

```text
ActionContractDraft
→ full materialization from current committed observation and state view
→ task-authority proof and capability intersection
→ SealedActionContract
→ exact approval of final contract hash H
→ snapshot/page/target/expiry preflight for H
→ serial Executor consumes the same immutable H
```

A sealed contract is non-replaceable and non-patchable. Any observation,
session/surface generation, route, target, parameter, coordinate transform,
provider schema, capability, provenance, verifier, risk, or effect change
requires a new draft, a complete materialization, a new digest, and renewed
admission. Old approval does not migrate when a hash-critical or authority
field changes.

Digest equality does not prove cross-thread revocation ordering. The current MVP
does not claim it: policy/approval/preflight and execution are serialized by one
trusted coordinator. Linearizable policy/schema revocation, state-version CAS,
clone-resistant/global permits and worker fencing are future hardening for a
broader threat model, not P4/P5 blockers.

The full RouteBinding—not only `request_payload`—is secret-free by schema.
Credential-bearing URI userinfo/query, cookie/token/private key/session handle,
signed-URL signature/expiry, and request signing material are forbidden from
the contract and every trace/checkpoint projection. The contract binds the
unsigned canonical resource plus opaque credential scope/principal/audience;
the Executor injects closed-allowlist auth/transport material only at the send
boundary, and it cannot change operation, resource, destination, body, or named
application parameters.

The effective capability envelope is the intersection of the frozen
provider/model/tool-schema descriptor, environment adapter support, product
policy, and current user grant. Unknown actions, absent required safety
features, schema/version drift, and capability-service failure are typed denial
or unavailable outcomes. They never synthesize grants or downgrade validation.

Web, email, PDF, DOM, AX, OCR, screenshot, notification, memory/skill, and tool
output are untrusted observation. Their content may supply a TaskSpec-authorized
value through a typed source-to-field binding, but cannot create user authority,
capability, approval, policy, TaskSpec revision, or control flow.

## Canonical algorithm

The canonical digest is:

```text
sha256(canonical-json(contract without contract_hash))
```

Canonical JSON uses sorted keys and compact separators. Nested immutable JSON
values are projected to JSON-compatible data only for digesting or explicit
external adapter/API boundaries.

## SAR-1 first cut

The first SAR-1 production cut freezes `ActionContract.locator` and
`ActionContract.parameters` with a reusable `freeze_json()` boundary, normalizes
contract list fields to immutable sequences before computing the digest, and
requires adapters/executors to thaw explicitly at external boundaries.

The same cut also freezes `ExecutionReceipt.evidence` and the compatibility
`PlannerDecision.result` / `PlannerDecision.planner_context` diagnostic maps at
construction time. Trace and artifact writers project frozen containers through
canonical JSON-compatible data before persistence, so immutable core payloads do
not become stringified trace artifacts.

The follow-up SAR-1 cut extends the same constructor boundary to
`Observation.metadata`, `Observation.target_fingerprints`,
`Observation.artifact_refs`, `Affordance.locator`, `Affordance.state`,
`Affordance.payload`, `Affordance.backend_candidates`, `Affordance.evidence`,
and `AffordanceLease.provenance`. Legacy code that reads these values must treat
them as `Mapping` / `Sequence` or explicitly project at an adapter boundary; core
code must not regain mutable references.

The verification boundary is included in the same SAR-1 repair:
`VerificationEvidence.observed`, `VerificationEvidence.expected`,
`VerificationReport.evidence`, and `VerifierEvaluation.observed` are frozen at
construction/materialization time. This prevents post-verification evidence
objects from changing after they have been linked into trace, progress
diagnostics, recovery, or later attribution experiments.

SAR-1.1 closes the remaining hash-reachable verifier-plan gap by freezing
`VerifierSpec.expected` and normalizing its criterion and requirement identity
sequences at construction. `ActionContract` now validates any supplied
`contract_hash` against the canonical frozen payload and rejects stale hashes;
callers that intentionally derive a replacement contract must pass an empty
hash so the digest is recomputed from the new payload. That is current-era
compatibility behavior only; the target `SealedActionContract` prohibits derived
replacement and requires full rematerialization. The same closure freezes
`SourceAssertion.value`, preventing source-local perception assertions from
retaining caller-owned mutable JSON values after arbitration or grounding has
accepted them.

Trace nodes are also frozen at append time: `TraceNode.payload` is deeply
immutable and `TraceNode.parents` cannot be mutated by the caller after
`TraceDag.add()`. The trace DAG itself remains the append-only collector, but
individual events no longer retain caller-owned mutable payload references.

Browser snapshots also freeze the optional browser accessibility-tree payload at
construction time. This keeps snapshot-local accessibility evidence from being
rewritten by a caller-owned dictionary after planning, verification, or trace
projection has already consumed the snapshot identity.

DOM page affordance models also freeze their affordance sequence at
construction time. Callers may still create a replacement model with an explicit
new affordance sequence, but mutating the original list supplied to
`PageAffordanceModel` cannot alter a captured snapshot's planner-facing target
inventory.

WoT thing affordance models apply the same rule to their affordance sequence
and state-source payloads. Device route planning therefore reads an immutable
Thing Description projection rather than a caller-owned list or dictionary that
can be rewritten after parsing.

Task envelopes now freeze caller-provided constraints and granted capability
lists at construction time. This keeps run-level policy and capability scope
stable after `TaskEnvelope` is passed to Runtime or Coordinator entrypoints,
instead of retaining mutable references owned by the caller.

Task-level API request and execution DTOs follow the same rule. `TaskRequest`
freezes external constraints and capability grants when a parent/tool adapter
submits work, while `TaskExecution` freezes result payloads and artifact lists
before they are stored in `RunView`. API responses explicitly project these
frozen containers back to JSON-compatible dicts and lists.

Semantic resolver and compiler outputs also freeze their parameter and
target-compatibility payloads at construction. A selected semantic action or
compiler-produced target scope therefore cannot be changed by mutating the
caller-owned dictionaries that produced it.

Canonical and intent repair proposal claim-id maps are frozen as well. Provider
graph IDs are diagnostic/local inputs only, but their mapping to Runtime-owned
canonical claim IDs must not drift after canonicalization or repair reporting.

Configured approval providers freeze their allowed-capability set at
construction time. A caller-owned set cannot be mutated after provider creation
to silently expand which high-risk contracts may receive an approval token.

Routing decisions freeze candidate backend order and score payloads at
construction time. Route-selection trace, contract binding, and later
diagnostics therefore cannot be rewritten by mutating caller-owned lists or
dictionaries after the route is selected.

This does not change progress authority, finish authority, Planner API,
Coordinator control flow, StateKernel mutation, or benchmark promotion status.

## Replay and trace threats

Replay is an offline simulation boundary. A missing event, receipt, or artifact
must fail explicitly; it cannot call a live executor, driver, browser, device,
API, network, credential, or account. Simulated receipts and real receipts are
different typed records. Re-execution requires a new live run identity and a
new observation/admission/approval/dispatch lifecycle.

Hashing does not make trace data safe to retain. Contract payloads, screenshots,
outputs, evidence, and artifact references remain subject to minimization,
redaction, encryption, access, and retention policy. Secret-bearing values must
not be duplicated into general trace payloads merely to improve audit detail.

## Complexity boundary

This threat-model closure requires deeply immutable value objects, one
transaction materializer, deterministic capability/source-to-field checks, and
negative tests. It does not require a general dynamic-taint engine, a new
microservice or discovery service, a universal provenance graph, or a
whole-program theorem prover.
