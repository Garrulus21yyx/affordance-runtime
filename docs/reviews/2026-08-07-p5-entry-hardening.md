# P5-0 Entry Hardening / Owner-Boundary Closure

## Baseline

- Branch: `agent/migrate-runtime-components`
- Start SHA: `92f7725397171200230d2f52767b477a69746092`
- Final HEAD SHA: `92f7725397171200230d2f52767b477a69746092` (changes uncommitted)
- Start worktree: clean
- Final worktree: modified by this review; no merge/push performed
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
were removed from product source. The closed delta family is:

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

- Full pytest after changes: `1032 passed`
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
- Move route calibration behind an authoritative committer-owned update.
- Complete compatibility consumer inventory/isolation and god-file containment.
- Run and record the separately provisioned Stable Task API 3/3 and official
  21-run core benchmark command if the harness is available.

P4 MVP remains CLOSED. P5 admission remains UNBLOCKED; P5-1 is not being
started from this slice because the deferred 0C/0D entry debt above is still
open. P5-R1 through P5-R4 have not started. No production
authorization platform was added.
