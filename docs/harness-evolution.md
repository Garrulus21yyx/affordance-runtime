# Harness Evolution

## 1. Principle

Affordance Runtime should not only execute tasks. It should learn from its own
failed traces in a controlled, auditable way.

The evolution loop is harness-level, not mystical self-improvement:

```text
Failed Trace
  -> Failure Analyzer
  -> Evolution Proposal
  -> Patch Candidate
  -> Replay Failed Task
  -> Replay Regression Suite
  -> Accept / Reject
```

## 2. What Can Evolve

Only bounded artifacts should be eligible for automatic or assisted evolution:

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

## 3. Failure Taxonomy

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

## 4. Skill Mining

A reusable skill is generated from repeated failure or repeated successful
recovery:

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

## 5. Evolution Proposal Schema

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
    "run cookie_modal_regression"
  ]
}
```

## 6. Regression Gate

No evolution artifact is accepted unless it passes:

- the original failed task
- the relevant task family
- a small global smoke suite
- safety checks
- trace determinism checks where possible

## 7. Human Review

The harness can propose improvements automatically, but it should support human
review for:

- prompt policy changes
- safety policy changes
- irreversible action rules
- credential or payment related workflows
- broad selector or grounding changes

## 8. Resume Framing

This is the Hermes-style part of the project:

> failed GUI interaction traces are analyzed, classified, and converted into
> reusable skills, postcondition improvements, policy patches, and regression
> fixtures, then validated through replay before being admitted into the
> runtime.

