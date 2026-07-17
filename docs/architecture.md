# Affordance Runtime Architecture

## 1. High-Level System

```text
Task Envelope
    |
    v
State Kernel
    |
    v
Budgeted Observer
    |
    v
Versioned Affordance Snapshot
    |
    v
Planner Port
    |
    v
Action Contract
    |
    v
Capability Gate / Preflight
    |
    v
Executor
    |
    v
Effect Receipt
    |
    v
Verifier Ladder
    |
    +--> Recovery / Replan
    |
    v
Trace DAG
    |
    v
Evaluator / Evolution Loop
```

The online runtime is bounded. It is not an unconstrained ReAct loop. It follows
a stateful workflow with explicit transitions, stale-state rejection, scoped
capabilities, and trace logging.

## 1.1 State Kernel

The State Kernel is the runtime's long-horizon memory for one task. It stores:

- goal and constraints
- active subgoals
- evidence and receipts
- hidden-state hypotheses
- pending obligations
- current environment revision
- action receipts and verifier results

This prevents the runtime from forgetting constraints such as `read_only`,
`no_purchase`, `approval_required`, or `must_return_evidence` when the page
changes halfway through a task.

## 2. Core Layers

### 2.1 Perception Layer

Collects environment state:

- DOM tree
- accessibility tree
- screenshots
- Set-of-Marks visual regions
- URL and navigation state
- network idle / loading status
- WoT Thing Descriptions or device state
- optional page-internal adapter state

### 2.2 Affordance Layer

Transforms environment state into executable opportunities:

```text
Page Affordance Model
Visual Affordance Model
Thing Affordance Model
Accessibility Affordance Model
```

An affordance is not only an element. It is an actionable interface with:

- label
- target
- backend candidates
- input type
- semantic role
- state
- risk
- confidence
- evidence
- environment revision
- lease TTL
- provenance

### 2.3 Affordance Lease

Each snapshot receives a lease:

```json
{
  "environment_revision": "url+dom+screenshot+loading-hash",
  "issued_at_s": 1780000000.0,
  "ttl_ms": 2000,
  "provenance": ["dom", "screenshot"],
  "confidence": 0.92
}
```

Before execution, preflight checks that the lease and action contract still
match the latest observation. A stale action returns `STALE_OBSERVATION` and
forces refresh or replan.

### 2.4 Action Contract Layer

Each action is represented by a contract:

```json
{
  "action_id": "click_submit",
  "intent": "submit the current form",
  "target": "button.submit",
  "backend": "dom",
  "preconditions": [
    "button.visible",
    "button.enabled",
    "form.valid"
  ],
  "expected_effects": [
    "url_changes_or_success_message",
    "no_error_banner"
  ],
  "risk": "medium",
  "required_capabilities": ["settings.write"],
  "idempotency_key": "task_1:submit_form:v1",
  "compensation": "restore_previous_setting",
  "timeout_ms": 5000,
  "fallbacks": ["visual_click", "keyboard_enter"]
}
```

The runtime executes contracts, not vague clicks.

### 2.5 Safety and Capability Layer

The safety layer checks:

- requested capabilities
- task constraints
- side-effect class
- approval requirements
- tainted instructions from page content
- credential/payment/export boundaries
- idempotency and compensation availability

Parent agents should call task-level APIs. Low-level click/type tools are
internal or debug-only because they bypass the harness.

### 2.6 Execution Layer

Backends:

- Playwright DOM actions
- keyboard / mouse actions
- visual click by mark id
- accessibility actions
- API / device actions
- page-internal JavaScript adapter when available

### 2.7 Verification Layer

Checks whether expected effects occurred:

- DOM state changed
- URL changed
- target text appeared
- success message visible
- error banner absent
- screenshot diff matches expected region
- device state changed
- postcondition oracle passed

Verifier ladder, strongest to weakest:

1. API, DB, file, network, or download receipt.
2. DOM or accessibility state.
3. Screenshot / visual mark evidence.
4. Model judge.
5. Human review.

### 2.8 Recovery Layer

Handles failures:

- retry after wait
- refresh affordances
- switch backend
- close blocking modal
- replan from current state
- ask parent agent
- request human approval
- safe abort

### 2.9 Trace and Evaluation Layer

Records:

- observations
- affordance snapshots
- plans
- action contracts
- execution results
- postcondition checks
- environment changes
- recovery attempts
- final metrics

## 3. Repository Layout

```text
src/affordance_runtime/
  contracts.py
  state_kernel.py
  runtime.py
  safety.py
  verification.py
  trace.py
  evolution.py
  adapters/
    dom.py
    som.py
    wot.py
  benchmarks/
    spec.py
    suites.py
    metrics.py
tests/
docs/
```

Planned expansion after the skeleton:

```text
src/affordance_runtime/
  observers/playwright.py
  executors/playwright.py
  recovery/policies.py
  integrations/mcp_server.py
  integrations/rest_server.py
  eval/runner.py
  eval/replay.py
  fixtures/local_saas_ops/
```

## 4. Runtime State Machine

```text
INIT
OBSERVING
MODELING
PLANNING
ACTING
VERIFYING
RECOVERING
WAITING_ENV
WAITING_USER
DONE
FAILED
ABORTED
```

State transitions are event-driven and traceable.

## 5. Design Principle

The runtime should prefer deterministic tools and bounded workflows for the
online path. LLM reasoning is used where ambiguity exists:

- task interpretation
- action selection among candidates
- recovery strategy selection
- explanation
- offline failure analysis
- skill mining

It should not rely on open-ended agent loops for every step.

## 6. Planner Port

The planner interface should be narrow:

```text
input:
  task envelope
  state kernel summary
  affordance snapshot
  allowed capabilities

output:
  action contract candidate
  verifier plan
  recovery preference
  ask/abort decision when uncertain
```

The planner is replaceable. The runtime owns action validity, preflight,
execution, verification, trace, and evaluation.

