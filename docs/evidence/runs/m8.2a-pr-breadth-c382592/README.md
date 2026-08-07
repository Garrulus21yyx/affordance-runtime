# M8.2A PR Breadth Rerun at c382592

This evidence records the clean PR breadth rerun after the
V-PRB-6B HAS_CHANGED text progress binding repair.

## Run identity

```yaml
revision: c382592d6d614e5784730fa2ff0347a9a1b09548
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
runtime_python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
python_version: 3.12.3
browsergym_miniwob_version: 0.14.3
playwright_version: 1.44.0
model_provider: ollama
model_name: qwen2.5:7b
episode_timeout_s: 165.0
model_call_timeout_s: 10.0
max_model_calls: 15
execution_reserve_s: 15.0
evaluation_run_identity: sha256:dc1b6b53c0e40ad17647d41ac3cd8cf04b4a13ab2e21e6b58c96583c8522d00b
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
official_success_rate: 0.9166666666666666
mean_official_reward: 0.9166666666666666
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

This is negative PR breadth evidence. The V-PRB-6B HAS_CHANGED text progress
binding repair passed its local RED/GREEN tests but did not change the PR
breadth matrix result. `enter-text:seed-1` still fails in task planning with
`entry_outcome_already_satisfied`; both `form-sequence` seeds remain V-PRB-6A
terminal-guard failures; `click-button:seed-1` remains a separate JSON-invalid
schema/provider robustness cluster.

The result means the selected V-PRB-6B adapter evidence-scope repair is safe
but insufficient. The next V-PRB-6B investigation should follow the
TaskPlan/progress replacement loop rather than continue broadening BrowserGym
text evidence declarations without new trace evidence.

This run does not close PR breadth acceptance, fresh diagnostic readiness,
nightly, release, promotion, or any official score claim.

## Artifact hashes

```yaml
browsergym-report.json: sha256:3a4b13bb1f0f003c0823c68c92813f13b5ca339b35cdad04480e684173daf390
browsergym-runtime-preflight.json: sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47
matrix-metadata.json: sha256:34cd41719a784f89c43a4b4430d9a666efbd40b2aa40777c4371a98f1e940334
ollama-gpu-preflight.json: sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d
```
