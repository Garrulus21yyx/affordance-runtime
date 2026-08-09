# P5-M3.6 Two-Stage Decision Decomposition

Date: 2026-08-09

## Decision

The two-stage diagnostic is closed as a benchmark capability and is not
admitted as a production profile. It separates decision routing from canonical
variant payload generation, measures both independently, and then measures the
same handoff through the unchanged strict parser and production Runtime control.

`format-only.v1` remains the current default. `compact-contract.v1` remains the
production-supported action-selection profile. `compact-contract.v2` remains
`EXPERIMENTAL_NOT_ADMITTED`. Production factory composition and AgentLoop do
not expose two-stage operation.

## Contract and containment

Stage 1 emits only current `context_id` and a seven-value canonical
`decision_type`. Candidate domains come from public compact-v2 usability and
contain at least three alternatives in every diagnostic case. Stage 1 cannot
execute, observe, page, wait, evaluate, or mutate Runtime state.

Stage 2 starts from the selected production Pydantic branch schema, binds the
canonical type and current context as constants, and narrows only public field
domains. It still emits the complete canonical object. The strict canonical
union parser, context identity checks, page/action/destination membership, and
production decision control remain authoritative and unchanged.

One logical decision has at most one routing and one payload call. The second
call performs a distinct responsibility and is not retry. Retry and fallback
counts are zero. Pacing is fixed at zero seconds for both local exact profiles.
Atomic progress is written at routing start/completion, payload
start/completion, and Runtime completion. It contains typed counts, hashes,
latency and token totals, but no raw prompt, raw response, emitted IDs, private
routes, credentials, or hidden reasoning. Progress is never auto-resumed or
replayed.

## Scripted and transport closure

Scripted, local OpenAI-compatible HTTP, and local Ollama-shaped HTTP fixtures
pass routing 7/7, payload 7/7, two-stage end-to-end 7/7, and production Runtime
outcomes 7/7. All eight multi-action and destination critical cases pass.
Fixtures establish harness correctness, not real-model support.

## Exact-profile results

All values below use five repetitions per cell and zero retry/fallback.

| profile | single stage | routing | payload-only | end-to-end | critical | conclusion |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen 2.5 7B | 20/35 | 26/35 | 35/35 | 25/35 | 30/40 | routing bottleneck |
| Llama 3.1 8B | 5/35 | 25/35 | 35/35 | 25/35 | 0/40 | routing bottleneck |

Payload-only fixes the correct route in the diagnostic harness. Its 35/35
result isolates payload capability and is not routing, end-to-end, or
production-policy evidence. Qwen routing failed SelectAction 5/5 and AskUser
4/5; its destination-forbidden and one-destination critical cells each failed
5/5. Llama routing failed SelectAction and Abort 5/5, causing every critical
cell to fail before payload generation. Both candidate gates fail and neither
20/20 support gate runs.

Qwen's isolated route-plus-payload token total is 20.3% above its single-stage
baseline and latency is 51.3% higher. Llama's is 16.2% and 15.5% higher. Actual
end-to-end call totals are 60 versus 35 for each profile; those failed runs
skip payload after bad routes, so their observed token and latency totals do
not represent the cost of 35 successful two-call decisions.

## Provider availability and earlier evidence

Mistral two-stage is `NOT_RUN`; the required remote opt-in was absent. Its
earlier formal paced single-stage compact-v2 candidate remains 70/75 and
`INCONCLUSIVE_PROVIDER_AVAILABILITY`. Five independent follow-up diagnostics
remain 5/5 and support only rate-limit attribution; they do not backfill the
formal candidate.

## Admission and unchanged boundaries

The diagnostic conclusion is observed coupling decomposition with a routing
bottleneck, not two-stage support. Production adoption remains `NOT_ADMITTED`.
Future adoption would require a passing candidate, 20/20 support, provider-call
budget, token and latency evaluation, rate-limit evidence, strong-provider
no-regression, exact-head CI, explicit rollback, and a separate production
review.

No parser, payload validation, Runtime admission, retry, fallback, factory
default, AgentLoop interface, Coordinator path, or external benchmark state
changed. External benchmarks remain `NOT_RUN / BLOCKED`.
