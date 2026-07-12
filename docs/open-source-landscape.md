# Open Source Landscape

## 1. Positioning Map

| Project | Type | What to Learn | Difference |
| --- | --- | --- | --- |
| Alibaba PageAgent | in-page JavaScript GUI agent | low-friction page integration, DOM text representation, MCP entry | PageAgent lives inside a webpage; Affordance Runtime is an external harness/runtime |
| browser-use | Python browser agent framework | agent loop, browser task execution, agent-framework integration | Affordance Runtime focuses on action contracts, trace, eval, recovery, and harness evolution |
| Stagehand | browser automation SDK | code + natural language hybrid actions, action cache, self-healing | Affordance Runtime generalizes beyond browser automation and makes evaluation central |
| Skyvern | visual browser workflow platform | vision-based page reading, no-code workflows, real business workflows | Affordance Runtime is a lower-level runtime and subagent interface |
| OpenHands / Open Operator | coding and computer-use agent platform | parent-agent integration, cloud execution, browser/GUI operator role | Affordance Runtime can be called as a GUI subagent |
| Agent S / Agent S2 | computer-use agent framework | desktop GUI planning, perception, fine-grained control | Affordance Runtime starts from web and affordance contracts, then expands |

## 2. PageAgent Comparison

PageAgent is designed for client-side web enhancement. It is embedded directly
into a web page through JavaScript. Its strengths are:

- one-line page integration
- DOM-text based operation
- no headless browser required
- optional extension for multi-page tasks
- MCP beta for external control
- strong product story for SaaS copilots, forms, ERP, CRM, and accessibility

Affordance Runtime should not compete with PageAgent on in-page convenience.
Instead, it can use a PageAgent-style adapter as one backend among many.

## 3. Browser Agent Frameworks

Browser-use and Stagehand are important references.

Browser-use is useful for:

- task-level browser agent loop
- browser action abstractions
- integration with agent clients

Stagehand is useful for:

- deciding when to write code versus natural language actions
- action caching
- self-healing browser automation
- production-minded browser workflows

Affordance Runtime should borrow these ideas but add:

- formal action contracts
- postcondition verification
- event-driven live feedback
- failure taxonomy
- trace replay
- benchmark evaluation
- harness evolution

## 4. Benchmarks and Papers

### MiniWoB++

Atomic web interaction benchmark. Useful for action grounding and small,
deterministic tasks.

### WebArena

Self-hosted realistic web environment for autonomous agents. Useful for
multi-step web workflows and reproducible evaluation.

### VisualWebArena

Multimodal web benchmark. Useful for testing visual grounding and screenshot
reasoning.

### Mind2Web

Dataset for generalist web agents across real websites and many domains. Useful
for studying generalization and instruction-to-action mapping.

### OSWorld

Real desktop computer-use benchmark. Useful as a future expansion target beyond
web GUI.

### LivingScreen

Benchmark for dynamic, living-screen GUI agents where observation is itself a
cost-bearing action. Useful for designing observation policy and measuring
over-observation / under-observation.

### GUI Agent Autonomy Levels

Conceptual framework for clarifying agent autonomy, responsibility, and risk.
Useful for defining what level Affordance Runtime supports.

## 5. Differentiation Statement

Affordance Runtime should be described as:

> an affordance-based GUI agent harness that makes environment interaction
> verifiable, recoverable, traceable, and evolvable.

Not:

> another browser agent.

