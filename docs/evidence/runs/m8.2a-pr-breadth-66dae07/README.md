# M8.2A PR breadth rerun at 66dae07

## Scope

This is the clean committed PR breadth rerun after
`9a63262` / `66dae07`, following the V-PRB-6B ready read-only discard repair.

It is evidence for local PR breadth classification only. It is not an official
benchmark score, fresh diagnostic, promotion, nightly, release, or remote-CI
claim.

```yaml
revision: 66dae07eb6de259a17c8f9604e30189a74fcc357
working_tree_clean: true
profile: pr
planner_profile: strict-generalist
llm_profile: local
model_provider: ollama
model_name: qwen2.5:7b
browsergym_version: 0.14.3
playwright_version: 1.44.0
python: /home/yang/.venvs/affordance-browsergym-py312/bin/python
output_dir: /tmp/affordance-pr-breadth-66dae07-20260728-130459
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
  passed: 12
  failed: 0

runtime_verification:
  passed: 9
  failed: 3

acceptance_errors:
  - enter-text:seed-1: execution_failed
  - form-sequence:seed-0: planner cannot finish before verifier-backed subgoal completion
  - form-sequence:seed-1: planner cannot finish before verifier-backed subgoal completion
```

## Classification

The V-PRB-6B ready read-only discard repair changes the PR breadth matrix
positively but does not close it:

- `click-button:seed-1` no longer reproduces the earlier JSON-invalid /
  schema-provider robustness failure in this clean committed rerun.
- `enter-text:seed-1` no longer loops on
  `entry_outcome_already_satisfied`; it now fails in task planning with
  `obligation_subgoal_missing`.
- `form-sequence:seed-0` and `form-sequence:seed-1` remain the separate
  V-PRB-6A / finish-guard progress-scope cluster.

Therefore:

```yaml
pr_breadth_acceptance: failed
matrix_impact: partial_positive
next_vertical_owner:
  - enter-text:seed-1 obligation/subgoal replacement accounting
  - form-sequence dependent-subgoal progress-scope binding
fresh_diagnostic: held
promotion: held
official_score_claimed: false
```

## Artifact hashes

```text
a5c5945d35959aba6a89d5cb079182c3abdffe57593948ea3d8b2da95b566878  browsergym-report.json
71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47  browsergym-runtime-preflight.json
063f6a831a8519c1a22498504a83235288eaecdd60ccef2b1c3d5257d2868cef  matrix-metadata.json
511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d  ollama-gpu-preflight.json
```
