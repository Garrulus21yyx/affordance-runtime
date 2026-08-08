# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-08
> **Reviewed start baseline:** `codex/migrate-world-interaction-capabilities@d435250e25f1d1c07ffd0f2558affcbdba4983a3`
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## Status vocabulary

`NOT_STARTED` → `PROTOTYPE_EXISTS_NOT_ADMITTED` → `INTEGRATED_NON_DEFAULT` →
`DEFAULT_CUTOVER` → `DELETED`. “Implemented” below never implies default
cutover unless stated explicitly.

## Current truth

The old transactional `Coordinator → RuntimeDelta → RuntimeCommitter →
StateKernel` path remains the current product baseline/default. It is frozen
against new product capability but has not been deleted.

The target path now has:

| Capability | Status |
|---|---|
| TaskGoal / EvaluationSpec | `INTEGRATED_NON_DEFAULT` |
| TaskPlan / Milestone / LocalObjective contracts | `INTEGRATED_NON_DEFAULT` (no model planner) |
| WorldObservation / AgentWorldView / ActionSpace | `INTEGRATED_NON_DEFAULT`; exact option/binding-group fidelity and source/world currentness closed |
| ActionIntent / BoundActionRequest / ActionResult | `INTEGRATED_NON_DEFAULT`; admitted selection identity retained through binding |
| Evaluator-owned completion and bounded Turn state | `INTEGRATED_NON_DEFAULT` |
| SurfaceAdapter / UnifiedWorldEnvironment | complete for DOM, Visual-only, and WoT single-surface minimums; semantic fusion pending |
| StaticEnvironment | `INTEGRATED_NON_DEFAULT` on new World contracts |
| real-browser DOM short loop | `INTEGRATED_NON_DEFAULT`, positive C1 proof |
| Visual new-loop vertical | `INTEGRATED_NON_DEFAULT`, positive C2 proof |
| WoT new-loop vertical | `INTEGRATED_NON_DEFAULT`, local-simulation positive C3 proof |
| semantic confirmation continuation | `INTEGRATED_NON_DEFAULT`; typed request/decision, run-scoped session, fresh semantic rebind, single-send consumption |
| P5-D6.1 confirmation/evaluation contract completion | `INTEGRATED_NON_DEFAULT`; effective risk, destination identity, bounded presentation, terminal immutability, policy reselection, evidence lineage, explicit task control |
| RoutePolicy | implemented, post-hard-gate only |
| BindingCache | `PROTOTYPE_EXISTS_NOT_ADMITTED` |
| ActionBatch | helper implemented; not AgentLoop-integrated |
| long-horizon TaskPlan execution | `NOT_STARTED` |
| default product cutover | `NOT_STARTED` |

The live DOM, Visual-only, and WoT local-simulation proofs use the same `TaskGoal` factory,
deterministic policy, semantic evaluators, and `activate` vocabulary. Each uses
an offered action ID, exact binding group, one execution, one measured surface
probe, a fresh observation, and evaluator-owned completion. DOM selectors and
Visual screenshot/region/viewport/point data stay inside private bindings.
WoT href, method, security reference, schema, rate metadata, and TD identity
also stay private. Credentials are resolved only inside the HTTP transport.

The live DOM proof uses one `TaskGoal`, a deterministic policy selecting an
offered action ID, an exact eligible-binding group, a selector-private DOM
binding, one execution, one measured live currentness probe, a fresh
observation, and an independent `TaskEvaluator` completion decision. The new
loop does not import or call the old Coordinator, StateKernel, RuntimeCommitter,
ActionContract, or ExecutionReceipt.

## Migrated foundations

- WoT TD security/rate/schema/event-description parsing and the non-default
  target-loop HTTP transport/SurfaceAdapter are implemented.
  Event subscription execution is not implemented and events are not offered
  as executable options.
- WoT read state sources carry public security-scheme, minimum-interval,
  content-type, and property-schema metadata. An unselected scheme is reported
  unavailable without transport fields, and related write/invoke affordances
  are withheld. The proof uses explicitly referenced `nosec` and Runtime
  `LOCAL_SIMULATION`; remote/physical scopes remain HIGH risk.
- SoM utilities and smart-room/mock-web assets are implemented.
- Smart-room images use committed lockfiles and `npm ci`. Audit debt remains:
  node-wot 4 vulnerabilities (2 moderate, 2 high); dashboard 2 (1 moderate,
  1 high). Fixes currently require breaking dependency upgrades.

## Proof and remaining gates

Focused target tests cover source/world/fingerprint stale zero-call, Visual
screenshot/viewport/scroll/DPR/zoom/orientation/region staleness, coordinate
isolation, WoT TD/form/security stale checks, one-probe/one-send, rate limits,
credential isolation, task-forbidden
effect filtering, higher-confidence forbidden-route exclusion, distinct schema
route identity, Runtime-owned risk floors, result lineage, schema values and
unsupported-type rejection, observation/probe budgets, unknown
no-retry, initial zero-op
completion, finish-proposal rejection, receipt/effect separation, private
parameter rejection, observation identity freshness, low-risk-only admission,
bounded turns, real Chromium DOM/Visual completion, and real local HTTP WoT completion.

The instrumented/plain-DOM, Visual-only, and WoT local-simulation minimums are closed; generic business-effect
classification beyond the current coarse categories remains future work. The
new-loop DOM/Visual/WoT adapter-only symmetry is proven for the shared-state
task. This does not prove semantic fusion or physical-device confirmation. Semantic fusion across
simultaneous sources remains future work. External full-agent
benchmarks remain blocked. Old-core deletion is not admitted.

P5-D is closed on the non-default target path. `ActionEvaluationStatus` now
distinguishes `EFFECT_CONFIRMED`, `NO_EFFECT_CONFIRMED`, `UNKNOWN`, and
`REJECTED`. `AgentRunSession` is process-local only: confirmation always starts
from a fresh observation, matches the semantic subject, binds the current
private route, and consumes confirmation only after `SENT`/`SENT_UNKNOWN`.
Unknown effect waits for the user and never replays automatically.

D6.1 applies the TaskGoal risk floor to the displayed and hashed effective
risk. Semantic destination identity now flows from SelectAction through
ActionSpace admission, ActionIntent and confirmation subject, while current
adapters correctly offer no destination. Confirmation summaries use only the
secret-free world view and bounded/redacted semantic parameters. Terminal
sessions return their original result. A missing exact confirmed subject returns
to policy rather than selecting a Runtime candidate. Confirmed action effects
require exact request/before/after lineage and evidence references;
TaskEvaluation UNKNOWN waits and BLOCKED terminates explicitly.

Semantic fusion remains deliberately deferred. The small `AgentLoopState` is
complete; a distinct LoopPolicy and optional TurnRecorder remain future work.
Model-backed target policy/evaluator composition and the new-loop benchmark
harness have not begun. WoT effectful rate limiting is implemented; property
read-side scheduling/rate limiting is not implemented.
