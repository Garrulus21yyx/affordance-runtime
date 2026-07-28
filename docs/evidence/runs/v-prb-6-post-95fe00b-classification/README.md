# V-PRB-6 post-95fe00b residual classification

This is a read-only diagnostic classification of the two `form-sequence`
residuals from the rejected `95fe00b` PR breadth rerun.

It does not admit production code, does not reopen the rejected
current-state progress reconciliation path, and does not claim PR breadth,
fresh diagnostic, promotion, or official score readiness.

## Source evidence

```yaml
implementation_revision: 95fe00b7c069c4f45b6d32e07de4921dba07e02b
current_revert_revision: 204ca17de9706f3109c45e68795ca72b4f8da776
pr_breadth_report: docs/evidence/runs/m8.2a-pr-breadth-95fe00b/browsergym-report.json
local_output_dir: /tmp/affordance-pr-breadth-95fe00b-rerun-20260728-140235
official_score_claimed: false
```

The comparable rerun result was:

```yaml
expected_episode_count: 12
observed_episode_count: 12
external_evaluator:
  passed: 11
  failed: 1
runtime_verification:
  passed: 10
  failed: 2
invalidated_episode_count: 0
provider_failures: 0
```

## Classification

### `form-sequence:seed-0`

Observed result:

```yaml
runtime_status: aborted
official_reward: 1.0
runtime_error: planner cannot finish before verifier-backed subgoal completion
```

The TaskPlan had three required obligations:

```yaml
- subgoal_id: obligation:e515e21388bc6a4f91fca0a7
  subject: slider_value_7
  relation: has_changed
  terminal: false
- subgoal_id: obligation:847ff8b7ec9e70c6612c7cf8
  subject: checkbox_3_state
  relation: has_changed
  depends_on:
    - obligation:e515e21388bc6a4f91fca0a7
  terminal: false
- subgoal_id: obligation:a04b4a88e7983c0781e57c3b
  subject: submit_button_state
  relation: has_changed
  depends_on:
    - obligation:847ff8b7ec9e70c6612c7cf8
  terminal: true
```

The trace shows action selection advanced to checkbox and submit while the
proposal's `subgoal` field still named the active slider subgoal:

```yaml
checkbox_action:
  event: PlannerProposalProduced
  line: 183
  action_kind: activate
  proposal_subgoal: slider_value_7 has changed
  target_affordance_id: semantic:checkbox-3:3a200f3fef88
  expected_effects:
    - checkbox-3 checked
submit_action:
  event: PlannerProposalProduced
  line: 204
  action_kind: activate
  proposal_subgoal: slider_value_7 has changed
  target_affordance_id: semantic:submit:c839464ca626
  expected_effects:
    - submitted
```

The submit verifier then credited the slider criterion instead of the dependent
checkbox/submit obligations:

```yaml
event: SubgoalCompleted
line: 218
completed_subgoal_id: obligation:e515e21388bc6a4f91fca0a7
evidence_id: verification:snap_b560fc962aeb4f9db4b19c32da59f9b8:1:state_delta_or_terminal:24
linked_criterion_id: subgoal:obligation:e515e21388bc6a4f91fca0a7:criterion:0
```

The finish proposal was then correctly rejected because verifier-backed
completion had not been recorded for the dependent checkbox subgoal:

```yaml
event: FailureDetected
line: 226
active_subgoal_id: obligation:847ff8b7ec9e70c6612c7cf8
completed_subgoals:
  - obligation:e515e21388bc6a4f91fca0a7
satisfied_effects:
  - target: semantic:checkbox-3:3a200f3fef88
  - target: semantic:submit:c839464ca626
```

Classification:

```yaml
root_owner: V-PRB-6A
mechanism: progress target mismatch
details: >
  The resolver selected dependent checkbox/submit actions, but the Runtime
  evidence binder still used the stale active/proposal subgoal for progress
  credit. Finish guard behavior is correct; the missing piece is a
  Runtime-owned intended progress target for the action being executed.
not_v_prb_6b: true
not_browsergym_reward_authority: true
not_finish_guard_weakening: true
```

### `form-sequence:seed-1`

Observed result:

```yaml
runtime_status: waiting_clarification
official_reward: 0.0
runtime_error: ""
```

The trace repeatedly attempted slider `press_key` actions, rejected their
progress evidence because it was not linked to active mandatory criteria, and
then produced an empty `ask_user` proposal before reaching the required external
state:

```yaml
last_context_before_stop:
  event: PlannerContextBuilt
  line: 117
  active_subgoal: slider_value has changed
  latest_verified_delta:
    target: 17
    verifier_kind: control_state
    observed: true
  visible_slider_context: -4
terminal_proposal:
  event: PlannerProposalProduced
  line: 120
  action_kind: ask_user
  subgoal: ""
  target_affordance_id: ""
```

Classification:

```yaml
root_owner: rejected-path regression symptom
mechanism: planner_waiting_clarification after uncredited active slider progress
details: >
  This residual exists in the rejected `95fe00b` path and regressed the
  external reward baseline. It should not become the next production owner by
  itself. Use it as evidence that the rejected progress reconciliation path is
  not acceptable, then return to the better accepted diagnostic baseline before
  opening a new production slice.
not_v_prb_6b_read_only_availability: true
not_evidence_broadening_target: true
```

## Decision

The next admissible production slice is not another V-PRB-6B current-state
availability repair. The strongest actionable mechanism is the V-PRB-6A
progress-target mismatch shown by `form-sequence:seed-0`.

The next RED should be based on a Runtime-owned explicit progress target:

```yaml
candidate_slice: v-prb-6a-explicit-progress-target
entry_baseline: use the accepted 66dae07 diagnostic baseline or a fresh clean
  rerun on the current reverted code before production admission
red_behavior: >
  When the resolver intentionally selects a dependency-unlocked checkbox or
  submit action while the active projection is stale, Runtime must bind verifier
  evidence to the intended subgoal, not always to the stale active subgoal.
forbidden:
  - BrowserGym official reward as completion authority
  - receipt success as subgoal completion
  - finish guard weakening
  - required obligation deletion
  - BrowserGym adapter evidence broadening without a generic Runtime target
  - immutable Planner input mixed into the same patch
```
