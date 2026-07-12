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

## 2. Trace Record

Each step should record:

```json
{
  "run_id": "run_001",
  "step": 4,
  "state": "ACTING",
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
  "execution": {
    "backend": "playwright_dom",
    "status": "success",
    "latency_ms": 134
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
```

### Safety

```text
high_risk_action_blocked
approval_required_count
unsafe_action_attempts
safe_abort_count
```

### Traceability

```text
evidence_coverage
decision_reason_coverage
postcondition_coverage
failure_classification_coverage
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

