# T3.2 Probe V2 Provider-Free Convergence Plan

Status: in_progress

## Goal

Converge the existing T3.2 semantic delivery gate without changing the GUI authority chain. Live/provider witness
execution is explicitly outside this increment by user direction.

## Constraints

- Preserve the run3 evidence as failed evidence; probe v2 produces a new evidence directory.
- Do not weaken product semantics to satisfy a probe.
- Do not change the existing one-tool-per-operation architecture, ActionSpace, Resolver, Binder, Executor, or native
  TaskEvaluator authority.
- Tool Schema convergence may remove repeated wording or redundant schema annotations only; it must not remove a
  currently reachable operation or control capability.
- Use `/home/yang/.venvs/affordance-browsergym-py312/bin/python` and load the project `.env` without printing secrets.
- Run no live provider call or task-0 witness in this increment.
- Do not commit `.codex-plans/`.

## Steps

- [done] Inspect current probe evaluator, frozen probes, task-21 evidence, Tool Schema projection, and runner
  commands on the dirty T3.2 tree.
- [done] Fix probe matching so one recovered item jointly satisfies label, role, required operation, and next
  DeliveryManifest membership.
- [done] Freeze probe v2: task 0 `Bestsellers + tab|link + activate`; task 27
  `Search + searchbox + type_text`.
- [done] Diagnose task 21 independently and classify the failure before changing its acceptance contract.
- [done] Reduce stable per-request Tool Schema estimate to <=2,000 tokens by removing repeated descriptions and
  schema prose without changing the Tool architecture or authority.
- [done] Run focused tests and all six provider-free probe-v2 cases into a new evidence directory; retain run3.
- [done] If and only if all six pass, run a fresh-context architecture/contract audit and repair only a proven
  shared invariant defect.
- [done] Record the user's cancellation of the live/provider witness; no provider call was made.
- [done] Run proportional final tests, Ruff, diff-check, synchronize architecture/benchmark status, and report the
  honest non-closed/closed gate state. Commit/push only if requested or already authorized by the active workflow.

## Evidence Log

- Existing failed evidence: `evidence/w1b-world-t32-semantic-delivery-run3/`.
- Task-21 diagnosis: official product page; old Search probe was task-irrelevant, while `Reviews (12)` is a current
  public executable link and the task-relevant recovery target. Product code was not changed.
- Focused probe/tool tests: 63 passed; Ruff import ordering repair pending rerun.
- Probe-v2 run1: retained failed evidence; five pages passed and task 44 rejected the unrelated Projects witness.
- Probe-v2 run2: `evidence/w1b-world-t32-probe-v2-run2/`; six of six passed, zero provider attempts, Tool Schemas
  1,739..1,879 estimated tokens, request median 6,802.5 tokens.
- Fresh-context audit 1: FAIL on one P1; bounded ContextBuilder could shrink public Actor facts after lossless
  projection while DeliveryIndex retained full World. P2 stale freeze wording also found.
- P1 repair: removed whole-context Actor fitting, added 8-KiB/64-node/256-public-fact lossless property witness, and
  corrected probe-v1/v2 governance wording.
- Post-repair provider-free evidence: `evidence/w1b-world-t32-probe-v2-lossless-run3/`; six of six passed, retained
  Actor nodes equal total nodes on all pages, Tool Schemas 1,739..1,879, request median 6,802 tokens.
- Fresh-context re-audit: PASS; no P0/P1/P2.
- Final verification: `1319 passed, 16 skipped`; Ruff and `git diff --check` passed.
- Live/provider witness: explicitly not run per user direction; requires separate future authorization.
