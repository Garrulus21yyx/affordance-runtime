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

## 6. External benchmark admission

Full external agent benchmarks remain **BLOCKED**. The same-task DOM/Visual/WoT
single-surface adapter-only activation matrix is complete, but admission still requires:

1. positive new-loop DOM, Visual, and WoT verticals (closed for the shared-state task);
2. the same TaskGoal, policy, evaluators, and semantic actions with adapter-only variation;
3. runtime-owned ActionSpace and evaluator-owned completion;
4. stale zero-call, fresh observation, and SENT_UNKNOWN no-retry;
5. P5-D confirmation/unknown-effect core (closed on the non-default target path);
6. P5-D6.1 general confirmation/evaluation contract completion (closed non-default);
7. P5-M0 model-safe policy/evaluator trust boundary (closed non-default);
8. P5-M0.1 disposable AgentContext/context identity/paging implementation (closed non-default);
9. P5-M0.1.1 one-shot epoch/cursor paging/projection operational closure (closed non-default);
10. P5-M1 model-backed target AgentPolicy (closed);
11. P5-M1.1 strict existing-ModelPort bridge (closed locally; no live-provider generalization claim);
12. P5-M2 minimum production evaluator composition and criterion adjudicators (closed locally);
13. P5-M2.1 evidence-semantic/dynamic-readiness entry gates (closed locally);
14. P5-M3 fixed internal benchmark harness that runs the new AgentLoop rather than the retained baseline (closed locally);
15. exact-head remote CI evidence with zero forbidden side effects and duplicate unknown attempts.

The first admitted external run is a small fixed BrowserGym/MiniWoB smoke set
for harness and loop-contract validation, not a generalization claim.
WebArena/WorkArena wait for an internal 20–50 turn case. OSWorld waits for
AX/Visual/CLI/app-switch contracts. Component tests and the local DOM, Visual,
and WoT verticals continue to run before this admission gate. Completing P5-D
alone does not admit an external run; the model-backed target policy/evaluators,
new-loop harness, and exact-head remote CI evidence remain mandatory.
P5-D6.1 completion likewise does not independently admit an external run.
P5-M0 completion likewise does not independently admit an external run.
P5-M0.1 completion likewise does not independently admit an external run.
P5-M0.1.1 completion likewise does not independently admit an external run.
P5-M2 completion likewise does not admit an external run: P5-M3 harness, an
exact live model-policy profile, and exact-head remote CI still block it.
P5-M2.1 admits work on the internal P5-M3 harness only; it does not admit an
external benchmark run.

The P5-M3 internal manifests are `internal-core`, `internal-safety`, and
`internal-evaluation`. They run sequentially through `AgentEpisodeRunner`, keep
expected terminal states outside all product inputs, record denominator-aware
rates (`N/A` for zero opportunities), and fail closed on forbidden effects,
duplicate unknown attempts, stale dispatch violations, cleanup failure, or
missing metrics. Their local acceptance does not admit an external run.

P5-M3.1 adds `internal-real-adapters`, whose deterministic cases use actual DOM,
Visual-only and WoT production adapters. `MetricMeasurement` distinguishes zero
from unmeasured, manifest expectations are digest-bound, and attestation hashes
exact-head report files. These are internal adapter and protocol proofs, not
BrowserGym/MiniWoB runs or model-generalization evidence.

P5-M3.2 fixes the first external candidate to the official
`browsergym-miniwob==0.14.3` registry entries
`browsergym/miniwob.click-button`, `browsergym/miniwob.enter-text`, and
`browsergym/miniwob.choose-list`, with MiniWoB source commit `7fd85d71...`.
This manifest is mechanical-only, so a live semantic evaluator is not a gate.
The optional SDK is isolated in the `external-smoke` extra. Admission still
requires one clean exact SHA across the complete internal run set, full CI, and
live policy attestations, zero safety counters, the exact manifest digest, and
a closed target-loop environment wrapper. The last wrapper is not yet closed;
therefore preflight is expected to reject execution and no external benchmark
is run.
Semantic fusion remains deferred and is not an M1 prerequisite.

## Exact model conformance ladder

The diagnostic ladder covers minimal structured JSON, SelectAction-only actual
IDs, full union/minimal context, full union/current AgentContext, and the real
DOM AgentLoop. Grounding variants are format-only, compact contract, full schema
text and context-bound schema. Each attempt makes one provider call and retains
only typed stage, sizes, hash and secret-free usage metadata. The measured exact
Ollama profiles originally failed when the full union carried a 2,000-character
completion-summary bound. After narrowing the canonical semantic budget to
1,024, both exact profiles passed one Level-2 format-only diagnostic and reached
destination admission at Levels 3/4. This removes the measured provider grammar
blocker but does not establish stable model support. It does not admit
BrowserGym/MiniWoB execution.

The destination-domain diagnostic ladder keeps the full decision union while
progressing from a forbidden destination (D0), through one/two offered nested
destinations (D1/D2), the real nested action page (D3), and the complete current
AgentContext (D4). Failure reports retain only a typed shape—never the emitted
ID or raw response—and Runtime membership remains unchanged.

After the 1,024-character grammar correction, the compact-contract candidate
was rerun against D3/D4 and then the complete support ladder. Exact Qwen 2.5 7B
and Llama 3.1 8B profiles each passed L0–L4 at 20/20 on clean HEAD `b4c04d6`;
their separate attestation files are accepted as `supported`. The corresponding
format-only D4 destination failures remain part of the diagnosis. These are
internal real-DOM policy/runtime proofs, not BrowserGym/MiniWoB execution.
