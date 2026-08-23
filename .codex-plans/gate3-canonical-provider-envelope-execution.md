# Gate 3 Canonical Provider Envelope execution

Status: complete

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
