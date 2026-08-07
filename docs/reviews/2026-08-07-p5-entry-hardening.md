# P5-0 Entry Hardening / Owner-Boundary Closure

> **Lifecycle:** CURRENT REFERENCE TO A FROZEN TRANSACTIONAL BASELINE
> **Direction status:** superseded as an implementation queue by the
> [Unified World Interface Evolution Plan](../superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

This review remains the factual record of P5-0 hardening work. Its committer,
delta, read-view, and dispatch recommendations are no longer future target gates.
They are retained baseline history until the short-loop path replaces them.
The repository's consolidated review baseline is now `8d7cfd6b7d43c72f9b45bb4144a62553d90c23a8`;
the intermediate SHAs below are preserved as the chronology of the review.

## Baseline

- Branch: `agent/migrate-runtime-components`
- P5-0E start SHA: `538be27f8a9aea3fa9d7f25d271b4d0bf6681f7f`
- P5-0E start worktree: clean
- Previous P5-0 review SHA: `538be27f8a9aea3fa9d7f25d271b4d0bf6681f7f`
- Baseline full suite: `1028 passed`
- Baseline Ruff, mypy, and `git diff --check`: passed

The repository documents contained older counts; this review uses the commands
run against the start SHA as the authoritative baseline.

## 0A — pre-dispatch linearization

Canonical owner: `RuntimeCommitter.admit_dispatch`.

Input is a final sealed `ActionContract`, exact observation, `ExecutionAttempt`,
final admission, and typed pre-dispatch events. Output is a single-use
`DispatchPermit` and the committed trace parent. The old owner was the local
`ActionStage.events` list crossing the Executor boundary.

The commit order is now:

`ContractBuilt → RouteSelected → PreflightPassed → ExecutionAttemptIssued →
ExecutionAttemptCommitted → DispatchIntentCommitted → Executor dispatch`.

The committer enters `ACTING`, binds exact contract/attempt, increments the
step/effectful counters once, and only then returns a permit. The premature
`ActionStarted` event was removed. Admission failure and permit replay remain
zero-call. Focused P4 C4 dispatch tests pass.

## 0B — typed deltas

`RuntimeTransition.state_updates` and generic `setattr(state, ...)` application
were removed from the previous product committer path. The typed delta family
was introduced, but it is not yet a closed commit protocol. Its current members
are:

`PhaseDelta`, `ObservationDelta`, `PlanningDelta`, `ExecutionAdmissionDelta`,
`ReceiptDelta`, `EffectSettlementDelta`, `ProgressDelta`, `RecoveryDelta`,
`CompletionDelta`, `ArtifactIndexDelta`, and `RouteCalibrationDelta`.

`RuntimeCommitter` rejects unknown delta types. Admission validates contract id,
contract hash, and expected state version; receipt validates current attempt
identity; recovery and progress deltas have separate fields and cannot carry
the other domain's state. Negative tests cover unknown deltas and authority
field absence.

The approval shadow write was removed. A run gate now references the root
gate's single in-process token dictionary; it is not global or persistent.

## 0C — state/read-set reduction

`RuntimeStateSnapshot` no longer binds a prototype or dynamically proxies
prototype methods. The snapshot factory now builds an explicit detached read
set instead of `deepcopy(vars(StateKernel))`. The old class name
`RuntimeStateProjection` was replaced with `ProgressWorkingState`; its output
is converted to a `ProgressDelta`. Coordinator verification shadow state was
removed: planning/result paths use committed `StateKernel.latest_verification`.

This slice is not fully closed. The remaining `ProgressWorkingState` mutable
working-set bridge and several stage input types still need migration to the
dedicated frozen `PerceptionStateView`, `PlanningStateView`,
`ActionAdmissionStateView`, `ProgressStateView`, `RecoveryStateView`, and
`ResultStateView` types. No checkpoint/resume format was introduced.

## 0D — compatibility and containment

Canonical transaction modules no longer import `planning.py`'s private
`_action_compatible`; the shared semantic owner is
`action_semantics.py`. Product default composition remains
`ActionTransactionMaterializer`.

The full compatibility consumer inventory remains open for the legacy builder,
BrowserGym compatibility builders, `legacy_run_request`, and benchmark-only
imports. God-file extraction was intentionally not expanded into a mechanical
split. This is deferred until the read-view seam is complete so that no second
owner or shadow path is introduced.

## Adversarial sweep

Covered by focused tests: stale admission/CAS, policy and capability drift,
permit replay, concurrent permit consumers, transport truth including
`SENT_UNKNOWN`, approval exactness, P4 zero-call behavior, and typed-delta
unknown/owner boundaries. Remaining active audit items are artifact lineage
streaming SHA/path containment and a commit-owned route-calibration update.

## Verification

- Full pytest after changes: `1036 passed` on the final completed run; one
  browser-fixture recovery case was rerun separately and passed.
- Ruff: passed
- mypy: passed (`192` source files)
- `git diff --check`: passed
- Adaptive routing benchmark tests: passed
- Local stale-recovery benchmark: passed
- P4 C4 dispatch focused suite: `18 passed`
- Typed delta/read-set/recovery focused suites: passed
- P4/API/benchmark focused acceptance set: `86 passed`

## Deferred

- Finish frozen per-stage read views and remove the mutable progress working set.
- Close transition dual-channel support and transition-level commit atomicity.
- Move route calibration behind an authoritative committer-owned update.
- Complete compatibility consumer inventory/isolation and god-file containment.
- Run and record the separately provisioned Stable Task API 3/3 and official
  21-run core benchmark command if the harness is available.

P4 MVP remains CLOSED. P5 admission remains UNBLOCKED; P5-1 is not being
started from this slice because the deferred 0C/0D/0E entry debt above is still
open. P5-R1 through P5-R4 have not started. No production authorization
platform was added.

## P5-0E follow-up

Start SHA: `538be27f8a9aea3fa9d7f25d271b4d0bf6681f7f`; the follow-up began from a
clean worktree and has not been pushed. Final local HEAD after the follow-up is
`ea94671eed0147212007e4580a022dfcded9cdf9`, with a clean worktree.

The transition owner is now `RuntimeTransition(expected_state_version, deltas)`.
`PreparedDispatch` is the immutable ActionStage-to-committer handoff. The
committer generates and orders `ContractBuilt`, `RouteSelected`, committed
preflight, approval, `PreflightPassed`, `ExecutionAttemptIssued`,
`ExecutionAttemptCommitted`, and `DispatchIntentCommitted`; stages no longer
provide the successful dispatch event tuple. Batch validation runs against
detached state and trace before live state, trace, artifact index, or failure
ownership is mutated.

Receipt and effect settlement deltas are attempt/hash-bound; duplicate receipts,
weak settlement evidence, stale versions, unknown/no-op deltas, and invalid
lineage fail closed. Artifact registration now enforces run-root containment,
rejects symlinks, and computes SHA-256 incrementally. Canonical compatibility
checks use `action_semantics.action_compatible` rather than a private planning
owner.

The remaining open owner debt is material: `RuntimeStateSnapshot` and
`ProgressWorkingState` are still a detached compatibility bridge, the complete
frozen per-domain read-view cutover is not done, and the full compatibility
consumer inventory/god-file containment is not closed. Accordingly this
follow-up does not declare P5-0 CLOSED or P5-1 READY. P4 MVP remains CLOSED;
P5-R1 through P5-R4 remain unstarted; no production authorization platform was
added.
