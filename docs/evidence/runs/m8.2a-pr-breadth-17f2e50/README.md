# M8.2A PR Breadth Rerun at 17f2e50

This evidence records the clean PR breadth rerun after the V-PRB-6B read-only
availability/cardinality child production repair.

## Run identity

```yaml
revision: 17f2e5021bc0c1eab8d1302bc01aa77b82323459
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
evaluation_run_identity: sha256:754500037010985bf4cc80aaa3599e3799530b1f313b4e7ac6285e322fe92a8f
official_score_claimed: false
promotion_status: held
remote_ci: disabled
```

The local provider preflight initially failed because the stale named `ollama`
container could not initialize NVML and loaded `qwen2.5:7b` with `size_vram=0`.
The container was recreated with `--gpus all` while preserving the named
`ollama` model volume. The archived preflight for this run is ready with
`size_vram_bytes > 0`.

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
runtime_error_counts: {"StructuredModelError: structured response failed LLMIntentDraft validation: :json_invalid": 1, "execution_failed": 1, "planner cannot finish before verifier-backed subgoal completion": 2}
official_success_rate: 0.9166666666666666
mean_official_reward: 0.9166666666666666
```

Failed or Runtime-failed episodes:

- `click-button:seed-1` — official_reward=0.0, runtime_status=failed, error=`StructuredModelError: structured response failed LLMIntentDraft validation: :json_invalid`
- `enter-text:seed-1` — official_reward=1.0, runtime_status=failed, error=`execution_failed`
- `form-sequence:seed-0` — official_reward=1.0, runtime_status=aborted, error=`planner cannot finish before verifier-backed subgoal completion`
- `form-sequence:seed-1` — official_reward=1.0, runtime_status=aborted, error=`planner cannot finish before verifier-backed subgoal completion`

## Governance interpretation

This is negative PR breadth evidence. V-PRB-6B changed shape but is not closed:
`enter-text:seed-1` no longer reaches the terminal-completion guard; it now fails
earlier in TaskPlan validation with `entry_outcome_already_satisfied`, then the
repair loop exhausts budget. The next V-PRB-6B owner should decide whether an
already-current read-only availability subgoal is completed from current-state
evidence instead of merely repairable by model replan.

V-PRB-6A remains open: both `form-sequence` seeds still abort at Runtime finish
with `planner cannot finish before verifier-backed subgoal completion`.

A new `click-button:seed-1` JSON-invalid intent draft failure also appears in
this comparable rerun. Treat it as a separate provider/schema robustness cluster;
do not mix it into V-PRB-6B.

This run does not close PR breadth acceptance, fresh diagnostic readiness,
nightly, release, promotion, or any official score claim.

## Artifact hashes

```yaml
browsergym-report.json: sha256:73127f5c558539d4e22a9e1723530cdb5bdf0f983fd30016fdc44942980c1fb1
browsergym-runtime-preflight.json: sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47
matrix-metadata.json: sha256:f678fa3dcd64941d9efd6c7bea7da077360b52ab402aebcff1c75aa21b162f3a
ollama-gpu-preflight.json: sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d
```
