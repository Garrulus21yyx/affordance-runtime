# World-interaction capability migration

Source baseline: `A-Modular-Action-System-Architecture`, branch
`origin/feature/C-009-unify-runtime-architecture`, commit `c3d85f5`.

## Boundary

The migration reuses the old repository's tested hands, eyes, environments,
and evaluation fixtures. It does not make the old controller or mutable world
state authoritative in the current Runtime.

| Capability | Current owner |
|---|---|
| DOM transduction | Existing `adapters/dom.py` and `BrowserSession` |
| WoT TD/security/rate/events | `adapters/wot.py`, `adapters/wot_security.py` |
| WoT target-loop contracts/HTTP transport | `surfaces/wot/contracts.py`, `transport.py` |
| WoT target-loop currentness/orchestration | `surfaces/wot/currentness.py`, `adapter.py` |
| Visual SoM/overlay | `adapters/som.py` |
| Visual screenshot/region contracts | `surfaces/visual/contracts.py` |
| Visual acquisition/currentness/pointer execution | `surfaces/visual/adapter.py`, `currentness.py`, `execution.py` |
| Unified world boundary | `surfaces/base.py`, `world/environment.py`, `world/orchestrator.py` |
| Deterministic target fixture | `testing/static_environment.py` |
| Edge-only old fixture | `testing/legacy_static_environment.py` |
| Failure catalogue | `testing/failure_injection.py` |
| Smart-room and mock web | `environments/` |
| External MiniWoB/WebArena glue | Existing BrowserGym benchmark modules |
| Viable-route ranking | `routing_policy.py` behind `UnifiedRoutePlanner` hard gates |
| Fast-path hints | `memory/binding_cache.py` |
| Target short control loop | `agent/` (`INTEGRATED_NON_DEFAULT`) |
| Low-risk batches | `execution/batch.py` helper only; not AgentLoop-integrated |
| Target WorldEnvironment lifecycle | typed `reset/capture/is_current/execute` port; M4.5-A origin/fallback/counting closure implemented non-default |

## Preserved invariants

- A route policy ranks only candidates that already passed currentness,
  executor, action-support, evidence, and verifier gates.
- A cached hint can resolve only to a freshly grounded candidate with the same
  source, executor, and target fingerprint.
- WoT credentials are resolved at the transport boundary and redacted from
  receipts and errors.
- WoT deployment scope is Runtime configuration. Local simulation permits LOW
  local-reversible invoke; remote service and physical device remain HIGH and
  cannot be downgraded by TD metadata.
- Every single action is followed by a fresh observation before evaluation.
- `SENT_UNKNOWN` never causes an implicit retry.
- Batches contain at most three low-risk actions on one backend and stop on
  the first failure or uncertain transport result.
- Telemetry and compatibility runtime state cannot authorize execution or mark
  a task complete in the new loop.
- Event descriptions may be parsed, but no `subscribe` ActionOption is exposed
  until a surface executor implements subscription execution.
- DOM policy input contains target semantics and offered action IDs, never the
  selector retained in `ActionBinding.payload`.
- World/source observation identity, source revision, and target fingerprint
  remain distinct and immutable across multi-adapter currentness checks.
- Unresolved WoT security produces unavailable source metadata and no
  executable write/invoke affordance; explicit `nosec` remains supported.
- Every offered action names an opaque eligible-binding group and schema
  digest; the Binder cannot escape that admitted group when ranking routes.
- DOM page metadata is a hint only. Runtime-owned classification supplies the
  effect category, risk floor, and observation barrier from TaskGoal and
  surface semantics; authored values can only raise restrictions.
- World identity is checked without physical acquisition, while DOM dispatch
  owns one live target probe whose count is reported separately from full
  observations.
- Visual policy input contains only semantic state and action IDs. Screenshot,
  region, bbox/point, viewport, scroll, DPR, zoom, orientation, and pointer
  data remain Runtime-private. In the current full-digest profile, Visual
  dispatch owns one coherent live capture, does not re-run the proposer, and
  never falls back to DOM.
- WoT policy input contains semantic targets, facts, schemas, and offered action
  IDs only. TD digest, href, method, security reference, content type, and rate
  metadata remain private. Execute performs one TD/affordance probe and one
  transport call without retry or cross-surface fallback.

The older state-kernel/coordinator implementation remains temporarily available
for compatibility and its existing benchmark evidence. The migrated AgentLoop
does not import it; boundary tests enforce that separation.

The current positive matrix status is DOM, Visual-only, and WoT local-simulation
complete for the same shared-state task/policy/evaluators. This proves only
single-surface adapter symmetry. Semantic fusion is not started. RoutePolicy is implemented only after hard gates. BindingCache remains
a not-admitted prototype. Cross-surface claims and default cutover are blocked.

## Historical acquisition gap and closure

At the P5-M4 baseline, the BrowserGym adapter cached reset/step raw snapshots
and consumed each once through `observe()`. It lacked independent active
capture, so refresh paths could reach an empty cache; formal rerun-v3 records
seven such RuntimeError failures.

M4.5-A now closes that gap on the non-default target path. Reset returns the
prepared initial `ObservationAcquisition`, capability-aware `capture()` calls
the pinned backend's read-only current-world API on its owner thread, and
`ExecutionOutcome` carries the typed post-action acquisition. Runtime validates
origin and fresh identity, reports the last real fallback cause and exact
attempt count, and never derives admission from AgentContext projection.

M4.5-B and B.1 separately close control accounting on top of that lifecycle:
execution/acquisition truth is recorded before evaluation, confirmation retries
merge into the original accepted-decision root, AgentLoopState remains current
evaluation authority, and benchmark mapping lives in its own typed projection.
This adds no ledger, replay, event sourcing or state reconstruction.
