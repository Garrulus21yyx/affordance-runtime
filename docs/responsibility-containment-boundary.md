# Responsibility Containment Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** module ownership, dependency direction, state mutation, and authority containment
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## 1. Core decision

Affordance Runtime is a modular monolith with one authoritative state/trace
writer. Single writer does not mean one universal algorithm owner.

```text
domain owner receives immutable input
→ returns typed result / transition request
→ RuntimeCommitter validates and commits
→ trace subscriber records committed event
```

Coordinator/RuntimeCommitter sequences phases and commits transitions. It must
not absorb semantic parsing, planning, grounding, verification matching,
failure-string interpretation, or recovery-command synthesis.

## 2. Authority ownership matrix

| Responsibility | Owner | Forbidden expansion |
|---|---|---|
| source identity/version | SourceEnvelopeBuilder | semantic interpretation |
| material source binding | SourceAnchorBuilder + TaskSpecAuthority | effect/capability grant |
| optional provenance audit | SemanticAudit | modifying proposal or TaskSpec |
| accepted task meaning | TaskSpecAuthority | steps/actions |
| canonical requirement identity | TaskSpecAuthority | duplicate semantic copies or claim/obligation graph |
| bounded source context | SourceContextProjector | semantic admission or unrestricted conversation projection |
| current plan admission | TaskPlanAuthority | modifying TaskSpec or granting capability |
| current observed semantics | CanonicalObservationBuilder | reading model presentation policy |
| full current legal choices | ActionChoiceBuilder | model call, execution, approval |
| model-facing bounded choices | ChoicePresentationProjector | Catalog membership changes |
| concrete action transaction | ActionContractBuilder | self-authorization or execution |
| task/effect/capability/approval/freshness gates | dedicated gate owners | silent widening or relocation |
| backend action dispatch | Executor | effect/step/task judgment |
| evidence extraction | internal EvidenceProvider | root completion or state writes |
| typed loop evaluation | LoopEvaluator | execution or progress mutation |
| task closure semantics | TaskCompletionEvaluator | state commit |
| required output closure | TaskCompletionEvaluator | Planner prose as structured output |
| failure classification | FailureOwnerRouter | recovery execution |
| recovery decision | typed owner | arbitrary StateKernel mutation |
| state and trace commit | RuntimeCommitter | semantic reinterpretation |
| benchmark/evolution | offline pipeline | synchronous Runtime authority |

## 3. Dependency direction

```text
neutral contracts
    ↑
pure domain collaborators
    ↑
phase/orchestration owners
    ↑
entrypoints and integrations
```

Neutral contracts and pure collaborators must not import Coordinator,
StateKernel mutation services, adapters, benchmark packages, trace writers, or
provider-specific clients. Adapters translate environment data; they do not own
task semantics. Benchmarks consume public Runtime contracts; Runtime core does
not import benchmark behavior.

## 4. Planner containment

Task Planner may propose `StepSpec` milestones and, when explicitly needed,
read a bounded `context_only` SourceContextView. Every Step must reference
existing TaskSpec requirement IDs. Step Choice Planner may select only IDs
shown in a bounded ChoicePage and normally receives no source text. Neither may:

- patch TaskSpec;
- build the Runtime Catalog;
- invent selector, coordinate, backend, capability, or approval;
- construct or execute ActionContract;
- write TaskProgress or terminal state.

The raw-text-free execution authority boundary covers ActionChoiceBuilder,
grounding/predicate resolution, selection validation, ActionContractBuilder,
all gates, Executor, LoopEvaluator, TaskCompletionEvaluator, and
RuntimeCommitter. These modules do not receive raw request, conversation text,
legacy claims, or SourceContextView. OpenSemanticResolver and
ClarificationComposer are bounded semantic consumers, not execution owners;
they return typed resolution, TaskSpecGap, or a question without modifying
TaskSpec.

## 5. State containment

StateKernel stores current authority identities and committed state, including
TaskSpec/TaskPlan revisions, current observation/Catalog refs, progress,
capability/approval state, budgets, recovery, and terminal result. It does not
interpret raw text, plan algorithms, model context, or verifier semantics.

Current observation facts stay in canonical observation. Recent action
causality stays in a bounded ActionOutcome index. Only durable artifact,
resource, transaction, or human evidence crosses observation epochs.

## 6. Change rule

A change touching an authority boundary must identify:

1. existing owner;
2. target owner;
3. typed input/output;
4. production cutover;
5. legacy deletion or isolated-adapter gate;
6. focused tests proving no second authority.

The detailed pre-consolidation containment document is archived at
[maintained-pre-consolidation/responsibility-containment-boundary.md](archive/superseded-2026-08-05/maintained-pre-consolidation/responsibility-containment-boundary.md).
