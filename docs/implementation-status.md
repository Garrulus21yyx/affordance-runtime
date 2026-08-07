# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-08
> **Reviewed start baseline:** `codex/migrate-world-interaction-capabilities@1336d6c5ac3c2c585ad9b885d0a0e0a2d4d8ea90`
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
| WorldObservation / AgentWorldView / ActionSpace | `INTEGRATED_NON_DEFAULT`; task-aware legality and source/world currentness closed |
| ActionIntent / BoundActionRequest / ActionResult | `INTEGRATED_NON_DEFAULT` |
| Evaluator-owned completion and bounded Turn state | `INTEGRATED_NON_DEFAULT` |
| SurfaceAdapter / UnifiedWorldEnvironment | complete for single-DOM minimum; multi-source identity/currentness closed, semantic fusion pending |
| StaticEnvironment | `INTEGRATED_NON_DEFAULT` on new World contracts |
| real-browser DOM short loop | `INTEGRATED_NON_DEFAULT`, positive C1 proof |
| Visual and WoT new-loop verticals | `NOT_STARTED` |
| semantic confirmation continuation | `NOT_STARTED` (typed waiting placeholder only) |
| RoutePolicy | implemented, post-hard-gate only |
| BindingCache | `PROTOTYPE_EXISTS_NOT_ADMITTED` |
| ActionBatch | helper implemented; not AgentLoop-integrated |
| long-horizon TaskPlan execution | `NOT_STARTED` |
| default product cutover | `NOT_STARTED` |

The live DOM proof uses one `TaskGoal`, a deterministic policy selecting an
offered action ID, a selector-private DOM binding, one execution, a fresh
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

Focused target tests cover source/world/fingerprint stale zero-call, task-forbidden
effect filtering, result lineage, schema values, observation budget, unknown
no-retry, initial zero-op
completion, finish-proposal rejection, receipt/effect separation, private
parameter rejection, observation identity freshness, low-risk-only admission,
bounded turns, and real Chromium DOM completion.

The new-loop DOM/Visual/WoT positive matrix is not complete. Semantic fusion and
route selection across simultaneous sources remain future work. External full-agent
benchmarks remain blocked. Old-core deletion is not admitted.
