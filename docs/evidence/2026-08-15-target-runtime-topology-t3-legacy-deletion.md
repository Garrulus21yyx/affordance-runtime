# Target Runtime topology T3 — legacy owner deletion

Date: 2026-08-15

Status: `T3_IMPLEMENTED / T4_READY / LIVE_NOT_RUN`

## Result

T3 removed the executable staged Runtime instead of retaining an import facade.
The only product lifecycle is now:

```text
TargetRuntime -> AgentLoop -> AgentRunSession
```

The deleted clusters include `Coordinator`, root runtime/composition/client,
contract-execution and runtime phases; workflow TaskSpec/TaskPlan authority;
action-choice, planning, perception, progress, recovery, transaction and
verification-phase owners; compatibility semantic compilers; legacy local and
BrowserGym benchmark executables; task RPC/local-scenario integrations; and
their sole-purpose tests and scripts.

The exact production-path absence contract is
[`tests/architecture/legacy_runtime_paths.txt`](../../tests/architecture/legacy_runtime_paths.txt).
It contains 179 paths. The adjacent architecture test proves every path is
absent and rejects any live source import of an exact deleted module or child.
After the slice, 331 production Python files remain: 30 at package root and 111
under `benchmarks`.

## Retained owners

- `TargetRuntime`, `AgentLoop`, `AgentRunSession`, task intake and target CLI
  remain the product façade/lifecycle owners.
- Reusable BrowserGym mechanics remain under `surfaces/browsergym`; MiniWoB
  manifests, task-state interpretation, runners and reports remain benchmarks.
- DOM document modeling is under `surfaces/dom/document_model.py`.
- WoT TD parsing and security are under `surfaces/wot`.
- SoM execution remains under `surfaces/visual/som.py`; route-free screenshot
  annotation values live at the model boundary and create no action authority.
- The visual proposal port needed by BrowserSession is retained as
  `surfaces/visual/proposal.py`; deleted task/workflow perception derivation is
  not wrapped.
- Pricing/settings target acceptance witnesses use a test-owned local HTTP
  fixture. Production contains no reference-scenario fixture or oracle.
- The benchmark CLI retains only independent ScreenSpot, WorkArena, WebArena,
  WASP and provider-preflight commands. Deleted runtime benchmark commands are
  unparseable.

## Compatibility and executable deletion

No `read-new/fallback-old`, re-export alias, archived executable source or
alternate composition fixture remains. Historical JSON/evidence documents stay
readable as records, but their runtime, launch scripts and report adapters are
not executable owners. Provider wire normalization and private backend
primitives introduced before T3 are unaffected; neither is a legacy Runtime
authority path.

## Test disposition

Tests of supported target, action, evaluation, continuation and surface
contracts remain. Tests that only preserved a deleted owner were deleted with
it. Retained invariants were rewritten at their current owner: target pricing
and settings acceptance, DOM structured-document projection, model-boundary
schema projection, benchmark CLI isolation, verification-package absence and
workflow-plan absence. The architecture manifest replaces implementation-detail
tests of the old Coordinator with a repository-wide physical/import property.

Validation:

- focused architecture/target/model witnesses: `132 passed`;
- full pytest: `1589 passed, 27 skipped`;
- Ruff: pass;
- mypy: pass across 331 source files;
- `git diff --check`: pass;
- live benchmark: not run.

## Non-claims

T3 does not close StateFact dual writes, multi-source observed-world graph A.1,
or the broad `activate` effect-authority defect. It adds no production
`scroll`, `press_key`, `focus`, `drag_to` or `hover` binding/tool. Those action
families remain blocked. The minimum topology prerequisite for A.1 is met, but
T4 surviving-file owner moves and T5 fresh-context topology review remain open.
