# ActionContract Digest Threat Model

> Status: SAR-1 active correctness/security record.
> Scope: ActionContract digest identity and approval-token binding.

## Boundary

`ActionContract.contract_hash` is the stable digest used to bind an accepted
Runtime action to approval, preflight, execution, verification, trace, and
recovery evidence. The digest is meaningful only if every hash-critical field is
deeply immutable before the hash is computed.

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

## Hash-critical fields

SAR-1 treats at least these `ActionContract` fields as hash-critical:

- `locator`
- `parameters`
- `preconditions`
- `expected_effects`
- `verifier_plan`
- `required_capabilities`
- `fallback_backends`
- route, grounding, gesture, scope, snapshot/page/target identity fields
- idempotency, compensation, timeout, risk, backend, action, schema version

Analytics-only data must not be added to `ActionContract`. It belongs in trace
or artifact records.

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
