# M8.2A PR breadth rerun after V-PRB-6B current-state progress reconciliation

This directory records the clean local PR breadth rerun for committed revision
`95fe00b7c069c4f45b6d32e07de4921dba07e02b`.

The run is negative evidence. It does not close PR breadth, does not authorize a
fresh diagnostic, and does not support any promoted or official benchmark score.

## Run identity

```yaml
revision: 95fe00b7c069c4f45b6d32e07de4921dba07e02b
branch: agent/migrate-runtime-components
working_tree_clean: true
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
python_version: 3.12.3
browsergym_miniwob_version: 0.14.3
playwright_version: 1.44.0
model_provider: ollama
model_name: qwen2.5:7b
planner_profile: strict-generalist
profile: pr
tasks:
  - click-button
  - enter-text
  - choose-list
  - click-dialog
  - click-button-sequence
  - form-sequence
seeds:
  - 0
  - 1
output_dir: /tmp/affordance-pr-breadth-95fe00b-rerun-20260728-140235
evaluation_identity_digest: sha256:7e05b36b3256e399d5df128759b94c2b5ba75a4c326b683ed53726fe5c75a793
official_score_claimed: false
```

## Result

```yaml
expected_episode_count: 12
observed_episode_count: 12
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
provider_failures: 0
rate_limit_retry_count: 0
transient_retry_count: 0
external_evaluator:
  passed: 11
  failed: 1
runtime_verification:
  passed: 10
  failed: 2
runtime_failure_count: 2
mean_official_reward: 0.9166666666666666
official_success_rate: 0.9166666666666666
```

Failure clusters:

```yaml
- episode_ids:
    - form-sequence:seed-0
  root_layer: CONTRACT / FIELD_BINDING
  failure_signature: proposal_validation:validation:planner_proposal_rejected
  runtime_error: planner cannot finish before verifier-backed subgoal completion
  official_reward: 1.0
- episode_ids:
    - form-sequence:seed-1
  root_layer: INTENT / PLANNING
  failure_signature: planner_waiting_clarification
  runtime_status: waiting_clarification
  official_reward: 0.0
```

## Decision

The V-PRB-6B current-state progress reconciliation slice reduced the observed
Runtime failure count from the previous 3-failure diagnostic baseline to 2, but
it did not preserve the clean external reward baseline. `form-sequence:seed-1`
regressed to external reward `0.0`.

Per the V-PRB-6B approval rule, external reward regression rejects the child
production slice. The production behavior must be reverted, the evidence kept,
and the next repair must be reclassified from the archived traces rather than
continuing to broaden BrowserGym adapter evidence or deleting required
obligations.

## Artifacts

```yaml
browsergym-report.json:
  sha256: a563f1fe452e60178f8b03aabcba94e8e93ee87f8ca5e59c3e4c7069217840b9
browsergym-runtime-preflight.json:
  sha256: 71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47
matrix-metadata.json:
  sha256: 7e46db654bcfe1ac9af8fd65a178a62693f9ffacfb9537a305deb8559a0f5dd3
ollama-gpu-preflight.json:
  sha256: 511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d
```
