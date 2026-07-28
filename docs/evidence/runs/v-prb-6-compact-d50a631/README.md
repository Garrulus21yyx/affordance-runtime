# V-PRB-6 Compact Trace Projection

This diagnostic projection is derived from the clean PR breadth evidence at
`docs/evidence/runs/m8.2a-pr-breadth-d50a631/` and the associated local trace
artifacts under `/tmp/affordance-pr-breadth-d50a631-20260728-020748/`.

It is not a production repair and does not authorize a Runtime behavior change.
It narrows V-PRB-6 into evidence-binding questions that must receive
non-BrowserGym RED coverage before any child production packet is opened.

## Evidence identity

```yaml
source_revision: d50a631a2e67b294db4b6273106df85fd941b3b7
source_evidence: docs/evidence/runs/m8.2a-pr-breadth-d50a631/
official_reward_matrix:
  expected: 12
  observed: 12
  official_reward_passed: 12
runtime_guard_failures:
  planner_cannot_finish_before_verifier_backed_subgoal_completion: 3
promotion_status: held
official_score_claimed: false
```

## Affected Runtime guard failures

| Case | Runtime status | Official reward | Final progress state |
|---|---|---:|---|
| `enter-text:seed-1` | `aborted / planner_proposal_rejected` | `1.0` | first text-change subgoal completed; independent submit-availability subgoal still active |
| `form-sequence:seed-0` | `aborted / planner_proposal_rejected` | `1.0` | first slider-change subgoal completed; dependent checkbox and submit subgoals incomplete |
| `form-sequence:seed-1` | `aborted / planner_proposal_rejected` | `1.0` | first slider-change subgoal completed; dependent checkbox and submit subgoals incomplete |

## V-PRB-6A projection: dependent follow-up evidence binding

`form-sequence:seed-0` and `form-sequence:seed-1` match the V-PRB-6A shape.

Observed pattern:

```text
TaskPlanAccepted
  -> repeated ActionCompleted / PostActionObservationCaptured
  -> SubgoalEvidenceRejected for the first slider subgoal
  -> SubgoalCompleted for the first slider subgoal
  -> planner proposes finish
  -> PlannerProposalRejected:
     planner cannot finish before verifier-backed subgoal completion
```

The final `plan_progress` for `form-sequence:seed-0` is:

```yaml
completed_subgoal_ids:
  - obligation:e515e21388bc6a4f91fca0a7
active_subgoal_id: obligation:847ff8b7ec9e70c6612c7cf8
evidence_by_subgoal:
  obligation:e515e21388bc6a4f91fca0a7:
    - verification:snap_6c19dc48d8f846e9a54a891c6d565977:1:state_delta_or_terminal:24
```

The final `plan_progress` for `form-sequence:seed-1` is:

```yaml
completed_subgoal_ids:
  - obligation:9d3429cc12d364eab99799f8
active_subgoal_id: obligation:47d81cc1f76d58fa9eb3a62b
evidence_by_subgoal:
  obligation:9d3429cc12d364eab99799f8:
    - verification:snap_c0ed03f8aa114e1ba3288b98b5fea967:1:state_delta_or_terminal:24
```

Both traces show strong verifier evidence only for the first slider subgoal.
The later checkbox/submit path succeeds externally, but TaskPlan progress is
not credited to the intended dependent subgoals before finish.

Diagnostic owner candidate:

```yaml
candidate_owner: BrowserGym active-subgoal progress declaration / subgoal evidence binding
primary_question: >
  When the active subgoal is a typed `HAS_CHANGED` checkbox or dependent
  submit-like outcome, does the adapter declare active-subgoal progress evidence
  for the current active subgoal, or does Runtime only see terminal/external
  evidence that cannot satisfy TaskPlan progress?
```

## V-PRB-6B projection: enter-text is not actually single-subgoal

The current trace contradicts the earlier compact label
`single-subgoal terminal completion`.

`enter-text:seed-1` has two TaskPlan subgoals:

```yaml
subgoals:
  - id: obligation:0fdfcd12de46fff314253a2d
    objective: text_field:Kanesha has changed
    action_family: type_text
    outcome: has_changed
  - id: obligation:592e0e1ca058be079d92e454
    objective: submit_button is available
    action_family: null
    outcome: is_available
```

The first text-change subgoal completes with strong verifier evidence:

```yaml
completed_subgoal_ids:
  - obligation:0fdfcd12de46fff314253a2d
evidence_by_subgoal:
  obligation:0fdfcd12de46fff314253a2d:
    - verification:snap_de964ae022f04a1ea9ac6cd555500d55:1:state_delta_or_terminal:15
```

The guard failure happens because the second independent read-only
`submit_button is available` subgoal is still active/incomplete when the planner
proposes finish.

Reclassified diagnostic owner candidate:

```yaml
candidate_owner: read-only terminal-availability progress binding / TaskPlan cardinality
primary_question: >
  Should an already-observed read-only availability obligation be credited by
  TaskPlan progress before the planner is allowed to finish, or should such
  availability be excluded from serial action-progress TaskPlans?
```

This projection means V-PRB-6B should not open a production repair as a
`single-subgoal` bug unless a separate RED proves an actual single-subgoal
Runtime path. The current evidence points to an independent read-only
availability subgoal that remains incomplete.

## Required next REDs

```yaml
v_prb_6a:
  red_name: checkbox HAS_CHANGED click declares active-subgoal progress evidence
  expected_current_result: fail
  current_failure_reason: click/control_state HAS_CHANGED remains task-terminal only

v_prb_6b:
  red_name: read-only availability subgoal must be resolved before finish or excluded from serial action progress
  expected_current_result: not_written
  current_reason: evidence reclassified the case away from single-subgoal terminal completion
```

