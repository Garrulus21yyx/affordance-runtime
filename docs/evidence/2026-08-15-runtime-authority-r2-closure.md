# R2 exact execution, evaluation, and control composition

> **Date:** 2026-08-15
> **Baseline:** `8bed5ba` (R1)
> **Scope:** `BoundActionRequest -> ExecutionOutcome -> post-action ObservationAcquisition -> EvaluationOutcome -> ControlTransition`
> **Status:** `R2_IMPLEMENTED / EXACT_EXECUTION_COMPOSITION / EXACT_EVALUATION_COMPOSITION / EXACT_CONTROL_TRANSITION / LEGACY_SUMMARIES_AND_TURN_DELETED / R3_IMPLEMENTATION_READY / A.2_STILL_OPEN / LIVE_NOT_RUN`

## Result

R2 removes caller-side reconstruction between binding and the decision root.
Production now retains one exact immutable chain:

```text
BoundActionRequest
-> ExecutionOutcome(request, result, post_acquisition | None)
-> EvaluationOutcome(before, execution, consumed acquisition, after,
                     action evaluation, task evaluation)
-> ControlTransition(exact phase aggregates)
```

`ExecutionOutcome` is defined and exported only by `execution`. The unified
world execution boundary is its production owner. The agent boundary also
requires the returned aggregate to retain the exact `BoundActionRequest`
object it issued, so an adapter cannot substitute an equal-looking request.
Evaluation aggregate
contracts own the named constructors for complete and interrupted values across
both execution-triggered and observation-triggered shapes; callers provide
exact inputs but do not choose the low-level field layout or identity.
`ControlReducer` validates exact outcomes and uses `AttemptReceipt` only for
consistency and accounting; it never constructs phase authority.

## Closed algebra and exceptional paths

- `NOT_SENT` retains the exact request/result and has
  `post_acquisition is None`; no acquisition fact is fabricated.
- `SENT` and `SENT_UNKNOWN` retain the exact primary post acquisition. An
  acquisition or evaluation failure cannot rewrite dispatch truth.
- execution cancellation is closed before propagation. A plain adapter
  cancellation before crossing dispatch becomes exact `NOT_SENT/CANCELLED`
  with no post acquisition. An adapter that crossed dispatch raises
  `ActionDispatchCancelled` with exact `SENT_UNKNOWN/CANCELLED`; the coordinator
  creates and retains a cancelled primary post acquisition, closes
  `ExecutionCancelled.outcome`, records that exact outcome in the decision
  scope, and only then propagates host cancellation.
- a proven `NOT_SENT` reroute creates a second exact `ExecutionOutcome`; both
  attempts remain reachable and at most one is effectful. The first error must
  be one of the bounded reroutable errors. Stale/currentness causes require one
  exact currentness acquisition between executions and the second request is
  bound to its world and fresh selection. Rate-limit/unsupported causes retain
  the first exact selection and cannot fabricate a currentness refresh. Every
  reroute advances the binding.
- fallback remains a distinct `LinkedAcquisition`; it is legal only when the
  exact primary post acquisition failed or reused the execution's before-world
  identity, never when the primary is already fresh. Evaluation names the
  exact primary or fallback acquisition it consumed.
- complete evaluation preserves object identity for execution, worlds,
  acquisition, `ActionEvaluation`, and `TaskEvaluation`.
- evaluator failure/cancellation cannot fabricate a complete task result.
  `EvaluationInterruption` is the closed reached-prefix alternative: exact
  causal execution or observation trigger, world/acquisition inputs, optional
  reached `ActionEvaluation`, and one of six typed interruption reasons. Its
  reason maps exactly—not by string matching—to failed or cancelled. It cannot
  represent success.
- foreign request/backend identity is rejected before post acquisition and
  cannot become an invalid exact outcome or trigger evaluation. The same
  exact-issued-request check protects independent capture and cancellation
  returns before they enter a transition.
- physical capture/execute receipts correlate one-for-one with exact reached
  aggregates. Run-scoped attempt and acquisition sequences advance
  monotonically; cancellation cannot become success, unresolved acquisition
  failure cannot become success or silent continuation, and evaluation
  interruption closes only as failed/cancelled.
- the transition after-world is an exact fold, in receipt order, of only those
  correlated acquisitions closed as `ACQUIRED`; otherwise it remains the exact
  before-world. Adjacent roots share that same world object, not merely an
  equal observation ID.
- confirmation continuation retains `CONFIRMED(exact fresh selection, exact
  fresh assessment, exact prior ConfirmationRequest)` plus the exact fresh
  `SelectAction`. The decision fields match the readmission, its first bound
  request retains that selection by identity, and the prior approval cannot be
  substituted. `already_satisfied` is the bounded reached branch with no
  execution.

`RunAccounting` owns contiguous physical attempt IDs and rejects any receipt
that is not the exact next sequence. The acquisition coordinator owns the
acquisition sequence. The reducer does not maintain a second watermark: it
only checks that the exact aggregates and receipts composed into its bounded
transition suffix preserve the owner-issued order.

## Deleted schemas and compatibility paths

The cutover physically deletes `ExecutionSummary`, `AcquisitionSummary`,
`AdmissionSummary`, compatibility `Turn`, `as_turn()`,
`AgentLoopState.recent_turns`, `AgentResult.turns`, `project_turns`, reducer
receipt-to-summary construction, and the world definition/export of
`ExecutionOutcome`.

`ActionAdmissionOutcome` retains reached admitted selection, issue, risk
assessment and confirmation request, including the continuation-only
`CONFIRMED` shape. `ControlTransition` convenience
properties are derived references into stored exact aggregates; they allocate
no second schema. Exact private authority is excluded from representations,
while model/session/benchmark DTOs remain one-way projections.

## Verification topology

`tests/architecture/test_runtime_authority_r2.py` proves that legacy schemas
are absent, `ExecutionOutcome` has one package and one production owner,
evaluation contracts own every legal named shape, the transition stores exact
types, and the reducer cannot construct phase authority. Generated tests cover
monotonic identity, contiguous roots, phase-authority mutation rejection,
terminal absorption, Wait/RequestObservation failure cross-products and
fail-closed status shapes. Representative integration/state-machine witnesses
cover all decision forms plus admission and confirmation-continuation shapes;
this is not claimed to be one exhaustive seven-decision generative model.
Integration tests cover
`NOT_SENT`, reroute, primary/fallback identity, consumed acquisition,
evaluation identity, both execution-cancellation sides of the dispatch
boundary, interrupted evaluation prefixes, admission/risk subject correlation,
confirmation decision/readmission/approval correlation, substituted execution
and capture requests, and removal or substitution of required reroute facts.

Primary changes span execution/evaluation contracts; world execution ports;
agent execution, transition and reducer owners; state/result/context
projections; benchmark instrumentation; and their tests.

## Root cause and newly exposed gaps

The same mechanism still explains every R2 held-out reopening: a downstream
boundary accepted an equal-looking identifier, copied field set, or loosely
correlated receipt in place of the exact upstream aggregate. Example-only
checks then left legal-looking but causally unreachable combinations open.

Fresh review exposed additional architecture gaps beyond the original summary
deletion list: request substitution at execution/capture returns; open and
substring-classified evaluator interruption reasons; missing reroute refresh
and selection identity; fallback without failed/reused primary and repeated
fallback/capture kinds; fabricated after-world installation; and same-ID world
clones across adjacent roots. These are closed by aggregate constructors,
typed reason algebra, exact boundary identity checks, and one deterministic
receipt-to-world fold rather than by benchmark-case branches.

## Final verification

- full repository: `1643 passed, 27 skipped`;
- documentation governance plus architecture suite: `87 passed`;
- focused independent architecture/integration/property/world review:
  `192 passed`;
- Ruff: pass;
- mypy: pass over 334 source files;
- `git diff --check`: pass;
- clean wheel: built from a temporarily empty build tree, legacy paths absent,
  installed wheel import smoke passed;
- independent fresh-context review: **PASS for R2 only**. It found no second
  R2 owner/schema/compatibility path after replaying all held-out mutations.

No live benchmark was run. This verification does not close R3, A.2, or the
full Runtime chain.

## Boundary

R2 does not change request-evidence/no-gain semantics, projection-suffix
enforcement, benchmark topology, `StateFact`, `Relation`, `SemanticDelta`, new
interactions or activate-effect authority. Those remain R3 or later work. No
live benchmark was run. A.2 remains open.
