# P5-M3.3 Exact Model-Profile Conformance

> **Lifecycle:** IMPLEMENTATION REVIEW RECORD  
> **Start:** `codex/migrate-world-interaction-capabilities@3d1ca4d2de22dc74129d8d94445e91024909dd6f`  
> **Date:** 2026-08-09

## Scope and ownership

`benchmarks/model_conformance/` owns exact profile identity, five diagnostic
levels, four explicit grounding variants, input/schema measurements, typed
failure attribution, support classification and secret-free attestation.
`model_port.py` remains the provider transport owner. Production
`model_policy/` retains canonical serialization/schema/parser and Runtime keeps
current-context/page/action admission. Diagnostics neither repair output nor
change policy, risk, execution or evaluation.

## Measured production input

The current safe real-DOM live task projects:

| Metric | Value |
|---|---:|
| serialized AgentContext | 4,972 bytes |
| authority system instructions | 746 bytes |
| canonical provider schema | 5,194 bytes |
| schema definitions | 10 |
| decision variants | 7 |
| schema maximum measured depth | 8 |
| visible actions / targets / facts | 1 / 1 / 7 |
| artifacts / conflicts / history | 3 / 0 / 0 |
| total serialized input components | 10,912 bytes |
| complexity class | `SMALL` |

The measured Mistral format-only Level-4 request reported 1,797 prompt tokens.
Compact grounding reported 2,117 prompt tokens for its one diagnostic call.

## Exact identities and matrix

Inventory came from the existing local Ollama API; no model was downloaded,
updated, created or deleted.

| Profile | Digest | Family / size / quantization | Runtime |
|---|---|---|---|
| `ollama:qwen2.5:7b` | `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e` | `qwen2 / 7.6B / Q4_K_M` | Ollama `0.32.0` |
| `ollama:llama3.1:8b` | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | `llama / 8.0B / Q4_K_M` | Ollama `0.32.0` |
| `mistral:mistral-medium-3-5` | provider-managed | undisclosed | remote existing ModelPort |

For both installed Ollama profiles, format-only and compact-contract each gave
L0 `5/5`, L1 `5/5`, L2 `0/5`, L3 `0/5`, L4 `0/5`. Full-schema-text and
context-bound-schema each gave L1 `3/3`, L2 `0/3`, L3 `0/3`. Failures begin
when the canonical seven-variant union reaches the Ollama structured-output
boundary; complete AgentContext is not the first failing layer.

Mistral Level 4 passed once under format-only and once under compact-contract.
Those calls are `SINGLE_RUN_ATTESTED`, not stable support or generalization.

## Grounding and support decision

`compact-contract` is `DIAGNOSTIC_ONLY`. It is deterministic, under 4 KiB, and
contains only current public context/action IDs, but it did not improve either
tested Ollama profile. Full-schema-text and context-bound-schema also remain
diagnostic-only. The production default remains format-only; there is no
model-name branch.

- tested `ollama:qwen2.5:7b` digest/profile:
  `UNSUPPORTED_FOR_AGENT_POLICY` with the canonical union;
- tested `ollama:llama3.1:8b` digest/profile:
  `UNSUPPORTED_FOR_AGENT_POLICY` with the canonical union;
- tested Mistral profile: `SINGLE_RUN_ATTESTED` for both Level-4 variants.

These statuses bind to the listed provider, tag, digest, quantization, runtime,
prompt/schema versions, grounding and context budget. They make no claim about
other Qwen/Llama profiles or general GUI reasoning ability.

## Retained boundaries

- canonical parser and seven-variant union: unchanged;
- Runtime context/page/action/destination admission: unchanged;
- retries/fallback: zero;
- raw prompt/response and chain of thought in reports: none;
- private route/credential leakage: none;
- external benchmark: `NOT_RUN / BLOCKED`;
- default Coordinator path: unchanged and `NOT_READY` for cutover.

Final exact-head reports and attestations are generated only after the fourth
commit on a clean worktree and remain revision-scoped `/tmp` evidence rather
than repository authority.

## Follow-up: canonical summary budget compatibility

The original matrix above remains the exact result for its recorded schema.
The full union contained `ProposeDonePayload.result_summary.maxLength=2000`,
which blocked grammar initialization in the tested Ollama runtime before model
sampling. The canonical semantic budget is now 1,024 characters in both the
provider payload and Runtime `ProposeDone` contract; there is no provider or
model-name branch and `agent-decision.v1` retains the same JSON shape.

With that single contract change, one format-only diagnostic per exact installed
profile produced:

| Profile | Level 2 | Level 3 | Level 4 |
|---|---|---|---|
| `ollama:qwen2.5:7b` | success / `select_action` | `hidden_destination` | `hidden_destination` |
| `ollama:llama3.1:8b` | success / `propose_done` | `hidden_destination` | `hidden_destination` |

Thus the former primary incompatibility is confirmed as provider grammar/schema
compatibility, not AgentContext size. Levels 3/4 now exercise actual model output
and Runtime admission; their failures do not weaken current-page authority and
do not establish stable support or general GUI capability. Reports are retained
under `/tmp/model-conformance-summary1024/` and contain no raw response.
