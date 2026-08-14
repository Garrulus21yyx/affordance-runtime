# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Updated:** 2026-08-14
> **Start baseline:** `codex/migrate-world-interaction-capabilities@792d327112cd72f3cb5c9bd02c273c80f626f349`
> **Active target-cutover baseline:** `311e094`
> **Review evidence:** none; Implementation Status owns any reviewed closure SHA
> **Implementation truth:** [Implementation Status](implementation-status.md)

## Current decision

The transaction-platform queue remains stopped. P5-A/B1/C1 has established the
target contracts, minimum Unified World Interface, and real DOM plus
Visual-only and WoT local-simulation short loops without changing the default product path.

## Active target-default convergence queue

This is the durable progress owner for the current natural-language-to-action
cutover. Detailed diagnoses and deletion gates remain in the
[runtime-chain audit](reviews/2026-08-13-runtime-chain-convergence-audit.md) and
[consumer map](reviews/2026-08-13-target-cutover-consumer-map.md).

| Slice | Status | Files / verification |
|---|---|---|
| Model protocol convergence | `ACTION_PROTOCOL_DONE / OBJECTIVE_MODEL_PHASE_WITHDRAWN_FROM_TARGET` | `grounded_tools.v2` is the benchmark action protocol and supported decisions are explicit. Schema repair returns bounded field errors. The failed live objective diagnostic and owner audit show that the Runtime execution DSL must not be the target agent's planning language; target product/benchmark composition can no longer configure that second model phase. Dormant objective transport remains pending physical deletion. |
| Product target composition/client | done, pushed | `compose_target_runtime`, `TargetRuntimeClient`, typed continuations; source-tree composition gate |
| Product evaluation/DOM evidence | `REOPENED_SPECIALIZATION_AUDIT` | evaluator is product-owned, but arbitrary world-fact/screenshot change currently confirms any activation; replace correlation with explicit effect obligations or semantic verifier evidence |
| Explicit target CLI | done, pushed | `target-run`, strict intake, thread-bound browser session, real CLI E2E; legacy `run` unchanged |
| Reference cutover readiness | implemented, governance redesign pending | typed gate exists, but scenario names and exact pytest node IDs are hard-coded in product source; move readiness evidence to an external manifest |
| Authoritative HTTP JSON surface | done, pushed (`0b3ab68`; CI fix `64d15ae`) | read-only registered state adapter; authoritative+DOM same-capture fusion; real settings confirmation/persistence target E2E; settings readiness blocker removed; replacement target attestation and BrowserGym conformance are green |
| Pricing structural/output projection | `REOPENED_SPECIALIZATION_FOUND` | pushed `4a37e7c` passes its witnesses but is not generic evidence: `article/dl/dt/dd`, fixed `structured_document`, record count, and broad activation-diff acceptance specialize the reference page |
| Export materialization/integrity | paused by specialization audit | do not extend the same projection/evaluator pattern; resume only after generic artifact and semantic-agent boundaries replace the reopened pattern |
| Target-default held-out benchmark | pending | predeclare profile, seeds, and threshold; run from a clean pushed SHA |
| Root default switch | pending | only after reference readiness, held-out gate, and fresh-context topology review |
| Legacy deletion | pending | delete owner-by-owner only after all default consumers resolve through target and shared claims have target-owned tests |

World invariant for every pending slice:

```text
DOM / Visual / WoT / HTTP facts -> SurfaceObservation
                               -> UnifiedWorldEnvironment + WorldFusion
                               -> one WorldObservation and one internal ActionSpace
```

No evaluator, CLI, benchmark, or reference scenario may query an out-of-band
state oracle. Surface-private selectors, coordinates, URLs, credentials, and
executor routes never enter the model view.

Implementation guardrail: tests and benchmarks are evidence consumers, never
production branching inputs. No task-name, fixture, label, selector, fixed
output-name, one-item-count, or benchmark-profile specialization—hard or soft—is
admitted. Adapters execute generic surface capabilities; artifact identity and
materialization are explicit Runtime contracts; evaluators consume current
world evidence without re-projecting or querying a second world. Mature browser,
download, accessibility, visual, and transport primitives remain delegated to
Playwright/BrowserGym or the selected provider instead of being reimplemented.

This does not mean that all semantics should become mechanical Runtime code.
Runtime handles only closed, falsifiable contracts: type/authority checks,
currentness, legal transitions, private binding, dispatch receipts, evidence
lineage, and explicit postconditions. Open page interpretation, task
decomposition, semantic grounding, and judgments without a deterministic
postcondition belong to an agent/model or a replaceable existing-model-backed
grounder/verifier port. Roles may reuse the same provider. This project does
not train, fine-tune, or RL-post-train a model; Runtime validates typed model
outputs and remains the final control-state owner.

Current audit result: specialization is confirmed, so the affected slices are
not closed. The current target path contains (1) a witness-shaped pricing DOM
projection, (2) correlation-based activation acceptance, (3) singleton
`allowed_effect` inference, and (4) permissive one-operation compact-tool
normalization. Historical/benchmark paths additionally contain MiniWoB DOM
pattern recognizers, task-grammar scripted policies, and a nominal strict
planner that still enables compatibility rewrites. Conformance fixtures remain
useful only when explicitly reported as conformance; none may support a
generalization claim.

Remote run `31740915053` stopped before mypy and the target gates because the
repository-wide Ruff step found six import-only test issues. Those concrete
failures are corrected in the current slice; this is recorded as the cause of
that run, not as a new permanent per-push policy.

Remote run `31742943533` then passed Ruff, mypy, target boundaries and docs but
exposed a separate CI environment defect: the declared dev install omitted
NumPy, and `pytest | tee` masked collection failure until attestation. Commit
`64d15ae` declares the dependency and preserves pytest exit status with
`pipefail`; replacement runs `31743521672` and `31743521683` are green.

## Slice status

| Slice | Status | Current result / debt |
|---|---|---|
| R0 | complete | facts reconciled; smart-room atomic mismatch fix; lockfiles/npm ci; WoT metadata/security/event boundary |
| A1 | complete, non-default | strong TaskGoal and optional EvaluationSpec; legacy projection is one-way edge |
| A2 | complete, contracts only | optional replaceable TaskPlan/Milestone/LocalObjective; no model planner |
| A3 | complete, non-default | immutable WorldObservation, private bindings, policy view, runtime ActionSpace |
| A4 | complete, non-default | ActionIntent/request/result, evaluations, decisions, bounded turns |
| B1 | complete for DOM minimum | SurfaceAdapter, UnifiedWorldEnvironment, DOM adapter, binder |
| C1 | complete, non-default | real Chromium positive loop plus negative matrix |
| C1.1/B1.1 | complete | task-aware ActionSpace, source/world/fingerprint currentness, lineage, schema, budget, Finish/unknown closure |
| C1.2/B1.2 | complete | exact option/binding groups, Runtime-owned coarse effect/risk, single-probe currentness, reset/schema/attempt lineage |
| C2/B3 Visual | complete, non-default | screenshot-only proposer, private coordinates, one-probe pointer execution, real Chromium loop |
| C3/B4 WoT | complete, non-default | real local HTTP TD/read/invoke, private transport binding, deployment scope, one-probe execution |
| DOM/Visual/WoT matrix | proven for shared-state task | same TaskGoal/policy/evaluators; adapter-only variation, no fusion |
| P5-D | complete, non-default | semantic confirmation, fresh rebind, single-send consumption, explicit effect certainty |
| P5-D6.1 | complete, non-default | effective risk, destination, presentation, terminal immutability, policy reselection, evaluation lineage/evidence, task-evaluation control |
| P5-M0 | complete, non-default | model-safe policy projections, evidence-resolved evaluations, target output integrity |
| P5-M0.1 AgentContext architecture | `COMPLETE_NON_DEFAULT` | disposable unified context, bounded intent/world/history, current context identity, relevance, paging, source assurance, typed decisions |
| P5-M0.1.1 operational closure | `COMPLETE_NON_DEFAULT` | one-shot epochs, fresh acquisition identity, cursor paging, projection coherence, recurrent decision history |
| P5-M1 model-backed AgentPolicy | `CLOSED` | canonical structured decision contract and deterministic evaluators retained |
| P5-M1.1 ModelPort bridge/hardening | `CLOSED` | hostile JSON, deadline, typed failures/metadata, zero retry/fallback and local HTTP proof; later exact Mistral evidence is separately scoped |
| P5-M2 production evaluator composition | `CLOSED_FOR_DECLARED_MINIMUM` | Runtime-composed mechanical/semantic/user/hybrid criteria and output binding |
| P5-M2.1 evidence semantics closure | `CLOSED_FOR_DECLARED_PROFILES` | relevance-bound effects, strong no-effect scope, presented evidence only, dynamic readiness |
| P5-M3 new-loop benchmark harness | `CLOSED_FOR_INTERNAL_FIXED_MANIFEST` | internal core/safety/evaluation accepted; later external evidence is tracked under M4 |
| P5-M3.1 measurement/real adapters | `CLOSED_LOCALLY` | typed expectations, actual safety counters, real DOM/Visual/WoT suite, exact-head attestation command |
| P5-M3.2 admission package | `CLOSED_FOR_PINNED_MECHANICAL_PROFILE` | full-CI/live/adapter evidence and fixed manifest feed a protected manual workflow |
| P5-M3.3–M3.6 model compatibility | `CLOSED_FOR_CURRENT_SCOPE / NON_BLOCKING` | exact-profile diagnostics remain evidence, not Runtime repair authority |
| P5-M4 BrowserGym pinned profile | `CLOSED_FOR_DECLARED_PROFILE` | historical reset/step profile plus current typed lifecycle, private binding, execution, mechanical verification and owner-thread active capture |
| P5-M4.2 local progress guard | `CLOSED_FOR_FILL_SELECT` | exact local repeated-action containment; not task planning/auditing |
| P5-M4.3 historical MiniWoB-60 | `VALID_NEGATIVE_EVIDENCE` | clean `b3b64a2`, 6/60; immutable standalone run |
| P5-M4.4 attribution | `CLOSED_FOR_CURRENT_SCOPE` | future typed attribution and inventory closure |
| post-M4.4 separately authorized rerun-v3 | `VALID_NEGATIVE_EVIDENCE` | separate clean `83dc4fa` run at 4/60 |
| P5-M4.5-A acquisition lifecycle | `COMPLETE_NON_DEFAULT` | typed reset/capture/post-action acquisition, origin/fallback/counting closure, Runtime admission and real BrowserGym active capture |
| P5-M4.5-B control/failure contract | `INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED` | implementation candidate under architecture-first reducer, boundary, failure-owner and property review; no reviewed closure SHA |
| P5-M4.5-C same-profile diagnostic | `COMPLETE_DIAGNOSTIC / EVIDENCE_VALID_AT_4924CE6 / FORMAL_EXIT_NOT_ATTESTED / PERFORMANCE_NOT_CLAIMED / GENERALIZATION_NOT_CLAIMED` | immutable 60/60, 8/60 run; diagnostic execution does not close B or claim performance/generalization |
| P5-M4.6 evidence-directed remediation | `TASK_STATE_CONTEXT_IMPLEMENTED / PUSHED_EB19C0D / LIVE_NOT_RUN / CRITIC_NOT_ADMITTED / GENERALIZATION_OPEN` | `eb19c0d` replaces the failed single-response atomic-memory topology with two model calls inside the same `AgentPolicy`: a task-state updater reconciles the previous advisory belief with the fresh Unified World and explicit previous-decision transition, then the actor receives that updated state and clean Runtime-issued tools. Memory is no longer an action parameter or decision capability. One binder owns the model context and a packaged YAML prompt bundle; the existing ActionSpace/admission/private-binding/execution/evaluation chain remains the sole Runtime path and only one environment action can occur. The historical default-4.1V run at `d524221` remains a valid 1/5 baseline for the superseded topology; no live result or task-quality claim exists for `eb19c0d`. See the [task-state context evidence](evidence/2026-08-14-task-state-context-eb19c0d.md), [atomic-memory diagnostic](evidence/2026-08-14-atomic-agent-memory-8f33d8a.md), [valid historical run](evidence/runs/p5-m4-6-e-atomic-memory-five-witness-d524221/report.json) and [shared-cause review](reviews/2026-08-13-five-witness-common-cause.md). |
| P5-M4.7 supported-subset multi-seed | `NOT_STARTED / BLOCKED_BY_M4_6_GATES` | thresholds and seed set must be frozen before execution |
| P5-E | `REOPENED / TARGET_COMPOSITION_DEWIRED / DORMANT_BRANCH_PENDING_DELETE` | Owner audit found that model-authored LocalObjective gives a large Runtime DSL execution authority and duplicates planning. Target product/benchmark composition no longer exposes the proposer/requirement. Existing action AgentPolicy remains the only target reasoning phase; dormant AgentLoop/model-objective code is the next deletion slice. |
| ActionBatch integration | `NOT_STARTED` | isolated legacy-contract helper remains only |
| default cutover/deletion | `IN_PROGRESS / TARGET ENTRY NON_DEFAULT` | explicit target CLI/client and readiness gate exist; reference capability remediation, held-out benchmark, root switch, and physical deletion remain open |

## Next admitted slice

The two-call `task-state update -> memory-conditioned action` arm is implemented
and pushed at `eb19c0d`. The next admitted work is validation, not another
architecture layer: wait for exact-head remote CI, then run one frozen
default-4.1V five-witness diagnostic with the same Unified World, provider and
single Runtime execution chain. The run must record both cognition calls,
task-state schema repair separately from action repair, the complete task state,
and the selected action. If the semantic failures remain, stop after causal
trace analysis rather than adding a critic, task rule, Runtime semantic guard,
LocalObjective planner, or repeated favorable-score sampling.

M4.5-A is complete on the non-default target path. It replaced the generic
observe/cache handshake with typed logical reset, independent capture and
execute-returned post acquisition; closed Runtime admission against
environment-owned capabilities; and added BrowserGym owner-thread active
capture without reusing old verifier evidence.

The A.1 closure makes the public package facades lazy without changing their
API, validates `INDEPENDENT_CAPTURE` origin, preserves the final fallback
status/reason with post-action failure semantics, and counts acquisitions that
already occurred before ActionResult lineage rejection. Real pinned active
capture is attested separately from the nine-test normal-action gate.

M4.5-B is an integrated non-default implementation candidate under reopened
convergence review. No commit is current reviewed closure evidence. The work
must converge the control reducer, strict external boundaries, terminal failure
authority, benchmark fact/classification owners, and state-machine properties
before an independent review can attest it.

A separately authorized M4.5-C diagnostic has now completed from clean
`4924ce61748d8efdec4fcc6de494acf8a9f224cc`: 60/60 cases, 8/60 success,
valid evidence and no generalization claim. The archive commit `5f8d6ac` is
docs-only and is not the run SHA or a B closure SHA. M4.6-A canonical BrowserGym
AX semantics/currentness, M4.6-B verifier/task-terminal truth and M4.6-C
semantic inventory truth are complete for their declared non-default scopes;
M4.6-D bounded control feedback remains implemented-not-verified. M4.6-E is
`IN_PROGRESS / DOM_FIRST_VISION_CONVERGENCE_FULL_VERIFIED / PROVIDER_SPLIT_FULL_VERIFIED / LIVE_GATE_FAILED_DIAGNOSTIC`: real screenshot transport, first
semantic breadth, stable identity, retained inventory, paging and
negative-claim traversal safety exist. The current-SHA 15-pair A/B archive is
valid but its comparison is provider-contaminated, so no screenshot gain is
claimed. P5-E is `IN_PROGRESS / UNIFIED_LOCAL_OBJECTIVE_OWNER_IMPLEMENTED /
LIVE_REVALIDATION_PENDING`: typed sequence/set/aggregate objectives share one
post-observation lifecycle and the displaced frontier/hypothesis path is deleted.

The current Phase-4 increment retains point grounders only as explicit
benchmark/legacy-compatibility arms; the BrowserGym target loop neither
advertises nor calls them. OmniParser may be enabled explicitly for open-world
region proposal; its unmatched output remains observation-only. Ambiguous DOM
candidates use a SoM/E-ref chooser that cannot represent a coordinate. Marks
use stable visual reading order and place their labels outside tiny controls.
When an operation has exactly one legal target, the ephemeral tool binding
carries that E-ref and does not require the model to echo a redundant target
argument.
Postcondition diagnosis remains typed in the gate but
is not fed from request prose or guessed failure state; it awaits an evaluator-
owned unresolved-postcondition fact.

The completed targeted M4.6-E slice is `grounded_tools.v2`: reuse the existing SoM
renderer in the current BrowserGym/tool path, give screenshot marks, the public
entity index, tool parameters and previous results one shared call-local `E*`
namespace, construct an allowlist `ToolPolicyView`, group schema-equivalent
verb tools, and disable the requirement proposer in the short-loop profile.
The stopped clean-`7c14190` run completed only 8/60 mixed-cohort cases and is
an incomplete diagnostic with no performance claim; it must not be resumed
across an implementation change. Separated capability-covered benchmark
validation remains open. B assurance review, default cutover and old-core
deletion remain independently open.

The `b9ad39a` gate is scoped to one BrowserGym screenshot+AX source. The next
admitted slice closes the previously deferred Unified seam: an
`ObservationOrchestrator` selects required and augment sources from typed offers
and budgets; `WorldFusion` preserves provenance while producing canonical
entities, facts and explicit conflicts; and `RouteSelector` chooses one exact
current equivalent binding. Bounded reroute is permitted only after typed
`NOT_SENT`, fresh world acquisition/fusion and revalidation, with at most one
effectful dispatch. `SENT` and `SENT_UNKNOWN` never fall through to another
route. Grounded-tools remains a route-free consumer of the fused public view;
the existing VisualRegionBinding enters only through this seam rather than a
BrowserGym-specific ActionSpace bypass.

The architecture-first causal model, owner map, bounded algebra and evidence
gates are recorded in the [M4.5-B convergence review](reviews/2026-08-11-p5-m45b-control-failure-convergence.md).
The diagnostic facts and claim limits are frozen in the
[M4.5-C attribution](reviews/2026-08-11-p5-m4-5-miniwob-60-diagnostic.md);
implementation and later run identities are tracked in the
[M4.6 remediation record](reviews/2026-08-11-p5-m4-6-evidence-directed-short-loop-remediation.md).

## Frozen work

- new RuntimeDelta/RuntimeCommitter/StateKernel capability;
- ledger, checkpoint/resume, event sourcing, generic recovery transaction;
- global approval/capability/token registry or worker fencing;
- ActionBatch integration or a new long-horizon planner before
  the M4.6 targeted/full rerun and M4.7 supported-subset multi-seed gates;
- default cutover or deletion before the positive cross-surface gates.
- any AgentContext ownership of Runtime state, private route projection, or
  LocalObjective-based legality/risk change.
- durable transition ledger, event sourcing, state replay/reconstruction,
  generic recovery engine, or combining ProgressController with planning.

## Verification policy

Every target slice runs focused pytest, Ruff, mypy on affected modules,
`git diff --check`, then the full suite. Evidence is exact-revision/profile
scoped; benchmark oracles never drive product behavior.

## P5-M3.3 closure

Exact model input/schema complexity is measured and installed Ollama failures
are stage-attributed. A canonical 1,024-character completion-summary budget
closes the observed full-union grammar-initialization blocker: exact Qwen and
Llama diagnostic reruns each pass Level 2, then fail current-page destination
admission at Levels 3/4 under format-only. D0–D4 destination diagnostics isolate the
next boundary: Qwen fails only when the complete context makes `target_id`
salient, while Llama first fails on the real nested action-page and also copies
`target_id` in the complete context. No destination auto-repair is admitted.
The post-repair compact-contract gate then passed L0–L4 at 20/20 for each exact
profile on clean HEAD, producing accepted per-profile action-selection
attestations. Mistral also passed one fresh Level-4 no-regression call for each
grounding. The production default stays format-only; adopting compact grounding
is a separate provider-neutral product decision.
M3.3 did not itself authorize external execution or a default cutover; later M4
adapter/run evidence is independent and does not widen this model-profile claim.

## P5-M3.4 closure

Compact grounding is production-supported as an explicit configuration, with
`compact-contract.v1` and actual canonical schema digest in secret-free model
metadata and exact-profile identity. Format-only remains the current default
and explicit rollback configuration. The pure cutover checker is currently
blocked by incomplete seven-decision live-local behavior, failed compact
strong-provider no-regression and unavailable exact-head CI. That slice admitted
no default flip; its model-profile blockers are non-blocking for the current
M4.5 queue.

## P5-M3.5 closure

The v1 guide is frozen and its evidence is scoped to action selection. The new
decision-neutral v2 profile, complete Runtime replay matrix, recurrent CLI and
secret-free attestation are implemented. Scripted candidate closure is 75/75.
Exact Qwen and Llama GPU candidates failed their 5/5 recurrent gates, so their
20/20 support gates were not run. This slice did not tune prompts,
switch defaults, run external benchmarks, or add repair/retry/fallback.

## P5-M3.6 closure

The two-stage decomposition diagnostic is implemented entirely under
`benchmarks/model_conformance/two_stage`. It measures routing, fixed-route
payload filling, end-to-end Runtime outcomes, and the original single-stage
compact-v2 baseline with atomic per-stage progress. Qwen and Llama both failed
candidate admission because routing remained incomplete despite 35/35 payload
isolation. No support gate, remote Mistral run, production adoption, external
benchmark, or default change is admitted. A future adoption review would still
need 20/20 exact evidence plus call-budget, latency, token, rate-limit,
strong-provider, rollback, and exact-head CI evidence.

## P5-M4 closure

The current mainline owner is the existing target loop. The pinned BrowserGym
adapter now owns lifecycle/projection/private binding/execution/mechanical
verification under `benchmarks/external_smoke`, while AgentLoop, parser,
Runtime admission, target core, and default Coordinator remain unchanged. Real
fixed-task adapter conformance is closed at 3/3. Run evidence is represented by
exact revision/profile artifacts rather than a durable status
literal in this plan. The historical fixed smoke failed at `cd49b8e`; later
MiniWoB-60 breadth records belong to M4.3/M4.4 and do not backfill it.

## P5-M4.2 local verified-progress closure

The local target-loop correction is complete: fresh structural fill/select
postconditions produce current action evidence; already-satisfied selections
are zero-call; an unchanged exact repeat terminates with a typed no-progress
code; bounded progress enters the next AgentContext; and watchdog timeout
retains partial counts/evaluation status. The fixed manifest now uses 10 turns
per simple case so `(max_turns - 1) * 7.5s` remains below its 120s watchdog
after a fixed 5s scheduling margin. No live provider, protected workflow, or
external smoke belongs to this slice. The historical `cd49b8e` timeout remains
the formal result until a separately authorized exact-head run occurs.

## P5-M4.4 short-loop breadth closure

The historical MiniWoB-60 seed-7 campaign remains a valid negative breadth
result at 6/60. M4.4 closed future typed failure metadata, froze full-registry
capability inventory v2, and ran deterministic local no-model diagnostics. Its
then-current decision to block a rerun remains revision-scoped history.

A later separately authorized rerun-v3 completed from clean `83dc4fa` with
valid 4/60 evidence. It does not backfill, replace, merge with, or establish a
trend against 6/60. It narrows the next generic gaps: 7 observation lifecycle
failures, 9 remaining unclassified typed failures and 11 Runtime rejections.
Provider/policy competence remains a measured product variable, not something
M4.5 may repair with retry, fallback or model-specific Runtime behavior.

## P5-M4.5-A observation acquisition lifecycle — complete

Delivered only the target world lifecycle boundary:

1. `reset(task) -> ObservationAcquisition` supplies initial world state.
2. `capture(request) -> ObservationAcquisition` reports `ACQUIRED`, typed
   `CAPABILITY_UNAVAILABLE`, or typed `FAILED`.
3. `execute(request) -> ExecutionOutcome` carries `ActionResult` plus a typed
   post-action acquisition.
4. Operational `independent_capture` / `post_action_observation` capabilities
   remain distinct from evidence modality/assurance.
5. Normal action evaluation consumes execute-returned observation directly;
   RequestObservation, Wait, stale/currentness and confirmation refresh use
   independent capture only when admitted.

Exit gates: successful reset always yields initial acquisition; BrowserGym
recovery paths no longer consume an empty reset/step cache; capability absence
never appears as a bare RuntimeError; acquisition failure cannot alter dispatch
truth; `SENT_UNKNOWN` stays single-send/no-replay; existing DOM/Visual/WoT and
BrowserGym action-path conformance stays green. An independent capture may use
the pinned environment's read-only current-observation facility, but it cannot
copy the previous step's verifier outcome under a new observation identity;
current verifier evidence must be reacquired or explicitly unavailable.

## P5-M4.5-B control/failure contract — reopened convergence review

The current code is only an integrated non-default implementation candidate.
`AgentLoopState` remains the current-state authority and a bounded pure reducer,
canonical Runtime failure, orthogonal benchmark facts and one classification
owner are implemented. Their repository-wide exceptional-path and loop-level
property assurance is not independently verified. Existing edge and held-out
examples are witnesses, not closure proof.

The exit gate requires strict typed external adapters, a closed supported
state/command/outcome algebra, deterministic rejection of unsupported input,
an operation/disposition/count matrix for physical attempts, monotonic committed
facts, epoch-coherent evaluations, orthogonal Runtime/watchdog/cleanup/harness
facts, one classification precedence owner, and a real Hypothesis reference
state machine. No reviewed implementation SHA exists. The former B gate was
not satisfied before M4.5-C, but the separately authorized diagnostic execution
is now an immutable fact; it does not change B assurance status or provide a B
closure SHA.

## P5-M4.5-C same-profile diagnostic — complete diagnostic evidence

The immutable run ID is `miniwob-60:e9551acfcd31466e91481ee5923fc9af` at
executed Git SHA `4924ce61748d8efdec4fcc6de494acf8a9f224cc`. It completed
60/60 with 8/60 success, 290 provider attempts and 555,164 tokens. Formal exit,
performance and generalization were not predeclared or attested.

Run patterns joined with exact `4924ce6` source review support four scheduled
remediation slices: AX/DOM currentness ownership, verifier task-terminal
information loss, semantic inventory/action projection coupling, and bounded
control feedback/repair/no-gain. Its direct repair witness is case 37: one
policy call, zero execution/step, three current options and terminal
`invalid_action_parameters` despite a canonical rejection fact. The same run
has seven adjacent final current-page action/destination rejections and two
invalid completion claims, but some cases dispatched earlier and the completion
claims remain outside D. Page and observation no-gain shapes could continue
without an information-gain bound. The immutable payload alone does not prove
that a repair turn would succeed,
that all 14 verifier-unknown cases were negative terminal outcomes, that broader
roles guarantee success, or that a later repair improves the score.

## P5-M4.6 evidence-directed remediation — in progress

Implement one independently measurable slice at a time:

1. M4.6-A canonical AX semantics/currentness, including owner-scoped select
   options and executable availability — `COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE`;
2. M4.6-B four-state verifier plus task-terminal fact orthogonal to
   `RuntimeFailure` — `COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE`;
3. M4.6-C semantic inventory separate from existing projection coverage and
   ActionSpace authority — `COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE`;
4. M4.6-D typed admission/no-gain source facts → canonical model-facing
   feedback, a frozen two-distinct-issue same-scope zero-dispatch repair/no-gain
   budget with immediate exact-repeat containment,
   explicit projection of existing validated no-effect strategy feedback, plus
   exact repeated no-gain containment for action pages and policy observations;
   AgentPolicy chooses the correction, Runtime never parses exception text or
   edits parameters, Runtime refresh is exempt, and sent/uncertain requests are
   never replayed — `REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED`;
5. M4.6-E stable opaque target identity followed by staged observable/executable
   semantic breadth and a referentially closed grounded-tool policy surface —
   `TASK_STATE_CONTEXT_IMPLEMENTED / PUSHED_EB19C0D / LIVE_NOT_RUN`. Existing SoM utilities are reused as a
   deterministic current-screenshot projection, not reimplemented and not made
   an execution authority.

The immediate execution order inside M4.6-E is now frozen:

```text
archive stopped 7c14190 8/60 as INCOMPLETE_DIAGNOSTIC
-> allowlist ToolPolicyView + shared E-ref GroundingIndex
-> existing SoM overlay bridged into the current BrowserGym path
-> schema-equivalent verb tools + private current-epoch resolver
-> short-loop proposer disabled; one normal policy call per GUI turn
-> login-user/duplicate-control targeted gate
-> Runtime source selection + provenance-preserving WorldFusion
-> one-route selection + bounded zero-dispatch reroute
-> route-free GroundingProjection consumes exact selected fused media
-> existing VisualRegionBinding bridged through the Unified seam
-> grid-coordinate/click-pie/click-shades/visual-addition visual gate
-> scroll + focus-aware keypress
-> table/list relations + dynamic semantic delta
-> observation-resolvable sequence/set/aggregate objectives
-> classify the 14 readiness-unassessed cases
-> targeted cohort after every slice
-> frozen MiniWoB-60 exact-profile rerun
-> post-60 drag/slider/hover/multi-select/general-canvas breadth
```

This historical staging list is no longer an active execution queue. The
atomic-memory diagnostic reached valid 1/5 evidence; `eb19c0d` implements the
smallest evidence-admitted cognition change. No later arrow is authorized until
its one frozen live diagnostic is analyzed.

SoM marks and AX aliases remain non-authoritative.
`ActionSpace` is still the only legal-action owner, and every accepted tool
command still passes the existing admission, binding/currentness,
risk/confirmation, execution and evaluation path. Full owner boundaries,
non-goals and falsifiable properties are defined in the active
[LocalObjective de-specialization plan](superpowers/plans/2026-08-13-m4-6-e-set-objective-de-specialization-plan.md).

The capability-covered cohort is a clean regression denominator, not a ceiling
on product scope. The frozen inventory currently reports 15 declared-supported,
31 declared-unsupported and 14 readiness-unassessed cases. Proven shared gaps
are scheduled for implementation and graduate into newly-covered cohorts; they
are not excluded indefinitely to preserve a favorable denominator. Runtime
continues to own action authority and verified state, while compare, sort,
arithmetic, text transformation and next-step selection remain general policy
competence rather than MiniWoB-specific Runtime branches.

All task names in this queue are benchmark witnesses, not production routing
keys. The intended capabilities are real-environment primitives: shared visual
grounding/binding, viewport navigation, focused keyboard input, relational and
dynamic observation, verified working state and typed value transfer. A
BrowserGym-specific geometry/transport adapter is allowed; Runtime, model
projection, tool construction and admission must remain invariant under a
benchmark case/task-ID rename and must not consume cohort/readiness metadata or
benchmark oracles.

Implementation is explicitly reuse/outsource-first. BrowserGym/Playwright own
browser acquisition and input mechanics; the browser/OS owns accessibility
semantics; existing SoM and VisualSurface foundations supply annotation,
geometry-bound currentness and pointer execution; provider-native tool calling
owns transport where supported; the selected model owns general reasoning; the
official environment evaluator owns source task outcome; OpenTelemetry/
Langfuse or JSON artifacts own downstream storage and visualization. Runtime
retains only the authority kernel: current epoch, source-selection policy,
canonical fusion/conflict truth, ActionSpace, route/ref/binding resolution,
admission, risk/confirmation, dispatch truth/no-replay, evidence validation,
verified working state and terminal disposition.

`grounded_tools.v2` must replace, not extend, the diagnosed v1 stack. The active
short-loop path removes full-AgentContext blacklist scrubbing, per-turn
hypothesis calls, anonymous one-option-per-tool catalogs and multiple repair
owners. It becomes one allowlist policy view, one current grounding/tool
catalog, one provider transport/validation boundary and one adapter into the
existing Runtime decision path. V1 remains frozen only for comparison/rollback
during the targeted gate and is removed from the active profile after v2
passes. Complexity is measured by call count, token/latency evidence, owner
coupling and duplicate truth, never by file LOC alone.

Each slice gets property/state-machine evidence and a new implementation SHA.
Targeted reruns receive new run IDs and immutable directories; no result is
backfilled into the `4924ce6` archive. LOC is only a review signal. Owner
boundaries and forbidden scope are normative in the M4.6 remediation record.

## Gates after M4.6

After the M4.6 targeted cohorts pass, run the same frozen MiniWoB-60 seed-7
profile and preserve it as a new independent exact-run record. Required gates
are zero observation contract
exceptions, complete typed classification, clean privacy/safety, zero retry/
fallback and explicitly sufficient provider capacity. If that short-loop run is
free of lifecycle/accounting hard-gate failures, freeze a supported-subset
immutable manifest, exact seed set, numeric provider-availability/capacity
floor, success floor and maximum seed variance before running the multi-seed
gate. No threshold may be chosen after seeing results.
The target agent-semantic slice is accepted only when these properties hold:

```text
natural-language task + current Unified World + bounded interaction history
→ one existing agent chooses one current public tool
→ Runtime resolves that tool to current ActionSpace authority and private binding
→ fresh observation re-resolution and evaluator-owned completion
```

Sequence/set/aggregate objective reducers are not evidence that Runtime can
understand every task. They are temporarily retained only as the closed
execution algebra of the still-existing legacy `TaskPlan` runtime. Do not add a
target caller, benchmark flag, task classifier or second planner for them.
