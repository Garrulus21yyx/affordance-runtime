# Runtime-first R4 Verifier-Calibrated Routing Evidence — 2026-07-22

## Scope

This slice closes the target-specific unified-routing Runtime gate without
adding BrowserGym task names, action-family branches, reward labels, or adapter
syntax to Core routing.

Implemented Runtime behavior:

- `SemanticEntityResolver` uses semantic role, label, action and container
  identity first, then uses current geometry to conservatively pair duplicate
  same-label siblings across sources. Ambiguous matches remain separate. A
  unique cross-source semantic match remains one target so material geometry
  disagreement reaches normal source arbitration.
- `UnifiedRoutePlanner` applies required evidence to each
  `GroundingCandidate`; evidence from another candidate on the same semantic
  target, or from an unrelated page-global screenshot, cannot satisfy its hard
  gate.
- `RouteOutcome` is emitted by `RunCoordinator` after post-action
  verification. It binds candidate, semantic target, contract, post snapshot,
  evidence ids, environment family, action, source, executor and verifier plan.
- `RouteCalibrator` keeps session-scoped statistics and affects route score only
  after at least two conclusive observations in the exact scope.
- only strong evidence from the current independent post-action observation can
  create `verified_success` or `verified_failure`. Receipt-only evidence and
  weak state-delta/terminal evidence are recorded as `inconclusive` and cannot
  update reliability.
- the older single-affordance `CostAwareRouter` is now a static configured
  cost/latency selector. Its receipt-success tracker and `observe(receipt)`
  learning channel were removed, leaving one adaptive policy path.
- ordinary browser observations attach an origin-level `environment_family`;
  other observers can supply an explicit environment/profile family in
  observation metadata.

## Non-BrowserGym acceptance evidence

`tests/test_route_calibration.py` proves:

1. receipt-only and weak state-delta evidence cannot train route reliability;
2. statistics do not cross environment, action, source/executor, or verifier
   scope;
3. two independently verified DOM failures and two visual successes change the
   route on a shifted-layout target with new candidate ids from DOM to visual;
4. the same statistics do not affect an unrelated environment.

`tests/test_unified_grounding.py` proves:

- one semantic target exposes DOM and visual/SoM candidates;
- candidates cannot borrow required evidence from one another;
- unrelated screenshot evidence cannot satisfy a DOM candidate;
- duplicate same-label siblings are paired only when geometry overlaps, while
  ambiguous identities remain separate.

`tests/test_generic_perception_coordinator.py` proves a successful normal
Coordinator path emits one trainable `RouteOutcomeRecorded` trace node carrying
strong post-observation evidence. No BrowserGym module is imported by these R4
acceptance tests.

## Safety and regression evidence

The existing six-profile non-BrowserGym adaptive routing ablation was rerun
after this change. It reports no acceptance errors. The adaptive-unified profile
keeps task success `1.0`, fallback success `1.0`, stale block rate `1.0`, and
unnecessary visual route/model-call rates `0.0`. Every profile retains:

~~~text
unsafe_side_effect_rate: 0.0
verifier_false_accept_rate: 0.0
duplicate_effect_risk_rate: 0.0
~~~

The generated diagnostic artifact is local-only under
`/tmp/affordance-r4-routing.aKpM4R`; it is not promoted as a frozen benchmark
score.

## Verification

Fixed environment:

~~~text
/home/yang/.venvs/affordance-browsergym-py312/bin/python
Python 3.12
~~~

Results:

~~~text
pytest: 442 passed
ruff check src tests: passed
mypy --ignore-missing-imports src/affordance_runtime:
  success, 74 source files
focused adaptive/authoritative/safety/fallback/calibration regression: 14 passed
~~~

## Remaining boundary

R4 is a session-scoped Runtime calibration layer, not an online durable learning
system. It does not persist statistics across runs, activate a TaskSkill, or
consume executor reward. R5 still owns removal of BrowserGym marker/bid/task
semantics from shared modules; R6 still owns canonical trace extraction and
offline, replay-gated durable learning.
