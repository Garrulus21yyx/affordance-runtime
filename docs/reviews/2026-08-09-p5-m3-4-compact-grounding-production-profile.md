# P5-M3.4 Compact Grounding Production Profile

> **Lifecycle:** IMPLEMENTATION REVIEW RECORD
> **Start:** `codex/migrate-world-interaction-capabilities@8ea60adfb5388feb2ce681bcfee65b4942b210dc`
> **Date:** 2026-08-09

## Owners and retained authority

`model_policy/grounding.py` owns the production enum and immutable
`format-only.v1` / `compact-contract.v1` semantics. `factory.py` owns explicit
composition. `schema_identity.py` hashes the canonical seven-variant provider
schema. `benchmarks/model_conformance/decision_matrix.py`, `matrix_runner.py`
and `compact_cutover.py` own only post-hoc diagnostic oracle, secret-free
measurement and readiness calculation. Parser, current context/page/action/
destination admission, risk, execution and evaluation are unchanged.

## Canonical production identity

- decision schema version: `agent-decision.v1`;
- schema digest: `sha256:187ef82e1205e863c2cd1e1688e92979da6439412fb1ff1541195fede955bf0f`;
- `ProposeDone.result_summary`: 1,024 characters in Runtime and provider schema;
- grounding variants: `format-only`, `compact-contract`;
- grounding profiles: `format-only.v1`, `compact-contract.v1`;
- context budget: `default-64k`;
- compact guide: 749 bytes for the measured real-DOM context, under 4 KiB;
- measured provider input delta: +952 bytes total (+785 user, +167 system);
- Mistral compact versus format prompt delta in the earlier single Level-4
  sample: +342 prompt tokens. Token overhead is profile/request dependent.

Factory precedence is explicit argument, then `LLM_DECISION_GROUNDING`, then
format-only. Unknown values and diagnostic variants fail closed. No provider or
model name selects grounding. Compact build failure becomes typed
`INTERNAL_ERROR` before the provider call; there is no retry, fallback or
format-only repair. Successful secret-free metadata binds grounding variant/
version, schema digest and summary limit.

## Exact local profiles and matrix

The local GPU identities remain limited to Ollama 0.32.0, Q4_K_M and the exact
digests `845dbda0…b697e` (Qwen 2.5 7B) and `46e0c10c…ca666e` (Llama 3.1 8B).
Compact L0–L4 support is 20/20 per level for each recorded profile. Final-head
reruns bind the new identity fields and are retained as secret-free `/tmp`
evidence, not repository authority.

The live compact behavior matrix used five attempts per case:

| Case | Qwen | Llama |
|---|---:|---:|
| SelectAction | 5/5 | 5/5 |
| RequestObservation | 0/5 to 5/5 | 0/5 |
| RequestActionPage | 5/5 | 0/5 |
| AskUser | 0/5 to 5/5 | 0/5 |
| ProposeDone | 0/5 to 5/5 | 0/5 |
| Wait | 0/5 | 0/5 |
| Abort | 0/5 | 0/5 |
| 8 actions, correct eighth | 5/5 | 5/5 |
| 16 actions, correct middle | 5/5 | 0/5 to 5/5 |
| 8 actions, non-first objective match | 5/5 | 5/5 |
| destination forbidden / one / non-first / similar IDs | 20/20 | 20/20 |

Neither model selected the first action in the 15 non-first-action
opportunities. This rejects first-action anchoring for the measured cases but
does not close the seven-decision gate. Runtime rejected wrong variants/domains;
the harness did not repair them. Reports retain no raw response or emitted ID.
Complete Qwen runs scored between 45/70 and 60/70, so the ranges above are
retained rather than treating any run as stable behavior. Llama ranged from
35/70 to 40/70.

## Strong-provider no-regression

The configured Mistral profile ran SelectAction, RequestObservation,
RequestActionPage and ProposeDone three times per grounding. Format-only passed
12/12. Two compact runs passed 2/12 and 3/12; the remaining calls produced
typed `provider_unavailable` under the required zero-retry profile. This is a failed
compact no-regression gate, not stable Mistral support and not a reason to add
retry or fallback.

## Cutover result and rollback

`compact-contract` is `PRODUCTION_SUPPORTED_PROFILE` for explicit use by the
two exact local profiles. `format-only` remains `CURRENT_DEFAULT` and the
explicit rollback setting `LLM_DECISION_GROUNDING=format-only`.

Global compact-default readiness is `BLOCKED_WITH_EXPLICIT_ERRORS`:

1. seven-decision matrix is not closed;
2. Llama 16-action matrix is not closed;
3. compact strong-provider no-regression failed;
4. exact-head remote CI is unavailable.

The default was not changed. No external benchmark was run or admitted, and
the old Coordinator remains the default product path. There is no transaction,
event, registry, retry, fallback or model-specific Runtime expansion.

## Commits and validation

- A: `b1da5c9` — production grounding configuration and identity;
- B: `3fbf7e3` — seven-decision and multi-action contracts;
- C: `3afc06e` — exact-profile matrix runner and privacy proof;
- D/final: this review/documentation commit; exact SHA is reported with the
  final clean-tree attestation and push result.

Focused gates ran before each commit. Final validation includes collection,
full pytest, Ruff, mypy, diff check, smart-room compose config, exact GPU
L0–L4 and matrix reruns. External benchmark commands are explicitly excluded.
