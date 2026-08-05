# Active Perception and Online Recovery Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** capture, canonical observation, coverage/conflict, observation continuation, and typed recovery
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## 1. Observation authority

```text
environment sources
→ PerceptionSession.capture
→ PerceptionCapture + SourceCoverage
→ CanonicalObservationBuilder
→ immutable UnifiedObservation epoch
```

The canonical observation is the only current semantic observation authority
for Runtime grounding, Catalog construction, binding, preflight, and typed
evaluation. PlannerObservationView and ChoicePage are bounded projections and
cannot be converted back into Runtime authority.

## 2. Acquisition and coverage

PerceptionCapture records what each source actually acquired, including source
identity, freshness, limits, errors, and coverage. Canonical targets retain
available source surfaces, action supports/bindings, typed state facts, source
assertions, confidence, and explicit conflict state.

These cases are distinct:

- target absent under complete relevant coverage;
- relevant source not acquired;
- required property not observed;
- material sources conflict;
- target exists but no legal action support;
- model presentation omitted the target.

Only the first permits a true target-not-present conclusion.

## 3. Active perception

Runtime may request a bounded read-only probe when a required source/property is
missing and the acquisition budget allows it. Targeted capture creates a new
canonical epoch; it does not patch the previous object in place.

Active perception cannot widen TaskSpec authorization, execute an effect,
manufacture a selector, or treat page content as user instruction.

## 4. Post-action observation continuation

Post-action capture goes through the same canonical builder and normally becomes
the next loop epoch. Perception owner returns one typed disposition:

| Disposition | When |
|---|---|
| `REUSE` | fresh, stable, no material conflict, required next sources present |
| `AUGMENT_TARGETED` | only a known required source/property is missing |
| `RECAPTURE` | stale, conflict, invalid capture, or broad new-source need |
| `WAIT_AND_RECAPTURE` | loading, asynchronous mutation, or pending external state |

A reusable post-action observation is not captured again immediately.
Coordinator executes this result; it does not invent the disposition.

## 5. Failure ownership

| Typed cause | Owner/response |
|---|---|
| coverage insufficient / state unobserved | Runtime perception recovery |
| complete coverage + step target absent | Task Planner replan |
| stale observation/Catalog/contract | reobserve and rebuild |
| material conflict | inspect, block, or user/terminal according to risk |
| invalid/unpresented model choice | planner/provider repair or next page |
| capability/approval failure | safety/user owner |
| open semantic unresolved | restricted resolver, then user/planner/terminal |
| final evidence insufficient | final acquisition/replan/block |
| uncertain external effect | authoritative recheck; never blind retry |

Owner selection comes from typed facts, not generic error-text parsing.

## 6. Recovery constraints

Recovery is budgeted and side-effect-aware. A command may inspect, wait,
targeted-perceive, replan, rebuild, request approval/clarification, or terminate.
It cannot mutate TaskSpec, reuse stale approval, silently relocate an old
ActionContract, or automatically repeat an uncertain non-idempotent effect.

## 7. Progress and trace

Current facts remain in the canonical observation. Contract-bound causality is
kept in bounded recent ActionOutcomes. Durable artifact/resource/transaction/
human evidence may cross epochs. Recovery and observation events are committed
in order by RuntimeCommitter and consumed by offline trace/evaluation.

The previous M8.6-era detailed design is archived at
[maintained-pre-consolidation/active-perception-and-online-recovery.md](archive/superseded-2026-08-05/maintained-pre-consolidation/active-perception-and-online-recovery.md).
