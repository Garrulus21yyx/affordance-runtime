# P5-M3 target-loop internal benchmark harness

## Scope and baseline

- branch: `codex/migrate-world-interaction-capabilities`
- start SHA: `9dd9d9ff046f956b111ec864f801ed08a67f1d03`
- M3-0 commit: `97893e35c25d99af87da05b4ce7684d6be550875`
- harness-core commit: `283a5dae2db9`
- fixed-matrix commit: `05b4afc`
- documentation commit: this record's commit (`docs: attest internal target-loop benchmark harness`)
- default product path changed: no
- external benchmark run: no
- live internal profile: `UNAVAILABLE`
- remote exact-head CI attestation: unavailable

## M3-0 closure

No-effect assurance is floored at structural and authoritative obligations stay
authoritative. Resolved facts require a typed current source. No-effect checks
all relevant current records, conflicts, agreement, and submitted-ref coverage.
Already-satisfied obligations are pruned. Authoritative/strict-lineage resolved
criteria without evidence become unknown. Per-criterion semantic evidence
windows distinguish projection truncation from absence. Semantic request
projection errors become criterion unknown with zero provider call. Criteria
that are complete while a generatable output is missing remain incomplete;
invalid integrity remains blocked.

## Harness ownership and authority

`contracts.py` owns immutable case/run/result contracts. `runner.py` owns
sequential case lifecycle through `AgentEpisodeRunner`; `metrics.py` contains
forward-only wrappers; `acceptance.py` owns post-run fail-closed assertions;
`reporting.py` writes bounded JSON; `cases.py` owns only explicit manifests;
`cli.py` is a narrow selector. Neither the manifest case ID nor expected status
enters TaskGoal, AgentContext, policy requests, evaluator requests, ActionSpace,
RiskPolicy, Binder, or observations.

Run identity contains exact git SHA/dirty state, stable manifest digest,
suite/profile/seed, UTC start, Python, and platform. Reports contain case status,
counts, latency, acceptance errors, and denominator-aware rates. A zero
denominator is JSON `null` (`N/A`), never 100%. Reports exclude selectors,
coordinates, hrefs, credentials, endpoint URLs, raw provider responses, hidden
reasoning, screenshots, and private artifact values.

## Fixed manifests and profiles

- `internal-core`: DOM/Visual/WoT shared-state, second-page selection, and
  low-risk inconclusive continuation.
- `internal-safety`: SENT_UNKNOWN no-replay, confirmation fresh rebind, stale
  zero-call, typed provider failure, and forbidden-route containment.
- `internal-evaluation`: dynamic semantic creation through an existing
  ModelPort local-HTTP judge and dynamic required-output progression.
- profiles: deterministic, scripted structured-model policy, existing-ModelPort
  local-HTTP model policy, and local-HTTP semantic judge. Local fixtures are
  protocol proofs, not live-model evidence.

## Actual commands and results

The repository was not editable-installed in the active host interpreter, so
the module commands used an ephemeral `PYTHONPATH=src` prefix. At clean exact
SHA `637063ccd924`, seed 7:

- `internal-core/deterministic`: accepted; 5 cases; errors `[]`.
- `internal-core/scripted-model`: accepted; 5 cases; errors `[]`.
- `internal-safety/scripted-model`: accepted; 5 cases; errors `[]`;
  duplicate-unknown rate `0/1 = 0`; stale zero-call rate `1/1 = 1`.
- `internal-evaluation/local-http-semantic-judge`: accepted; 2 cases; errors
  `[]`; semantic judge one HTTP attempt and zero retries.

All four reports bind the exact SHA and clean-tree state. The scripted policy
passes canonical AgentContext serialization, raw structured JSON, strict parser,
typed decision, and Runtime admission. The local HTTP semantic case passes the
existing OpenAI-compatible ModelPort and Runtime evidence applicability. Neither
profile demonstrates real-model generalization.

## Status and gates

P5-M3 new-loop benchmark harness is
`CLOSED_FOR_INTERNAL_FIXED_MANIFEST`. Internal deterministic, scripted-model,
and local-HTTP semantic profiles are `ATTESTED`. BrowserGym, MiniWoB, WebArena,
WorkArena, and OSWorld were not run. External benchmark admission remains
`BLOCKED` pending exact live profiles, exact-head remote CI, and a reviewed fixed
external manifest. Default cutover is `NOT_READY`; no transaction/event core,
registry, database, scheduler, retry platform, or old-core deletion was added.
