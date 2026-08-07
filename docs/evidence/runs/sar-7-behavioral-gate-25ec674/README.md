# SAR-7 behavioral gate at 25ec674

## Scope

This is the clean committed SAR-7 behavioral validation after the bounded
semantic closure that repaired the current PR breadth regressions in
`enter-text` and `form-sequence`.

It is local behavioral evidence only. It is not a promoted benchmark score,
nightly, release, or remote-CI claim; `official_score_claimed=false`.

```yaml
revision: 25ec6745ce08f6337c8d040cf1b31bd2a384ff6e
working_tree_clean: true
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
official_score_claimed: false
promotion_status: held
remote_ci: disabled
```

## Clean PR breadth result

```yaml
profile: diagnostic
selected_tasks:
  - enter-text
  - form-sequence
  - choose-list
  - click-button-sequence
  - click-dialog
  - text-transform
seeds: [0, 1]
output_dir: /tmp/affordance-sar7-prbreadth-25ec674-20260730-122136
run_identity_digest: sha256:92c157fa3851c3b6dca209ec691b60a3d5c4e66b1aafad088036dd2c0b2d27c3
source_tree_digest: sha256:bc5c31816d67aed2f1b436c368f07a6fe1e10f322ec544f9c59797d50f8b01c8

expected_episode_count: 12
observed_episode_count: 12
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
provider_failures: 0
rate_limit_retries: 0
transient_retries: 0

external_browsergym_reward:
  passed: 12
  failed: 0
  official_success_rate: 1.0
  mean_official_reward: 1.0

runtime_verification:
  passed: 12
  failed: 0
  runtime_failure_count: 0
```

## Fresh diagnostic result

```yaml
profile: diagnostic
selected_task_count: 30
seeds: [0, 1]
output_dir: /tmp/affordance-sar7-fresh-diagnostic-25ec674-20260730-122427
run_identity_digest: sha256:3baf9b5ea2f88ce90bdbedf5d907425e0dc79fc54e22c7b0a31e3bfe71a09f82
source_tree_digest: sha256:bc5c31816d67aed2f1b436c368f07a6fe1e10f322ec544f9c59797d50f8b01c8

expected_episode_count: 60
observed_episode_count: 60
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
provider_failures: 0
rate_limit_retries: 0
transient_retries: 0

external_browsergym_reward:
  passed: 15
  failed: 45
  official_success_rate: 0.25
  mean_official_reward: 0.25

runtime_verification:
  passed: 15
  failed: 45
  runtime_failure_count: 45
```

Fresh diagnostic failure clusters:

```yaml
runtime_owner_failure_clusters:
  - signature: schema_incompatible
    root_layer: CONTRACT / FIELD_BINDING
    episodes: 1
  - signature: execution_uncertain:execution:execution_failed
    root_layer: EXECUTION
    episodes: 3
  - signature: intent_compilation_rejected
    root_layer: INTENT / PLANNING
    episodes: 2
  - signature: planner_waiting_clarification
    root_layer: INTENT / PLANNING
    episodes: 26
  - signature: task_planning:validation:planner_proposal_rejected:action_instruction_subgoal
    root_layer: INTENT / PLANNING
    episodes: 1
  - signature: task_planning:validation:planner_proposal_rejected:entry_outcome_already_satisfied
    root_layer: INTENT / PLANNING
    episodes: 9
  - signature: verification:verification:verification_failed:state_delta_or_terminal
    root_layer: VERIFICATION
    episodes: 3
```

## Local code gate

```yaml
full_pytest: "/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest -q => 1268 passed"
ruff: "/home/yang/.venvs/affordance-browsergym-py312/bin/python -m ruff check src tests scripts => passed"
mypy: "/home/yang/.venvs/affordance-browsergym-py312/bin/python -m mypy --ignore-missing-imports src => success over 143 source files"
uv_build: "uv build => passed"
diff_check: "git diff --check => passed"
```

The host `python -m pytest` environment lacks Playwright and failed
`tests/test_pricing_gold_path.py` for that reason. The repository's BrowserGym
Python 3.12 environment above is the validation environment for this evidence.

## Artifact hashes

```text
bf578c116c7dcadebeee72b4e4514b103e6d8e693f20d530e641b513eab0cbba  pr-breadth/browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  pr-breadth/browsergym-runtime-preflight.json
fa5419b8f9b7de72eb547b069f69c08173e6e6f1af89e919c239ef2cd736c178  pr-breadth/episodes/matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  pr-breadth/ollama-gpu-preflight.json
07d20e1185c5e1b4fe05f2bc7e9a3a73ca02af2e7f641db662f249df16f0d34c  fresh-diagnostic/browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  fresh-diagnostic/browsergym-runtime-preflight.json
4ebddebc8c1bf38a7db1eb340900bc8fb5936ced83b65e0e7e98697a2c969bc7  fresh-diagnostic/episodes/matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  fresh-diagnostic/ollama-gpu-preflight.json
```

## Classification

```yaml
sar_7_selected_goal:
  progress_writer_extraction: complete
  terminal_writer_centralization: complete
  semantic_cleanup_sar_7_1_to_7_5: complete
  clean_pr_breadth: passed_12_of_12
  fresh_diagnostic: complete_with_residuals
  status: local_complete_for_sar_7_behavioral_gate

sar_7_promotion:
  remote_ci: disabled
  fresh_diagnostic_success_rate: 0.25
  promotion_status: held
  official_score_claimed: false

next:
  - SAR-8 single recovery protocol may proceed as architecture work.
  - Fresh diagnostic residuals remain capability work and must not be
    converted into a promotion claim.
```
