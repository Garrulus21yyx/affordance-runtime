# Benchmark Plan

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** evaluation profiles, metrics, and claim gates

## 1. Evaluation objective

Measure whether one semantic agent policy can efficiently complete the same
task across heterogeneous world surfaces, while preserving local action safety
and truthful evaluation.

## 2. Required profiles

### Core positive matrix

Use the same TaskGoal, AgentPolicy, semantic action vocabulary, and evaluators.
Only the adapter/environment representation changes:

```text
DOM · AX · Visual-only · SVG · WoT
```

Initial tasks should include an activation/toggle, a structured selection, and
a spatial move where applicable. API/Device/CLI join after symmetric adapters exist.

### Safety regression

- stale observation/binding → zero executor calls;
- changed semantic confirmation subject → confirmation invalidated;
- binding-only fresh rebind with unchanged semantics → confirmation retained;
- result/receipt-only completion rejected;
- UNKNOWN effect → no duplicate attempt;
- missing/mismatched required artifact rejected;
- model-injected selector/coordinate/backend payload rejected.

### Adapter conformance

Each adapter proves truthful coverage, stable target identity, supported action
reporting, binding freshness, execute result, and fresh reobservation.

## 3. Metrics

```text
task success rate
steps to completion
observation and targeted-observation count
model and visual calls
latency
route selection and wrong-route count
fallback count
human-confirmation count
stale detection
unknown-effect duplicate rate
long-horizon constraint retention and verified milestone progress
ask-user correctness
batch utilization and observation-barrier rejection
cache hit and currentness rejection
```

Zero-opportunity rates are reported as N/A. Event/delta/commit metrics may be
legacy diagnostics but are not target acceptance measures.

### Long-horizon profile

At least one 20–50 turn task spans pages/applications or surface types and
requires milestone verification, new-information retention, ask_user, and
fact-driven plan replacement. Cross-day/background/crash-resume is excluded.

### Batch and memory ablations

Batch compares success, model calls, observations, steps and latency against
single-action execution. BindingCache/Skill comparison reports stale rejection
and must use the same ActionSpace/RiskPolicy/evaluator path.

## 4. Run identity

Every report records git revision, dirty state, task/adapter manifest, profile,
model/provider configuration, seeds, required denominators, and raw result
locations. Historical evidence does not roll forward.

## 5. Claim gate

No “cross-platform generalization” claim is allowed until all required surface
variants complete positively under the same policy/evaluators and adapter-only
variation is demonstrated. A shared failure or shared entry into the same old
pipeline is not success evidence.
