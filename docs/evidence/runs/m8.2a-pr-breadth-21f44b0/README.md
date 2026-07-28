# M8.2A PR breadth rerun at 21f44b0

## Scope

This is the clean committed PR breadth rerun after the attempted
`f6d053b` / `21f44b0` V-PRB-6B empty-value `HAS_CHANGED` fill-delta
evidence-binding repair.

It is negative evidence for that attempted production slice only. It is not an
official benchmark score, fresh diagnostic, promotion, nightly, release, or
remote-CI claim.

```yaml
revision: 21f44b09d409902252615747badf27dc60238f95
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
output_dir: /tmp/affordance-pr-breadth-21f44b0-20260728-131602
official_score_claimed: false
promotion_status: held
remote_ci: disabled
```

## Result

```yaml
expected_episode_count: 12
observed_episode_count: 12
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
provider_failures: 0

external_browsergym_reward:
  passed: 11
  failed: 1

runtime_verification:
  passed: 9
  failed: 3

acceptance_errors:
  - enter-text:seed-1: execution_failed
  - form-sequence:seed-0: planner cannot finish before verifier-backed subgoal completion
  - form-sequence:seed-1: planner cannot finish before verifier-backed subgoal completion
```

## Classification

This rerun is a negative regression relative to the prior clean
`66dae07` PR breadth evidence:

- `66dae07` reached 12/12 external BrowserGym reward with 3 Runtime failures.
- `21f44b0` drops to 11/12 external BrowserGym reward while retaining 3 Runtime
  failures.

Therefore the empty-value `HAS_CHANGED` fill-delta evidence-binding repair is
not admitted as an ongoing production repair. The evidence shows that binding
the first text fill as active-subgoal progress changes the later task flow and
regresses `enter-text:seed-1` externally. The repair must be reverted or
redesigned from a stronger TaskPlan/progress-accounting RED.

```yaml
pr_breadth_acceptance: failed
matrix_impact: negative_regression
attempted_slice: docs/change-admission/v-prb-6b-empty-has-changed-fill-delta-binding.yaml
required_action:
  - revert attempted production behavior
  - keep V-PRB-6B rooted at required read-only obligation completion/accounting
  - keep V-PRB-6A form-sequence progress-scope binding separate
fresh_diagnostic: held
promotion: held
official_score_claimed: false
```

## Artifact hashes

```text
09e940792c4faa0d0a8d40aeaa31453b8684d4053dea73585fcd4fb3906ede1c  browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  browsergym-runtime-preflight.json
1c2ffb571671f15478890aad79cc676d093cd5fab32bb4ed59facfd87659985c  matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  ollama-gpu-preflight.json
```
