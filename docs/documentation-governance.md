# Documentation Governance

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** documentation authority, lifecycle, discovery, and maintenance
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
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
- `AgentWorldView` is the compact model-facing projection.
- `SemanticTarget` retains one identity across surface representations.
- `ActionBinding` contains surface/backend-specific execution material.
- `ActionSpace` is the observation-bound set shown to policy.
- `ActionIntent` is the user/model-facing semantic action.
- `BoundActionRequest` is one ActionIntent bound to current observation and binding.
- `ActionResult` reports execution/transport status; it does not prove effect.
- `ActionEvaluation` and `TaskEvaluation` are independent post-observation judgments.
- `TaskPlan<Milestone>` is optional and replaceable; `LocalObjective` is the
  nearby state for one to several turns.
- `AgentLoopState` is small serial loop state.
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
