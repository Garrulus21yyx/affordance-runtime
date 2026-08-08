# P5-C1.1/B1.1 correctness closure

> **Lifecycle:** IMPLEMENTATION RECORD
> **Semantic authority:** false
> **Start SHA:** `63e714bbcfd1de0f7df044a1bf64dce348d69d26`
> **Date:** 2026-08-08

## Result

The single-DOM vertical remains non-default. This record closed source/world
identity but did not yet close exact option-to-binding fidelity or Runtime-owned
effect/risk classification; those follow in the C1.2/B1.2 record. No Visual or
WoT SurfaceAdapter was added.

- ActionBinding retains world observation, source observation, source revision,
  and target fingerprint identities. Multi-adapter currentness never rewrites a
  stale request or binding.
- DOM currentness probes the live page revision and target fingerprint before
  dispatch; asynchronous DOM mutation produces zero executor calls.
- Surface primitives are normalized before WorldObservation: DOM click,
  Visual point activation, and WoT invoke share canonical `activate` semantics.
- ActionSpace is task-aware and filters unallowed/forbidden semantic effects,
  material target conflicts, stale bindings, and expired bindings.
- The finite parameter validator covers object/required/additionalProperties,
  string/number/integer/boolean, enum, minimum, and maximum.
- ActionEvaluator receives BoundActionRequest. AgentLoop rejects mismatched
  result request/backend lineage before evaluation.
- SENT_UNKNOWN with VERIFIED or NOT_VERIFIED evidence continues from facts;
  UNKNOWN waits without replay; REJECTED stops.
- Observation budget is reserved before reobserve or execution. A rejected
  Finish is recorded with TaskEvaluation feedback and does not end the episode.
- WoT unresolved security retains only an explicitly unavailable state-source
  description; transport fields and executable affordances are withheld.
- Architecture tests enforce import directions plus 350-file/80-function gates.

## Default baseline correction

The settings recovery xfail was removed. Its root cause was a legacy
no-progress guard rejecting a second attempt even after independent evidence
settled the first effect as `NOT_OCCURRED`. The narrow baseline fix allows the
retry only for verified absence. The benchmark recovery observation also waits
for its fixture's bounded asynchronous readiness transition before capturing,
so the intended stale/retry proof does not race an unrelated timer. The test
passed three consecutive standalone runs, and CI also runs it independently
with `--runxfail` so a future marker cannot conceal failure.

## Admission state

```text
single_DOM_minimum: CLOSED
task_aware_legality: PARTIAL_AT_THIS_REVISION
multi_source_identity_currentness: CLOSED
Visual_surface_vertical: NOT_STARTED
WoT_surface_vertical: NOT_STARTED
external_benchmark_status: BLOCKED
default_cutover: NOT_READY
```

## Verification

```text
pytest: 1107 passed
independent settings recovery --runxfail: passed
focused DOM Chromium vertical: 4 passed
target boundaries/currentness/WoT: 16 passed
ruff: passed
mypy: passed (230 source files)
docker compose config: passed
git diff --check: passed
```
