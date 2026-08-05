# Runtime-First Architecture Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** product boundary between Runtime, models, parent agents, adapters, and benchmarks
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## 1. Product boundary

Affordance Runtime is the product. A parent agent or reference planner may
submit intent and make bounded planning choices, but the Runtime owns whether a
concrete GUI action is legal, fresh, approved, executed, verified, recoverable,
and committed.

BrowserGym, MiniWoB++, WorkArena, WebArena, ScreenSpot, WASP, and local fixtures
are consumers/evaluators. None defines production semantics.

## 2. Runtime-owned chain

```text
legal source identity
→ accepted TaskSpec
→ canonical current observation
→ admitted TaskPlan
→ full Runtime ActionChoiceCatalog
→ admitted selection
→ concrete ActionContract
→ authority/capability/approval/preflight
→ dispatch receipt
→ post-action canonical observation
→ typed LoopEvaluation
→ authoritative commit
```

Model views are bounded projections. Omission from a model view cannot erase a
Runtime target, action, fact, authorization, or conflict.

## 3. Model proposal boundary

Models may propose MinimalIntentProposal, TaskPlan steps, displayed choice IDs,
open-semantic evidence, or clarification. Models never own:

- SourceEnvelope identity;
- accepted TaskSpec or revision;
- full ActionChoiceCatalog membership;
- concrete grounding/binding;
- capabilities or approval tokens;
- stale-state override;
- progress or TaskCompleted commits.

Page/adapter content is untrusted observation and cannot become user authority.

## 4. Adapter boundary

DOM, AX, visual, SVG, API, device, and browser adapters provide captures,
bindings, execution routes, and evidence. Each adapter reports coverage,
freshness, confidence, and conflicts without deciding task meaning or success.

Acquisition truncation is represented as SourceCoverage; it is not equivalent
to target absence. Presentation truncation is a model-context property; it is
not acquisition or Runtime candidate truncation.

## 5. Benchmark boundary

Production code, prompts, semantic compilers, planners, and recovery policies
must not branch on task ID, seed, family, expected answer, selector, coordinate,
or fixture-authored shortcut. A benchmark finding becomes production work only
after it is expressed as a generic contract/invariant with non-benchmark tests.

## 6. Evidence boundary

Execution receipt proves dispatch status only. Typed evaluation determines
effect/step/task semantics. External benchmark reward is evidence for an exact
run/profile, never Runtime completion authority.

Target claims require current implementation inspection and reproducible
evidence at one immutable revision. Historical reports do not roll forward.

The previous detailed boundary is archived at
[maintained-pre-consolidation/runtime-first-boundary.md](archive/superseded-2026-08-05/maintained-pre-consolidation/runtime-first-boundary.md).
