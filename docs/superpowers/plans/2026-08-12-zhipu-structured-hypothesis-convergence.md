# Zhipu Structured Hypothesis Convergence

Status: IMPLEMENTED_DIAGNOSTIC_NOT_VALIDATED — fresh live evidence pending

## Goal

Close the bounded response-to-action path for Zhipu GUI runs without granting
model output authority it does not own:

```text
provider response
→ bounded normalization
→ schema validation
→ item projection
→ item admission
→ tracked hypothesis state
→ model feedback/context
→ decision normalization and validation
→ independent ActionSpace admission
→ dispatch
```

Implementation completion is not verified closure. Closure requires fresh live
evidence on held-out cases and an independent fresh-context review.

## Known reopenings and shared cause

1. OpenAI `json_schema + strict` was sent to Zhipu, which only declared
   `json_object` for text models and prompt/local validation for the selected
   VLM.
2. A malformed requirement response was dropped without a bounded repair.
3. Repair produced a mixed-validity batch, but batch admission rejected every
   item.
4. Admission became item-wise, but the preceding payload-to-runtime projection
   remained batch-atomic.
5. A schema-named single wrapper around an otherwise valid decision package was
   rejected, while no safe normalization algebra existed.
6. Public evidence recorded only coarse failure categories and did not prove
   accepted/rejected hypothesis transitions.

Shared mechanism: provider syntax, schema validation, semantic projection,
runtime admission, and feedback were treated as one success/failure boundary.
The chain lacks a closed normalization algebra and item-addressed outcomes.

## Authority and bounded contracts

- Provider output is untrusted syntax.
- Normalization may remove only declared, single, exact schema-name wrappers or
  complete Markdown JSON fences. It may not synthesize, rename, coerce, or
  repair fields locally.
- Pydantic payload validation owns public wire shape.
- Runtime predicate constructors own semantic reference/type invariants.
- Hypothesis admission is item-wise because hypotheses are independent.
- Runtime assigns hypothesis IDs; model candidates never create authority.
- Verifier alone assesses SATISFIED / CONTRADICTED / UNKNOWN.
- ActionSpace remains the sole execution authority.
- Invalid items must never block independent valid items and must never enter
  tracked state.
- Unsupported wrappers/nesting, ambiguous multiple candidates, trailing text,
  and unknown reference kinds fail deterministically and typed.

## Work plan

| Step | Status | Evidence / files |
|---|---|---|
| Repository-wide causal-surface review | implemented | provider port, proposer, decision bridge, admission, context projection, instrumentation |
| Define normalization and item-outcome contracts | implemented | typed item rejection algebra and bounded schema repair |
| Implement safe exact-wrapper normalization | implemented | `model_port.py`, strict negative wrapper tests |
| Implement item-wise hypothesis projection + admission | implemented | proposer/runtime contracts, mixed-batch tests |
| Project accepted/rejected outcomes into feedback/evidence | implemented | state/context/result/snapshot/metrics/trace |
| Property/state-machine regression suite | implemented | permutation, duplicate, replacement-liveness, wrapper, authority tests |
| Full repository validation | passed | 2272 passed, 24 skipped; Ruff and diff checks pass |
| Fresh held-out Zhipu cases | pending | clean-SHA evidence |
| Independent fresh-context review | pending | review record |

## Provider contract comparison (checked 2026-08-12)

- OpenAI Structured Outputs documents schema adherence for supported models when
  JSON Schema strict mode is used; JSON mode alone only guarantees valid JSON:
  <https://platform.openai.com/docs/guides/structured-outputs>.
- Zhipu's OpenAI-compatible chat documentation declares JSON object response
  formatting and instructs callers to describe the expected JSON in the prompt:
  <https://docs.bigmodel.cn/cn/guide/develop/jsonmode>.

Engineering inference: the Runtime must keep one provider-neutral local schema
validator and a bounded repair path. It must not treat Zhipu JSON mode as native
strict-schema enforcement or silently coerce semantically invalid items.

## Implemented transition algebra

```text
raw response
  → whole fenced JSON normalization (optional)
  → exact one-key schema-name wrapper removal (optional)
  → strict wire-schema validation
  → on schema failure: one provider repair call, zero GUI turns
  → per-item semantic projection
  → per-item Runtime admission
  → accepted item gets Runtime hypothesis ID
  → rejected item gets {item_index, typed code}
  → state/context/result/snapshot/trace expose bounded public outcomes
```

Malformed wrappers, duplicate JSON keys, non-standard numeric constants,
dangling entity/fact references, invalid predicates, capacity overflow, and
duplicate proposals all fail deterministically without blocking independent
valid siblings. Rolling replacement retains bounded history without exhausting
the active hypothesis capacity.

## Falsifiable exit criteria

- A valid item in any bounded mixed batch is installed exactly once with a
  Runtime ID regardless of independent invalid siblings.
- Every invalid item has a stable item index and typed rejection code; no raw
  provider text is exposed publicly.
- An exact single schema wrapper is normalized; misspelled, nested, multiple,
  ambiguous, or extra-sibling wrappers are rejected.
- Normalization never changes values or creates fields.
- Decision normalization does not bypass objective or ActionSpace admission.
- Policy context exposes installed hypotheses and bounded typed rejection
  summaries from the preceding proposal.
- Evidence separately measures proposal calls, schema repairs, accepted items,
  rejected items, and rejection codes.
- Full tests pass; fresh live cases demonstrate both mixed-batch installation
  and successful dispatch without a production branch per case.

## Non-goals

- Treating hypotheses as authoritative task requirements.
- Installing malformed or dangling references.
- General-purpose JSON repair or provider-specific response guessing.
- Building a static task DAG or new action authority.
- Claiming general MiniWoB success from the bounded cohort.
