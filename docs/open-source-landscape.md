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
| BrowserAct | browser skill/action substrate | indexed state/action, session ownership, confirmation gates | Affordance Runtime adds lease-bound contracts, verifier ladder, and trace DAG |
| WebArena-Verified | audited benchmark methodology | deterministic structural scoring, network-trace evaluation | Affordance Runtime should prefer structural oracles over LLM judges |
| WASP | web prompt-injection benchmark | tainted page content and security boundaries | Affordance Runtime needs capability gates and untrusted-content handling |

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

OSWorld-style long-horizon tasks motivate the State Kernel: constraints,
pending obligations, and hidden state must survive many observation/action
cycles.

### LivingScreen

Benchmark for dynamic, living-screen GUI agents where observation is itself a
cost-bearing action. Useful for designing observation policy and measuring
over-observation / under-observation.

LivingScreen-style dynamics motivate budgeted observation and Affordance Lease
TTL. The runtime should know when to refresh and when an observation is current
enough to act.

### Dynamic GUI Benchmarks

DynamicGUIBench-style tasks show that a single screenshot after each action is
not enough for dynamic interfaces. This motivates event streams, environment
revisions, and hidden-state hypotheses in the State Kernel.

### WebArena-Verified

Audited task definitions and structural scoring are a better benchmark target
than pure model-judge grading. Affordance Runtime should produce receipts and
oracles that can be checked without trusting the acting model.

### WASP / Prompt Injection

Web pages can contain hostile or misleading instructions. The runtime should
treat page text as tainted observation data, not as trusted system policy.
Capability gates and approval policies should dominate page content.

### WeaveBench-Style Trajectory Judging

Outcome-only grading can overestimate success. The benchmark should inspect
actions, files, screenshots, logs, receipts, and verifier outputs across the
trajectory.

### GUI Agent Autonomy Levels

Conceptual framework for clarifying agent autonomy, responsibility, and risk.
Useful for defining what level Affordance Runtime supports.

## 5. Differentiation Statement

Affordance Runtime should be described as:

> an affordance-based GUI agent harness that makes environment interaction
> verifiable, recoverable, traceable, and evolvable.

Not:

> another browser agent.

