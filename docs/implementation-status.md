# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-08
> **Reviewed start baseline:** `codex/migrate-world-interaction-capabilities@b14e6fbbafc83f4e163bdada4a4e3750010f6a84`
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
| SurfaceAdapter / UnifiedWorldEnvironment | complete for single-DOM and Visual-only minimums; multi-source identity/currentness closed, semantic fusion pending |
| StaticEnvironment | `INTEGRATED_NON_DEFAULT` on new World contracts |
| real-browser DOM short loop | `INTEGRATED_NON_DEFAULT`, positive C1 proof |
| Visual new-loop vertical | `INTEGRATED_NON_DEFAULT`, positive C2 proof |
| WoT new-loop vertical | `NOT_STARTED` |
| semantic confirmation continuation | `NOT_STARTED` (typed waiting placeholder only) |
| RoutePolicy | implemented, post-hard-gate only |
| BindingCache | `PROTOTYPE_EXISTS_NOT_ADMITTED` |
| ActionBatch | helper implemented; not AgentLoop-integrated |
| long-horizon TaskPlan execution | `NOT_STARTED` |
| default product cutover | `NOT_STARTED` |

The live DOM and Visual-only proofs use the same `TaskGoal` factory,
deterministic policy, semantic evaluators, and `activate` vocabulary. Each uses
an offered action ID, exact binding group, one execution, one measured surface
probe, a fresh observation, and evaluator-owned completion. DOM selectors and
Visual screenshot/region/viewport/point data stay inside private bindings.

The live DOM proof uses one `TaskGoal`, a deterministic policy selecting an
offered action ID, an exact eligible-binding group, a selector-private DOM
binding, one execution, one measured live currentness probe, a fresh
observation, and an independent `TaskEvaluator` completion decision. The new
loop does not import or call the old Coordinator, StateKernel, RuntimeCommitter,
ActionContract, or ExecutionReceipt.

## Migrated foundations

- WoT TD security/rate/schema/event-description parsing is implemented.
  Event subscription execution is not implemented and events are not offered
  as executable options.
- WoT read state sources carry public security-scheme, minimum-interval,
  content-type, and property-schema metadata. An unselected scheme is reported
  unavailable without transport fields, and related write/invoke affordances
  are withheld. Only an explicitly referenced `nosec` scheme is executable.
- SoM utilities and smart-room/mock-web assets are implemented.
- Smart-room images use committed lockfiles and `npm ci`. Audit debt remains:
  node-wot 4 vulnerabilities (2 moderate, 2 high); dashboard 2 (1 moderate,
  1 high). Fixes currently require breaking dependency upgrades.

## Proof and remaining gates

Focused target tests cover source/world/fingerprint stale zero-call, Visual
screenshot/viewport/scroll/DPR/zoom/orientation/region staleness, coordinate
isolation, task-forbidden
effect filtering, higher-confidence forbidden-route exclusion, distinct schema
route identity, Runtime-owned risk floors, result lineage, schema values and
unsupported-type rejection, observation/probe budgets, unknown
no-retry, initial zero-op
completion, finish-proposal rejection, receipt/effect separation, private
parameter rejection, observation identity freshness, low-risk-only admission,
bounded turns, and real Chromium DOM completion.

The instrumented/plain-DOM and Visual-only minimums are closed; generic business-effect
classification beyond the current coarse categories remains future work. The
new-loop DOM/Visual adapter-only equivalence is proven for the shared-state
task, but the DOM/Visual/WoT positive matrix is not complete. Semantic fusion across
simultaneous sources remains future work. External full-agent
benchmarks remain blocked. Old-core deletion is not admitted.
