# Trace and Evaluation

## 1. Trace-First Rule

Every run must be replayable enough for debugging and evaluation.

The trace is the substrate for:

- diagnosis
- benchmark scoring
- regression replay
- skill mining
- policy evolution
- parent-agent reporting

## 2. Storage Model

The canonical storage can be an append-only JSONL event log. DAG parent links
are stored on events and used to derive causal views.

This keeps streaming simple while preserving causality for:

- recovery branches
- parallel observations
- candidate plans
- parent/subagent handoff
- evolution proposals

## 3. Trace Event

Each observation, affordance snapshot, contract, capability decision, execution
receipt, verifier result, recovery attempt, and evolution proposal is a trace
event with parent links and artifact references.

Example event:

```json
{
  "schema_version": "1.0",
  "run_id": "run_001",
  "event_id": "evt_0004",
  "step": 4,
  "state": "ACTING",
  "parents": ["contract_0003"],
  "observation_ref": "artifacts/run_001/obs_004.json",
  "snapshot_id": "snap_004",
  "contract_hash": "sha256:...",
  "execution_receipt": {
    "backend": "playwright_dom",
    "status": "success",
    "latency_ms": 134,
    "started_revision": "rev_12",
    "ended_revision": "rev_13"
  },
  "verification": {
    "postcondition": "enterprise_details_visible",
    "status": "PASSED",
    "evidence_refs": ["artifacts/run_001/dom_005.json"]
  }
}
```

## 4. Minimum Trace Fields

Every completed run should include:

- task envelope
- runtime version
- contract schema version
- environment version
- observation refs
- snapshot ids
- action contracts
- policy and approval decisions
- execution receipts
- post-action observations
- verification reports
- recovery decisions
- final result
- artifact index

Sensitive values such as passwords, cookies, tokens, and unnecessary private
form content must be redacted or omitted from trace artifacts.

## 5. Evaluation Layers

Evaluate eight layers:

1. Observation: did the runtime perceive the right state?
2. Affordance modeling: did it expose the right actions?
3. Action execution: did it perform the selected action?
4. Verification: did it judge success correctly?
5. Recovery: did it adapt when the environment changed?
6. Safety: did it block unapproved or tainted side effects?
7. Replay: can the failure or success be reproduced semantically?
8. Evolution: did proposed harness changes pass regression gates?

## 6. Metric Families

### Task Success

```text
task_success_rate
postcondition_pass_rate
completion_rate
```

### Efficiency

```text
step_count
latency_ms
token_cost
observation_cost
affordance_refresh_count
cost_per_success
```

### Reliability

```text
selector_failure_rate
visual_fallback_rate
retry_count
replan_count
stale_detection_recall
false_stale_block_rate
effect_receipt_coverage
verifier_false_accept_rate
```

### Safety

```text
constraint_violation_rate
high_risk_action_blocked
approval_required_count
unsafe_action_attempts
safe_abort_count
unsafe_side_effect_rate
approval_gate_pass_rate
```

### Traceability

```text
evidence_coverage
decision_reason_coverage
postcondition_coverage
failure_classification_coverage
trace_parent_coverage
trace_required_field_coverage
```

### Harness Evolution

```text
evolution_accept_rate
quarantine_rate
rollback_rate
regression_delta
negative_example_coverage
```

## 7. Metric Definition Rules

Each metric must define:

```text
name
definition
numerator
denominator
direction
unit
ground_truth_source
aggregation
acceptance_threshold
```

Examples:

```text
stale_detection_recall
  blocked injected-stale actions / injected-stale actions
  direction: higher better
  ground truth: perturbation label

verifier_false_accept_rate
  failed ground-truth outcomes judged successful / failed outcomes
  direction: lower better
  ground truth: scenario oracle

unsafe_side_effect_rate
  unsafe side effects / side-effect opportunities
  direction: lower better
  ground truth: policy log + fixture audit log
```

## 8. Benchmark Suites

### Local SaaS Tasks

The MVP starts with three local SaaS tasks because they make the runtime's
differentiators visible:

- [Pricing Extraction](scenarios/pricing-extraction.md): read-only extraction
  with evidence chain.
- [Reversible Settings Update](scenarios/settings-update.md): controlled write
  with modal, selector drift, async button state, and persistence oracle.
- [Approval-Gated Report Export](scenarios/approval-gated-report-export.md):
  approval-gated side effect with download/file receipt.

### MiniWoB++

Use for atomic web interaction:

- click
- type
- select
- drag
- form submission
- small navigation tasks

### WebArena-Style Mock Environments

Use for realistic multi-step workflows:

- shopping
- email
- forum
- admin dashboard
- support portal

### VisualWebArena-Style Tasks

Use for visual grounding:

- image-dependent selection
- layout-dependent tasks
- visual comparison
- mark-level target matching

### WoT / Device Demo

Use only as a non-web affordance proof:

- thermostat
- lighting
- projector
- failure injection
- postcondition mismatch

## 9. Reports

Each evaluation run should output:

```text
eval_report.json
eval_report.md
metrics.csv
failure_cases/
trace_index.json
screenshots/
artifacts/
regression_summary.md
```

The Markdown report should summarize:

- task suite
- environment versions
- runtime version
- model/provider
- baseline and ablation configuration
- success metrics
- failure taxonomy
- selected trace links
- proposed evolution artifacts

## 10. Trace Acceptance Requirements

Every completed run should make these questions answerable:

1. Which environment revision was the action based on?
2. Which affordance and lease produced the action contract?
3. Which capability gate allowed or blocked it?
4. What structural receipt or verifier evidence proved the effect?
5. What changed in the State Kernel after the action?
6. If recovery happened, what failed and which policy was selected?
7. Can the trace be replayed offline or semantically?
