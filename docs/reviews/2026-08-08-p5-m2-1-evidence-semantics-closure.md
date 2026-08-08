# P5-M2.1 evidence semantics and dynamic evaluation closure

## Status

- P5-M1 / M1.1: `CLOSED`
- P5-M2 criterion composition: `CLOSED_FOR_DECLARED_MINIMUM`
- action verification scope: `CLOSED_FOR_RUNTIME_DERIVED_CRITERION_AND_ARTIFACT_PROFILE`
- exact future-state prediction: `NOT_REQUIRED`
- general causal attribution: `NOT_IMPLEMENTED`
- low-risk inconclusive continuation: `CLOSED`
- no-effect verification: `CLOSED_FOR_DECLARED_OBLIGATION_PROFILE`
- semantic evidence presentation: `CLOSED`
- semantic evidence entailment: `PARTIAL`
- hybrid component separation: `CLOSED`
- dynamic semantic readiness: `CLOSED_FOR_TARGET_FACT_AND_OUTPUT_PROFILE`
- artifact evidence linkage: `CLOSED_FOR_OUTPUT_ID_PROFILE`
- artifact deterministic absence: `DEFERRED`
- live semantic evaluator: `UNAVAILABLE`
- P5-M3 benchmark harness: `ADMITTED / NOT_STARTED`
- external benchmark: `BLOCKED`
- default cutover: `NOT_READY`

## Action verification boundary

Runtime derives narrow immutable verification obligations from mechanical task
criteria relevant to the selected semantic target/destination and from explicit
Runtime-owned output IDs. It does not infer predicates from button labels,
model reasons, benchmark IDs or the after observation, and it does not require
the Agent to predict a complete future world.

`EFFECT_CONFIRMED` means current evidence newly satisfies one declared
obligation. It is an evidence-supported effect claim, not scientific causal
attribution. `NO_EFFECT_CONFIRMED` requires complete, sufficiently strong,
referenced evidence for every declared fact obligation. Artifact absence remains
UNKNOWN without an explicit complete inventory profile.

A LOW-risk `SENT` observation/local-reversible action may remain inconclusive
and continue from the fresh world; the request is never replayed. `SENT_UNKNOWN`,
elevated risk and external/irreversible effects continue to wait for user
direction unless validated task evaluation already completes.

## Semantic evidence boundary

Semantic judges receive a single bounded `SemanticJudgeRequest`: public task
view without criterion internals, semantic-only criterion views, pinned public
world scope and a catalog of public current evidence records. The catalog refs
are exactly the refs the model may cite. Artifact records bind canonical ref,
current source and output ID without exposing path or raw value.

Hybrid mechanical evaluation runs first. An UNSATISFIED or UNKNOWN mechanical
component makes zero semantic calls; a mechanical fact cannot be reused as the
semantic proof. With complete coverage, a not-yet-created semantic target/output
is UNSATISFIED and task evaluation is INCOMPLETE, allowing policy to create it.
Truncated/failed coverage remains UNKNOWN. Once the scope appears, one semantic
judge call may propose evidence and Runtime performs final applicability and
completion composition.

No live semantic provider was configured:
`live_evaluator_attestation: unavailable`. No external benchmark was run.
Exact-head remote CI is recorded separately; absent a returned run/status,
`remote_ci_attestation: unavailable`.

All M2.1 entry gates admit the next internal slice, P5-M3 new-loop benchmark
harness. This does not admit an external benchmark, which remains blocked by
the harness evidence, exact live model-policy profile and exact-head remote CI.
