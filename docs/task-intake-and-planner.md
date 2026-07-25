# Task Intake and Generalist Planner

## 1. Purpose and Authority

This document defines the current implementation target for turning real user
requests into bounded GUI tasks and planner proposals. It is part of the
lightweight implementation plan, not only the production blueprint.

The planner is environment-general. BrowserGym, MiniWoB++, WorkArena, and
WebArena are benchmark inputs to the same interface, not the planner's product
boundary.

The implementation must preserve this separation:

```text
natural-language understanding and planning
  != authorization
  != target grounding
  != execution
  != success verification
```

The raw-request pipeline, typed `TaskSpec`, shallow `TaskPlan`, and action-level
`GeneralistLMPlanner` exist. `TaskEnvelope(goal: str)` remains a compatibility
path, not the long-term authority boundary.

Current maturity is narrower than the schema list suggests. `TaskSpec`
currently records requested effects, but does not yet compile every sourced
user dependency and terminal outcome into an executable obligation graph. The
current `GeneralistLMPlanner.propose()` also owns too much residual semantic
policy. The next mandatory slice is:

```text
IntentDraft -> TaskSpec -> TaskObligationSpec[] -> TaskPlan
Task + active obligation + current evidence -> DecisionConstraintSet
DecisionConstraintSet + snapshot -> GeneralistLMPlanner
```

The critical assessment is recorded in
[Current Governance Critical Audit](current-governance-critical-audit-20260725.md).

## 2. End-to-End Chain

```text
UserRequest or Parent Task
  -> LLMIntentCompiler
  -> IntentDraft
  -> deterministic validation and policy intersection
  -> immutable TaskSpec revision
  -> sourced TaskObligationSpec validation
  -> immutable DecisionConstraintSet
  -> initial observation
  -> adaptive task-planning router
  -> optional shallow TaskPlan
  -> active outcome-oriented subgoal
  -> GeneralistLMPlanner
  -> PlannerProposal
  -> Grounder / ContractBuilder
  -> ActionContract
  -> capability / approval / preflight
  -> DOM, visual, accessibility, or WoT executor
  -> post-action observation
  -> VerificationReport
  -> continue / replan / clarify / recover / finish

Every stage
  -> Trace and artifacts

Completed or failed traces
  -> benchmark and failure analysis
  -> regression-gated harness evolution
```

Only the Coordinator advances authoritative runtime state. The compiler and
planner return immutable typed outputs.

## 3. Runtime Modes

| Mode | Request owner | Intent compilation | Planner |
| --- | --- | --- | --- |
| Standalone | end user | `LLMIntentCompiler` | `GeneralistLMPlanner` |
| Parent-agent | Codex, Claude, OpenHands, or another agent | parent may submit `TaskSpec` directly | parent adapter or generalist planner |
| Benchmark | benchmark adapter | canonical `TaskSpec` or separately evaluated compiler | reproducible planner adapter |
| Runtime diagnosis | test harness | fixed `TaskSpec` | `ScriptedPlanner` |

BrowserGym-specific planners never become the only standalone planner.

## 4. Intent Compiler

### 4.1 Responsibilities

The compiler extracts:

- objective and referenced entities;
- requested operations and side effects;
- user preferences and soft ranking criteria;
- desired outputs;
- success criteria;
- explicit constraints and forbidden effects;
- evidence requirements;
- unresolved ambiguity;
- provenance for security-relevant fields.

It does not:

- grant capability;
- approve an effectful action;
- select a DOM selector, coordinate, or WoT form;
- trust page text as a user instruction;
- silently resolve high-risk ambiguity;
- execute an action.

### 4.2 Inputs

`UserRequest` contains:

```text
request id
raw user text
conversation references selected by the caller
explicit attachments and target references
caller identity and channel
optional profile/context references
locale and time context
```

Only relevant, source-labelled context enters the compiler. Cookies, credentials,
full traces, stale locators, and unrelated history are excluded.

### 4.3 IntentDraft

The LM produces an `IntentDraft` under a strict schema:

```text
objective
entities[]
requested_effects[]
preferences[]
desired_outputs[]
candidate_success_criteria[]
candidate_constraints[]
candidate_forbidden_effects[]
ambiguities[]
source_map
confidence_by_field
```

The draft is not executable and carries no authority.

### 4.4 Deterministic Compilation Result

A deterministic validator converts the draft into one of:

```text
READY
NEEDS_CLARIFICATION
POLICY_CONFLICT
UNSUPPORTED
```

Blocking ambiguity includes an unresolved target, recipient, amount, destructive
scope, credential boundary, payment boundary, or external communication
channel. Low-risk environmental ambiguity may remain for read-only exploration.

### 4.5 TaskSpec

A ready task becomes an immutable, versioned `TaskSpec`:

```text
schema_version
task_id
revision
objective
operation_class
targets[]
preferences[]
desired_outputs[]
success_criteria[]
constraints[]
forbidden_effects[]
evidence_requirements[]
requested_capabilities[]
ambiguity_status
source_request_ref
field_provenance
created_at
```

`operation_class` begins with:

```text
READ_ONLY
NAVIGATION
REVERSIBLE_WRITE
EXTERNAL_SIDE_EFFECT
IRREVERSIBLE
```

Requested capability is not granted capability. Effective authority is the
intersection of caller grants, runtime policy, and action requirements.

A user intent change creates a new `TaskSpec` revision. Pending proposals and
contracts based on an older revision are rejected or revalidated.

### 4.6 Task obligations

`requested_effects[]` is descriptive input, not by itself a completion
contract. Raw natural language first produces a bounded sourced claim ledger;
the obligation compiler then produces typed obligations that cover those
claims:

```text
SourcedTaskClaim
  claim_id
  kind: effect | value | dependency | terminal | constraint
  source_ref
  statement
  required

TaskObligationSpec
  obligation_id
  kind: predicate | effect
  subject
  relation
  value_source: none | literal | observation | obligation_output
  expected_value
  claim_ids[]
  depends_on[]
  evidence_requirements[]
  blocking
  terminal
```

Dependencies are graph edges, not an obligation kind. Evidence requirements
are properties of the obligation they can prove, not synthetic evidence nodes.
A literal value must be present in an authorized source claim. An
`obligation_output` value must name a declared direct prerequisite. Terminal
obligations must use a terminal-compatible typed relation and independent
evidence requirement. Duplicate ids, cycles, dangling references, blank source
claims, invalid value-source combinations, or a terminal without evidence are
invalid.

Every required claim must be covered by at least one obligation and every
obligation must cite one or more authorized claims. This proves structural
coverage against the claim ledger; it does not let one model certify the
semantic completeness of its own natural-language extraction. Parent/typed
callers may supply an authoritative ledger. The raw-language path uses a
bounded independent coverage check; disagreement, an uncovered imperative
clause, or unresolved data dependency causes one budget-neutral repair or
`NEEDS_CLARIFICATION`/`UNSUPPORTED`. It may not silently compile a permissive
flat plan.

Every effectful task must have at least one terminal obligation and independent
evidence requirement. Every user-stated dependency must either appear in the
compiled graph or cause a fail-closed compilation result. The compiler may
normalize user language; it may not infer authority from page content or invent
a benchmark-family solution.

`TaskPlanValidator` must prove that each blocking obligation is covered by a
subgoal and that at least one reachable terminal subgoal discharges the
terminal obligations. A passed action receipt or unrelated verification event
cannot satisfy an obligation.


## 5. Planner Boundary

### 5.1 PlannerContext

The planner receives a bounded, redacted view:

```text
TaskSpec
active subgoal
current AffordanceSnapshot summary
selected screenshot or artifact refs when needed
granted capability names, never approval secrets
remaining step, time, effect, and recovery budgets
pending evidence obligations
last action receipt and VerificationReport
recent relevant failures or recovery-incident summary
accepted applicable skills and policies
task revision, state version, and snapshot id
```

The planner does not receive raw credentials, cookies, complete historical DOM,
unrelated traces, executor handles, or benchmark oracle answers.

Before the model is called, deterministic owners derive an immutable
`DecisionConstraintSet`:

```text
allowed_action_families
required_outcomes
forbidden_effects
candidate_scope
terminal_readiness
required_evidence
remaining_budgets
recovery_constraints
```

The planner chooses among permitted semantic actions. It must not own terminal
readiness policy, global ordinal/pagination policy, benchmark-family semantics,
or evidence-coverage rules. Those rules belong to the obligation compiler,
task-plan lifecycle, candidate resolver, or verifier. This keeps
`GeneralistLMPlanner` general enough for real environments.

### 5.2 PlannerProposal

The planner returns a semantic proposal, not an executable contract:

```text
proposal_id
based_on_task_revision
based_on_state_version
snapshot_id
subgoal
action_kind
target_affordance_id or environment-discovery request
parameters
expected_effects[]
evidence_requirements[]
uncertainty
requires_clarification
done
result
reason
```

The initial action vocabulary is intentionally small:

```text
activate
type_text
select_option
navigate
scroll
wait
ask_user
finish
```

Surface-specific execution data is not planner output. DOM locator candidates,
visual bounding boxes, accessibility paths, and WoT forms stay in typed
affordance payloads.

### 5.3 ContractBuilder

A deterministic `ContractBuilder` binds a valid proposal to the current
affordance and creates the only executable object, `ActionContract`. It adds:

- current snapshot, revision, target fingerprint, and expiry;
- selected backend and typed target payload;
- preconditions and expected postconditions;
- required capability and approval binding;
- risk, idempotency, compensation, and timeout;
- verifier plan.

A stale proposal, missing target, unsupported action, or policy conflict never
reaches an executor.

## 6. GeneralistLMPlanner

### 6.1 ModelPort

The reference implementation depends on a provider-neutral `ModelPort`:

```python
class ModelPort(Protocol):
    async def generate_structured(
        self,
        messages: list[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T: ...
```

Provider adapters may use OpenAI, Anthropic, Gemini, OpenRouter, vLLM, or
Ollama. Runtime core does not import a provider SDK.

The shipped environment factory supports `local`, `mistral`, `gemini`, and
`zhipu` profiles. Gemini and Zhipu use OpenAI-compatible endpoints. Gemini reads only
`LLM_GEMINI_BASE_URL`, `LLM_GEMINI_MODEL`, and `LLM_GEMINI_API_KEY`; the
Zhipu profile reads `LLM_ZHIPU_BASE_URL`, `LLM_ZHIPU_MODEL`, and
`LLM_ZHIPU_API_KEY`; either profile is selected with `LLM_ACTIVE_PROFILE`.
Missing configuration fails closed before a request is sent. Secrets are never
added to traces, reports, or error details.

The provider boundary distinguishes transient 429 throttling, exhausted quota,
and provider capacity. It parses bounded `Retry-After` and
`google.rpc.RetryInfo` delays, opens a local circuit after terminal provider
failure, and lets the Coordinator persist a redacted resumable deferral. Local
Ollama evidence must pass `provider-preflight-ollama`, including container GPU
visibility and non-zero model VRAM residency.

The compiler and planner may use the same underlying model, but they are
separate structured calls with separate prompts and traces.

### 6.2 Planning Strategy

The first generalist planner is one LM worker with:

- current goal and active subgoal;
- compact affordance inventory;
- selected multimodal evidence;
- bounded recent outcomes;
- optional plan summary;
- explicit expected-effect and evidence obligations;
- one semantic action per decision.

The v47 reliability profile bounds the inventory to 80 ranked affordances and
retains only one recent proposal, one verified state delta, and one relevant
failure. Bounded repair calls use a dynamically narrowed action/target schema
after semantic or progress rejection. Page-derived state remains bounded and
untrusted.

It may update a short plan after verification or unexpected state change. It
does not require Manager/Worker/Reflector agents for the first release.

### 6.3 Mature Open-Source Reuse

Reuse established designs without importing a second execution runtime:

- AgentLab: model configuration, reproducibility, observation/history
  compaction, plan/memory/critique, and BrowserGym benchmark baseline;
- browser-use: real-Web context management and action-error feedback;
- Agent S: general GUI reflection and multimodal grounding patterns.

Planned adapters are:

| Adapter | Purpose |
| --- | --- |
| `ScriptedPlanner` | deterministic runtime and fault tests |
| `GeneralistLMPlanner` | standalone real-user mode |
| `ParentAgentPlannerAdapter` | external agent composition |
| `AgentLabPlannerAdapter` | BrowserGym and public Web benchmark baseline |
| `AgentSPlannerAdapter` | optional future desktop/visual comparison |

AgentLab or BrowserGym action strings must be intercepted and translated into
`PlannerProposal`. They may not call `env.step()` or an executor outside the
Coordinator.

### 6.4 Adaptive Shallow Task Planning - implemented baseline, governance open

The implemented `GeneralistLMPlanner` remains the action-level planner: it
selects one semantic action from the latest affordance snapshot. The optional
task-level layer now decomposes a complex `TaskSpec` into a small number
of verifiable outcomes before action selection.

The design is adaptive rather than always hierarchical:

```text
simple task
  -> one synthetic subgoal
  -> existing action-level loop

complex or long-horizon task
  -> shallow TaskPlan
  -> serial subgoal execution
  -> existing action-level loop per subgoal
```

The supported hierarchy is exactly two levels:

```text
TaskSpec
  -> outcome-oriented SubgoalSpec
    -> observe / plan one action / act / verify
```

Do not add nested phases, per-subgoal agents, or a generic workflow engine.

#### Planning router

A deterministic `PlanningRouter` selects the path:

- blocking user-intent ambiguity returns clarification before any planner;
- a single target with one directly verifiable success condition uses a
  synthetic single-subgoal plan;
- an exact accepted skill or task template uses `RuleTaskPlanner`;
- open-world, multi-stage, cross-application, or data-dependent work uses
  `LLMTaskPlanner`;
- a rule skeleton may lock mandatory outcomes and constraints while the LM
  fills only explicitly open slots.

User-intent ambiguity is not an LM-planning problem. Recipients, destructive
scope, amounts, credentials, payment, or external communication channels are
never guessed. Environmental ambiguity, such as an unknown application path,
may be explored by the LM within read, action, and recovery budgets.

#### TaskPlan contract

`TaskPlan` is immutable and versioned:

```text
plan_id
task_id
task_revision
plan_version
based_on_state_version
generated_by: rule | llm | parent | skill
subgoals[]
assumptions[]
```

Each `SubgoalSpec` contains:

```text
subgoal_id
objective
depends_on[]
success_criteria[]
evidence_requirements[]
operation_class
max_actions
max_recoveries
```

Subgoals describe desired environment states, not UI scripts. They may not
contain selectors, coordinates, backend handles, executable code, approval
tokens, or granted capabilities.

`depends_on` permits a bounded partial order and future-proofs the schema. The
current runtime selects one ready subgoal at a time and executes serially. It
does not implement parallel nodes, fan-out/fan-in, a DAG scheduler, or multiple
agents controlling one session. Initial multi-stage plans are limited to 2-8
subgoals; simple rule plans use one.

Mutable progress is separate from the immutable plan:

```text
active_subgoal_id
completed_subgoal_ids
failed_subgoal_ids
evidence_by_subgoal
task_replan_count
```

#### Mandatory validation

Every plan candidate passes the same deterministic `TaskPlanValidator`,
whether produced by rules, an LM, a parent agent, or an accepted evolution
artifact. Validation includes:

- matching task and state revisions;
- unique IDs, valid dependencies, and cycle rejection;
- bounded subgoal and budget counts;
- at least one terminal outcome;
- verifiable completion and evidence requirements for every subgoal;
- preservation of TaskSpec constraints and forbidden effects;
- no capability grant, approval, selector, coordinate, or executable action;
- operation classes compatible with task policy.

The validator returns `ACCEPT`, `REPAIRABLE`, or `REJECT`. An LM candidate
may receive one bounded repair attempt with structured validation errors. An
invalid rule plan is an engineering/configuration failure and is not silently
hidden by an LM fallback.

`TaskPlanValidator` does not replace proposal validation, contract building,
preflight, or post-action verification. Each model-controlled boundary retains
its own typed, deterministic gate.

#### Loop and replanning ownership

`RunCoordinator`, not `TaskPlanner`, owns the dynamic environment loop. For
the active subgoal it repeatedly:

```text
observe
  -> action-level PlannerProposal
  -> validate and build ActionContract
  -> preflight
  -> execute
  -> post-action observe
  -> verify action effect and subgoal criteria
```

Only verifier evidence advances a subgoal. Planner self-report does not.
Selector drift, stale leases, temporary disabled state, ordinary modals, and
single-action failures stay inside local observation, action replanning, or
bounded recovery.

Task-level replanning occurs only when a subgoal remains unreachable after its
local budget, a plan assumption is disproved, a newly discovered mandatory
stage is missing, TaskSpec is revised, constraints change, or a repeated-error
incident shows that the plan structure is invalid. Replanning preserves
verified completed outcomes and creates a new plan version.

Post-action observation remains mandatory. Navigation, modal, and download
hooks may provide targeted feedback; a continuous watcher remains deferred
until benchmark evidence shows an advantage.

The baseline does not close task planning governance. Plan versions,
completed-evidence summaries, failure summaries, current environment summaries,
and sourced obligations must be present on every replan. Aggregate benchmark
gain cannot justify embedding residual task semantics in the step planner.
Protected-family and non-BrowserGym evidence are required before promotion.

## 7. Multimodal and Cross-Surface Planning

The planner consumes one common affordance envelope with typed payloads.

It may request:

- DOM/accessibility details for semantic controls;
- a screenshot crop or SoM view for visual attributes and layout;
- WoT property/action metadata for device operations;
- stronger observation when confidence is insufficient.

For requests such as "choose a restaurant with a quiet date-night vibe", visual
evidence is a first-class planner input. The final success claim still requires
traceable evidence and a task-appropriate verifier.

The same planner can choose between DOM, visual, and WoT affordances, but
`CostAwareRouter` and `ContractBuilder` retain final backend binding.

## 8. Feedback, Clarification, and Recovery

After every action the planner receives a normalized outcome:

```text
PASSED
FAILED
INCONCLUSIVE
ERROR
POLICY_BLOCKED
STALE
```

The next decision is:

```text
continue
replan
request stronger observation
ask user
hand off to bounded recovery
finish
```

The planner cannot convert a denial into permission. An uncertain effect is
observed and verified before any retry. Repeated failures are linked to the
implemented `RecoveryIncident` and loop detector.

## 9. Context, Memory, and Skills

The planner uses three bounded sources:

| Source | Purpose |
| --- | --- |
| Working context | current task, snapshot, budgets, obligations, latest outcome |
| Episodic summary | relevant prior steps from this run |
| Accepted harness knowledge | regression-approved skills, policy patches, and negative examples |

User-profile memory is an optional sourced context provider, not authority.
Profile-derived preferences may rank choices but cannot approve payment,
deletion, submission, messaging, or credential use.

Only accepted, applicable, versioned evolution artifacts can alter planner
policy. Raw failed traces do not become live instructions.

## 10. Trace and Reproducibility

Add trace events:

```text
UserRequestReceived
IntentDraftProduced
ClarificationRequested
TaskSpecCreated
TaskSpecRevised
PlannerContextBuilt
PlannerProposalProduced
PlannerProposalRejected
ContractBuilt
```

Record:

- compiler/planner implementation and prompt version;
- model provider, model snapshot, decoding configuration, and endpoint class;
- task revision, state version, and snapshot id;
- schema-valid structured output;
- retry/parse failures, latency, token use, and cost;
- links from proposal to contract, receipt, verification, and recovery;
- redaction decisions.

Remote APIs may not be bit-identical over time. Reproducibility therefore means
pinned configuration plus complete inputs/outputs and repeated seeded reports,
not an unsupported claim of deterministic model internals.

## 11. Evaluation

Evaluation is split so errors remain attributable.

### 11.1 Intent Compilation Suite

```text
raw request and selected context
  -> canonical TaskSpec
```

Metrics:

- objective and entity extraction;
- explicit-constraint recall;
- forbidden-effect recall;
- blocking-ambiguity recall and false clarification rate;
- success-criteria validity;
- capability over-request rate;
- provenance coverage;
- schema validity.

The controlled gate contains at least 30 requests: read-only, reversible-write,
external-side-effect, ambiguous, conflicting, and unsupported cases, with
paraphrases and context updates.

Mandatory safety gates are:

```text
forbidden-effect recall = 1.0
blocking high-risk ambiguity recall = 1.0
capability over-grant count = 0
schema validity = 1.0
```

### 11.2 Planner Suite

```text
canonical TaskSpec + environment
  -> verified task result
```

Metrics:

- task success and verified completion;
- valid proposal rate;
- stale proposal rejection;
- planner-induced policy violation;
- replan success after failed/inconclusive verification;
- repeated-action and recovery-cascade rate;
- action, token, latency, and cost budgets.

### 11.3 End-to-End Suite

```text
raw user request
  -> final verified result
```

Run the three local SaaS scenarios, cross-surface conformance task, and selected
realistic paraphrase variants. BrowserGym runs remain a separate benchmark
track and reuse the same planner boundary.

For BrowserGym, compare the same model/planner in two configurations where
possible:

```text
AgentLab direct action baseline
AgentLabPlannerAdapter -> Affordance Runtime
```

This isolates the value of contracts, policy, verification, recovery, and trace.

### 11.4 Adaptive Planning Ablation

Evaluate task-level planning separately from action-level planning:

```text
Flat: one synthetic subgoal for every task
Always-plan: LLM TaskPlan for every task
Adaptive: deterministic router + rule/LLM TaskPlanner
```

Compare:

- verified task and subgoal success;
- model calls, tokens, latency, and action count;
- task-plan validation and repair rate;
- local action replan versus task-level replan rate;
- plan invalidation and repeated-error rate;
- policy violations and verifier false accepts.

MiniWoB-style short tasks should demonstrate that adaptive routing preserves
the flat path. A controlled multi-stage local task and available
WebArena/WorkArena long-horizon tasks should test whether shallow planning
improves completion without excessive inference or stale-plan overhead.

## 12. Implementation Milestone: M8.2A

### Deliverables

1. Add `UserRequest`, `IntentDraft`, `CompilationResult`, and versioned
   `TaskSpec` schemas.
2. Add deterministic validation, ambiguity, provenance, and policy-intersection
   rules.
3. Migrate `TaskEnvelope` to carry or reference `TaskSpec` while preserving a
   compatibility constructor.
4. Change the planner boundary from direct `ActionContract` output to
   `PlannerProposal` followed by deterministic `ContractBuilder`.
5. Add provider-neutral `ModelPort` plus one local or remote reference adapter.
6. Implement `LLMIntentCompiler` and `GeneralistLMPlanner`.
7. Add `ParentAgentPlannerAdapter` and `AgentLabPlannerAdapter` without exposing
   primitive execution.
8. Add compiler/planner trace events, redaction, and model manifests.
9. Run the controlled compiler, real-environment planner, and end-to-end suites.

### Exit Criteria

M8.2A is complete when:

- a raw natural-language request reaches a verified result through the full
  Coordinator path;
- a blocking high-risk ambiguity stops before planning;
- a user clarification creates a new TaskSpec revision and invalidates stale
  proposals;
- one read-only, one reversible-write, one approval-gated, and one
  DOM/visual/WoT cross-surface task pass;
- no LM output grants capability, approval, or direct executor access;
- the same PlannerPort runs a BrowserGym smoke without task-specific solver
  logic;
- prompt/model/schema versions and proposal-to-contract lineage are traceable;
- compiler and planner failures are reported separately from runtime failures.

## 13. Implementation Milestone: M8.4

### Adaptive Shallow Task Planning - implemented baseline, follow-through open

The listed baseline components exist. Remaining work is sourced obligation
coverage, complete replan inputs and version lineage, planner responsibility
reduction, and protected-family/non-BrowserGym evidence.

Original entry criteria:

- the M8.2B consolidation gate and current action-planner PR profile are
  reproducible;
- the TaskPlan, SubgoalSpec, validation-report, and progress schemas are frozen;
- at least one controlled multi-stage scenario has independent subgoal oracles.

Deliverables:

1. Add `TaskPlannerPort`, `PlanningRouter`, `RuleTaskPlanner`, and
   `LLMTaskPlanner`.
2. Add immutable `TaskPlan`/`SubgoalSpec` and separate mutable
   `PlanProgress`.
3. Add deterministic `TaskPlanValidator` with one bounded LM repair path.
4. Let the Coordinator select one ready subgoal while preserving its existing
   single-writer and single-action semantics.
5. Advance subgoals only from verifier-backed evidence.
6. Add explicit local-action and task-level replan reasons to trace.
7. Run Flat, Always-plan, and Adaptive ablations.

Exit:

- simple tasks bypass LM task planning and retain their existing runtime path;
- complex tasks execute 2-8 outcome subgoals through the same action planner,
  contracts, preflight, verification, recovery, and trace;
- invalid rule, LM, parent, and evolution plans fail the same validation gate;
- no plan can grant authority or contain an executable GUI target;
- no effectful subgoals execute in parallel;
- adaptive planning improves at least one controlled long-horizon task family
  without regressing the short-task safety suite;
- a full trace distinguishes task planning, action planning, local recovery,
  and task-level replanning.

## 14. Scope Control

Not required for M8.2A:

- multi-planner voting;
- autonomous online prompt mutation;
- distributed planner services;
- long-term vector memory;
- training or fine-tuning a GUI model;
- arbitrary code-generation actions;
- desktop/mobile execution;
- a mandatory LangGraph dependency.

Not required for M8.4:

- a generic DAG scheduler or graph database;
- parallel subgoal execution;
- recursive planning hierarchies;
- one agent per subgoal;
- continuous environment watching;
- a workflow-framework dependency in runtime core.

The target is a complete real-user planning loop with one mature, replaceable
LM planner, not a new general-purpose agent framework.
