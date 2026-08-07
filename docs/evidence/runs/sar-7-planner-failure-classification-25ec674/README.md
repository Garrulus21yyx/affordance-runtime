# SAR-7 planner failure classification before SAR-8

## Scope

This is a read-only classification of the SAR-7 fresh diagnostic residuals.
It is intended to inform SAR-8 recovery protocol design. It does not modify
Runtime behavior, Planner behavior, recovery behavior, StateKernel, or
Coordinator.

```yaml
source_report: /tmp/affordance-sar7-fresh-diagnostic-25ec674-20260730-122427/browsergym-report.json
source_revision: 25ec6745ce08f6337c8d040cf1b31bd2a384ff6e
classifier_revision_base: 2cf111002dcb27e5aa3f258768e1f1255e13ca42
classifier_output: docs/evidence/runs/sar-7-planner-failure-classification-25ec674/classification.json
provider_profile_for_future_execution: local_ollama
official_score_claimed: false
promotion_status: held
```

## Result

```yaml
expected_episode_count: 60
observed_episode_count: 60
runtime_failure_count: 45

category_counts:
  current_step_already_satisfied_owner: 9
  model_deferral_with_action_space: 26
  validator_rejected_planning_output: 1
  outside_planner_classification_scope: 9

planner_waiting_clarification_count: 26
entry_outcome_already_satisfied_count: 9
```

## Interpretation

All 26 `planner_waiting_clarification` residuals had at least one non-ask
permitted action in the planner context. The conservative classification is:

```yaml
dominant_planner_waiting_owner: planner_model_or_action_choice_builder
dominant_recovery_semantics: bounded_retry_or_deterministic_choice
not_default_replan: true
not_default_user_clarification: true
```

The 9 `entry_outcome_already_satisfied` failures are not a recovery-policy
problem. They are an owner mismatch:

```yaml
owner: progress_precheck
correct_semantics: current_step_criterion_satisfied_then_complete_step
wrong_semantics: task_plan_invalid_then_replan
fix_before_sar_8: recommended
```

The remaining failures are outside this bounded Planner classification slice
and should be classified by SAR-8 using the existing failure envelopes.

## Next

```yaml
next_sequence:
  - Fix already-satisfied current-step owner path.
  - Proceed to SAR-8 single recovery protocol.
  - Later redesign Planner capability around ActionChoiceBuilder, not another
    chain of task-family regex fallbacks.
```
