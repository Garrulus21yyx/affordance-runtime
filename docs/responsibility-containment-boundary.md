# Responsibility Containment Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** module ownership, dependency direction, state mutation, and authority containment
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

Rows covering live surfaces, dispatch permits, checkpointing, and resume are
target containment contracts spanning future hardening and not-yet-started P5-R
recovery. They constrain future implementation and do not claim those planned
modules are already cut over.

They are also non-blocking future hardening under the current trusted
single-process/single-coordinator MVP. The MVP dispatch boundary is one
final immutable contract checked by policy/approval/preflight and then consumed
unchanged by the serial Executor; that P4 MVP boundary is now closed.

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

Authority ownership is logical, not a deployment topology. The modular-monolith
MVP may implement authorities as pure functions, immutable validators, or
in-process policy composition. Four action gates may share one admission
service, and fact/binding/outcome/durable namespaces may share one physical
RunLedger, provided their typed results, deny semantics, lifetimes, and write
boundaries remain distinct. A matrix row does not justify a new process,
database, queue, or model call.

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
| source acquisition truth/coverage | each environment acquisition adapter | builder-inferred `COMPLETE` or absence from missing coverage |
| full current legal choices | ActionChoiceBuilder | model call, execution, approval |
| model-facing bounded choices | ChoicePresentationProjector | Catalog membership changes |
| full Draft/Sealed action transaction | ActionTransactionMaterializer, composing pure route/binder/evaluator collaborators | partial old-contract patching, self-authorization, execution, session acquisition, or state writes |
| durable execution-context requirement | TaskSpecAuthority | credentials, live handles, or claiming a current session match |
| live session/surface generation | environment session owner | semantic authorization, approval, or checkpoint resurrection |
| route-specific coordinate transform | grounding/adapter owner | policy admission, execution, or reuse after surface change |
| mutable GUI surface exclusivity | logical SurfaceLease owner in the session lifecycle | target freshness, task claim, capability, or approval |
| task/effect/capability/approval/freshness gates | dedicated gate owners | silent widening or relocation |
| final contract admission | Task/Capability/Approval/Preflight owners checking the complete immutable ActionContract | approving a choice/Draft then allowing payload mutation; state writes |
| optional dispatch-token hardening | existing owners/RuntimeCommitter only when a broader concurrency fault model is admitted | a fifth permission system, P4/P5 blocker, or production-grade claim without evidence |
| backend action dispatch | serial Executor consuming the admitted ActionContract unchanged | effect/step/task judgment or changing approved parameters |
| evidence extraction | internal EvidenceProvider | root completion or state writes |
| typed loop evaluation | LoopEvaluator | execution or progress mutation |
| task closure semantics | TaskCompletionEvaluator | state commit |
| actual required output production | typed OutputMaterialization provider | declaring requirements or committing task completion |
| required output admission/closure | TaskCompletionEvaluator | Planner prose, OutputSpec metadata, or trace projection as an actual result |
| failure classification | FailureOwnerRouter | recovery execution |
| recovery decision | typed owner | arbitrary StateKernel mutation |
| state and trace commit | RuntimeCommitter | semantic reinterpretation |
| checkpoint snapshot projection | RuntimeCommitter over committed state | object-graph serialization or physical-store policy |
| checkpoint encoding/storage | focused codec/store port | semantic validation, live authority, or state reconstruction |
| resume validation/routing | planned pure runtime-resume boundary | session opening, perception, effect adjudication, approval, dispatch, completion, or persistence |
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
grounding/predicate resolution, selection validation, ActionTransactionMaterializer,
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

When a scenario needs multi-account/profile or coordinate identity, execution
context is split across three owners and lifetimes:

- durable `ExecutionContextRequirementRef` is an opaque authorized scope with no
  secret or live handle;
- ephemeral `LiveSurfaceBinding` binds the current account/profile, session
  generation, run owner, backend/display, app/process, window/tab/frame/document,
  focus/modal state, and surface revision;
- ephemeral `CoordinateBinding` binds route-specific source/destination spaces,
  screenshot/viewport/crop/scroll/scale/origin inputs, document/frame identity,
  and transform digest.

No equality over URL, DOM or screenshot may substitute for a live identity
claim once that optional scenario is enabled. `SurfaceLease`, task/run claim
and multi-worker fencing are future hardening; MVP freshness uses snapshot,
page/document revision, target fingerprint and expiry.

A checkpoint is a versioned projection of committed identities and lifecycle
facts. It stores refs/digests, including `last_committed_observation_ref`, rather
than StateKernel, canonical observation, executable contract, or live adapter
objects. After restart that observation ref is historical. Fresh session,
surface lease, canonical observation, Catalog, contract, approval, and dispatch
admission are reconstructed through their normal owners, never deserialized as
current authority.

## 6. Anti-God-object composition rules

- Do not introduce a universal `Context`/`ExecutionContext` object containing
  TaskSpec, observation, session, approval, coordinates, credentials, and
  recovery state. Phase APIs receive the smallest typed refs/views they need.
- `ActionTransactionMaterializer` consumes an accepted selection and committed
  observation/context/coordinate/capability refs. It cannot open a browser/app,
  capture perception, acquire a surface lease, approve, commit, or dispatch.
- The planned `runtime_resume.py` boundary validates checkpoint
  identity/version/dependencies and returns a typed `ResumeDirective` or
  rejection. It does not reconstruct StateKernel, open sessions, capture,
  perform effect-specific status lookup, settle effects, plan, authorize,
  approve, dispatch, materialize outputs, complete, persist, or commit. Those
  operations remain with existing owners selected by the route.
- The planned checkpoint schema/codec/store remains a bounded projection and
  persistence port. `RuntimeCommitter` is the snapshot producer, but does not
  absorb serialization, filesystem/database policy, or restore orchestration.
- `OutputMaterialization` producers construct actual typed values/artifacts and
  lineage; they do not own TaskSpec success. Trace projectors redact and record
  committed facts; they do not become evidence admission or completion owners.
- A logical row in the ownership matrix may be an immutable value, pure
  function, validator, or in-process protocol. It does not justify a new
  service, queue, database, manager class, or distributed lease system.
- The current closure has no `ActionBatch`, `BatchApproval`, batch cursor,
  rollback coordinator, or batch owner. Same-surface actions stay serial, and a
  future batch must preserve per-child observation, contract, attempt, receipt,
  effect settlement, and approval boundaries.

## 7. Change rule

A change touching an authority boundary must identify:

1. existing owner;
2. target owner;
3. typed input/output;
4. production cutover;
5. legacy deletion or isolated-adapter gate;
6. focused tests proving no second authority.

Physical extraction additionally requires measured isolation, concurrency,
scale, reliability, or regulatory need. Convenience or naming symmetry alone
is insufficient.

The detailed pre-consolidation containment document is archived at
[maintained-pre-consolidation/responsibility-containment-boundary.md](archive/superseded-2026-08-05/maintained-pre-consolidation/responsibility-containment-boundary.md).
