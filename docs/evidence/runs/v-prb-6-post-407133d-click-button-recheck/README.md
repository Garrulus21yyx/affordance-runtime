# Post-407133d click-button JSON-invalid recheck

## Scope

This diagnostic reran only `click-button`, seeds 0 and 1, after the clean
`407133d` PR breadth matrix reported a structured intent-draft `json_invalid`
failure for `click-button:seed-1`.

It is a targeted reproducibility check, not PR breadth, fresh diagnostic,
promotion, nightly, release, remote-CI evidence, or an official score claim;
`official_score_claimed=false`.

```yaml
revision: 47932a2d84266983c632258afdfacae9b1cdcd94
source_tree_digest: sha256:4cf199d0067d191e8d0dcefc6fa945fb0f98b5607741d82a5c00437f81f6f654
working_tree_clean: true
profile: diagnostic
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
output_dir: /tmp/affordance-click-button-recheck-47932a2-20260728-165356
official_score_claimed: false
promotion_status: held
```

## Result

```yaml
expected_episode_count: 2
observed_episode_count: 2
missing_episode_count: 0
unrun_episode_count: 0
invalidated_episode_count: 0
provider_failures: 0
rate_limit_retries: 0
transient_retries: 0

external_browsergym_reward:
  passed: 2
  failed: 0

runtime_verification:
  passed: 2
  failed: 0
```

## Classification

`click-button:seed-1` did not reproduce as a stable failure in this targeted
2-episode recheck. The clean `407133d` PR breadth result still remains failed
and promotion-held, but this isolated result is too weak to authorize a
production repair for click-button schema/provider robustness.

Next production owner selection should prioritize the stable remaining
`form-sequence` V-PRB-6A dependent-subgoal progress-scope / finish-guard
cluster. The click-button JSON-invalid cluster remains monitored and requires
stronger reproducibility evidence before a production repair is admitted.

## Artifact hashes

```text
9b494ccc08687f07472fdece298686c89ef74b8735ec2aa09f5569b7518e807c  browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  browsergym-runtime-preflight.json
486689579fbe62009e64d253c5bf664bd42e1804984d8d0e27451ff03ba3fcb4  matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  ollama-gpu-preflight.json
```
