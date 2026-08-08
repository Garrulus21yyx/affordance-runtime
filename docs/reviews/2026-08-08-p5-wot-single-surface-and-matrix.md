# P5-B4/C3 WoT single-surface vertical and three-surface matrix

> **Lifecycle:** IMPLEMENTATION RECORD
> **Semantic authority:** false
> **Branch:** `codex/migrate-world-interaction-capabilities`
> **Requested start SHA:** `0ace7d7d6a34ced4ac4679707eae786f56896cbb`
> **Actual W1 start SHA:** `d7dd608272b6bcb567b4763a50ff08eeef84ae84` (W0 was completed first as its required independent commit)
> **W1–W4 implementation SHA:** `4369b3521a626a3b1e661123d162796398a86ee2`
> **Final HEAD:** the commit containing this record; exact pushed SHA is reported by Git and the final task report
> **Expected post-commit working tree:** clean
> **Date:** 2026-08-08

## Status

```text
DOM_single_surface_vertical: CLOSED
Visual_single_surface_vertical: CLOSED
Visual_adapter_conformance: CLOSED_FOR_CURRENT_FULL_DIGEST_PROFILE
bounded_region_diff: DEFERRED
WoT_single_surface_vertical: CLOSED
DOM_Visual_WoT_adapter_only_matrix: PROVEN
semantic_fusion: NOT_STARTED
physical_device_confirmation: NOT_IMPLEMENTED
P5_D_confirmation: NOT_STARTED
external_benchmark: BLOCKED
default_cutover: NOT_READY
```

This slice proves WoT protocol symmetry only for an explicitly configured
`LOCAL_SIMULATION`. It does not authorize unconfirmed physical-device control.
It added no semantic fusion, automatic cross-surface fallback, ActionBatch,
long-horizon planner, external benchmark run, transaction/event platform, or
default-path cutover.

## W0 Visual housekeeping

- Bounded/task-conditioned proposers report `TRUNCATED`; only explicit
  `acquisition_exhaustive=True` reports `COMPLETE`, and region count is bounded.
- Full-digest currentness no longer invokes the proposer. A successful loop has
  two proposer calls total and zero during the one currentness probe.
- Browser capture performs viewport-before → screenshot → viewport-after,
  retries once on drift, then fails without producing an incoherent frame.
- Pre-pointer acquisition failures are `NOT_SENT / CURRENTNESS_UNAVAILABLE`,
  with zero pointer calls and fresh AgentLoop reobservation.
- Integer click points are rounded/clamped and revalidated inside bbox and
  viewport. Proposer state is projected through a bounded semantic whitelist.

## WoT owner map

| Concern | Canonical owner | Input | Output / boundary |
|---|---|---|---|
| TD/security/rate parsing | existing `adapters/wot.py`, `wot_security.py` | raw TD | `ThingAffordanceModel`; no second parser |
| deployment/route/result contracts | `surfaces/wot/contracts.py` | parser affordance + Runtime scope | immutable WoT-local identity |
| HTTP and credential binding | `surfaces/wot/transport.py` | private route + public scheme | explicit transport status; credential never returned |
| currentness | `surfaces/wot/currentness.py` | bound route + freshly parsed TD | pure identity comparison |
| observation/execution | `surfaces/wot/adapter.py` | task + parser + transport | ordinary SurfaceObservation/ActionResult |
| effect/risk classification | `world/action_classification.py` | task + semantic action + Runtime scope | Runtime category/risk/barrier |

No new owner depends on the old ActionContract, Coordinator,
RuntimeCommitter, StateKernel, recovery transaction, or benchmark task data.

## Deployment scope and classification

```text
read_property: OBSERVATION / LOW
LOCAL_SIMULATION invoke/write: LOCAL_REVERSIBLE / LOW
REMOTE_SERVICE invoke/write: EXTERNAL / HIGH
PHYSICAL_DEVICE invoke/write: EXTERNAL / HIGH
default scope: PHYSICAL_DEVICE
```

TD metadata may raise but cannot lower these Runtime-owned floors or grant an
effect absent from TaskGoal. MEDIUM/HIGH tasks and remote/physical routes stop
at the existing typed confirmation placeholder with zero transport action calls.

## Transport, security, rate, and currentness

The narrow port exposes TD fetch, property read, affordance execution, and TD
revision probe. `HttpWotTransport` resolves credentials only while building the
request. Credentials, Authorization/query auth, signed URLs, and headers never
enter WorldObservation, AgentWorldView, ActionSpace, Turn, ActionResult evidence,
repr, or errors.

Bindings privately retain thing ID, TD digest, source identity/revision,
affordance kind/name/source ID/fingerprint, href, method, content type, schema,
security reference, minimum interval, executor, primitive, semantic action,
and expiry. Policy sees only semantic targets/state, offered actions and public
parameter schemas.

Execute performs one TD probe, exact affordance comparison, schema validation,
run-local rate check, credential late-binding, and at most one HTTP action call.
Stale/unavailable/rate/invalid input are `NOT_SENT`; invocation uncertainty is
`SENT_UNKNOWN`; neither retries nor falls back. Rate limiting never sleeps.

## WoT real HTTP positive proof

The test fixture exposes a real TD endpoint, readable `expanded` property, and
`enable` action over local HTTP with explicit `nosec`. State reaches the Runtime
only through HTTP reads and the existing TD parser.

```text
TaskGoal factory: shared_state_task
Policy: FirstOfferedActionPolicy
ActionEvaluator: SharedStateActionEvaluator
TaskEvaluator: SharedStateTaskEvaluator
semantic action: activate
registered adapters: wot only
status: DONE
full observations: 2
currentness probes: 1
executions: 1
turns: 1
TD HTTP calls: 3 (initial, probe, post-action)
property HTTP reads: 2
action endpoint calls: 1
DOM calls: 0
Visual calls: 0
credential exposure: 0
```

## Negative matrix

Focused tests cover unresolved security, explicit nosec, missing identity,
events without subscription binding, stale TD/form/method/security/schema,
reset invalidation, currentness exceptions, partial read coverage, rate limits,
malformed parameters, pre-send failure, one-call uncertainty, private policy
injection, missing action, forbidden/unallowed effects, higher-confidence
forbidden routes, remote/physical scope, MEDIUM/HIGH task risk, unchanged
property, confirmed/unresolved unknown outcome, and wrong result lineage before
evaluation.

## DOM / Visual / WoT adapter-only matrix

The parameterized test instantiates the same TaskGoal factory, policy class,
action evaluator, task evaluator, semantic action, and expected result. Only
the environment adapter changes.

| Profile | Full observations | Probes | Model/proposer calls | Transport/action calls |
|---|---:|---:|---:|---:|
| DOM | 2 | 1 | 0 | 1 DOM click |
| Visual | 2 | 1 | 2 | 1 pointer click |
| WoT | 2 | 1 | 0 | 1 WoT invoke |

All profiles are `DONE`, one execution, one turn, fresh post-action identity,
private route isolation, and TaskEvaluator-owned completion. This proves only
single-surface adapter symmetry—not fusion, automatic routing, broad
generalization, or production physical-device safety.

## Containment and verification

```text
wot/__init__.py: 17 lines
wot/adapter.py: 277 lines
wot/contracts.py: 200 lines
wot/currentness.py: 40 lines
wot/transport.py: 159 lines
functions over 80 lines: 0
WotSurfaceAdapter imports AgentLoop: no
agent imports WotSurfaceAdapter: no
WoT currentness imports DOM/Visual: no
WoT production imports benchmark tasks: no
target core imports old transaction owners: no
```

Final working-tree commands:

```text
pytest -q: 1234 passed
ruff check src tests: passed
mypy src: passed (243 source files)
git diff --check: passed
docker compose -f environments/smart_room/docker-compose.yml config: passed
DOM Chromium E2E: passed
Visual Chromium E2E: passed
Visual adapter focused suite: passed
WoT adapter focused suite: passed
WoT real HTTP AgentLoop E2E: passed
DOM/Visual/WoT matrix: 3 passed
target core boundaries: passed
specified legacy --runxfail: passed
external benchmark commands: not run
```

External full-agent benchmarks remain blocked by P5-D semantic confirmation,
zero-forbidden-effect/zero-duplicate-unknown exact-head evidence. The old
default product path remains unchanged and cannot yet be deleted.
