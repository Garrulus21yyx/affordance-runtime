# M8.2A PR Breadth Rerun at 9ad1288

This evidence records the clean PR breadth rerun after the
V-PRB-6B current-state discard replacement child production repair.

## Run identity

```yaml
revision: 9ad128848a070ba1026f3696e2ea5a9edc55a592
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
runtime_python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
python_version: 3.12.3
browsergym_miniwob_version: 0.14.3
playwright_version: 1.44.0
model_provider: ollama
model_name: qwen2.5:7b
model_digest: 845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e
episode_timeout_s: 165.0
model_call_timeout_s: 10.0
max_model_calls: 15
execution_reserve_s: 15.0
official_score_claimed: false
promotion_status: held
remote_ci: disabled
```

BrowserGym runtime and Ollama/GPU preflight were ready for this run. Remote CI
was intentionally disabled for this iteration, so this archive is local
equivalent evidence only and does not make a remote-green claim.

## Matrix result

```yaml
expected_episode_count: 12
observed_episode_count: 12
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
official_reward:
  passed: 11
  failed: 1
runtime_failure_count: 4
runtime_error_counts:
  "StructuredModelError: structured response failed LLMIntentDraft validation: :json_invalid": 1
  execution_failed: 1
  "planner cannot finish before verifier-backed subgoal completion": 2
official_score_claimed: false
promotion_status: held
```

Failed or Runtime-failed episodes:

- `click-button:seed-1` — official_reward=0.0, runtime_status=failed,
  error=`StructuredModelError: structured response failed LLMIntentDraft validation: :json_invalid`
- `enter-text:seed-1` — official_reward=1.0, runtime_status=failed,
  error=`execution_failed`
- `form-sequence:seed-0` — official_reward=1.0, runtime_status=aborted,
  error=`planner cannot finish before verifier-backed subgoal completion`
- `form-sequence:seed-1` — official_reward=1.0, runtime_status=aborted,
  error=`planner cannot finish before verifier-backed subgoal completion`

## Governance interpretation

This is negative PR breadth evidence. The V-PRB-6B current-state discard
replacement is a safe local repair, but this clean rerun proves it is
insufficient for PR breadth closure. `enter-text:seed-1` still does not reach
Runtime completion, and both `form-sequence` seeds still fail Runtime finish
admission even though the BrowserGym external reward is 1.0.

V-PRB-6A remains open as the separate dependent checkbox/submit progress-scope
binding diagnostic. The `click-button:seed-1` JSON-invalid intent draft failure
remains a separate schema/provider robustness cluster and must not be mixed
into V-PRB-6A or V-PRB-6B.

This run does not close PR breadth acceptance, fresh diagnostic readiness,
nightly, release, promotion, or any official score claim.

## Artifact hashes

```yaml
browsergym-report.json: sha256:b959f61bcdceaa8035f3e5775f9d3714fd82be1ebc0d254301a6ec005e98f6ce
browsergym-runtime-preflight.json: sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47
matrix-metadata.json: sha256:70ea52bd73a583a737ef594715d405029509f612138553f471c17a311799e9c2
ollama-gpu-preflight.json: sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d
```
