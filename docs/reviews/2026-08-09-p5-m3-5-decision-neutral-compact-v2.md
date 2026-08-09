# P5-M3.5 Decision-Neutral Compact Grounding v2

> **Lifecycle:** IMPLEMENTATION REVIEW RECORD
> **Start:** `codex/migrate-world-interaction-capabilities@eb626297a760720ca9fdb08c5064e91c22d057c4`
> **Date:** 2026-08-09

## Owners and boundaries

`model_policy/grounding.py` owns explicit production profile identity;
`grounding_v2.py` owns the immutable public-context-only v2 projection;
`factory.py` composes one selected profile. Model-conformance modules own
typed expectations, Runtime replay, candidate/support gates, attestations and
pure cutover readiness. They do not own ActionSpace, parser, Runtime legality,
execution, evaluation, retry, fallback or product routing.

Inputs are canonical serialized public `AgentContext`, canonical
`agent-decision.v1`, and provider responses. Outputs are a bounded guide,
typed secret-free attempts and readiness evidence. Private bindings, routes,
credentials, benchmark oracle/answers and raw provider responses are excluded.

## Frozen identities

- decision schema: `agent-decision.v1`;
- digest: `sha256:187ef82e1205e863c2cd1e1688e92979da6439412fb1ff1541195fede955bf0f`;
- `result_summary` maximum: 1,024 characters in Runtime and provider schema;
- `format-only` → `format-only.v1` → `CURRENT_DEFAULT`;
- `compact-contract` → `compact-contract.v1` →
  `PRODUCTION_SUPPORTED_ACTION_SELECTION_PROFILE`;
- `compact-contract-v2` → `compact-contract.v2` →
  `EXPERIMENTAL_NOT_ADMITTED` after its candidate gate failed.

V1 serialization, concrete first-action SelectAction example and size semantics
are unchanged. Its prior Qwen/Llama L0–L4 20/20 evidence is now explicitly
`ACTION_SELECTION_SUPPORTED`, never broad/full recurrent `SUPPORTED`.

## Decision-neutral v2 guide

V2 contains action, observation, paging, completion and wait-budget domains,
plus symmetric required-field/domain contracts for SelectAction,
RequestObservation, RequestActionPage, AskUser, ProposeDone, Wait and Abort.
There is no concrete answer example or actual first-action skeleton. Runtime
revalidation is explicit. Abort excludes `internal`; Page carries the exact
current cursor; Done carries current criteria/evidence; Wait carries remaining
and per-decision budgets.

The 16-action matrix guide is 4,031 bytes, retains 16/16 actions and reports
`truncated=false`. Evidence refs use a deterministic reversible prefix/suffix
encoding. Privacy tests show zero selector, coordinate, bbox, point, href,
method, backend, executor, binding/observation identity, credential,
Authorization, private path, oracle or raw-response leakage. Build failure is
typed `INTERNAL_ERROR` before any provider call.

## Runtime matrix correction

The oracle now distinguishes provider_unavailable, timeout,
structured_output, schema_error, wrong_variant, wrong_field_domain,
runtime_rejected, runtime_outcome_mismatch and success. Non-SelectAction
payloads are no longer accepted by discriminator alone. The wrong empty Page
cursor fixture is corrected to exact `cursor:next`.

All seven decisions enter production decision control. SelectAction performs a
declared dry-run admission; Observation and Wait produce fresh observations;
Page changes page identity; AskUser returns `WAITING_USER`; ProposeDone reruns
TaskEvaluator; Abort terminates with zero execution and is not PolicyFailure.
The scripted/local structured candidate closes 75/75 with Runtime control 7/7.

## Exact GPU qualification

Runs used the dedicated GPU endpoint `127.0.0.1:11435`, with `size_vram`
4,748,056,984 bytes for Qwen and 5,271,715,839 bytes for Llama. Models ran
strictly serially. The accidental CPU endpoint attempt was stopped before any
report and is not evidence.

### Qwen 2.5 7B Q4_K_M

- candidate: 64/75, failed;
- recurrent: SelectAction 5/5, Observation 5/5, Page 4/5, AskUser 5/5,
  ProposeDone 5/5, Wait 0/5, Abort 0/5;
- critical matrix: every case 5/5;
- non-first: 0 wrong first selections in 20 opportunities;
- failures: wrong_field_domain 1, wrong_variant 10;
- retry/fallback/safety: 0/0/0;
- 20/20 support: not run because candidate failed;
- status: `ACTION_SELECTION_SUPPORTED` from v1 evidence;
  v2 `FULL_RECURRENT_POLICY_PARTIAL / NOT_ADMITTED`.

### Llama 3.1 8B Q4_K_M

- candidate: 20/75, failed;
- recurrent: ProposeDone 5/5; the other six variants 0/5;
- critical: destination-forbidden, non-first two-destination and similar-ID
  cases 5/5; other critical cases 0/5;
- non-first: 5 wrong first selections in 20 opportunities;
- failures: schema_error 5, wrong_field_domain 25, wrong_variant 25;
- retry/fallback/safety: 0/0/0;
- 20/20 support: not run because candidate failed;
- status: `ACTION_SELECTION_SUPPORTED` from v1 evidence;
  v2 `FULL_RECURRENT_POLICY_PARTIAL / NOT_ADMITTED`.

### Mistral

The retained format-only matrix evidence is 12/12. No explicit v2 strong-
provider opt-in was configured in this run, so v2 and strong-provider
no-regression are `INCONCLUSIVE_PROVIDER_AVAILABILITY`, not a semantic
regression. No retry or fallback was used.

## Cutover and non-goals

Global default remains `format-only`; rollback remains
`LLM_DECISION_GROUNDING=format-only`. Cutover is
`BLOCKED_WITH_EXPLICIT_ERRORS`: both exact v2 recurrent profiles failed
candidate admission, Llama showed first-action bias, strong-provider v2 samples
are unavailable, and exact-head CI is pending until push. Parser and Runtime
admission are unchanged. External benchmarks were not run and remain gated.
The default Coordinator product path is unchanged. No semantic fusion,
ActionBatch integration, long-horizon planner, repair, retry/fallback, model
registry or provider-specific Runtime was added.
