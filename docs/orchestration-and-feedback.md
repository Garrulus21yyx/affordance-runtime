# Agent Orchestration and Live Feedback

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** serial Runtime loop, phase results, feedback, continuation, and commit ordering

The dispatch, surface, and restart clauses below include target contracts
spanning future hardening and not-yet-started P5-R recovery. They define the required
cutover and acceptance boundary; the document status does not by itself assert
that the current product path has implemented that lifecycle.

For the current one-process/one-coordinator MVP, only the finalized-contract,
hash-equality, stale zero-call, verifier-backed completion and no-blind-retry
rules formed the P4 semantic gate; their closure evidence now passes and P5 is
admitted but not started. Permit/CAS/fencing/revocation/collateral clauses are
future hardening and do not block P5.

## 1. Main loop

```text
capture canonical observation
→ trigger task-completion precheck when required
→ reuse/direct-plan/replan current TaskPlan through typed planning gate
→ activate StepSpec
→ build full Runtime ActionChoiceCatalog
→ select directly or through bounded ChoicePage
→ capture fresh preflight observation O1
→ revalidate/rebuild Catalog and selection against committed O1
→ materialize and freeze complete executable ActionContract H
→ independent task authority + effective capability admission
→ policy/capability + exact approval evaluate H
→ final snapshot/page/target/expiry check
→ serial Executor dispatches H with approved_hash == executed_hash
→ commit typed transport outcome
→ capture canonical post-action observation
→ settle effect and run LoopEvaluator(step, triggered task, continuation)
→ materialize required outputs from admitted evidence
→ RuntimeCommitter
→ continue / perceive / recover / replan / ask / finish
```

The loop is serial by default. Parallel observation providers may run inside a
capture only when their results join into one explicit canonical epoch before a
semantic consumer proceeds.

## 2. Physical sequence and logical authority

The non-bypassable action boundary is:

```text
committed O1
→ sealed exact contract
→ authority/capability/approval admission
→ final snapshot/page/target/expiry check
→ assert approved_hash == executed_hash
→ serial Executor of the same immutable ActionContract
```

Approval may involve a wait, so the final freshness check occurs after the
grant and immediately before Executor. The approval request
and one-shot grant bind the exact contract hash, run and session-generation
nonce, TaskSpec/Catalog/observation revisions, route/effect/capability/policy
digests, subject/resource, destination/recipient, named parameters, execution
context, surface/coordinate digests, risk, and expiry. A response arriving after
interrupt, cancellation, restart, request supersession, contract staleness, or
session-generation change is rejected/tombstoned; it cannot revive an old
request from checkpoint audit data.

The current trusted serial path may use `FinalDispatchAdmission` or
`DispatchPermit` as internal values, but Executor authority is the final
immutable ActionContract already checked by policy/approval/preflight. A token
cannot change that contract. Linearizable revocation, clone-resistant/global
consumption, state-version CAS and surface fencing require a broader concurrency
threat model and are future hardening, not P4/P5 gates.

The complete `RouteBinding` and contract projection are secret-free. Canonical
target/destination identities exclude credential-bearing URI/query components;
cookie/token/signature/signed-URL material is injected only at the true dispatch
boundary under the sealed principal/audience/credential scope and a closed
late-binding policy, never persisted in contract, trace, or checkpoint.

Verification is physically inside the loop so each action receives immediate
feedback. Transport and effect remain logically separated:

- Executor always returns a typed transport outcome, including failure exits;
- `NOT_SENT` means the boundary is proven not crossed, `SENT_UNKNOWN` means it
  may have been crossed, and `SENT` means transport was sent (with any backend
  acknowledgement retained in the typed receipt);
- effect settlement separately returns `NOT_OCCURRED`, `OCCURRED`, or
  `STILL_UNCERTAIN` from identity-bound evidence;
- EvidenceProviders extract observations;
- LoopEvaluator returns typed evaluations;
- TaskCompletionEvaluator computes full TaskSpec.success closure;
- RuntimeCommitter applies progress/terminal transitions.

A backend acknowledgement or `SENT` receipt never implies `OCCURRED`. An
exception, timeout, connection reset, process loss after committed dispatch
intent, or absent final receipt must not default to `NOT_SENT`; if the send
boundary cannot be proved, it is `SENT_UNKNOWN`. `OCCURRED` and `NOT_OCCURRED`
claims use symmetric effect/risk-specific assurance and
attempt/transaction/resource identity.

No phase may bypass another by writing StateKernel directly.

## 3. Planning horizons

Task Planner changes milestone structure under current facts. Step Choice
Planner selects among displayed members of a Runtime-built Catalog. Zero/one/N
choice handling is Runtime-owned. A model request never creates the candidate
space it is asked to reason over.

Task Planner may receive an optional bounded SourceContextView as a
non-authoritative side input. The execution path does not receive
SourceContextView or raw request content. If planning or open-semantic
resolution discovers missing admitted meaning, the loop routes TaskSpecGap or
clarification; it does not continue to action construction with inferred
authority.

Task planning has a deterministic reuse/direct fast path. A still-feasible
active Step continues without a Task Planner call; a model plan request exists
only when a typed planning/replanning trigger is committed. Replaceable planning
therefore does not mean regenerating a DAG every loop.

## 4. Live feedback

Feedback consists of committed typed facts:

- observation/coverage/conflict changes;
- selection, contract, gate, and receipt results;
- effect/step/task evaluations;
- bounded progress and recent action outcomes;
- recovery owner/command/outcome;
- approval/clarification requests;
- session generation, surface/coordinate binding, lease, attempt, dispatch,
  transport, and effect transitions through bounded refs/digests;
- required `OutputMaterialization` refs and their admission results;
- terminal result and evidence/trace refs.

Streaming UI may project these events but cannot mutate their meaning.

## 5. Continuation safety

- new observation epoch invalidates stale Catalog/contract/approval bindings;
- snapshot/page/target changes invalidate downstream action artifacts; extra
  session/surface/coordinate dimensions apply only when the adapter scenario declares them;
- plan replacement does not revise TaskSpec;
- plan exhaustion triggers final evaluation, not completion;
- required outputs must be represented by actual typed `OutputMaterialization`
  values/artifact refs, integrity digests, and source/criterion lineage before
  completion; `OutputSpec`, metadata, or Planner/final prose is not a result;
- uncertain external effects route to inspect/recheck/block, not automatic retry;
- post-action observation is reused when the typed Perception disposition permits.

## 6. Coordinator boundary

Coordinator invokes owners, receives typed results, commits transitions/events,
and chooses the next phase. Algorithms remain in their domain owners. Generic
exception text may be logged but cannot select a recovery owner or synthesize a
command.

Checkpoint resume is validation and routing only. It validates schema,
identity, revisions/digests, trace head, approval/attempt lifecycle, and
`last_committed_observation_ref`, then returns a typed route to rejection, fresh
session/perception, or effect reconciliation. Existing owners perform those
operations. Resume does not rebuild StateKernel from an object graph, open a
browser/app, acquire a lease, capture an observation, grant approval, settle an
effect, dispatch, materialize output, or commit completion.

## 7. Serial action scope; no batch authority

The current closure admits one sealed `ActionContract` per `ExecutionAttempt`.
It does not introduce `ActionBatch`, `BatchActionContract`, `BatchApproval`, a
batch cursor, rollback coordinator, or wildcard approval. Actions targeting the
same mutable GUI surface remain serialized; only read-only acquisition inside a
single canonical epoch may run in parallel before the join.

Any future batch design must preserve a fresh observation, exact contract,
attempt, receipt, effect settlement, and approval decision for each effectful
child. An uncertain child blocks later dependent dispatch. This future
possibility does not add a batch owner or batch state to the P5-R checkpoint.

## 8. Interrupt and cancellation boundary

Interrupt/cancel is observed at safe phase boundaries. Before dispatch it
invalidates pending grants/contracts/permits and prevents the attempt. Once
dispatch intent is committed, cancellation cannot pretend to retract an input
event or external request; the attempt must reach a typed transport outcome or
recover as `SENT_UNKNOWN`, followed by effect reconciliation. No mid-dispatch
exception path may erase the committed attempt lifecycle.

## 9. Risk-derived feature profiles

`DIRECT_LOW_RISK`, `MULTI_STEP`, and `HIGH_RISK_MULTI_SOURCE` progressively
enable optional audit, paging/refinement, open semantics, model evidence, and
durable transaction evidence. Profiles are derived from TaskSpec risk and
actual scale; they cannot disable required Task/Capability/Approval/Freshness
gates, uncertain-effect protection, output closure, or single-writer commit.

The previous detailed orchestration document is archived at
[maintained-pre-consolidation/orchestration-and-feedback.md](archive/superseded-2026-08-05/maintained-pre-consolidation/orchestration-and-feedback.md).
