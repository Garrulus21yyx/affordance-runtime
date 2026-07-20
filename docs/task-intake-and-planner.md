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

The current `TaskEnvelope(goal: str)` and scripted planners are executable
runtime scaffolding. They do not yet constitute general user-intent
understanding.

## 2. End-to-End Chain

```text
UserRequest or Parent Task
  -> LLMIntentCompiler
  -> IntentDraft
  -> deterministic validation and policy intersection
  -> immutable TaskSpec revision
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

## 13. Scope Control

Not required for M8.2A:

- multi-planner voting;
- autonomous online prompt mutation;
- distributed planner services;
- long-term vector memory;
- training or fine-tuning a GUI model;
- arbitrary code-generation actions;
- desktop/mobile execution;
- a mandatory LangGraph dependency.

The target is a complete real-user planning loop with one mature, replaceable
LM planner, not a new general-purpose agent framework.
