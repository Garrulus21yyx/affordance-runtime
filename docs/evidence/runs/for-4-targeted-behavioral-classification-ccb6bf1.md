# FOR-4 targeted behavioral classification — ccb6bf1

This is targeted diagnostic evidence for Failure Ownership Router closure. It
is not PR breadth, fresh diagnostic, remote CI, or promotion evidence.

```yaml
revision: ccb6bf15f7719a6c61eaf9761e868e1c1d4c8154
working_tree_clean: true
model_provider: ollama
model_name: llama3.1:8b
output_dir: /tmp/affordance-for4-targeted-ccb6bf1
report: /tmp/affordance-for4-targeted-ccb6bf1/browsergym-report.json
profile: smoke
planner_profile: strict-generalist
tasks:
  - enter-text:seed-0
  - form-sequence:seed-0
  - choose-list:seed-0
observed: 3
passed: 1
failed: 2
provider_failures: 0
official_score_claimed: false
promotion: held
```

Episode classification:

| Episode | Runtime status | Runtime error | Official success | Classification |
| --- | --- | --- | --- | --- |
| `form-sequence:seed-0` | `done` | none | true | aligned pass |
| `choose-list:seed-0` | `failed` | `execution_failed` | false | Runtime execution owner |
| `enter-text:seed-0` | `failed` | `ValueError: intent compilation unsupported: missing_source_claims,missing_task_obligations` | false | Intent / planning owner |

Failure clusters from the generated report:

```yaml
failure_clusters:
  - episode_count: 1
    episode_ids:
      - choose-list:seed-0
    failure_signature: execution_failed
    family: selection
    root_layer: EXECUTION
  - episode_count: 1
    episode_ids:
      - enter-text:seed-0
    failure_signature: intent_compilation_rejected
    family: text_entry
    root_layer: INTENT / PLANNING
```

Interpretation:

- The ActionChoice / SAR-8C path still completes `form-sequence`.
- The remaining sampled failures are categorized rather than collapsed into
  `planner_waiting_clarification`.
- `choose-list` is now an execution-layer residual for follow-up execution /
  verification handling.
- `enter-text` is an intent/planning intake residual caused by missing source
  claims and task obligations.
- This run does not authorize promotion or a PR breadth claim.
