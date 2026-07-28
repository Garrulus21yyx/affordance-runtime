# ODG-5 shadow diagnostic after post-observation trace hookup

## Scope

This run collects focused ODG-5 shadow-comparison diagnostics after
`commit_post_observation_progress()` started writing diagnostic-only
`ObligationProgressShadowCompared` trace events.

It is not PR breadth, fresh diagnostic, nightly, release, promotion evidence,
or an official score claim. The purpose is to classify whether the remaining
`form-sequence` progress failures are explained by divergence between legacy
TaskPlan progress and canonical obligation ready projection before opening
ODG-6.

```yaml
revision: 04a2fcd310f8af246b23fb4bfced6a0fad8519fb
source_tree_digest: sha256:3fe7d7c5f43c5f7f5e3cb030ee65f264b825cdf480389fc3965037c7aed4bda0
working_tree_clean: true
profile: diagnostic
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
output_dir: /tmp/affordance-odg5-shadow-04a2fcd-20260728-205619
official_score_claimed: false
promotion_status: held
```

## Result

```yaml
expected_episode_count: 4
observed_episode_count: 4
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
provider_failures: 0
rate_limit_retries: 0
transient_retries: 0

external_browsergym_reward:
  passed: 4
  failed: 0

runtime_verification:
  passed: 2
  failed: 2
```

The two Runtime failures are the known `form-sequence` finish-guard failures:

```yaml
failure_cluster:
  episodes:
    - form-sequence:seed-0
    - form-sequence:seed-1
  runtime_error: planner cannot finish before verifier-backed subgoal completion
  phase: proposal_validation
  root_layer: CONTRACT / FIELD_BINDING
```

## Shadow comparison summary

```yaml
enter-text:seed-0:
  compared_events: 2
  classifications:
    aligned: 2
  shadow_failed_events: 0

enter-text:seed-1:
  compared_events: 3
  classifications:
    role_pending: 3
  role_pending_reason: blocking_availability_predicate_pending
  shadow_failed_events: 0

form-sequence:seed-0:
  compared_events: 10
  classifications:
    aligned: 10
  shadow_failed_events: 0

form-sequence:seed-1:
  compared_events: 8
  classifications:
    aligned: 8
  shadow_failed_events: 0
```

## Classification

The focused diagnostic provides two useful facts:

1. The `form-sequence` residuals are not explained by divergence between the
   legacy active TaskPlan subgoal and the canonical ready-obligation projection.
   At the final failure point, both projections agree on the ready dependent
   checkbox obligation, while the planner attempts `finish`.
2. `enter-text:seed-1` is now Runtime-passing, but the shadow model still
   reports the submit-button availability predicate as `role_pending`. That
   supports keeping availability-role semantics out of the standard progress
   authority until ODG-6 has an explicit current-observation satisfaction rule.

The observed `form-sequence` mechanism remains a post-action/progress
attribution gap: checkbox and submit effects appear in `satisfied_effects`, but
only the first slider subgoal receives verifier-backed completion credit. This
supports continuing toward ODG-6/ODG-7/ODG-9 rather than reopening the rejected
BrowserGym evidence expansion, weakening the finish guard, or returning to
pre-action TaskPlan progress-target expansion.

## Boundaries

```yaml
diagnostic_only: true
obligation_ledger_initialized: false
obligation_ledger_mutated: false
coordinator_obligation_commit: false
finish_gate_changed: false
planner_context_changed: false
taskplan_behavior_changed: false
browsergym_adapter_changed: false
pr_breadth_claimed: false
promotion_claimed: false
```

## Artifact hashes

```text
4f858963c7a99354ca0680d3a724788057edfb14fd1d6d225eb071ab752f605a  browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  browsergym-runtime-preflight.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  ollama-gpu-preflight.json
886a1846e3b7fa60ac78bfff25b977b8a5b6d6e23f372966e765a02cd92caff9  matrix-metadata.json
b5e04dcf2127c64db39121132051089e07a905fa7a0276ec0b267d708aed16f0  episodes/enter-text-427ded534111-seed-0.json
890846a4751a0cc0cb13d88b86d8071f187a3ef9168df1ee9dc60177ce7aba40  episodes/enter-text-427ded534111-seed-1.json
fac75ae69ef786e69ab57388b7d76b6b3f2b232d48d3e62d4769e10c8aace7bb  episodes/form-sequence-38db0cbc4539-seed-0.json
20201df87eccf02099aaff3ec19e88de8da52a983debe6f932f9ef71036ead03  episodes/form-sequence-38db0cbc4539-seed-1.json
```
