# M4.6 Runtime Recovery Implementation Plan

Goal: implement the bounded inference-time recovery contract for provider calls,
repairable decision rejection, and semantic action effects, then rerun the frozen
25-case MiniWoB control-feedback selection.

Constraints:

- Preserve one authoritative owner for provider facts, ActionSpace/ActionPage,
  admission violations, execution receipts, action effects, and task state.
- Provider attempts do not create GUI decisions, transitions, or turns.
- Recovery feedback is a model-safe projection and never becomes a second action
  authority.
- A recovery page cannot reset the control epoch or fabricate information gain.
- Screenshot/multimodal transport and real subgoal planning remain out of scope.
- Existing immutable evidence is never modified; the rerun receives a new run ID
  and evidence directory.

## Steps

| Step | Status | Work | Files created or modified |
|---|---|---|---|
| 1 | done | Map current provider, admission, effect, projection, benchmark, and evidence owners; freeze the smallest compatible algebra. | This plan |
| 2 | done | Implement typed provider attempt/outcome orchestration with bounded retry, Retry-After/backoff policy, optional compatible fallback, single accepted response, and environment wiring. | `model_policy/provider_orchestrator.py`, provider bridge/factory/policy, instrumentation |
| 3 | done | Extend repairable rejection feedback with the rejected public decision, owner-produced violation, recovery constraints, and current ActionPage projection without duplicated authority. | control feedback, admission/schema/page owners, model projection |
| 4 | done | Extend post-execution feedback with owner-produced expected/observed semantic effects and mechanical recovery permissions. | execution cycle and control feedback |
| 5 | done | Update evidence schemas, projections, attestation, and focused invariant/property tests. | targeted benchmark v2, canonical metrics, focused/property tests |
| 6 | done | Run focused tests, affected regressions, type/lint/architecture gates, then resolve failures. | Ruff/mypy passed; final full pytest: 2204 passed, 27 skipped; documentation/property regressions resolved |
| 7 | done | Rerun the frozen 25 MiniWoB cases into a new immutable evidence directory and compare outcomes with `miniwob-control-feedback-25:98e8fff597d94badb82a44f6ed1a4c44`. | valid run `miniwob-control-feedback-25:58be2cd216a24c4bb4fb7786dbebb9e6` |
| 8 | done | Update authoritative implementation/status/review documentation with implementation identity, evidence limits, run ID, and honest outcome distribution. | implementation/status/roadmap/review projections updated without closure claim |

## Exit criteria

- Retryable provider failures are retried within declared attempts/deadline;
  non-retryable failures fail immediately; exhaustion remains infrastructure.
- Exactly one provider response can be accepted for a policy request, including
  late/cancelled attempts.
- Repair feedback names the related public decision, exact owner violation,
  fields that must change, repeat permission, and current offered actions.
- Execution feedback distinguishes dispatch from effect and exposes a typed
  semantic delta plus deterministic retry/rollback/strategy permissions.
- Generated/property tests cover exceptional paths and authority/projection
  boundaries without adding a production branch per witness.
- The same frozen 25 case IDs complete under a new run identity, with evidence
  validity and the full outcome distribution reported without performance or
  generalization overclaim.

## Progress log

- 2026-08-11: plan created; repository was clean at
  `31a6ede3a89d4dbbc3a3708228c37ace5870e68e`.
- 2026-08-11: mapped existing owners. `model_port.py` owns HTTP/provider
  classification and Retry-After; `ModelPortDecisionAdapter` is the one-attempt
  structured bridge; `ActionSpaceBuilder`/`InternalActionPage` own admission and
  offered candidates; `ActionEvaluation` and task evaluation own post-action
  facts; `ControlFeedback` is projection/budget state only. Frozen implementation
  direction: add orchestration above the one-attempt bridge, enrich owner facts,
  and project them without changing screenshot transport or task planning.
- 2026-08-11: provider recovery, rejection snapshots, semantic-effect recovery,
  model-safe projection, and targeted evidence v2 implemented. Focused recovery
  suite passed (129 tests); Ruff passed; full pytest exposed one documentation
  registration gap from this plan and one pre-existing exception-token property
  counterexample, both corrected before rerunning the suite.
- 2026-08-11: first formal launch stopped before directory creation because the
  legacy formal-policy identity gate accepted only the one-attempt adapter. The
  gate now explicitly distinguishes legacy one-attempt campaigns from the
  frozen recovery wrapper; focused identity/runner tests passed (19 tests).
- 2026-08-11: a second launch was stopped after four cases when live inspection
  showed its untracked output directory would invalidate the clean-tree gate;
  the partial directory is retained locally and excluded from evidence.
- 2026-08-11: clean-SHA run `58be2cd216a24c4bb4fb7786dbebb9e6`
  completed 25/25 with valid v2 evidence. Outcomes: 16 control repetitions,
  two ordinary no-progress repetitions, six task failures and one success.
  There were no provider terminal failures, but also no actual provider retries;
  controlled tests, not this live run, exercise retry/exhaustion behavior.
