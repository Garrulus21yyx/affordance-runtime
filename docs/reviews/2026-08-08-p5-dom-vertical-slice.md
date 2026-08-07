# P5-A/B/C1 Unified World and DOM vertical implementation record

> **Lifecycle:** IMPLEMENTATION RECORD
> **Semantic authority:** false
> **Start branch:** `codex/migrate-world-interaction-capabilities`
> **Start SHA:** `1336d6c5ac3c2c585ad9b885d0a0e0a2d4d8ea90`
> **Final revision:** the commit containing this record
> **Date:** 2026-08-08

## Scope and result

R0, A1, A2, A3, A4, B1, and C1 are complete for a non-default DOM minimum.
The target contracts are implemented, the Unified World Interface has a DOM
adapter, and a real Chromium task reaches COMPLETE after one semantic action.
Visual/WoT target verticals, full confirmation continuation, long-horizon
planning, ActionBatch integration, default cutover, and old-core deletion were
not started.

## Canonical owner map

| Slice | Canonical owner | Input → output | Displaced/legacy owner |
|---|---|---|---|
| A1 | `task/contracts.py` | semantic request data → TaskGoal/EvaluationSpec | scaffold TaskGoal; TaskSpec only via one-way edge projector |
| A2 | `task/planning_contracts.py` | desired states → optional plan/local objective | mandatory legacy planner request/StepSpec |
| A3 | `world/contracts.py`, `world/view.py`, `world/action_space.py` | current source facts/bindings → WorldObservation/policy view/options | legacy Observation/action catalog for target loop |
| A4 | `execution/contracts.py`, `evaluation/contracts.py`, `agent/decisions.py`, `agent/state.py` | semantic selection/dispatch/evidence → typed result/evaluations/turn | ActionContract, ExecutionReceipt, agent types god-file |
| B1 | `surfaces/base.py`, `surfaces/dom/adapter.py`, `world/orchestrator.py`, `world/binder.py` | DOM snapshot + intent → current private request/result | EnvironmentPort/Coordinator route for target loop |
| C1 | `agent/loop.py` | TaskGoal + WorldEnvironment + policy/evaluators → AgentResult | scaffold policy-owned ActionContract/DONE loop |

The only task compatibility projector is `task/legacy_projection.py`, legacy →
target. The isolated pre-target ActionBatch fixture is explicitly named
`LegacyStaticEnvironment`; it is not integrated with AgentLoop.

## R0 environment reconciliation

- Thermostat `postcondition_mismatch` now prevents both target and current
  temperature convergence updates.
- Both Node projects commit lockfiles and Docker builds use `npm ci`.
- Audit debt remains visible: node-wot 4 vulnerabilities (2 moderate, 2 high),
  dashboard 2 (1 moderate, 1 high); available fixes are breaking upgrades.
- WoT state sources expose public scheme/rate/content/schema metadata.
- Missing TD security selection is unresolved rather than dictionary-order
  guessing. Explicit `nosec` remains supported.
- Event descriptions are parsed, but subscriptions are not executable options.

## C1 positive and negative evidence

The real-browser case uses the TaskGoal “Enable shared state”, deterministic
first-offered-action policy, DOM SurfaceAdapter, runtime-private selector,
fresh observation, and independent evaluators:

```text
status=COMPLETE
observation_count=2
execution_count=1
old Coordinator/StateKernel/RuntimeCommitter calls=0
```

Focused tests cover unknown action, execution-payload injection, stale binding,
unconfirmed Finish, initially satisfied task, receipt success without state
change, reused post-action identity, both SENT_UNKNOWN outcomes, non-low-risk
admission, and bounded recent turns. Recorder behavior is outside this slice
because no recorder was integrated.

## Import and size boundaries

AST tests prohibit target-core imports of ActionContract/legacy Observation,
EnvironmentPort, StateKernel, RuntimeCommitter, or the legacy projector. Agent
code does not import BrowserSession/adapters; surfaces do not import AgentLoop.

Largest new target-core file is `agent/loop.py` below the 350-line review
trigger. No target-core function exceeds 80 lines. No legacy frozen hotspot
received new product capability; BrowserSession is reused unchanged behind the
DOM adapter.

## Verification

Start-HEAD baseline, before production edits:

- full pytest: `1067 passed, 1 failed`; the local settings benchmark failure
  passed immediately when rerun alone at the same HEAD and was not deselected;
- Ruff: pass; mypy: pass; diff-check: pass; Compose config: pass.

Final verification commands (no deselection):

```text
pytest -q
ruff check src tests
mypy src
git diff --check
docker compose -f environments/smart_room/docker-compose.yml config
pytest -q tests/test_dom_agent_loop_e2e.py -vv
```

Final result: `1091 passed, 1 xfailed in 31.72s`; Ruff passed; mypy passed
over 228 source files; diff-check and Compose config passed. The one xfail is
the explicit legacy-Coordinator order-dependent fixture described above, with a
three-consecutive-full-pass/deletion exit condition. The real Chromium vertical
also passed independently in 0.86s.

## Remaining debt and gates

- Old transactional Coordinator is still default and retained as baseline.
- `agent/types.py` is a deprecated re-export edge with deletion gated on default cutover.
- Legacy ActionBatch helper still uses ActionContract/ExecutionReceipt and is not integrated.
- BindingCache is a not-admitted prototype.
- Visual/WoT positive target-loop verticals and the cross-surface matrix remain pending.
- Human confirmation has only a typed waiting placeholder; continuation is P5-D.

```text
external_benchmark_status: BLOCKED
remaining_internal_gates:
  - Visual positive target-loop vertical
  - WoT positive target-loop vertical
  - same-task adapter-only DOM/Visual/WoT matrix
  - P5-D semantic confirmation and unknown-effect core
  - zero forbidden side effects and duplicate unknown attempts
```

No old core was deleted and no transaction-platform capability was expanded.
