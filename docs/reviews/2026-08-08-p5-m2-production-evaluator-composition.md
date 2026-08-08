# P5-M2 criterion-adjudicated production evaluation composition

## Status

- P5-M1 / M1.1: `CLOSED`
- M2-0 strict model boundary: `CLOSED`
- criterion adjudicator contracts: `CLOSED`
- mechanical criterion evaluation: `CLOSED_FOR_DECLARED_MINIMUM`
- semantic judge composition: `CLOSED_FOR_INJECTED_AND_LOCAL_HTTP_PROFILE`
- user acceptance: `CLOSED_FOR_EXPLICIT_USER_EVIDENCE_PROFILE`
- hybrid criteria: `CLOSED_FOR_DECLARED_MINIMUM`
- action effect applicability: `CLOSED_FOR_STATE_TRANSITION_AND_ARTIFACT_PROFILE`
- success expression: `CLOSED_FOR_BOUNDED_BOOLEAN_PROFILE`
- authoritative checks: `CLOSED_FOR_CRITERION_ASSURANCE_PROFILE`
- strict source lineage: `CLOSED_FOR_CURRENT_OBSERVATION_PROFILE`
- output semantic binding: `CLOSED_FOR_PATH_SHA_ARTIFACT_PROFILE`
- live evaluator provider: `UNAVAILABLE`
- general semantic entailment: `PARTIAL`
- P5-M3 benchmark harness: `NOT_STARTED`
- external benchmark: `BLOCKED`
- default cutover: `NOT_READY`

## Implemented boundary

Success-criterion mappings are normalized once into Runtime-only adjudicator
contracts. Current observation facts and artifacts become typed evidence
records; mechanical checks and applicability validate subject, predicate,
scope, assurance and current lineage. Semantic and hybrid criteria share at
most one strict structured provider call. That call returns criterion proposals
only: it cannot return task status, create evidence, execute an action, grant
effects, alter risk, or bypass output checks.

Runtime composes final status from normalized criterion results, the bounded
`criterion`/`all`/`any`/`not` expression profile, authoritative checks, current
source lineage and requested outputs. File outputs require the same declared
path and SHA-256 in the evaluated value, a current matching artifact ref, a
regular file and a streamed digest match. ProposeDone remains advisory.

Explicit user acceptance requires a current authoritative user-source fact;
DOM, Visual and WoT content cannot impersonate it. HYBRID requires both its
mechanical and semantic components. General semantic entailment, user-answer
collection UI, provenance graphs and model-controlled completion remain out of
scope.

## Proof profile

The DOM, Visual and WoT adapters each perform one safe action between two fresh
observations and close the same normalized mechanical criterion through the
same production composer with no semantic call. A local OpenAI-compatible HTTP
fixture proves the existing ModelPort semantic bridge, strict response schema,
system/user separation, one attempt, zero retry/fallback, typed failures and
Runtime evidence validation. It is transport/composition evidence, not live
model quality or cross-surface generalization.

No live evaluator configuration was supplied, so
`live_evaluator_attestation: unavailable`. No external benchmark was run.
`remote_ci_attestation: unavailable` unless an exact-head status is separately
published after this commit.

The next admitted slice is P5-M3 new-loop benchmark harness. External benchmark
admission still requires that harness, an exact live model-policy profile,
exact-head remote CI, zero forbidden effects and zero duplicate unknown
attempts.
