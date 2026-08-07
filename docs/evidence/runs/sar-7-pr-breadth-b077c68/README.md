# SAR-7 PR breadth behavioral gate at b077c68

## Scope

This is the clean committed PR breadth run after SAR-7.5 removed TaskSkill
progress from default `StateKernel` authority.

It is local behavioral gate evidence only. It is not a promoted benchmark
score, fresh diagnostic, nightly, release, or remote-CI claim;
`official_score_claimed=false`.

```yaml
revision: b077c68d06a3b8187a8897fea32c1b4b249c29f3
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
output_dir: /tmp/affordance-sar7-pr-breadth-b077c68-20260730-112545
run_identity_digest: sha256:7e56656285880d18ffe06c3459a1bf8494570a3e52517595e69a6eeae45d68d2
source_tree_digest: sha256:841a0cf0339b7e7a3de95a2072ba4c23184c63215446553b802fdd0050e0e201
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
rate_limit_retries: 0
transient_retries: 0

external_browsergym_reward:
  passed: 6
  failed: 6

runtime_verification:
  passed: 6
  failed: 6

acceptance_errors:
  - choose-list:seed-1: ValueError request summary values must be JSON-like and immutable
  - click-button:seed-1: StructuredModelError json_invalid before TaskSpec creation
  - enter-text:seed-0: planner_waiting_clarification
  - enter-text:seed-1: planner_waiting_clarification
  - form-sequence:seed-0: planner_waiting_clarification
  - form-sequence:seed-1: planner_waiting_clarification
```

## Classification

SAR-7.1 through SAR-7.5 local code gates pass, but the SAR-7 behavioral gate
does not pass. Full SAR-7 milestone closure remains blocked by current PR
breadth failures.

The run is comparable and complete, with no provider or infrastructure failure.
The dominant residuals are outside TaskSkill progress-state removal:

- `enter-text` and `form-sequence` fail in INTENT / PLANNING via
  planner clarification.
- `choose-list:seed-1` fails in step planning with a request-summary
  immutability validation error.
- `click-button:seed-1` fails before normal Runtime verification with
  structured intent draft JSON incompatibility.

Therefore:

```yaml
sar_7_code_closure: local_completion_candidate
sar_7_behavioral_gate: failed
sar_7_full_milestone: incomplete
next_action: classify_pr_breadth_residuals_before_sar_8
sar_8: not_authorized
promotion: held
official_score_claimed: false
```

## Artifact hashes

```text
27c88a8fa13f0ab93c04e355e44d511718947616d6d57e8154450265eebdb230  browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  browsergym-runtime-preflight.json
0f35227ef87b2d4906aab1c4d6329e1eeb199212305b58392affa6df7dfe7393  matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  ollama-gpu-preflight.json
```
