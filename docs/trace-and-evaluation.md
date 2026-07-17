# Trace and Evaluation

## 1. Trace-First Rule

Every run must be replayable enough for debugging and evaluation.

The trace is not only a log. It is the substrate for:

- diagnosis
- benchmark scoring
- regression replay
- skill mining
- policy evolution
- parent-agent reporting

## 2. Trace DAG

The trace is a causal DAG, not a flat JSON log. Each observation, affordance
snapshot, contract, capability decision, execution receipt, verifier result,
recovery attempt, and evolution proposal is a node with parent links.

Each step should still be serializable as a record:

```json
{
  "run_id": "run_001",
  "step": 4,
  "state": "ACTING",
  "parents": ["contract_0003"],
  "observation": {
    "url": "https://example.com/pricing",
    "dom_hash": "abc123",
    "screenshot": "artifacts/run_001/step_004.png",
    "affordance_snapshot": "artifacts/run_001/affordances_004.json"
  },
  "decision": {
    "subgoal": "open enterprise plan details",
    "selected_action": "click",
    "target": "button.enterprise-details",
    "reason": "visible, enabled, matches text and role"
  },
  "execution_receipt": {
    "backend": "playwright_dom",
    "status": "success",
    "latency_ms": 134,
    "started_revision": "rev_12",
    "ended_revision": "rev_13",
    "receipt": "download:report_001.csv"
  },
  "verification": {
    "postcondition": "enterprise_details_visible",
    "passed": true
  },
  "environment_events": [],
  "recovery": null
}
```

## 3. Evaluation Layers

Evaluate five layers:

1. Observation: did the runtime perceive the right state?
2. Affordance modeling: did it expose the right actions?
3. Action execution: did it perform the selected action?
4. Verification: did it judge success correctly?
5. Recovery: did it adapt when the environment changed?
6. Safety: did it block unapproved or tainted side effects?
7. Replay: can the failure or success be reproduced semantically?
8. Evolution: did proposed harness changes pass regression gates?

## 4. Metrics

### Task Success

```text
success_rate
postcondition_pass_rate
recovery_success_rate
completion_rate
```

### Efficiency

```text
step_count
latency_ms
token_cost
observation_cost
affordance_refresh_count
```

### Reliability

```text
selector_failure_rate
visual_fallback_rate
retry_count
replan_count
regression_pass_rate
replay_success_rate
stale_action_block_rate
effect_receipt_coverage
verifier_false_accept_rate
```

### Safety

```text
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
trace_dag_parent_coverage
```

### Harness Evolution

```text
evolution_accept_rate
quarantine_rate
rollback_rate
regression_delta
negative_example_coverage
```

## 5. Benchmark Suites

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

### WoT / Device Demo

Use for non-web affordances:

- thermostat
- lighting
- projector
- failure injection
- postcondition mismatch

### Custom SaaS Tasks

Use for resume-friendly demonstrations:

- pricing extraction
- invoice download
- form filling
- settings update
- report export

The MVP benchmark plan starts with three local SaaS tasks because they make the
runtime's differentiators visible:

- read-only extraction with evidence chain
- reversible settings update with modal, selector drift, and async button state
- approval-gated report export with a download receipt

## 6. Reports

Each evaluation run should output:

```text
eval_report.json
eval_report.md
metrics.csv
failure_cases/
trace_index.json
screenshots/
regression_summary.md
```

The Markdown report should summarize:

- task suite
- environment versions
- runtime version
- model/provider
- success metrics
- failure taxonomy
- selected trace links
- proposed evolution artifacts

## 7. Trace Acceptance Requirements

Every completed run should make these questions answerable:

1. Which environment revision was the action based on?
2. Which affordance and lease produced the action contract?
3. Which capability gate allowed or blocked it?
4. What structural receipt or verifier evidence proved the effect?
5. What changed in the State Kernel after the action?
6. If recovery happened, what failed and which policy was selected?
7. Can the trace be replayed offline or semantically?

