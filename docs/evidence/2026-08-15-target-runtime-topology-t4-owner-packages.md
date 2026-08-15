# Target Runtime topology T4 owner-package cutover

Date: 2026-08-15

Status: `IMPLEMENTED / T4_COMPLETE / T5_READY / LIVE_NOT_RUN`

## Result

T4 moved only surviving implementations whose owner was already established:

- product lifecycle façade, composition and product CLI: `app/`;
- capability registry, ActionSpace, admission, binding, routing and action
  policy contracts: `actions/`;
- Actor/model context, policy/tool compilation, evaluator bridge and provider
  transport: `model/context`, `model/policy`, `model/evaluator` and
  `model/providers`;
- browser session/thread ownership and visual grounding/geometry helpers:
  `surfaces/dom` and `surfaces/visual`;
- execution context, task material/action-family contracts, world observation
  and source assertions: their existing `execution`, `task` and `world`
  packages;
- benchmark command and reference-readiness policy: `benchmarks/`.

This was not a blanket rename. Cohesive existing packages such as `agent`,
`evaluation`, `risk`, `confirmation`, `verification` and most `world` modules
were left in place. The package root now has exactly four Python files:
`__init__.py`, `__main__.py`, `immutable.py` and `schema_digest.py`.

## Sole-owner and deletion proof

`ActionOption`, `ActionRisk`, `AdmittedActionSelection` and `ActionSpace` have
one physical definition in `actions/space_contracts.py`. `world/contracts.py`
retains observed-world values and the world-bound private `ActionBinding`; it
imports the shared action risk/destination validation contract rather than
defining a second ActionSpace.

Every production, test and script import was migrated. Old modules were
physically removed, including the root product/CLI modules, `agent/runtime.py`,
`agent/composition.py`, `model_boundary`, `model_policy`, `model_evaluator`,
the action owners formerly under `world`, and displaced root DOM/visual/model
utilities. There are no re-export files, import aliases, fallback-old branches
or dual-read paths. `tests/architecture/test_t4_owner_topology.py` guards the
root file set, displaced import prefixes, single ActionSpace definitions,
benchmark isolation and the `app/runtime.py -> agent/loop.py` dependency.

## Scope and truthful non-claims

This cutover changes physical ownership and imports only. It does not add
`scroll`, `press_key`, `focus`, `drag_to` or `hover` bindings; close StateFact
dual writes; repair the open activate effect-authority gap; implement observed
world graph A.1; or provide fresh live benchmark evidence. T5 remains the
fresh-context topology closure review.

## Verification

Frozen-tree results:

- focused owner/runtime/action/model/surface, architecture and documentation
  governance tests: `237 passed`;
- full pytest: `1594 passed, 27 skipped`;
- Ruff: passed;
- repository-standard mypy: no issues in 335 source files;
- pytest collection: 1616 tests;
- product import and `python -m affordance_runtime --help`: passed;
- isolated sdist and wheel build: passed;
- `git diff --check`: passed.

Live benchmark was not run by design.
