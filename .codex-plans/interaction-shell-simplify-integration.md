# Interaction Shell × simplify integration plan

Goal: integrate `codex/external-interaction-shell@98103dae` onto local
`codex/simplify-core-runtime@baebf2e2` without changing either existing dirty
worktree, while preserving simplify's benchmark hot path and the verified Shell
v3 authority/control/recovery contract.

Constraints:

- one `CoreAgentLoop`, one Runtime authority, one checkpoint truth;
- simplify owns the current delivery, context, provider exchange, repair and
  history-compaction implementation;
- Shell control boundaries, durable checkpoint/recovery/revision/effect and
  user-control lease must be adapted into those current owners;
- no live benchmark without separate authorization;
- no unrelated changes or test-specific production branches.

| Step | Status | Evidence / files |
|---|---|---|
| S0. Establish clean integration worktree, read authorities, inventory branch delta and preserve both dirty worktrees | done | New branch/worktree created at `baebf2e2`; project policy and existing approved Shell authorities were read. Original Shell/mainline worktrees remain untouched with 24/17 status entries. |
| S1. Merge Shell branch without committing and classify every textual/semantic overlap by owner | done | The expected seven conflicts were the complete textual set; twelve automatically merged shared files remain in the verification surface. |
| S2. Resolve Runtime state/CoreLoop conflicts using simplify hot path plus Shell control/checkpoint invariants | done | Combined observation projection with control/effect state; retained simplify delivery index, context-aware action page and canonical transition. Reconciliation now rebuilds one lineage-consistent projection for its filtered capability space. |
| S3. Resolve provider history/persistence conflicts using simplify invocation/exchange pipeline | done | Retained simplify task-anchor/canonical exchange and output retry pipeline; attached StepPersistence conversation/run lineage to each physical SDK call; retained typed terminal control closure. |
| S4. Reconcile authority/status docs and retain both test suites | done | Mainline benchmark reopening remains first; external Shell capability section retained; both grounding and checkpoint-history tests retained; maintained-doc set now names the frontend governance authority. |
| S5. Run focused static/unit/property/integration gates; repair owner-level failures | done | High-risk Runtime/provider set 193 passed, 3 skipped; broader owner set 934 passed, 3 skipped plus the documented absent-trace failure; Shell backend/architecture 91 passed, 1 skip; final root provider-free run 1942 passed, 19 skipped, 1 explicit absent-trace deselection. Ruff and backend Pyright pass; scoped Mypy has exactly the simplify baseline's 42 existing findings. |
| S6. Run generated-contract, frontend unit/lint/typecheck/build and synthetic Playwright E2E gates | done | Regenerate-and-diff, typecheck, 27 unit tests, lint, build and Playwright synthetic E2E all pass. |
| S7. Run complete relevant provider-free suite, diff hygiene, final authority audit and commit | done | Full provider-free suite passes apart from the explicit historical live-trace deselection. Independent fresh-context review returned APPROVE with no blocking finding; merge commit `04dcc4ac` and post-commit regenerate-and-diff pass. No live benchmark. |
