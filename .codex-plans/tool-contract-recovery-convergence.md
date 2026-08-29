# Tool contract and recovery convergence

Status: fresh_review_pending

## Goal

Close the committed action-outcome feedback loop so one ActionPolicy receives the real effect of its prior GUI call,
the existing bounded ref-free recent trajectory, and a persistent typed recovery constraint. Remove the default
StrategyRevision split-brain path and reject only mechanically proven exact no-effect replays before binding or
execution.

## Positive invariants

- `ExecutionReceipt` owns dispatch/transport; `ActionOutcome` owns local effect; `TaskEvaluator` alone owns task
  completion. These facts remain orthogonal in the provider-visible ToolReturn.
- A deferred GUI ToolCall is closed exactly once under its original call id on the next provider request, with typed
  dispatch and effect availability, including typed pre-dispatch rejection and exceptional paths.
- `AgentWorkspace.recent_trajectory` remains bounded and ref-free and is projected into the current ActionPolicy
  request without exposing private binding state or creating a second memory store.
- `EpisodeMonitor` owns a persistent recovery epoch. Read/search/discovery probes cannot close a GUI-effect recovery,
  replace its root failed attempt, or consume the next effectful recovery deliberation.
- Runtime admission rejects only an exact public attempt with a still-valid, stable, sent no-effect proof. Unknown,
  sent-unknown, changed-precondition, progressive input, and sequence-only cycle cases are not hard-blacklisted.
- The sole ActionPolicy owns semantic reflection and next-action choice. StrategyRevision performs no default provider
  call and Monitor emits facts/constraints rather than business-route advice.
- No task id, page text, selector, action id, or benchmark-specific production branch is introduced.
- Live benchmark execution remains separately authorized; implementation closure requires provider-free properties,
  held-out coverage, updated architecture/benchmark status, and a fresh-context review.

## Steps

1. [completed] Add characterization and positive gates for GUI ToolReturn dispatch/effect projection and bounded
   recent-trajectory provider delivery; implement the two conversion-owner fixes; run focused gates; commit.
2. [completed] Define the closed recovery epoch/transition algebra, bounded failed-attempt set, deliberate lease, task
   revision and checkpoint semantics; replace ephemeral signal clearing; run state-machine/property gates; commit.
3. [completed] Harden exact-attempt identity and consolidate typed pre-bind replay admission/rejection ToolReturn across
   GUI and local tools; run generative and vertical zero-dispatch gates; commit.
4. [completed] Remove StrategyRevision from the default hot path and remove Monitor semantic route advice while
   preserving one ActionPolicy deliberate recovery; run provider transcript/call-count gates; commit.
5. [completed] Migrate exceptional consumers, traces, prompts, checkpoint restore, architecture tests, and documentation;
   run focused suites, full pytest, Ruff/type gates and negative source scans; commit.
6. [in_progress] Perform a fresh-context implementation review, fix any owner/invariant gaps, record held-out evidence and
   leave live benchmark explicitly pending user authorization; final commit if needed.

## Files changed by step

- Step 1: `.codex-plans/tool-contract-recovery-convergence.md`,
  `src/affordance_runtime/agent/tool_result_projection.py`, `src/affordance_runtime/agent/workspace.py`,
  `src/affordance_runtime/model/policy/grounded_policy_context.py`,
  `tests/unit/agent/test_tool_result_projection.py`, `tests/unit/model/test_model_world_projection.py`,
  `tests/integration/model/test_pydantic_ai_spike.py`, `tests/architecture/test_workspace_authority.py`.
  Focused/unit/PydanticAI gates passed (126 focused plus all 111 PydanticAI integration tests). The broader
  agent/model/architecture run passed 571 tests and had one unrelated missing captured-evidence fixture failure at
  `tests/unit/agent/test_semantic_delivery.py:1008`.
- Step 2: persistent Monitor recovery epoch, lifecycle/checkpoint v5, local-versus-GUI recovery closure properties.
- Step 3: action-scoped ref-free attempt identity, verified-failure-only hard constraints, Runtime same-ID typed
  zero-dispatch rejection, checkpoint v6 migration, property and vertical tests.
- Step 4: removal of StrategyRevision production path, persistent deliberate lease, prompt/trace/context migration,
  run8-shaped diagnostic-read vertical test.
- Step 5: current architecture and benchmark contracts, full fixed-interpreter provider-free gate
  (`2101 passed, 19 skipped, 1 deselected, 1 warning`), isolated missing-fixture reproduction, repository Ruff check,
  changed-surface Ruff format, compileall, and negative source scans. Changed-file mypy is explicitly non-green but
  improves from the base commit's 89 errors in six files to 83 errors in three files; it is recorded as baseline
  evidence, not a passing gate.
- Step 6: pending.

## Commits

- `e479d3d0 Close GUI outcome feedback to action policy`
- `e2d27d33 Persist monitor-owned recovery epochs`
- `4cce34a4 Enforce proven failed attempts at runtime`
- `24bebb0a Unify recovery reasoning in action policy`
