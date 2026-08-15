# Documentation Governance

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** documentation authority, lifecycle, discovery, and maintenance
> **Target:** [Target AgentLoop Authority Map](task-execution-authority-map.md)
> **Manifest:** [documentation-manifest.yaml](documentation-manifest.yaml)

## 1. One discovery path and scoped authority

Humans and agents start at [Documentation Index](README.md), then use the
manifest. Filename date, file length, backlinks, search rank, or the word
“architecture” does not establish authority.

| Question | Sole owner |
|---|---|
| What must the target become? | authoritative architecture |
| In what order and with which deletion gates? | authoritative evolution plan |
| What does reviewed code do now? | implementation status |
| What slice is active now? | current implementation plan |
| What is the durable product direction? | project plan |

Target design and implementation truth are deliberately separate. A target
contract is not implemented merely because it is authoritative. Legacy code is
not a target merely because it is current.

## 2. Authority precedence

```text
authoritative architecture
→ authoritative evolution plan
→ implementation truth / active queue / product roadmap
→ bounded normative contract
→ maintained reference
→ immutable evidence or admission record
→ archive
```

A more specific named scope owner wins only inside its scope. Bounded contracts
may explain perception, evaluation, or integration, but may not repeat or
replace the whole architecture.

## 3. Lifecycle classes

| Lifecycle | Meaning | Defines target semantics? |
|---|---|---:|
| `current authoritative` | exactly one target and one evolution plan | yes |
| `current status` | factual state and active scheduling | no |
| `current normative` | one bounded responsibility | only within that scope |
| `current reference` | scenario, entrypoint, review, threat model | no |
| `immutable record` | exact revision/profile evidence | no |
| `archived` | superseded history | no |
| `redirect` | stable pointer to archive/replacement | no |

## 4. Current terminology

- `TaskGoal` is responsibility-thin but semantically strong: goal, constraints,
  effect boundaries, inputs, completion, outputs, risk profile, and optional
  material bindings—never page structure, route, or Plan.
- `EvaluationSpec` is optional strict completion/output semantics.
- `WorldObservation` is the Runtime's complete current semantic world model.
- `ObservationCapabilities` declares operational independent-capture and
  post-action-observation support; it is separate from evidence modality and
  source assurance.
- `ObservationAcquisition` is the closed request-correlated aggregate for one
  acquisition: request, plan, provider activations/per-need outcomes, fusion
  outcome and acquired/capability-unavailable/failed status remain reachable.
- `AgentWorldView` is the compact model-facing projection.
- `SemanticTarget` retains one identity across surface representations.
- `ActionBinding` contains surface/backend-specific execution material.
- `ActionSpace` is the observation-bound set shown to policy.
- `ActionIntent` is the user/model-facing semantic action.
- `BoundActionRequest` is one ActionIntent bound to current observation and binding.
- `ActionResult` reports execution/transport status; it does not prove effect.
- `ExecutionOutcome` retains the exact BoundActionRequest and ActionResult;
  dispatched outcomes also retain the typed post-action
  ObservationAcquisition. Acquisition failure does not erase dispatch truth,
  and `NOT_SENT` does not fabricate an acquisition.
- `ActionEvaluation` and `TaskEvaluation` are independent post-observation judgments.
- `TaskPlan<Milestone>` is an optional replaceable hypothesis; `LocalObjective`
  is the nearby state selected from the current task frontier.
- `VerifiedTaskState` is the P5-E run-scoped authority for the validated task
  frontier and accepts only validated evidence updates.
- `AgentLoopState` is the authority for current run control state.
- `ControlTransition` is one bounded typed record per accepted policy decision
  and composes exact phase aggregates rather than independently writable
  execution/acquisition summaries.
  It is run-scoped and in-memory, not a durable ledger, event-sourcing stream,
  replay source, or state-reconstruction authority.
- `ProgressController` is the local `fill`/`select` liveness guard;
  `TaskProgressAuditor` separately owns criterion/milestone/frontier auditing.
- `HumanConfirmation` binds semantic intent, risk and consequences; a fresh
  binding alone does not change what the user confirmed.
- `ActionBatch` is semantic selection and `BoundActionBatch` is its current
  execution form; both are max-three, low-risk, same-surface and no-barrier.
- `TurnRecorder` is optional telemetry and never execution authority.

`TaskSpec`, `ActionContract`, `StateKernel`, `RuntimeDelta`,
`RuntimeCommitter`, recovery transaction, and TraceDag remain implementation or
historical terms until migration deletes them. Maintained documents may mention
them only to describe code truth, migration sources, or legacy scenarios.

## 5. Update protocol

When target architecture changes:

1. update architecture and evolution plan together;
2. update implementation status only with factual evidence;
3. update active queue with dependencies and exit/deletion gates;
4. update affected bounded contracts;
5. update root README, index, and manifest;
6. archive superseded prose rather than layering another authority;
7. run documentation governance, relative-link, and architecture checks.

## 6. Mechanical gate

The documentation test verifies manifest paths/lifecycles, one architecture and
one evolution plan, non-archive authority links, redirect validity, and relative
links in maintained Markdown. It does not make historical prose authoritative
or prove that target code exists.
