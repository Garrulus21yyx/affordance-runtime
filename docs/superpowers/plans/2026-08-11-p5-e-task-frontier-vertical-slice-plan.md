# P5-E Task Frontier Vertical Slice Plan

Goal: implement the smallest general task-frontier loop that turns verified
local effects into an explicit next-objective boundary without introducing a
task-specific planner, a second action authority, or an extra model call.

Constraints:

- `TaskGoal` remains the stable what/boundary/done authority.
- `VerifiedTaskState` contains verifier-backed requirement/value/evidence facts;
  an `ActiveObjective` is only an admitted temporary control hypothesis.
- The first predicate algebra is closed and unknown predicates fail typed and
  deterministic.
- Objective operation and ordinary decision share one `context_id` and admit
  atomically; failure is zero-dispatch and cannot half-install an objective.
- `ActionSpace` remains the only action authority. Objectives may affect later
  relevance/ranking but never create legal actions.
- `EFFECT_CONFIRMED` does not by itself verify an objective; the typed predicate
  must be satisfied by authoritative public evidence.
- Preserve the M4.6-D provider/feedback/repetition contracts and baseline
  evidence. Screenshot transport remains M4.6-E scope.
- No MiniWoB task-name branches, static full-plan DAG, multi-objective
  concurrency, or natural-language verifier in this slice.

## Steps

| Step | Status | Work | Files created or modified |
|---|---|---|---|
| 1 | done | Map existing TaskGoal, plan/objective state, decision schema, admission transaction, evaluation and progress owners; freeze a minimal algebra and migration boundary. | This plan |
| 2 | done | Add closed objective predicate/operation, ActiveObjective and VerifiedTaskState contracts with strict identity/reference validation. | `task/frontier_contracts.py`, `task/frontier.py` |
| 3 | done | Extend model decision/schema/projection with same-call objective operation while preserving deterministic v1 decision compatibility. | model policy schema/parser/prompt/grounding; model context frontier projection |
| 4 | done | Implement atomic package admission and state commit with zero-dispatch/no-half-install failure semantics. | decision control, loop state, objective admission feedback |
| 5 | done | Implement verifier-driven objective lifecycle and task frontier projection after authoritative observation/evaluation updates. | `agent/frontier_control.py`, execution/observation/top-loop audit paths |
| 6 | done | Add focused invariant, privacy and runtime tests, including copy-paste-style fill-to-next-frontier behavior. | `tests/test_task_frontier_vertical_slice.py` and migrated schema/projection tests |
| 7 | done | Run Ruff, mypy, full pytest and resolve regressions. | Ruff and mypy passed; full pytest 2208 passed, 27 skipped |
| 8 | in_progress | Run an honest targeted benchmark only after the vertical slice is stable, using a new immutable identity and without imposing a circular pre-implementation success threshold. | clean implementation commit and fresh evidence pending |

## Exit criteria

- A model can atomically propose/retain/replace one objective together with one
  ordinary decision in a single policy call.
- Runtime allocates objective IDs; stale retain/replace references fail typed.
- Objective predicates use only the admitted closed algebra and public bounded
  references.
- Invalid objective or invalid decision produces no dispatch and no objective
  state mutation.
- Only verifier-backed evidence can satisfy, invalidate or advance a
  requirement/objective; no-effect normally leaves the objective active while
  prohibiting unchanged action replay.
- The next model context distinguishes satisfied requirements, current frontier
  and active objective, so a verified fill cannot silently collapse back into
  the already-satisfied step.
- Existing M4.6-D recovery, safety, privacy and benchmark evidence contracts
  remain valid.

## Progress log

- 2026-08-11: plan created from the accepted rolling-horizon contract. Initial
  implementation direction combines an Agent-S3-style single-call flat policy
  with verifier-owned task state; no independent Manager call is admitted.
- 2026-08-11: owner map completed. The existing open-dict `LocalObjective`
  remains compatibility-only for relevance tests. New typed frontier contracts
  will be parallel and model packages will opt into them; TaskEvaluation and
  ActionEvaluation remain the only progress evidence inputs, while ActionSpace
  and risk admission remain unchanged action authorities.
- 2026-08-11: vertical slice implemented. Production model output is now
  `agent-decision-package.v2`; one objective operation and one ordinary decision
  share a context and commit only after both admission paths succeed. Objective
  rejection produces typed repair feedback owned by `task_frontier`.
- 2026-08-11: verifier lifecycle and bounded model projection implemented.
  Raw verified values remain Runtime-private; the model receives fact refs,
  requirement states/current frontier, one active typed predicate and recent
  verified/invalidated checkpoints. A focused two-action test proves
  fill-predicate verification leads to a new submit objective; a second test
  proves valid-objective/invalid-action is zero-dispatch and zero-commit.
- 2026-08-11: Ruff, mypy and full pytest passed (2208 passed, 27 skipped).
  Benchmark execution remains separate from implementation completion and has
  not yet supplied held-out closure evidence.
- 2026-08-11: first clean-SHA benchmark run
  `miniwob-control-feedback-25:3a2c917624da468dad895033ca6e41de`
  completed 25/25 with valid evidence but zero successes: 21 control
  repetitions, one ordinary repetition and three task failures. A fresh
  `copy-paste-2` capture showed the shared cause: BrowserGym tasks use an
  outcome-only TaskGoal with no explicit criteria, so the first implementation
  exposed an empty requirement frontier and rejected a semantically concrete
  objective as `unknown_objective_requirement`.
- 2026-08-11: added one Runtime-owned `requirement:task_outcome` for exactly the
  no-explicit-criteria profile, with state derived only from TaskEvaluation.
  Also projected a mechanical next-objective constraint after a verified
  checkpoint while task outcome remains incomplete. A fresh diagnostic then
  showed the model creating and advancing multiple verified objectives instead
  of immediately repeating the first fill; that diagnostic ended in provider
  exhaustion and is not benchmark evidence. A new clean-SHA run remains due.
