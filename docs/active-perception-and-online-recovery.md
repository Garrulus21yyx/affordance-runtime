# Active Perception and Online Recovery Architecture

Status: **normative target design for M8.6**

This document defines how Affordance Runtime absorbs the useful
active-perception and online-recovery ideas from C009 without importing its
ContinuousInteractionManager, mutable CognitiveMap, smart-room policies, or
primitive-action authority chain.

It is subordinate to the Runtime-First Architecture Boundary and Benchmark
Governance and Anti-Specialization Boundary. Benchmarks may reveal gaps; they do
not own this design.

## 1. Objective

The Runtime must answer two separate control questions:

1. Active perception: what additional evidence should be acquired now to make a
   safe and useful decision?
2. Online recovery: after a phase failed, what bounded change can make the next
   attempt meaningfully different?

~~~text
TaskSpec / active Subgoal
  -> derive PerceptionRequirements
  -> base coherent observation
  -> sourced assertions and unified candidates
  -> arbitrate evidence
       -> accepted snapshot
       or ActivePerceptionController
            -> targeted ProbeCommand
            -> new coherent epoch
            -> re-arbitrate
       or safe inconclusive
  -> task/action planning
  -> semantic PlannerProposal
  -> PlannerProposalValidator
  -> candidate binding and ActionContract
  -> policy / preflight / execution
  -> post-state inspection and verification
       -> continue / complete
       or RecoveryCoordinator
            -> typed RecoveryCommand
            -> changed evidence, assumption, plan, route,
               verifier, provider/context, authority, or user input
            -> re-enter the owning phase
  -> canonical trace
  -> offline regression-gated learning
~~~

## 2. Decisions and Boundaries

### 2.1 One state writer

RunCoordinator remains the only writer of StateKernel and the only component
that advances the top-level phase.

ActivePerceptionController and RecoveryCoordinator are request-scoped decision
collaborators. They return immutable plans, commands, assessments, and receipts.
They never own a second run state.

### 2.2 Perception is a cost-bearing action

Every probe consumes observation, latency, model-call, and cost budgets.

A probe is read-only. Scrolling, expanding, or opening an inspection surface
must use a normal ActionContract when it can change environment state. An
observer cannot hide an effectful action.

### 2.3 Recovery is not retry

Another attempt is recovery only when it changes at least one of:

- observation source, scope, freshness, or coherence;
- task interpretation or ambiguity;
- task plan or active subgoal;
- planner context or provider;
- semantic target or grounding candidate;
- execution route;
- verifier source or strength;
- accepted skill usage;
- authority or user-provided information.

Repeating the same planner against the same semantic state is a loop even when a
raw target id or backend string changes.

### 2.4 Facts before effects

When an action may have occurred, the first recovery command is post-state
inspection. The Runtime cannot reroute or repeat the effect until it determines
occurred, not occurred, or still uncertain.

### 2.5 Rule-first arbitration

Source confidence remains parser-local until held-out calibration proves
cross-source comparability.

The arbiter first uses schema validity, freshness, property-specific authority,
independent agreement, explicit conflict, risk, and materiality. Probabilistic
fusion remains deferred until labelled evidence proves a safety-preserving gain.

### 2.6 No second agent runtime

Optional LM or VLM ports may classify, ground, or propose within bounded
contracts. They do not create another execution loop. Every proposal still
passes validators, ContractBuilder, policy, preflight, post-observation,
verification, and trace.

## 3. Current Foundation

| Capability | Current implementation |
| --- | --- |
| Task-derived evidence needs | PerceptionRequirements |
| Coherent observation | PerceptionSession.capture |
| Targeted observation port | PerceptionSession.capture_targeted |
| Multi-source claims | SourceAssertion |
| Rule-first arbitration | SourceAssertionArbiter |
| Active-perception request | ActivePerceptionRequest |
| Conflict-preserving targets | SourceAssertionOrchestrator |
| Route escalation | PerceptionEscalation |
| Lower-half recovery assessment | RecoveryHandler |
| Repeated/no-progress/A-B detection | RecoveryCascadeDetector |
| Inspect-before-repeat | BoundedRecoveryPolicy |
| Recovery replay and artifacts | recovery_evolution and accepted profiles |

Missing integration:

- evidence-gap and probe contracts above capture_targeted;
- a controller selecting probes by authority, information value, risk, and cost;
- a FailureEnvelope valid before or after ActionContract construction;
- a RecoveryCoordinator spanning all Runtime phases;
- typed execution and receipts for recovery commands;
- a changed-strategy guard;
- consistent accepted-profile loading;
- an end-to-end trace across perception and recovery.

## 4. Ownership

| Component | Returns | Must not do |
| --- | --- | --- |
| RunCoordinator | applied transition | delegate state ownership |
| PerceptionSession | coherent BrowserSnapshot | decide task success |
| AssertionArbiter | accepted/conflict/reobserve/inconclusive | invent evidence |
| ActivePerceptionController | ProbePlan | execute or mutate state |
| TaskPlanner | TaskPlan proposal | grant authority |
| StepPlanner | semantic PlannerProposal | emit selectors or execute |
| PlannerProposalValidator | validation result | hide repairs or effects |
| ContractBuilder | ActionContract | reinterpret user intent |
| RecoveryCoordinator | RecoveryPlan | execute or mutate state |
| RecoveryExecutor | RecoveryReceipt | choose strategy |
| Verifier | VerificationReport | treat dispatch as success |
| Evolution pipeline | quarantined/accepted artifact | mutate online policy immediately |

## 5. Shared Contracts

### 5.1 EvidenceGap

~~~text
EvidenceGap
  gap_id, run_id
  task_revision, plan_version, active_subgoal_id
  entity_key, property_key
  gap_kind, required_evidence_kind
  current_assertion_refs, conflicting_assertion_refs
  reason, materiality, risk_relevance, blocks
  source_event_ids
~~~

Gap kinds:

- MISSING_REQUIRED_EVIDENCE;
- STALE_EVIDENCE;
- SOURCE_CONFLICT;
- AMBIGUOUS_ENTITY;
- AMBIGUOUS_TARGET;
- VISUAL_PROPERTY_UNKNOWN;
- SPATIAL_RELATION_UNKNOWN;
- DEVICE_STATE_UNKNOWN;
- GROUNDING_DISPROVED;
- VERIFIER_INCONCLUSIVE;
- POST_ACTION_EFFECT_UNKNOWN.

EvidenceGap contains no benchmark identity, selector, coordinate, backend
action, or official reward.

### 5.2 ProbeCapability

~~~text
ProbeCapability
  source, probe_kind
  supported_evidence_kinds, supported_properties
  target_scope
  expected_latency_ms, estimated_cost, model_calls
  freshness_semantics, coherence_semantics, confidence_semantics
  side_effect_class: READ_ONLY
  availability
~~~

Typical probes:

| Source | Probe |
| --- | --- |
| DOM | refresh document or target subtree |
| Accessibility | recapture role/name/state tree |
| SVG | extract current geometry and attributes |
| Screenshot | recapture viewport or bounded region |
| OCR / SoM | read or mark a bounded image region |
| Pure visual | ground one semantic target or relation |
| WoT | read a property or discover current Thing Description |
| API | query an independent state endpoint |
| Runtime hook | inspect navigation, modal, download, or loading state |

### 5.3 ProbeCommand and ProbePlan

~~~text
ProbeCommand
  command_id, gap_ids
  based_on_state_version, based_on_snapshot_id
  source, probe_kind
  entity/property/region scope
  expected_information
  freshness and coherence requirements
  timeout, artifact, model-call, and cost budgets
  reason

ProbePlan
  plan_id, based_on_state_version, gap_ids
  ordered commands
  stop_conditions
  total_budget
  fallback
~~~

The first version is serial and shallow. Read-only probes may run concurrently
only when the adapter proves a coherent observation epoch.

### 5.4 ProbeReceipt

~~~text
ProbeReceipt
  command_id
  started_at, completed_at
  observation_epoch_id, source
  success
  artifact_refs, assertion_refs
  error_code, cost, latency_ms
~~~

Transport success does not resolve a gap. The arbiter must evaluate the new
assertions.

### 5.5 FailureEnvelope

FailureEnvelope is valid even when no ActionContract exists.

~~~text
FailureEnvelope
  failure_id, run_id
  task_revision, plan_version, active_subgoal_id
  phase, failure_class
  semantic_family_key, exact_debug_key
  state_version, observation_epoch_id, snapshot_id
  proposal_id, contract_id
  expected_effect, error_code, message
  evidence_refs, receipt_ref, verification_ref
  effect_status
  attempted_strategy_ids, rejected_assumptions
  remaining_budgets, recoverable
~~~

Effect status:

- NOT_DISPATCHED;
- MAY_HAVE_OCCURRED;
- CONFIRMED_OCCURRED;
- CONFIRMED_NOT_OCCURRED;
- IRREVERSIBLE_OR_UNKNOWN.

### 5.6 RecoveryCommand, Delta, and Receipt

RecoveryCommand is a tagged union:

- REOBSERVE;
- ACTIVE_PERCEPTION;
- COMPACT_CONTEXT;
- SWITCH_PROVIDER;
- REPAIR_MODEL_SCHEMA;
- CLARIFY_INTENT;
- REPLAN_TASK;
- REPLAN_STEP;
- REGROUND;
- REROUTE;
- INSPECT_POST_STATE;
- RETRY_IDEMPOTENT;
- COMPENSATE;
- REQUEST_APPROVAL;
- ASK_USER;
- ABORT.

~~~text
RecoveryCommand
  command_id, failure_id
  based_on_state_version, strategy_id
  expected_change, preconditions
  budget_cost, timeout, risk, reentry_phase

RecoveryDelta
  previous_attempt_fingerprint
  next_attempt_fingerprint
  changed_dimensions
  new_evidence_refs, retired_assumptions
  new_plan_or_route_ref
  explanation

RecoveryReceipt
  command_id, success
  state_before, state_after
  changed_dimensions
  artifact, observation, plan, route, verification refs
  error_code, latency, cost
~~~

An empty RecoveryDelta is rejected. RecoveryReceipt cannot complete a task or
subgoal; criteria-bound verification remains authoritative.

## 6. Active Perception Controller

### 6.1 Inputs

ActivePerceptionContext contains:

- TaskSpec revision and active SubgoalSpec;
- PerceptionRequirements;
- current observation epoch and unified affordances;
- assertions, arbitration decisions, and conflicts;
- ProbeCapabilities and recent probe history;
- rejected grounding candidates;
- expected effects and verifier gaps;
- risk, capabilities, and remaining budgets.

### 6.2 Triggers

Normal path:

- visual, spatial, device, or independent evidence is required;
- base sources lack mandatory evidence;
- current candidates are ambiguous;
- material sources disagree;
- a high-risk action lacks strong preflight evidence.

Recovery path:

- grounding is stale, missing, or disproved;
- a route failed before dispatch;
- a verifier is inconclusive;
- effect status is uncertain;
- a modal, overlay, or navigation transition is suspected;
- planner context lacks current affordances.

### 6.3 Hard gates and selection

A probe must be read-only, relevant, available, traceable, within budgets, and
capable of producing a coherent new epoch. It cannot repeat an equivalent failed
probe without changed scope or freshness.

Selection order:

1. remove stale, unsafe, unavailable, and irrelevant probes;
2. prefer the property-authoritative source;
3. prefer an independent source for conflict;
4. choose the lowest-cost probe that can close a blocking gap;
5. prefer bounded region/target capture;
6. require stronger evidence as action risk rises;
7. stop when blocking gaps resolve or budgets expire.

Numeric confidence is not compared across sources without calibration.

### 6.4 Coherent epoch

Each ProbePlan creates a new observation epoch rather than mutating the old
snapshot. Older assertions may be reused only if freshness, entity identity,
target fingerprint, navigation state, and provenance permit it.

Materially asynchronous DOM, screenshot, accessibility, SVG, and WoT evidence
cannot be silently merged.

### 6.5 Resolution loop

~~~text
extract EvidenceGaps
  -> enumerate ProbeCapabilities
  -> select ProbePlan
  -> execute ProbeCommand
  -> ProbeReceipt
  -> new coherent observation
  -> SourceAssertions
  -> arbitrate
       -> accepted: continue
       -> useful gap and budget: probe again
       -> material unresolved conflict: safe inconclusive
       -> no useful probe: ask / replan / abort
~~~

Active-perception depth is separate from action-recovery depth.

### 6.6 Required examples

- ordinary form: DOM/A11y resolve; no visual model call;
- SVG/canvas: SVG geometry primary, screenshot/SoM/VLM fallback;
- DOM versus visual overlay: targeted refresh, block if unresolved;
- dashboard versus WoT state: authoritative device repoll;
- uncertain download: inspect event, artifact, and audit state before repeat.

## 7. Online Recovery Coordinator

### 7.1 Inputs

RecoveryCoordinator receives FailureEnvelope, bounded incident history,
RunState summary, task/subgoal obligations, accepted/conflicting evidence,
available recovery capabilities, current plan/proposal/route/contract/receipt/
verification references, accepted recovery profile, budgets, and safety policy.

### 7.2 Safety-first decision order

1. determine whether an external effect may have occurred;
2. stop on authority violation or unsafe duplicate-effect risk;
3. inspect environment when effect state is uncertain;
4. acquire missing facts through reobserve or active perception;
5. repair intent, context, task plan, or step plan;
6. reground or reroute from a new current candidate;
7. retry only after confirmed non-dispatch or missing effect and idempotency;
8. compensate only through an authorized, verified contract;
9. request approval or user information when needed;
10. abort when no safe changed strategy remains.

### 7.3 Phase strategy matrix

| Phase | Primary strategy | Secondary | Forbidden shortcut |
| --- | --- | --- | --- |
| INTAKE | clarify or reject policy conflict | new TaskSpec revision | guess high-risk intent |
| OBSERVATION | reobserve / active perception | switch source | invent affordances |
| FUSION | authoritative-source probe | safe inconclusive | arbitrary confidence winner |
| TASK_PLANNING | compact or schema repair | provider switch / ask | grant authority |
| STEP_PLANNING | add evidence / replan step | task replan | task-family dispatch |
| PROPOSAL_VALIDATION | bounded repair | replan step | hidden executable mutation |
| GROUNDING_BINDING | reground | active perception / reroute | reuse stale target |
| PREFLIGHT | reobserve and rebuild | request approval | patch old contract |
| EXECUTION_NOT_DISPATCHED | reroute | idempotent retry | assume effect |
| EXECUTION_UNCERTAIN | inspect post-state | verify / compensate | blind retry |
| VERIFICATION_FAILED | stronger evidence | replan / compensate | trust receipt |
| PROVIDER_CONTEXT | compact, defer, configured switch | ask user | unbounded timeout |
| SKILL_ACTIVATION | invalidate and System 2 fallthrough | replan | replay stale sequence |

### 7.4 Strategy preconditions

- ACTIVE_PERCEPTION requires an EvidenceGap and eligible ProbeCapability.
- REPLAN_STEP requires new evidence, a rejected assumption, or route failure.
- REPLAN_TASK preserves already verified subgoals.
- REROUTE requires non-dispatch or confirmed missing effect, a fresh candidate,
  and a new ActionContract.
- RETRY_IDEMPOTENT requires confirmed absent effect and idempotency authority.
- COMPENSATE requires confirmed effect and an explicit authorized contract.
- ASK_USER requires blocking ambiguity, missing authority, or irreducible
  conflict.
- ABORT applies when safety forbids continuation, budgets expire, no non-empty
  RecoveryDelta exists, or effect remains dangerously uncertain.

### 7.5 Semantic cascade

Keep exact signatures for replay. Detect repeated behavior using:

~~~text
phase
+ failure class
+ active subgoal
+ expected effect
+ effect status
+ normalized progress fingerprint
~~~

Selector, target, backend, mark, and coordinate values are excluded from the
semantic family key.

Detect repeated semantic failure, unchanged evidence/plan/route, A-B
oscillation, repeated stale reconstruction, repeated inconclusive verification,
provider/schema repair loops, exhausted perception/routes, duplicate-effect
risk, and context growth without progress.

### 7.6 Validation, execution, and re-entry

RecoveryPlanValidator rejects stale commands, budget overflow, authority
escalation, retries without effect evidence, same-candidate reroute, empty
RecoveryDelta, implicit compensation, benchmark task-family strategy, and
bypasses around contracts or verification.

RecoveryCoordinator never executes. RunCoordinator applies one validated
command through the owning port:

| Command | Owning executor |
| --- | --- |
| REOBSERVE / ACTIVE_PERCEPTION | PerceptionSession |
| COMPACT_CONTEXT | PlannerContextBuilder |
| SWITCH_PROVIDER / REPAIR_MODEL_SCHEMA | configured ModelPort orchestration |
| CLARIFY_INTENT | IntentCompiler plus new TaskSpec revision |
| REPLAN_TASK | TaskPlanLifecycle |
| REPLAN_STEP | GeneralistStepPlanner |
| REGROUND / REROUTE | entity resolver, router, ContractBuilder |
| INSPECT_POST_STATE | PerceptionSession plus Verifier |
| RETRY_IDEMPOTENT | normal contract execution loop |
| COMPENSATE | new compensation ActionContract |
| REQUEST_APPROVAL / ASK_USER | parent/user boundary |
| ABORT | Coordinator terminal transition |

The executor returns RecoveryReceipt. Coordinator validates RecoveryDelta,
traces it, updates bounded state, and re-enters the declared phase.

## 8. Integrated Runtime Loop

### 8.1 Normal path

~~~text
CREATED
  -> compile/validate TaskSpec
  -> flat or shallow TaskPlan
  -> OBSERVING
       -> requirements
       -> base epoch
       -> arbitration
       -> active perception if a blocking gap exists
       -> accepted snapshot or FailureEnvelope
  -> PLANNING
       -> semantic proposal
       -> PlannerProposalValidator
  -> BINDING
       -> current unified candidate and route
       -> ActionContract
  -> PREFLIGHT
  -> ACTING
  -> VERIFYING
       -> post-action observation
       -> active perception if evidence is insufficient
       -> criteria-bound result
  -> PLANNING or DONE
~~~

BINDING remains a traced activity inside the current top-level state machine
unless evidence justifies another public state.

### 8.2 Failure path

~~~text
FailureEnvelope from any phase
  -> RecoveryCoordinator
  -> cascade and safety assessment
  -> RecoveryPlanValidator
  -> one RecoveryCommand
  -> responsible executor
  -> RecoveryReceipt
  -> non-empty RecoveryDelta
  -> trace and phase re-entry
       or WAITING_APPROVAL / WAITING_USER
       or ABORTED / FAILED
~~~

Active perception is part of normal observation and verification. Recovery
invokes it through an ACTIVE_PERCEPTION command when failure reveals the gap.

### 8.3 No continuous watcher requirement

M8.6 remains request-driven: base observation, targeted probe, preflight
revalidation, post-action observation, and navigation/download/modal hooks.

A continuous watcher is promoted only when measured failures show this cannot
react in time.

## 9. State, Budgets, and Trace

StateKernel retains current bounded references:

- task/plan/subgoal revisions;
- accepted observation and snapshot;
- evidence gaps and conflicts;
- active ProbePlan and latest ProbeReceipt;
- current failure incident;
- latest RecoveryPlan/Receipt;
- semantic attempt fingerprints;
- rejected assumptions;
- remaining budgets;
- pending approval or user question.

Full history remains in trace and artifact stores.

Budgets include normal observations, active probes, probes per gap, visual/model
probes, planning repair, task replans, recovery depth, route fallbacks, wall
time, model/API cost, effectful attempts, and user escalations.

Required events:

- EvidenceGapDetected / Resolved / Unresolved;
- ActivePerceptionPlanned;
- ProbeStarted / Completed;
- AssertionArbitrated;
- FailureDetected / RecoveryIncidentOpened;
- RecoveryStrategySelected / Rejected;
- RecoveryCommandStarted / Completed;
- RecoveryDeltaValidated;
- RecoveryReenteredPhase;
- RecoveryEscalatedToUser / Aborted;
- PerceptionPolicyCandidateProposed;
- RecoveryArtifactCandidateProposed.

Every event records run/state/task/plan/subgoal identity, causation, artifact
references, budgets before/after, and redaction status.

## 10. Metrics

Active perception:

- gap detection recall and resolution by source;
- material conflict false-resolution;
- probe precision and redundancy;
- probes, latency, model calls, and cost per resolved gap;
- safe inconclusive rate;
- stale cross-epoch reuse violations.

Online recovery:

- failure detection recall by phase;
- success by changed strategy;
- no-op recovery rejection;
- semantic cascade depth and A-B cycles;
- inspect-before-repeat coverage;
- blind retry and duplicate effects;
- ask-user and abort precision;
- latency/cost and accepted-artifact uplift.

Hard requirements remain zero unauthorized effect, zero unapproved high-risk
effect, and zero blind repeat of uncertain effects.

## 11. Harness Learning

Repeated verified traces may propose PerceptionPolicyPatch containing typed gap,
environment capability profile, preferred probe order, scope, and stop
conditions. It cannot contain benchmark identity, selectors, coordinates, mark
ids, or answers.

Repeated incidents may propose RecoveryPolicyPatch, RecoverySkill, verifier
strengthening, or a generic failure fixture.

Every artifact is quarantined and replayed against original, related generic,
held-out, global, safety, and uncertain-effect suites. Accepted artifacts still
create fresh probes, plans, routes, contracts, and verifications.

## 12. Implementation Order

The order is facts-first and reuses current modules.

### AR0: Freeze contracts and controls

Add EvidenceGap, phase-general FailureEnvelope, ProbeCapability/Command/Receipt,
RecoveryCommand/Delta/Receipt, profile identity, and behavioral negative tests.
Do not change online behavior.

Exit: schemas round-trip, generic contracts contain no benchmark identity, and
safety/no-op command validation exists.

### AR1: Complete active-perception planning

Build ActivePerceptionController above SourceAssertionArbiter and
PerceptionSession.capture_targeted.

Add gap extraction, probe registry, hard gates, selection, coherent epochs,
budgets, stop conditions, and trace.

Exit: structured, visual-primary, cross-source conflict, and safe inconclusive
cases work; ordinary DOM does not trigger an unnecessary visual call.

### AR2: Integrate active perception into normal flow

Wire it into initial observation, candidate ambiguity, high-risk preflight
evidence, and post-action verification.

Exit: normal Coordinator traces gap, probe, new epoch, arbitration, and
continuation with no second state writer.

Implementation status on 2026-07-23: **AR0-AR2 complete for G2.5**. The Runtime
has strict evidence-gap/probe/receipt/resolution contracts, one minimum-cost
read-only controller, coherent targeted capture, and normal, preflight,
verification-repair, and lower-half recovery-inspection call sites. It stops
safely on surviving material gaps and never treats a transport receipt alone as
resolution. AR3-AR6 remain planned; in particular, the recovery call site does
not yet constitute the full-phase RecoveryCoordinator.

### AR3: Introduce full-phase recovery contracts

Adapt current FailureSignature/RecoveryIncident into FailureEnvelope. Add
semantic family keys and RecoveryPlanValidator. Keep RecoveryHandler through a
temporary lower-half adapter.

Exit: planner exception, invalid proposal, no-affordance, binding rejection,
stale contract, execution uncertainty, and verifier failure share one envelope.

### AR4: Recover pre-contract phases

Implement reobserve, active perception, context compaction, configured provider
defer/switch, schema repair, intent clarification, task/step replan, and reground.

Exit: one observation failure changes source, one planning failure changes
context/plan, one ambiguity asks the user, and equivalent planning loops stop.

### AR5: Unify contract and effect recovery

Move preflight/execution/verification recovery behind RecoveryCoordinator and
typed commands. Add post-state inspection, fresh reroute, idempotent retry,
compensation contract, approval/abort, and changed-strategy guard.

Exit: not-dispatched reroute, uncertain-effect inspection, duplicate avoidance,
verified compensation, and zero blind retry are proven.

### AR6: Load accepted policies and close trace

Load accepted PerceptionPolicyPatch, RecoveryPolicyPatch, and RecoverySkill
profiles with digests, fallthrough, rollback, and fresh replay.

Exit: perception cost or cascade depth improves without safety regression;
stale/mismatched artifacts fall through.

### AR7: Generalization and benchmark audit

Run non-benchmark conformance and fault injection first. Then report
strict-generalist, strict plus accepted artifacts, compatibility, and ablation
profiles separately.

Exit: gains transfer across unseen local Web, visual, and WoT environments;
benchmarks confirm rather than define the capability.

## 13. Test Matrix

| Scenario | Required behavior |
| --- | --- |
| ordinary form | DOM/A11y accepted; no visual probe |
| SVG point | SVG primary, visual fallback |
| canvas target | screenshot/SoM/VLM primary within budget |
| DOM versus overlay | targeted refresh; block if unresolved |
| dashboard versus WoT | authoritative repoll; no blind write |
| zero affordances | active perception or replan, not repeated ask-user |
| invalid planner schema | bounded repair, then context/provider recovery |
| missing proposal target | new-epoch reground, not old target patch |
| action timeout | post-state inspection before repeat |
| inconclusive verifier | stronger evidence without repeating effect |
| stale accepted skill | System 2 fallthrough |
| varied wrong targets | semantic cascade detected |
| provider quota | typed defer/switch, no timeout inflation |
| missing authority | approval, ask, or abort |

Every case requires a non-BrowserGym fixture before external replay.

## 14. Module Skeleton

Retain current modules:

~~~text
coordinator.py
perception.py
perception_session.py
source_assertions.py
recovery.py
recovery_handler.py
recovery_evolution.py
routing.py
task_plan_lifecycle.py
planner_context.py
~~~

Add focused modular-monolith responsibilities:

~~~text
active_perception.py
  EvidenceGap extraction
  ProbeCapability registry
  ActivePerceptionController
  ProbePlanValidator

failure_envelope.py
  phase-general failures
  semantic family key
  effect-status algebra

recovery_coordinator.py
  strategy registry
  RecoveryPlanValidator
  changed-strategy guard
  re-entry decision

recovery_commands.py
  typed command union
  RecoveryDelta
  RecoveryReceipt
~~~

Migration adapters map ActivePerceptionRequest to ProbeCommand and existing
RecoveryRequest to FailureEnvelope when a contract exists. RecoveryHandler
becomes a lower-half strategy provider. Accepted artifacts load through the new
strategy registry.

Do not create services, queues, one agent per phase, another Coordinator, or a
second event store.

## 15. Completion Boundary

The architecture is complete when it can truthfully state:

> The Runtime acquires only evidence needed for the active decision, keeps
> conflicts explicit, and stops safely when truth remains inconclusive. Any
> phase may enter one bounded recovery protocol, and another attempt occurs only
> after a traceable change in evidence, assumption, plan, grounding, route,
> verifier, provider/context, authority, or user input.

An enum, schema, unit test, or benchmark adapter alone does not complete this
design. The normal Coordinator path must consume it.
