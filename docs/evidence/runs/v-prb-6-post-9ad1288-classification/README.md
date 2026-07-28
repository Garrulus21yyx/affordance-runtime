# V-PRB-6 Post-9ad1288 Residual Classification

This compact projection classifies the residual failures from the clean
`9ad1288` PR breadth rerun. It is read-only diagnostic evidence and does not
admit a production repair by itself.

## Source run

```yaml
revision: 9ad128848a070ba1026f3696e2ea5a9edc55a592
source_evidence: docs/evidence/runs/m8.2a-pr-breadth-9ad1288/
runtime_artifacts: /tmp/affordance-pr-breadth-9ad1288-20260728-123843
expected: 12
observed: 12
official_reward_passed: 11
official_reward_failed: 1
runtime_failures: 4
promotion_status: held
official_score_claimed: false
```

## Cluster A — click-button:seed-1

```yaml
episode: click-button:seed-1
official_reward: 0.0
runtime_status: failed
phase: intent_compilation
event: IntentCompilationFailed
error_type: StructuredModelError
message: structured response failed LLMIntentDraft validation: :json_invalid
candidate_owner: intent draft structured decoding / schema-provider robustness
production_change_admitted: false
```

Classification:

This is not V-PRB-6A or V-PRB-6B. Runtime never creates a `TaskSpec`; the
failure happens during model drafting before task planning, proposal binding,
execution, verifier progress, or finish admission. The next repair, if
selected, must be a separate schema/provider robustness slice with a
non-BrowserGym malformed structured-draft reproduction.

## Cluster B — enter-text:seed-1

```yaml
episode: enter-text:seed-1
official_reward: 1.0
runtime_status: failed
phase: task_planning
latest_error: task plan validation: repairable [entry_outcome_already_satisfied]
candidate_owner: verifier-to-subgoal progress binding and task-plan replacement accounting
production_change_admitted: false
```

Key trace facts:

- Initial accepted active subgoal is `text_field:Kanesha has changed`.
- The first `type_text` action passes DOM postcondition evidence, but
  `SubgoalEvidenceRejected` reports that the strong DOM evidence has no
  explicit link to the active mandatory criterion/requirement.
- The subsequent submit action is proposed while the proposal subgoal remains
  `text_field:Kanesha has changed`.
- Submit terminal evidence later completes the text-change subgoal through a
  `task_terminal` verifier, leaving the task-plan replacement/replan loop to
  report `entry_outcome_already_satisfied`.
- The V-PRB-6B current-state discard replacement is therefore insufficient by
  itself; the residual is not simply an already-current availability subgoal.

Required next evidence:

Before another production repair, create a non-BrowserGym RED showing whether
strong DOM value evidence should bind to the active text-change subgoal at the
first postcondition, or whether submit-terminal evidence is incorrectly
backfilling the previous text-change obligation.

## Cluster C — form-sequence:seed-0 and seed-1

```yaml
episodes:
  - form-sequence:seed-0
  - form-sequence:seed-1
official_reward: 1.0
runtime_status: aborted
phase: proposal_validation
latest_error: planner cannot finish before verifier-backed subgoal completion
candidate_owner: V-PRB-6A dependent-subgoal progress-scope binding
production_change_admitted: false
```

Key trace facts:

- The strict semantic resolver selects dependent checkbox/submit actions while
  the proposal subgoal remains the older slider subgoal.
- Checkbox and submit effects appear in `satisfied_effects`.
- Runtime completes only the slider subgoal; the final failure fingerprint
  shows the active subgoal is still a dependent checkbox/submit obligation.
- The finish proposal is produced from BrowserGym external terminal success and
  is correctly rejected because `TaskPlanLifecycle` is incomplete.

Required next evidence:

The existing V-PRB-6A strict xfail remains the right diagnostic direction:
dependent checkbox/submit evidence must be bound to the intended ready
subgoal, not to the stale slider active subgoal and not directly to task
terminal completion.

## Governance decision

```yaml
pr_breadth_acceptance: failed
fresh_diagnostic: not_authorized
promotion: held
next_action: choose exactly one child diagnostic/RED
allowed_next_slices:
  - v-prb-6a-dependent-subgoal-progress-scope-binding
  - v-prb-6b-enter-text-progress-binding-residual
  - click-button-json-invalid-schema-provider-robustness
forbidden_batching:
  - do not mix schema/provider robustness with V-PRB-6 progress accounting
  - do not weaken Runtime finish guard
  - do not use BrowserGym reward as Runtime completion authority
  - do not start immutable Planner input unless trace evidence implicates mutable Planner state
```
