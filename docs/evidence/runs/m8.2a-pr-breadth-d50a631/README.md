# M8.2A PR Breadth Rerun at d50a631

This evidence records the clean PR breadth rerun after the third V-PRB-5C
strict-planner proposal repair.

## Run identity

```yaml
revision: d50a631a2e67b294db4b6273106df85fd941b3b7
source_tree_sha256: sha256:ff68bc0347e2e0e87d25273dcfec055297c3bad06bbb4bab3d6064b9fab5e1ea
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
runtime_python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
python_version: 3.12.3
browsergym_miniwob_version: 0.14.3
playwright_version: 1.44.0
model_provider: ollama
model_name: qwen2.5:7b
episode_timeout_s: 165
model_call_timeout_s: 10
max_model_calls: 15
execution_reserve_s: 15
evaluation_run_identity: sha256:6855a4359c435386f7abfbfbbabe2b5b63d5661ee8da199d2e4658fa9c1b562d
official_score_claimed: false
promotion_status: held
remote_ci: disabled
```

## Matrix result

```yaml
expected_episode_count: 12
observed_episode_count: 12
official_reward:
  passed: 12
  failed: 0
runtime_failure_count: 3
runtime_error_counts:
  planner cannot finish before verifier-backed subgoal completion: 3
provider_failure_counts: {}
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
```

The external BrowserGym reward gate is 12/12 for this selected PR breadth
matrix. Runtime accounting is not closed: three episodes reached official
reward 1.0 but aborted after a `finish` proposal was rejected by the Runtime
terminal-completion guard.

Affected guard episodes:

- `enter-text:seed-1`
- `form-sequence:seed-0`
- `form-sequence:seed-1`

## Governance interpretation

This rerun closes V-PRB-5C for the current PR breadth matrix: the previous
`form-sequence` official reward failures caused by terminal-submit follow-up
and negative-slider stop/direction no longer reproduce.

It does not close PR breadth acceptance, fresh diagnostic readiness, nightly,
release, or promotion. V-PRB-6 must classify and repair the Runtime terminal
completion guard without weakening independent verifier authority or treating
BrowserGym reward as Runtime completion authority.

## Artifact hashes

```yaml
browsergym-report.json: sha256:dc4b4b9d7cf192c3de9aab00544396ea26ab8932c55b75d2212ba09b94ec5518
matrix-metadata.json: sha256:d68de8f9f0c8ee37cb2b67a7aa3c580c0ea9f46291b6d85bdefcaa7eeaa03872
browsergym-runtime-preflight.json: sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47
ollama-gpu-preflight.json: sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d
```
