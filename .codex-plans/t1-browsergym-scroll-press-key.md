# T1 BrowserGym Scroll / Press Key Plan

Status: in_progress

## Goal

Onboard BrowserGym `scroll` and `press_key` end to end through the existing semantic capability chain, without adding
new global actions, tool-registry bypasses, raw Playwright routes, or prompt/manager/evaluator changes.

## Constraints

- Do not commit `.codex-plans/`.
- Do not modify `.env` or print credentials.
- Use fixed BrowserGym Python: `/home/yang/.venvs/affordance-browsergym-py312/bin/python`.
- Reuse BrowserGym primitives: `scroll`, `press`, and `keyboard_press`; do not implement container `scroll_at` in T1.
- Keep CoreLoop, ActionPolicy prompt, GoalCompiler, Manager/Auditor/MissionState, provider transport, TaskEvaluator,
  and World compression out of scope unless a shared contract defect is proven.

## Owner Chain

- Semantic registry: existing closed public contracts for `scroll` and `press_key`.
- BrowserGym source/projection/profile/binding/execution: install honest subjects, private bindings, translators, and
  primitive dispatch.
- ActionSpace/Pager/PerTurnToolCatalog: expose current options naturally through existing compiler/resolver.
- Binder/Executor/OutcomeProjector: preserve dispatch authority, fresh acquisition, typed local outcome.
- Diagnostics/docs/tests: update capability baseline, W1b regression, and physical dispatch evidence.

## Steps

- [done] Read task request, AGENTS.md, and requested architecture/benchmark sections.
- [done] Confirm T0 commit and clean product worktree; `.codex-plans/` is local-only.
- [in_progress] Inspect current registry/profile/binding/execution/tool compiler/test topology and BrowserGym primitive signatures.
- [pending] Implement viewport scroll subject/binding/translator/executor route.
- [pending] Implement entity and focused-context press_key subject/binding/translator/executor routes.
- [pending] Add focused property/conformance tests for registry/profile/composer, projection/binding, tool catalog,
  executor/currentness, and core integration.
- [pending] Run true BrowserGym conformance evidence for scroll and press_key with fixed interpreter.
- [pending] Rerun T0 invariants, MiniWoB Like context regression, and W1b-World six-site diagnostic.
- [pending] Run full pytest, Ruff, diff-check, and bounded fresh-context audit.
- [pending] Update docs/evidence status, commit, and push if scope remains T1-only.

## Evidence Log

- T0 HEAD: `740f9a24676932e89349bde75a9b10bba2909d38`.
- Physical dispatch evidence: pending.
- W1b-World T1 regression: pending.
- Full gates: pending.
