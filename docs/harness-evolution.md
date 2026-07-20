# Harness Evolution

## 1. Principle

Affordance Runtime should not only execute tasks. It should learn from its own
failed traces in a controlled, auditable way.

The evolution loop is harness-level, not mystical self-improvement:

```text
Failed Trace
  -> Failure Analyzer
  -> Evolution Proposal
  -> Quarantined Patch Candidate
  -> Replay Failed Task
  -> Replay Regression Suite
  -> Accept / Reject
```

The first implementation should be assisted evolution: the system may propose
changes, but acceptance is gated by regression evidence and review. Do not allow
failed traces to directly mutate production runtime behavior.

## 2. Prerequisite Gate

Harness evolution work may begin only after:

1. The core benchmark suite has a stable version.
2. The trace schema is stable enough for replay and diagnosis.
3. At least N classified failures exist.
4. Regression runs are deterministic enough for comparison.
5. At least one manually designed patch has completed the full gate.
6. Safety checks and approval checks are part of the regression suite.

Before these conditions are true, evolution should be treated as manual failure
analysis plus regression fixture generation.

## 3. What Can Evolve

Only bounded artifacts should be eligible for automatic proposal or assisted
acceptance:

```text
Prompt Policy
  Example: if a login modal appears, report blocked instead of clicking randomly.

Action Policy
  Example: prefer DOM click, then visual click, then keyboard fallback.

Affordance Rule
  Example: combine aria-label, visible text, role, and bounding box into selector
  candidates.

Reusable Skill
  Example: close_cookie_banner.

Postcondition
  Example: dashboard_loaded should check URL, heading, and absence of error.

Benchmark Fixture
  Example: add a modal-interruption regression case.
```

The runtime should not let failed traces directly mutate arbitrary production
code without review.

## 3.1 Evolution Registry

Every proposed artifact must be tracked with:

- artifact id and version
- artifact type
- source runtime version
- source trace ids
- target suite versions
- applicability conditions
- negative examples
- TTL / expiration rule
- baseline results
- candidate results
- mandatory safety results
- rollback artifact/version
- reviewer decision
- status: proposed, quarantined, accepted, rejected, rolled_back

This keeps self-evolution concrete and auditable. The harness can suggest
changes, but acceptance is a versioned registry decision.

## 4. Failure Taxonomy

```text
Perception Error
  Environment was observed incorrectly.

Planning Error
  Task decomposition or step ordering was wrong.

Action Grounding Error
  The selected target was wrong or unstable.

Execution Error
  Browser, device, network, timeout, or permission failure.

Verification Error
  The action succeeded but postcondition logic failed, or vice versa.

Recovery Error
  The recovery strategy made the situation worse or failed to adapt.

Safety Error
  The runtime attempted a high-risk action without approval.
```

## 5. Implemented Recovery-Evolution Boundary

M8.3 bounds and traces recovery, groups causally related attempts into one
incident, recognizes normalized recurring failures, detects no-progress and
A-B oscillation, and preserves root cause separately from secondary symptoms.
Typed policy and skill payloads can be loaded only after digest/status checks
and are constrained to bounded safe actions.

The implementation does not perform arbitrary source mutation or online
learning. Cross-run proposal generation remains offline and regression-gated;
only accepted artifacts can affect a fresh candidate runtime.

## 6. Recovery Incident and Cascade Model

M8.3 implements:

```text
FailureSignature
  phase, normalized error, action/backend, target fingerprint,
  verifier kind, relevant state revision

RecoveryIncident
  source event/contract/snapshot, ordered attempts,
  signatures, recovery actions/outcomes,
  root failure, symptom chain, terminal outcome
```

Detect repeated signatures, unchanged progress after recovery, A-B
action/state oscillation, rebuilding the same stale contract, repeated failed
postconditions, and fallback exhaustion. Online detection only stops or
escalates within the existing budget; policy learning stays offline.

Required diagnostics are `cascade_depth`, `repeated_failure_rate`,
`recovery_loop_abort_rate`, `recovery_action_effectiveness`, and
`duplicate_effect_risk_count`.

## 7. Recovery Evolution

The first executable artifacts are narrow declarative `RecoveryPolicyPatch`
and `Skill` payloads. They match a signature/incident pattern, select a
bounded observe/verify/reroute/ask/compensate/abort response, and declare
idempotency, evidence, risk, applicability, and postconditions.

A fresh candidate replays the original incident, task family, global smoke,
and safety smoke. Acceptance requires breaking the loop or reducing cascade
depth, zero new unsafe effects, no blind retry after uncertain effect, a
persisted decision, and demonstrated rollback. The clean `07e406f` evidence
passes all four categories and explicitly records `RecoveryStateInspected` on
the uncertain-effect path before failing safe.

## 8. Skill Mining

A reusable skill may be proposed from repeated failure or repeated successful
recovery only after incident grouping and signatures are implemented:

```yaml
skill_id: close_cookie_banner
trigger:
  page_contains:
    - "Accept all"
    - "Reject all"
    - "Cookie settings"
actions:
  - find button matching ["Reject", "Close", "Accept"]
  - click safest option based on policy
postcondition:
  - banner_not_visible
risk: low
evidence:
  - traces/run_017.jsonl
```

Skills should be versioned and tested against regression fixtures.

## 9. Evolution Proposal Schema

```json
{
  "proposal_id": "prop_001",
  "source_trace": "run_017",
  "failure_type": "action_grounding_error",
  "target_artifact": "affordance_rule",
  "change_summary": "Use role+text+bbox voting for submit buttons.",
  "expected_benefit": "Reduce wrong submit-button clicks in forms.",
  "risk": "low",
  "validation_plan": [
    "replay run_017",
    "run form_submission_regression",
    "run cookie_modal_regression",
    "run safety_smoke"
  ]
}
```

## 10. Regression Gate

No evolution artifact is accepted unless it passes:

- the original failed task
- the relevant task family
- a small global smoke suite
- safety checks
- approval checks
- trace schema validation
- trace determinism checks where possible

The gate must use direction-aware metric rules. A single `min_score >= 1.0`
style rule is invalid because some metrics are higher-is-better and others are
lower-is-better.

Example rule shape:

```json
{
  "metric": "unsafe_side_effect_rate",
  "direction": "max",
  "threshold": 0.0
}
```

```json
{
  "metric": "task_success_rate",
  "direction": "min",
  "threshold": 0.9,
  "allowed_regression": 0.02
}
```

A patch that fixes one modal case but hurts visual grounding or side-effect
safety stays quarantined.

## 11. Human Review

The harness can propose improvements automatically, but it should support human
review for:

- prompt policy changes
- safety policy changes
- irreversible action rules
- credential or payment related workflows
- broad selector or grounding changes
- any artifact that changes approval behavior

## 12. Current Implemented Boundary

M6 implements one deliberately narrow executable path: a verification failure
can produce a SHA-bound `verifier_patch` that enables a whitelisted structural
verification feature for a declared task. The patch is loaded into a fresh
candidate runtime before new original, task-family, global-smoke, and
safety-smoke Chromium runs. Acceptance and rollback are persisted, and a
rolled-back artifact cannot be loaded again.

Other artifact types remain typed proposals only. Reusable skill, policy,
affordance-rule, and benchmark-fixture payload loaders require their own narrow
schemas, replay evidence, and review gates before they can be described as
executable evolution.
