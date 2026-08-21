# T3.2 ActionPolicy output-budget recovery

Status: completed_locally_non_closed
Branch: `codex/simplify-core-runtime`
Started: 2026-08-20

## Goal

Close the provider/wire failure where a reasoning model exhausts its completion budget without final JSON, while
preserving the single-command ActionPolicy contract and existing GUI execution chain.

## Frozen scope

1. Capture provider `finish_reason`, final-content presence, reasoning-content presence, usage, and bounded response
   field metadata at the provider boundary.
2. Separate `output_truncated`, `empty_final_content`, `json_invalid`, and `multiple_tool_calls` typed outcomes.
3. Permit at most one same-turn, same-World retry only for confirmed budget truncation; the retry uses a bounded
   recovery output configuration and does not count as a GUI step.
4. Keep normal ActionPolicy reasoning enabled; any thinking-disabled behavior is a narrow truncation recovery only
   when the endpoint/config explicitly supports it.
5. Make Monitor feedback and stall classification preserve the real failure kind.
6. Keep Manager contracts semantic and free of concrete tool names.
7. Raise ordinary WebArena executor episode budget from 10 to 15 without making 20 the default.

## Non-goals

- No World, DeliveryManifest, Catalog, Binder, Executor, Auditor, GoalPlan, or CoreAgentLoop authority redesign.
- No arbitrary multi-action execution, action queue, fill_form, SemanticTargetSelector, or global reasoning disable.
- No live provider or WebArena witness in this implementation turn.

## Plan

1. [completed] Map provider response parsing, metadata/trace, typed failure algebra, monitor feedback, Manager prompt,
   and WebArena episode-budget ownership.
2. [completed] Implement provider response diagnostics and closed failure classification.
3. [completed] Implement one bounded same-turn truncation retry with explicit output/reasoning settings.
4. [completed] Remove concrete tool vocabulary from Manager prompt/contracts and adjust WebArena budget to 15.
5. [completed] Add focused transport, retry, zero-dispatch, monitor, Manager, and budget properties.
6. [completed] Run provider-free diagnostics, full pytest, Ruff, diff-check, cleanup search, and fresh-context audit.
7. [completed] Re-audit the owner-boundary findings, retain non-closed status, and commit/push only after every local
   gate passes.

## Baseline

- HEAD/origin: `d176b295 fix: scope mission recovery and policy wire`.
- No tracked modifications at task start.
- Existing untracked `.codex-plans/*` and `output/` are preserved.
