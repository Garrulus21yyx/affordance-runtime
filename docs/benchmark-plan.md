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
- plan exhaustion not equal to task completion;
- product safety profile cannot be replaced by a benchmark ablation profile;
- provider/model/tool-schema capability intersection and schema-drift fail-closed;
- TaskPlan typed semantic subsumption beyond requirement-ID membership;
- third-party observation cannot become user authority or control flow;
- sealed transaction binding for execution context, live surface, coordinate
  transform, effective capability, provenance, and exact current epoch;
- full rematerialization instead of `replace()` or partial preflight patching;
- strict offline replay with zero live-driver/network/credential fallback;
- trace and artifact redaction, encryption, access, and retention behavior.

## 4. Profiles

Profiles are immutable report inputs. At minimum separate:

- deterministic/reference conformance;
- strict-generalist planner;
- ablations and accepted-skill profiles;
- external suite PR/breadth/nightly/release;
- security/injection and uncertain-effect profiles.

Results from one profile never silently merge with another.
Product-conformance profiles always retain safety gates. Benchmark ablations run
through a benchmark-only composition and record every disabled control in the
profile digest; they are ineligible for product promotion on their own.

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
- required-variant presence and each rate's explicit opportunity denominator;
- latency, model calls/tokens, captures, actions, and budgets;
- benign utility, utility-under-attack, and targeted attack success rate for
  injection suites, reported as three distinct metrics;
- collateral-effect probe violations and unavailable/unknown probe counts;
- capability/schema drift rejection and unsupported-action counts;
- replay attempts to call live adapters, which must remain zero;
- trace redaction/privacy-policy violations.

## 6. Optional SOTA release profiles

| Gate | Required use | Explicit non-use |
|---|---|---|
| AgentDojo | state-based benign utility, utility-under-attack, targeted ASR, adaptive injection cases | production dependency, user-authority source, or single safety proof |
| WASP | isolated browser prompt-injection subset with the same three metrics | copying malicious/evaluator metadata into Runtime planner context |
| OSWorld-V2 | pinned release manifest, functional checkpoints, applicable credential/data/document/resource/privilege/process/sandbox collateral probes | external reward, partial score, or model judge as Runtime completion authority |

The suites are optional nightly/release/paper-claim profiles, not P4/P5
mainline gates. Their models, harnesses, and
leaderboard methods do not define ActionContract, dispatch, effect, or completion
semantics. Collateral probes are selected by effect/risk class rather than run in
full for every read or click.

## 7. Run identity and reporting

Every scored report binds repository revision and dirty status, profile digest,
provider/model identity, environment/assets, seed/task manifest, budgets,
timeouts, Runtime result, external result, artifact hashes, and
`official_score_claimed`.

The identity also binds product-or-ablation composition, policy digest,
provider/model/tool/action schema descriptor and digest, coordinate-transform
policy, acquisition policy, verifier versions, and collateral-probe set. Drift
creates a different run; it cannot silently resume or merge denominators.

Interrupted or resumed runs preserve immutable identity. Missing/unrun episodes
remain explicit and cannot be dropped from denominators.

`BenchmarkReport` fails closed when any required variant is absent, when a rate
has no valid opportunity denominator for a profile that requires one, or when
an expected fail-closed variant lacks its typed failure reason and trace signal.
An unrelated crash or a vacuous `0/0` rate cannot satisfy an ablation gate.

Replay consumes only immutable recorded artifacts. A miss fails explicitly;
there is no fallback to a real browser, device, API, account, credential, or
network. A requested live rerun creates a new identity and repeats observation,
admission, approval, and dispatch.

## 8. Published release/benchmark-claim gate

A published release or benchmark claim requires at one immutable revision:

1. architecture and documentation admission;
2. focused and protected regression suites;
3. non-benchmark/metamorphic evidence;
4. safety and uncertain-effect evidence;
5. required breadth/cross-surface profiles;
6. reproducible artifacts and truthful claim flags;
7. capability/schema drift and transaction-rematerialization negative probes;
8. separate injection utility/ASR and collateral-effect results where applicable;
9. strict replay sentinel and trace-privacy checks.

Promotion does not require a general dynamic-taint system, new benchmark
microservices, a second obligation/evidence graph, or whole-program theorem
proving. Required controls are narrow typed boundaries, deterministic semantic
subsumption, and effect/risk-specific checks inside the modular monolith.

Historical reports remain under `docs/evidence/` and apply only to their exact
identity.

The previous detailed plan is archived at
[maintained-pre-consolidation/benchmark-plan.md](archive/superseded-2026-08-05/maintained-pre-consolidation/benchmark-plan.md).
