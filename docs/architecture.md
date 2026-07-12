# Affordance Runtime Architecture

## 1. High-Level System

```text
Task Request
    |
    v
Coordinator
    |
    v
Environment Observer
    |
    v
Affordance Builder
    |
    v
Planner
    |
    v
Action Router
    |
    v
Executor
    |
    v
Verifier
    |
    +--> Recovery / Replan
    |
    v
Trace Logger
    |
    v
Evaluator / Evolution Loop
```

The online runtime is bounded. It is not an unconstrained ReAct loop. It follows
a stateful workflow with explicit transitions and trace logging.

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

### 2.3 Action Contract Layer

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
  "timeout_ms": 5000,
  "fallbacks": ["visual_click", "keyboard_enter"]
}
```

The runtime executes contracts, not vague clicks.

### 2.4 Execution Layer

Backends:

- Playwright DOM actions
- keyboard / mouse actions
- visual click by mark id
- accessibility actions
- API / device actions
- page-internal JavaScript adapter when available

### 2.5 Verification Layer

Checks whether expected effects occurred:

- DOM state changed
- URL changed
- target text appeared
- success message visible
- error banner absent
- screenshot diff matches expected region
- device state changed
- postcondition oracle passed

### 2.6 Recovery Layer

Handles failures:

- retry after wait
- refresh affordances
- switch backend
- close blocking modal
- replan from current state
- ask parent agent
- request human approval
- safe abort

### 2.7 Trace and Evaluation Layer

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

## 3. Suggested Repository Layout

```text
affordance_runtime/
  app/
    main.py
    api/
      tasks.py
      runs.py
      traces.py
      skills.py
      evals.py
  runtime/
    coordinator.py
    state.py
    planner.py
    action_router.py
    executor.py
    verifier.py
    recovery.py
  perception/
    dom_adapter.py
    accessibility_adapter.py
    visual_adapter.py
    wot_adapter.py
    page_agent_adapter.py
  affordance/
    model.py
    builder.py
    registry.py
    contracts.py
  events/
    bus.py
    watcher.py
    classifiers.py
  trace/
    logger.py
    schema.py
    replay.py
    viewer.py
  eval/
    task_runner.py
    oracle.py
    metrics.py
    failure_classifier.py
    reports.py
  evolution/
    analyzer.py
    proposal.py
    skill_miner.py
    policy_patch.py
    regression_gate.py
  integrations/
    mcp_server.py
    rest_server.py
    langgraph_node.py
    codex_tool.py
    claude_tool.py
    openhands_adapter.py
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

