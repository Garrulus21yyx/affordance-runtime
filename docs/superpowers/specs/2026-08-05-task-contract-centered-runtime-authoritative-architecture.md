# Retired Task-Contract-Centered Architecture

> **Lifecycle:** RETIRED POINTER
> **Updated:** 2026-08-13
> **Current authority:** [Target AgentLoop Authority Map](../../task-execution-authority-map.md)
> **Implementation truth:** [Implementation Status](../../implementation-status.md)

This filename is retained only so historical records keep a resolvable link. It
is not an architecture authority and does not define a compatibility path.

The discarded design coupled the target GUI `AgentLoop` to workflow
`TaskSpec/TaskPlan`, rolling frontier, requirement-hypothesis, and packaged
objective-operation owners. Those owners were not part of the short-loop
contract and created duplicate semantic authority before the first world
observation. They have been removed from the target loop.

The current contract is:

```text
UserRequest
  -> Thin Intake
  -> TaskGoal + bounded IntentContext(context_only)
  -> initial WorldObservation
  -> current ActionSpace
  -> disposable AgentContext
  -> one typed AgentDecision
  -> Runtime admission/currentness/private binding
  -> execute once
  -> fresh observation and validated evaluations
```

No exact DOM ID, entity ID, E-ref, coordinate, action ID, or binding exists at
intake. A `LocalObjective` may be proposed only from a current AgentContext and
contains observation-resolvable semantics, never a durable GUI identity. Its
set, sequence, and aggregate reducers share one lifecycle owner and re-resolve
against every fresh observation.

See the current authority map for owners, legal transitions, evidence source
rules, projection constraints, deletion gates, and exit properties.
