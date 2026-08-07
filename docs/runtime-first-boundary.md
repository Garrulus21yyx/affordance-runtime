# Runtime-First Architecture Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** product boundary between Runtime, models, parent agents, adapters, and benchmarks
> **Architecture authority:** [Task Contract-centered architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## 1. Product boundary

Affordance Runtime is the product. A parent agent or reference planner may
submit intent and make bounded planning choices, but the Runtime owns whether a
concrete GUI action is legal, fresh, approved, executed, verified, recoverable,
and committed.

The current product is a GUI-agent research Runtime with complete vertical loop
and limited horizontal breadth. Its MVP boundary is one process, one run, one
coordinator, one browser session, and one active finalized ActionContract.
In-process components are trusted; state mutation, approval consumption, and
effectful execution are serialized.

The trusted computing base (TCB) includes Runtime-selected and configured
in-process adapter/provider implementation code. Adapter-observed or
provider-returned external content is outside that trust boundary: page, email,
PDF, DOM, AX, OCR, screenshot, notification, memory/skill, tool, and remote
provider data remain untrusted observations even when trusted code acquires
them.

It does not claim production-grade security. Multi-tenant authorization,
multiple workers/agents controlling one surface, distributed leases/fencing,
hard-crash dispatch recovery, malicious internal permit cloning, and atomic
cross-thread policy/schema revocation are explicitly deferred.

The product composition uses a safety-preserving profile. A feature profile may
activate optional machinery according to task risk, but it cannot disable task
authority, capability intersection, required approval, freshness/preflight,
uncertain-effect protection, required-output closure, or the RuntimeCommitter
write boundary. If a required policy or safety dependency is unavailable, the
product fails closed with a typed outcome.

Benchmark ablations use a separate benchmark-only composition and profile
digest. They are never accepted by the product composition and may not be
imported as a production fallback.

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
→ materialize and freeze complete executable ActionContract H
→ task/policy/capability admission over H
→ exact approval of H when required
→ final snapshot/page/target/expiry preflight for H
→ serial Execute of H, asserting approved_hash == executed_hash
→ typed dispatch receipt
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

Adapter-observed page/external content is untrusted observation and cannot
become user authority. These sources cannot create capability, approval,
policy, TaskSpec revision, or control flow. An observation-derived value may
enter an effectful sink only through a TaskSpec-authorized typed source-to-field
flow.

## 4. Adapter boundary

DOM, AX, visual, SVG, API, device, and browser adapters provide captures,
bindings, execution routes, and evidence. Each adapter reports coverage,
freshness, confidence, and conflicts without deciding task meaning or success.

Execution adapters must expose actual supported actions and receipt semantics.
Full capability manifests and coordinate bindings (source/destination spaces,
screenshot/viewport, DPR/zoom/origin/transform) are enabled only for adapters or
benchmarks whose action semantics need them; they are not universal P4/P5 gates.

Acquisition truncation is represented as SourceCoverage; it is not equivalent
to target absence. Presentation truncation is a model-context property; it is
not acquisition or Runtime candidate truncation.

## 5. Transaction and capability closure

The effective action/capability envelope is the intersection of actual adapter
support, product policy, and current user grant. Unknown actions fail closed; a
provider safety decision is evidence for local policy, never local authority.
Provider/schema manifest pinning is optional release or high-risk-adapter
hardening.

`ActionTransactionMaterializer` first creates the complete executable contract,
including its final payload, then freezes and hashes it. Task/policy/capability
and approval evaluate that final object. Preflight checks snapshot, page
revision, target fingerprint and expiry; a stale result makes zero Executor
calls. Executor receives the same immutable contract and the Runtime verifies
`approved_contract_hash == executed_contract_hash`. `replace()`, partial
patching, and any approval-after-which-parameters-are-added path are forbidden.

`FinalDispatchAdmission`, state-version CAS, clone-resistant/global permits,
revocation linearizability, run/surface fencing and attempt-bound collateral are
future hardening for a broader concurrency or fault model. An internal token may
remain an implementation detail, but it is not an MVP authority or P5 blocker.

The complete RouteBinding is secret-free. Canonical target/destination/resource
encoding excludes credential-bearing URI/query components; cookies, tokens,
request signatures, and signed URLs are injected only at the dispatch boundary
under the sealed principal/audience/credential scope and closed late-binding
policy, never stored in contract, trace, or checkpoint.

Current production dispatches primitive transactions only. Batch and macro
actions remain plan-level/deferred; they cannot share one approval, receipt, or
success value across multiple effectful actions.

## 6. Benchmark boundary

Production code, prompts, semantic compilers, planners, and recovery policies
must not branch on task ID, seed, family, expected answer, selector, coordinate,
or fixture-authored shortcut. A benchmark finding becomes production work only
after it is expressed as a generic contract/invariant with non-benchmark tests.

AgentDojo/WASP adversarial reporting and OSWorld-V2 functional/collateral
profiles are future release or paper-claim gates. They never become online
dependencies or Runtime completion authority, and they do not block ordinary
P4/P5 mainline development.

## 7. Evidence boundary

Execution receipt proves dispatch status only. Typed evaluation determines
effect/step/task semantics. External benchmark reward is evidence for an exact
run/profile, never Runtime completion authority.

Published benchmark/release claims require reproducible immutable-revision
evidence. Working-tree P4/P5 scheduling uses focused tests and the core
benchmark; historical reports still do not roll forward. The core benchmark is
integration evidence that the five P4-MVP invariants hold on the default route,
not an additional Runtime invariant or completion authority.

## 8. Replay and trace boundary

Replay is offline simulation. A replay miss must fail explicitly and can never
call a live driver, network, credential, account, or effectful adapter. Simulated
and real receipts are different typed records. A new real attempt requires a new
live run identity, observation, admission, approval, and dispatch lifecycle.

Trace and artifact collection follow data minimization. Secret-bearing source
values, screenshots, outputs, and evidence use explicit redaction, encryption,
access, and retention policy; observability does not authorize copying raw
sensitive data into general trace payloads.

## 9. Selective SOTA adoption and non-goals

The Runtime adopts typed actions, partial-observation semantics,
trusted-control/untrusted-data separation, functional effect checks, and
demand-gated capability/coordinate descriptors. It rejects
generic success booleans, provider safety as authority, model/verifier output as
completion truth, effectful no-feedback batches, schema-validation fail-open,
and replay fallback to live execution.

The pinned source snapshots and the explicit adopt/reject/strengthen decisions
live only in the authoritative architecture's
[SOTA adoption record](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md#08-sota-选择性吸收记录). This summary does not create a second source-of-truth matrix.

SOTA methods are selected for the GUI vertical loop; they do not silently expand
the local threat model. These boundaries remain value objects and pure collaborators inside the modular
monolith. They do not require a general dynamic-taint platform, a new
microservice topology, a universal knowledge/evidence graph, or a whole-program
theorem prover.

The previous detailed boundary is archived at
[maintained-pre-consolidation/runtime-first-boundary.md](archive/superseded-2026-08-05/maintained-pre-consolidation/runtime-first-boundary.md).
