# M8.2A PR breadth rerun at 407133d

## Scope

This is the clean committed PR breadth rerun after the V-PRB-6B
verifier-backed progress accounting integration.

It is evidence for local PR breadth classification only. It is not an official
benchmark score, fresh diagnostic, promotion, nightly, release, or remote-CI
claim; `official_score_claimed=false`.

```yaml
revision: 407133d1a1c902436ae2576175f834a7a74b1367
production_repair_revision: d17a1f3cf9f3190e3188ad5a9f5bfbc2ef017e2c
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
output_dir: /tmp/affordance-pr-breadth-407133d-20260728-164614
run_identity_digest: sha256:fee98e7b2a1084cc5c17f75a003c7dbfdb2fdfcca134b71c01a062e1b735a5b6
source_tree_digest: sha256:4cf199d0067d191e8d0dcefc6fa945fb0f98b5607741d82a5c00437f81f6f654
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
  passed: 11
  failed: 1

runtime_verification:
  passed: 9
  failed: 3

acceptance_errors:
  - click-button:seed-1: StructuredModelError json_invalid before TaskSpec creation
  - form-sequence:seed-0: planner cannot finish before verifier-backed subgoal completion
  - form-sequence:seed-1: planner cannot finish before verifier-backed subgoal completion
```

## Classification

The V-PRB-6B verifier-backed progress accounting integration is effective for
the `enter-text:seed-1` required read-only availability case: the episode now
reaches Runtime completion and BrowserGym reward 1.0.

The PR breadth ability gate remains failed:

- `enter-text:seed-1` is closed relative to the prior `66dae07` diagnostic
  baseline.
- `form-sequence:seed-0` and `form-sequence:seed-1` remain the separate
  V-PRB-6A dependent-subgoal progress-scope / finish-guard cluster.
- `click-button:seed-1` reappears as a structured intent-draft
  `json_invalid` failure before TaskSpec creation. This is a schema/provider
  robustness cluster and must not be mixed into V-PRB-6A or additional 6B
  progress accounting work.

Therefore:

```yaml
pr_breadth_acceptance: failed
matrix_impact: mixed
v_prb_6b_enter_text_required_read_only_availability: closed
next_vertical_owner:
  - V-PRB-6A dependent-subgoal progress-scope binding for form-sequence
  - separate click-button:seed-1 structured intent-draft json_invalid robustness
fresh_diagnostic: held
promotion: held
official_score_claimed: false
```

## Artifact hashes

```text
aa494d334cefb01ee18659d77cebd10fcf9f90491647240d5b735830881dc58f  browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  browsergym-runtime-preflight.json
da08b4e6120c2b7cf02878b478a934d7b5b621e73a8f00a1ea88dc45dbfac697  matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  ollama-gpu-preflight.json
```
