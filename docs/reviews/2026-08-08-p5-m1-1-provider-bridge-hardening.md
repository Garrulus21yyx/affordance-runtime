# P5-M1.1 existing ModelPort bridge and invocation hardening

Date: 2026-08-08

## Status

- P5-M0.1 / M0.1.1: `CLOSED`
- P5-M1 model policy core: `CLOSED`
- P5-M1.1 strict decision boundary: `CLOSED`
- P5-M1.1 existing ModelPort bridge: `CLOSED`
- local HTTP provider-transport proof: `CLOSED`
- live provider profile: `UNAVAILABLE`
- deterministic evaluators: `RETAINED`
- production model evaluators: `NOT_STARTED`
- semantic evidence entailment: `NOT_STARTED`
- benchmark harness: `NOT_STARTED`
- external benchmark: `BLOCKED`
- default cutover: `NOT_READY`
- remote_ci_attestation: `unavailable`

## Implemented boundary

The canonical Pydantic response specification is the sole owner of the seven
decision variants, provider JSON Schema, exact field/type validation, enum
constraints, schema version and typed conversion. A strict loader rejects
duplicate keys at every object depth, non-finite numbers, non-object roots,
malformed Unicode/JSON, responses over 32 KiB, depth above 32 and trees above
2,048 nodes. Raw dictionaries stop at the parser.

`ModelPortDecisionAdapter` delegates transport exclusively to the existing
`ModelPort.generate_structured()` owner. It sends fixed authority instructions
as the system message and canonical serialized AgentContext as the user
message, passes the canonical decision schema, requires zero retry counts and
rejects `FallbackModelPort`. `ModelBackedAgentPolicy` adds a bounded outer
deadline. Typed provider/parse failures terminate with zero execution and no
Agent-authored Abort or Turn; raw provider reasons and responses are not retained.

Secret-free provider/model/endpoint-class/response identity, prompt/schema
versions, latency, token totals and zero retry counts are copied from
`ModelCallRecord` for diagnostics only. Artifact summaries expose canonical
evidence refs without artifact values or private paths.

## Evidence and claim boundary

The local OpenAI-compatible HTTP fixture traverses the real repository path:

`ModelBackedAgentPolicy → ModelPortDecisionAdapter → OpenAICompatibleModelPort
→ local HTTP → strict payload → Runtime admission → deterministic evaluators`.

The success proof makes one HTTP request and one execution and reaches DONE.
429, 500, malformed output and delayed-response proofs each make one request,
perform zero executions and produce typed failures without retry. Existing
scripted DOM, Visual and WoT policy verticals remain regression evidence.

This is transport-composition evidence, not actual LLM reasoning or
cross-surface generalization. No opt-in live profile was configured, so live
provider attestation is unavailable. Production evaluator composition remains
the next admitted slice, P5-M2; external benchmarks remain blocked by P5-M2,
P5-M3 and exact-head remote CI.

Local collection contained 1,511 tests. Four deterministic file manifests
collected 447, 378, 441 and 245 node IDs with union 1,511 and zero intersection,
missing or extra IDs. All shards passed (the one live smoke was skipped as
unavailable), and the single-process suite passed 1,510 with that same one
skip. Ruff, mypy, diff-check, Docker Compose config, required three-surface
E2E, symmetry, confirmation, target-boundary and legacy `--runxfail` gates passed.
