# Benchmark Plan

> **Lifecycle:** CURRENT NORMATIVE EXECUTION POLICY
> **Scope:** evaluation layers, profiles, metrics, reporting, and promotion evidence
> **Governance:** [Benchmark Governance Boundary](benchmark-governance-boundary.md)

## 1. Evaluation objective

Evaluate whether Runtime preserves authorization, builds legal actions from
current observations, rejects stale/unsafe transactions, verifies typed effects
and completion, recovers without duplicate side effects, and reports truthful
evidence across surfaces.

## 2. Evaluation layers

| Layer | Primary question |
|---|---|
| contract/unit | are identities, digests, gates, predicates, and transitions correct? |
| local integration | does the shared Runtime loop complete deterministic scenarios safely? |
| cross-surface conformance | do DOM/AX/visual/API/device paths preserve the same semantic contract? |
| external benchmark | does the general Runtime handle unseen tasks/layouts under fixed profiles? |
| safety/security | are prompt injection, stale state, approval, uncertain effects, and replay boundaries preserved? |
| architecture | do source, observation, Catalog, evaluation, and commit owners remain unique? |

## 3. Required architecture properties

Benchmark coverage must include:

- ordinary intake without mandatory claim/obligation graph;
- material SourceAnchor and optional SemanticAudit veto/clarification;
- initial `STATE_HOLDS` completion and `ACTION_CAUSED` causal evidence;
- canonical acquisition coverage vs presentation omission;
- unique target beyond bounded model pages;
- multi-source conflict and multi-binding preservation;
- stale Catalog/contract/approval rejection;
- high-risk effect final recheck and no blind duplicate retry;
- no-evidence UNKNOWN and disabled-verification non-PASSED;
- plan exhaustion not equal to task completion.

## 4. Profiles

Profiles are immutable report inputs. At minimum separate:

- deterministic/reference conformance;
- strict-generalist planner;
- ablations and accepted-skill profiles;
- external suite PR/breadth/nightly/release;
- security/injection and uncertain-effect profiles.

Results from one profile never silently merge with another.

## 5. Metrics

Report both denominators and missing coverage:

- Runtime TaskCompleted rate and external-oracle success rate;
- unsafe/unauthorized side-effect rate;
- receipt/effect/step/task disagreement;
- verifier false accept/reject and UNKNOWN/CONFLICT/UNSUPPORTED counts;
- recovery success, repeated-failure depth, duplicate-effect attempts;
- acquisition/choice coverage and unpresented-choice rejection;
- approval/preflight stale rejection;
- provider/runtime/accounting failures, missing and unrun episodes;
- latency, model calls/tokens, captures, actions, and budgets.

## 6. Run identity and reporting

Every scored report binds repository revision and dirty status, profile digest,
provider/model identity, environment/assets, seed/task manifest, budgets,
timeouts, Runtime result, external result, artifact hashes, and
`official_score_claimed`.

Interrupted or resumed runs preserve immutable identity. Missing/unrun episodes
remain explicit and cannot be dropped from denominators.

## 7. Promotion gate

Promotion requires at one immutable revision:

1. architecture and documentation admission;
2. focused and protected regression suites;
3. non-benchmark/metamorphic evidence;
4. safety and uncertain-effect evidence;
5. required breadth/cross-surface profiles;
6. reproducible artifacts and truthful claim flags.

Historical reports remain under `docs/evidence/` and apply only to their exact
identity.

The previous detailed plan is archived at
[maintained-pre-consolidation/benchmark-plan.md](archive/superseded-2026-08-05/maintained-pre-consolidation/benchmark-plan.md).
