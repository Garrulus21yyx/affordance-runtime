# Gate 3 Canonical Provider Envelope execution

Status: reopened_breakdown_diagnostic_coordinate_conservation; core_transport_and_admission_scoped_evidence_only;
Gate_4_aborted_not_admitted

## Goal

Cut over the production model boundary to one immutable `CanonicalProviderEnvelope` produced once, admitted once, and consumed without semantic reconstruction by the PydanticAI model-boundary codec. Preserve frozen Gate 1 World and Gate 2 Delivery contracts, verify provider-free, commit independently, and stop before Gate 4.

## Constraints

- HEAD baseline: `3d976a07811773a1610a33ad5158f900e5870809`.
- Preserve untracked `output/`; never stage it.
- No real provider, live benchmark, Task7 replay, raw HTTP builder, or external token-count request.
- Do not change World projection, Delivery selection/order/minimum-progress/suffix semantics, GUI execution, terminal/finalization, or goal semantics.
- If evidence shows Gate 1 World or Gate 2 Delivery content is wrong, stop and reopen that gate instead of mixing a repair into Gate 3.

## Steps

1. [completed] Read mandated sources and audit current producers/consumers/reconstruction/capacity paths.
2. [completed] Record owner/consumer/deletion map and positive target contract.
3. [completed] Implement the owner-level envelope/binder/admission/model-boundary cutover and delete superseded authorities.
4. [completed] Add owner, identity, capacity, exact-boundary, media/tool, fault-injection, and two-turn production-path verification.
5. [completed] Run focused suites, full pytest, Ruff, compileall, diff checks, and production negative searches.
6. [completed] Update architecture, benchmark, and C10 plan status without claiming overall closure.
7. [completed] Stage only Gate 3 files, commit `refactor: bind one canonical provider envelope`, verify worktree, and stop.
8. [completed] Correct reserve algebra so input limits and complete context-window limits each subtract reserve exactly once.
9. [completed] Close the supported ActionPolicy message algebra at one instruction and no independent history messages.
10. [completed] Add default-budget, soft-target, complete-window, and ghost-algebra regression properties.
11. [completed] Re-run Gate 3 focused/full/static/negative verification and update non-admitted status docs.
12. [completed] Commit the Gate 3 correction independently and stop before Gate 4.

## Files produced or modified

- `.codex-plans/gate3-canonical-provider-envelope-execution.md` — persistent execution plan.
- `src/affordance_runtime/model/policy/canonical_provider_envelope.py` — immutable contract and sole binder.
- `src/affordance_runtime/model/policy/request_admission.py` — complete-envelope capacity authority.
- `src/affordance_runtime/model/policy/turn_packer.py` — tentative bind/admit and final envelope reuse.
- `src/affordance_runtime/model/policy/pydantic_ai_bridge.py` — admitted-envelope consumer and typed codec.
- Gate 0 recorder, provider-free owner/integration tests, and architecture/benchmark status authorities.

## Evidence log

- Baseline `git status --short`: only `?? output/`.
- Baseline HEAD: `3d976a07811773a1610a33ad5158f900e5870809`.
- Gate 3 owner-focused C8-C12 suite: `583 passed, 3 skipped`.
- Full provider-free pytest: `1594 passed, 24 skipped` (using `/dev/shm` basetemp; three strict lifecycle wall-clock tests were filesystem-latency-sensitive under `/tmp` and pass unchanged in memory-backed temp storage).
- Ruff: pass.
- Post-commit audit reopened Gate 3: `7844b7f1` double-counts output/protocol/safety reserve against an already-derived
  input `admission_limit`, and the Envelope type admits multiple instructions/nonempty history that the codec does not
  transport. Both owner contracts and their default-profile properties now pass, but Gate 4 remains explicitly not
  admitted until a separate Gate 3 exit review grants entry.
- Corrected Gate 3 owner-focused C8-C12 suite: `587 passed, 3 skipped`.
- Corrected full provider-free pytest: `1598 passed, 24 skipped` using `/dev/shm` basetemp.
- Gate 4 read-only consumer audit found that `prefit_estimated_total_tokens`, `full_candidate_tokens`, and
  `lens_candidate_tokens` have no distinct candidate producers and are all written as complete-request totals, while
  the active WebArena diagnostic compares `full_candidate_tokens` with input-only `estimated_total_tokens`. The core
  Envelope/admission algebra was not falsified; the breakdown diagnostic owner is reopened for deletion of the ghost
  fields and consumer rather than probe-side conversion.
