# Run10 partial working outcome and bounded replan convergence

Status: complete

## Goal

Allow evidence-backed local working outcomes to differ from the overall subtask assessment, while routing semantic
subtask misalignment through the existing ActionPolicy -> Supervisor -> Manager recovery chain.

## Invariants

- EvidenceBoundary validates evidence write legality only; it never judges plan quality or cross-granularity semantic sufficiency.
- TaskGoal remains authoritative; SubtaskContract remains advisory.
- No keyword validator, second planner, second loop, Auditor planning, or task/site specialization.
- Replanning is bounded and materially-different mechanically; native TaskEvaluator remains final authority.
- Preserve the dirty worktree; no live provider, BrowserGym, task-7, or W2 during implementation/gates.

## Steps

1. [completed] Audit WorkingStateProposal producers/consumers, boundary rejection algebra, yield kinds, monitor/recovery, prompt/context projection, and tests/docs.
2. [completed] Remove cross-granularity assessment equality and rename completed_outcomes to working_outcomes without alias.
3. [completed] Add task_link through Manager schema/lowering/trace/ActionPolicy subtask view and prompts.
4. [completed] Add typed needs_replan yield and Supervisor bounded materially-different strategy handling.
5. [completed] Separate fatal evidence/authority boundary rejection from recoverable working-proposal shape feedback.
6. [completed] Add generic counterexample/property/fault tests and removal scans.
7. [completed] Run focused tests, full pytest, Ruff, diff-check, and bounded fresh-context audit; no live.
