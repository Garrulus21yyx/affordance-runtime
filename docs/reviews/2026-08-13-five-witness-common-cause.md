# Five-witness live diagnostic: shared pre-action failure

> **Status:** diagnostic complete; remediation and clean-SHA revalidation open
> **Implementation SHA:** `5d2e96df6abb94f88cd441c60e0e4d92abb7e477`
> **Run evidence:** [public run directory](../evidence/runs/p5-m4-6-e-step13-five-witness-seed7-5d2e96d-audit-rerun/)

## Result

The frozen seed-7 witness set completed 5/5 cases and succeeded 0/5. Every case
ended as `structured_output_failure` before BrowserGym received an action. This
is one shared protocol/composition failure, not five task-specific failures.

| Case | World targets | Action options | Provider attempts | Schema repairs | Argument repairs | BrowserGym steps | Executions |
|---|---:|---:|---:|---:|---:|---:|---:|
| `miniwob-60-05` | 54 | 25 | 2 | 1 | 0 | 0 | 0 |
| `miniwob-60-34` | 21 | 1 | 2 | 1 | 1 | 0 | 0 |
| `miniwob-60-42` | 18 | 13 | 2 | 1 | 0 | 0 | 0 |
| `miniwob-60-49` | 21 | 1 | 2 | 1 | 1 | 0 | 0 |
| `miniwob-60-60` | 24 | 2 | 3 | 2 | 1 | 0 | 0 |

The observations and action spaces were nonempty. The failure therefore
precedes visual grounding, action selection, private binding and execution.

## Causal model

The normal GUI decision surface should be bounded and simple:

```text
task + current Unified World context + current semantic action tools
-> model selects one tool with its public arguments
-> Runtime privately resolves the internal action/binding and executes it
```

The Step-13 runner instead passes
`LocalObjectiveProposalRequirement.REQUIRED` for the entire cohort and always
constructs a local-objective proposer. None of the five case manifests declares
that capability need. This forces every case through objective proposal before
the existing action adapter can run.

The Python action and objective adapters are distinct, but their compact JSON
transport still derives from `GroundedToolCommandPayload`. Its outer fields are
`op`, `target`, `text` and `value`. The objective catalog then embeds the much
larger sequence/set/aggregate/predicate algebra under an operation's `value`
argument. The diagnostic objective catalog was roughly 11--20 KB. Thus a direct
GUI task that should see a small action menu is instead asked to construct an
internal objective DSL through an action-shaped command envelope.

A private, non-committed one-case capture confirmed the mechanism without being
used as public benchmark evidence. For grid coordinate `(1,-2)`, the model chose
the offered `propose_local_objective` operation but placed the semantic value in
the action-shaped `target` field. Local validation correctly produced
`target:value_error`. The bounded top-level schema retry then discarded that
known field violation and supplied only a generic request for flat JSON. The
selected-operation argument-repair path already carries typed `code`,
`field_paths`, `expected` and `actual`; the top-level schema-repair path does not.

For the Zhipu visual profile, structured output is
`prompt_json_local_validation`: the JSON Schema is included in the provider
prompt and the response is validated locally by Pydantic. It is not provider
native `json_schema` enforcement. This makes clear, minimal repair feedback more
important, but does not justify a second model protocol or retry pipeline.

## Responsibility defects

1. **Composition defect:** a benchmark runner enables an optional semantic phase
   for cases whose manifest does not require it.
2. **Protocol-boundary defect:** action/objective Python types are split, while
   the compact transport envelope remains action-shaped for both roles.
3. **Recovery defect:** the existing model port knows the schema violation, but
   the existing grounded adapter's top-level repair prompt drops it.
4. **Observability defect:** objective-proposer calls are reported as
   `decision_mode=act` and counted as policy calls, hiding the actual failing
   phase.
5. **Evidence-identity defect:** progress files are created inside the worktree
   after the initial clean check, so the runner later reports
   `git identity was dirty or changed during the arm`. This invalidates formal
   attestation but is independent of the five GUI outcomes.

## Admitted remediation order

No parallel chain is authorized.

1. Remove the Step-13 runner's unconditional objective requirement and proposer;
   use the existing cohort path's typed `NOT_REQUIRED` default unless a manifest
   explicitly declares another requirement.
2. Re-run the five held-out witnesses through the existing action adapter. Mine
   the next shared failure only after the agent reaches action selection.
3. If an explicitly objective-requiring manifest still falsifies the existing
   objective contract, harden the current grounded-tools bridge in place: reuse
   its existing objective types/catalog/resolver and existing retry path; do not
   add another adapter, planner, model protocol or state owner.
4. Attribute objective calls and schema errors to their actual phase and keep
   progress output from invalidating the implementation identity.

No task name, coordinate grammar, SVG family, label, fixture or benchmark ID may
enter production behavior. The five cases remain witnesses and cannot justify a
case-shaped branch or a generalization claim.

## Existing-mainline remediation result

Commit `b354398` removed only the Step-13 runner's unconditional objective
proposer and `REQUIRED` override. It did not add or replace a planner, adapter,
protocol, world source, evaluator or executor. The clean-SHA rerun wrote progress
outside the worktree and produced [valid public report
evidence](../evidence/runs/p5-m4-6-e-step13-five-witness-seed7-b354398/report.json):

- 5/5 completed, 3/5 succeeded;
- `run_evidence_valid=true` and the bounded visual gate accepted;
- every case reached the existing action adapter;
- all action calls resolved through grounded tools and private Runtime binding;
- no unknown operation, grounding authority or execution failure explains the
  remaining two cases.

| Case | Outcome | Turns / executions | Failure boundary |
|---|---|---:|---|
| `miniwob-60-05` | success | 1 / 1 | none |
| `miniwob-60-34` | success | 2 / 2 | none |
| `miniwob-60-42` | task failed | 1 / 1 | agent submitted before satisfying the set |
| `miniwob-60-49` | success | 2 / 2 | none |
| `miniwob-60-60` | task failed | 2 / 2 | agent supplied the wrong visual aggregate, then submitted |

A separate private replay, retained only outside the repository, checked the
actual failed-turn context. For `click-shades`, Unified World exposed public
`appearance.color_family` and `selected` state for every clickable entity. The
agent selected two blue entities, then submitted while more unselected blue
entities remained. For `visual-addition`, the screenshot represented eight
blocks plus two blocks; the agent filled `11` and submitted. BrowserGym then
returned authoritative terminal failure in both cases.

These failures must not be repaired by a color loop, block counter, instruction
keyword, task ID or submit guard in Runtime. They are respectively persistent
set semantics and multimodal aggregate semantics, already within the declared
scope of the existing LocalObjective algebra and model role.

The next common boundary is agent planning and memory, not another task-family
classifier. The frozen external breadth manifest declares only low-level
`required_primitives`; it even labels visual addition as `activate`. That data
cannot safely drive open semantic behavior. A task or manifest may require a
generic planning capability, but the agent must decide the plan's semantics.
Derivation from benchmark IDs, task-name substrings, labels or observed pass/fail
is prohibited.

## SOTA responsibility correction and bounded-history falsification

Current computer-use systems do not make the harness enumerate open GUI task
semantics. Native systems put perception, task decomposition, milestone
tracking, reflection and action choice in the model. Compositional systems put
high-level planning in a manager agent, action generation in a worker agent and
localization in grounding experts. In both forms the harness supplies
observations and a bounded action interface, executes actions, returns new
observations/errors, and owns safety/control. BrowserGym likewise exposes an
observation/action/reward environment over Playwright rather than implementing
task-family policies.

This comparison invalidates a stronger interpretation of the preceding
task-capability proposal: Runtime and benchmark code must not enumerate
`set/aggregate/sequence` task families and branch behavior on them. A manifest
may declare whether planning, visual perception or interaction capabilities are
available/required, but cannot become a semantic router. Open semantic choice
remains agent work.

Repository inspection found that `AgentContext` already owned a bounded typed
history of up to 12 turns, while grounded-tools projected only the final turn.
Commit `31720e4` closes that loss in place: earlier turns enter one
`interaction_history`, the final turn remains the nonduplicated
`previous_tool_result`, and private target identities are still translated only
to current call-local E-refs. It adds no memory owner, planner or protocol.

The clean-SHA rerun is [valid negative
evidence](../evidence/runs/p5-m4-6-e-step13-five-witness-seed7-31720e4/report.json):
2/5 succeeded, all cases reached grounded action execution, and the visual gate
accepted. This does not show that history reduced performance. The newly failed
grid case chose the wrong coordinate on its first turn, when history was empty;
the shades case also submitted on its first turn; visual addition again supplied
the wrong aggregate. Both two-turn pie cases consumed history and succeeded.
The 3/5 and 2/5 runs therefore demonstrate model decision variance, not a
directional performance result. Multi-seed held-out evidence is required before
claiming an improvement or regression.

Primary references used for the responsibility comparison:

- [OpenAI Computer Use guide](https://developers.openai.com/api/docs/guides/tools-computer-use):
  the model reads screenshots/history and returns a bounded computer action;
  the harness executes it, captures the next observation and owns confirmation.
- [UI-TARS](https://arxiv.org/abs/2501.12326): an end-to-end native GUI model
  performs task decomposition, milestone recognition, reflection, grounding and
  action prediction over interaction history. Its training path is outside this
  project's scope, but its model/runtime responsibility boundary is relevant.
- [Agent S2](https://arxiv.org/abs/2504.00906): a manager agent plans subgoals, a
  worker agent produces semantic actions, and grounding experts localize them;
  this project may reuse existing models as roles but will not train specialists.
- [BrowserGym/AgentLab](https://openreview.net/forum?id=5298fKGmv3): the browser
  is an observation/action/reward environment over Playwright with safe action
  mappings and feedback, not a task-family semantic engine.

## Schema repair closure and objective-semantic reopening

Three in-place grounded-tools changes now close the originally observed wire and
repair defects without adding a protocol:

1. `5b64bf0` gives every existing structured-output adapter the same bounded,
   value-free `field_path + code` repair contract. The retry count remains one;
   raw provider responses and exception text are not returned to the model.
2. `eaed5a7` finishes the compact wire split. Action selection uses
   `op/target/text/value`; objective proposal uses only `op/value`. Each payload
   owns its parameter extraction, so no phase/cast branch reconstructs fields.
3. `b0631b6` removes duplicate `expected` and raw `actual` from selected-tool
   repair. The operation's input schema appears once alongside owner/code/paths.

A clean private live diagnostic at `eaed5a7` explicitly enabled the existing
objective proposer for one witness. The first response correctly used the new
shape (`propose_local_objective` with `value=null`); Runtime identified the
missing `parameters.value` and issued the existing selected-operation repair.
The second response then mixed sequence, set and aggregate fields into one value
and failed as `invalid_tool_arguments`. No prompt, screenshot or provider
response from that capture is committed.

This falsifies “wire split plus better repair closes objective proposal.” The
remaining obstacle is the size and cognitive shape of the Runtime-owned
sequence/set/aggregate/predicate DSL, not missing JSON instructions. Continuing
to add task-shaped prompts or more schema branches is prohibited.

## Owner/consumer audit and architecture decision

The repository-wide owner audit separates two uses that had been conflated:

- `task_planner.py` compiles an admitted `TaskPlan` step into
  `EntityStepExecution`, `SetStepExecution`, or `AggregateStepExecution`. This
  is a closed execution algebra owned by the legacy planning runtime.
- `objective_spec.py` and `GroundedObjectiveAdapter` ask a model to construct
  the same algebra from an open natural-language task. The public target
  composition was its only intended product ingress, and no non-benchmark
  source caller enables that factory.
- Once installed in `AgentLoop`, a LocalObjective is not advisory working
  memory: it filters the public action page, fixes admitted action parameters,
  invokes visual predicate classification, refreshes after execution and can
  reject an otherwise legal model action. It therefore carries execution
  authority.

The decision is to stop treating the Runtime execution algebra as the target
agent's planning language. Open task decomposition, set/aggregate
interpretation and next-action choice stay with the existing action agent over
the current Unified World and bounded interaction history. Runtime keeps the
closed shell: current legal tools, private binding, admission, risk,
confirmation, execution, fresh observation and authoritative environment
outcomes. Runtime does not enumerate task families.

The target product composition and target benchmark contracts therefore no
longer accept an objective proposer or per-case objective requirement. This is
a subtraction from the existing chain, not a new planner. The closed
sequence/set/aggregate types remain temporarily because the legacy `TaskPlan`
runtime still consumes them; their model-facing target adapter and dormant
`AgentLoop` branch are deletion debt, not an optional benchmark arm.

Physical deletion order is consumer-based:

1. remove the now-unreachable model objective phase from target `AgentLoop`
   and its model transport/instrumentation;
2. retain the execution algebra only while the legacy `TaskPlan` owner has a
   default consumer;
3. after root/default cutover and replacement evidence, delete the legacy
   planner lifecycle and then its algebra/tests together.

Tests for a removed target objective phase are deleted rather than used to keep
that phase alive. Reducer tests for the still-consumed legacy execution algebra
remain until its owner is removed.

## Goal delivery and pre-execution verification audit

The remaining GLM failures are not caused by losing or mechanically rewriting
the MiniWoB goal:

- `BrowserGymMiniWobEnvironment.open` requires the public `raw["goal"]` string
  and passes that exact value into `NaturalLanguageTaskRequest`.
- `ThinTaskIntake` copies the instruction into `TaskGoal` without planning or
  parsing it, and `reset` rejects any task whose instruction differs from the
  saved BrowserGym goal.
- `project_task` bounds the instruction to 1,024 characters; the five witness
  goals are below that bound. Grounded-tools sends it as
  `task_brief.instruction` alongside the screenshot, current public entities,
  bounded interaction history and current tool menu.

There is no task-semantic verifier between `SelectAction` and dispatch. Runtime
does validate current action authority, binding, risk and currentness, and the
environment evaluates the task after execution. Those owners cannot know a
hidden expected answer before a terminal action without becoming a benchmark
oracle. In the failed evidence, GLM therefore chose Submit before satisfying
the visible set, or submitted after trusting its own wrong aggregate.

This is a reliability gap in deliberate agent control, not proof that the
model or execution path cannot solve the tasks. A separate clean
`click-shades` seed-7 GLM witness already selected five blue controls and then
Submit successfully in six turns. The same model family can produce both a
correct multi-step trajectory and a premature terminal action.

[Zhipu's official GLM-4.1V-Thinking page](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-4.1v-thinking)
states that the family has built-in deep thinking and demonstrates
`glm-4.1v-thinking-flashx` without an explicit `thinking` parameter. The
current multimodal port does not send `thinking=disabled`; absence of an
explicit `enabled` flag is therefore not an evidenced cause and must not be
patched speculatively.

Current GUI-agent references do not give Runtime an omniscient correctness
oracle. UI-TARS generates deliberate thoughts before actions and learns
reflection through training; Agent S2 separates manager, worker and grounding
roles with proactive replanning; OpenAI Computer Use keeps model action choice
inside an observation/action loop while the harness owns execution and
high-impact confirmation. Under this project's no-training constraint, a
future pre-commit review must be an agent semantic judgment over the same
current Unified World and candidate action. Runtime may hold, admit or reject
that candidate, but must not infer task completion from a task name, benchmark
ID, button label or hidden expected value. Such a review must reuse the
existing `AgentLoop`/model policy boundary; it cannot introduce a second
planner or execution path.

## Prompt-shape SOTA comparison and admitted first change

The active grounded-tools action request already includes the original task,
marked screenshot, public grounding index, current state, bounded action/result
history, and each offered tool's name, description and JSON argument schema.
Tool definition or task delivery is therefore not absent. The prompt-shape gap
is narrower: its system message began with a command to choose one operation,
did not explicitly establish a persistent GUI-agent role, and described useful
signals without prescribing a stable deliberation order.

Primary implementation comparisons:

- [UI-TARS computer-use prompt](https://github.com/bytedance/UI-TARS/blob/582f3a7e/codes/ui_tars/prompt.py)
  explicitly starts with “You are a GUI agent”, supplies task, screenshots and
  action history, enumerates the action space, and asks one response to contain
  a small plan/Thought followed by one Action. It does not require a separate
  manager or verifier for each short step and does not include task-specific
  few-shot examples in this prompt.
- [Agent S2 worker procedural memory](https://github.com/simular-ai/Agent-S/blob/main/gui_agents/s2/memory/procedural_memory.py)
  gives the worker one current subtask plus screenshot/history/tool methods and
  asks a single response to verify the previous action, analyze the screenshot,
  choose the next semantic action and ground exactly one executable action.
  Manager/reflection modules are additional roles for longer-horizon planning
  and trajectory failure, not a Runtime task-family classifier.
- [AgentLab GenericAgent configuration](https://github.com/ServiceNow/AgentLab/blob/main/src/agentlab/agents/generic_agent/agent_configs.py)
  enables thinking and abstract/concrete format examples in representative
  configurations. Its own GPT-3.5 comments say explicit plan and critic are
  usually detrimental while thinking and examples are useful, including for
  MiniWoB. This is model/configuration evidence, not a universal law.
- [OpenAI Computer Use](https://developers.openai.com/api/docs/guides/tools-computer-use)
  uses the same iterative shape: task plus current screenshot, model-selected
  UI actions, harness execution, fresh screenshot and repeat. It does not ask
  the harness to compile arbitrary task semantics before action selection.

The admitted first change therefore stays within the existing action adapter:
the system prompt now establishes one GUI-agent role and requires an internal
order of end-state identification, current observation analysis, previous
effect verification, and one next action. It explicitly treats tasks as
multi-turn and requires observable prerequisites to be checked before a
finalizing/commit action. The wire remains one simple command and Runtime
authority is unchanged. The shared prompt-based structured-output transport
also preserves that existing role at the start of the first system message and
appends its JSON Schema contract afterward. Previously the transport inserted
a schema-only system message before the role, so the provider-facing order did
not match the source prompt's intended hierarchy.

No few-shot example is added in this slice. The failed witnesses produced
schema-valid, privately resolvable tool calls, so output formatting is not the
shared failure. Any later examples must be abstract protocol examples selected
by a predeclared held-out A/B; GUI task, label, benchmark and witness examples
are prohibited. A separate manager, critic or verifier is likewise deferred
until the single-agent prompt contract is measured and a shared residual cause
demonstrates that another role is necessary.

## Clean prompt-alignment revalidation

The clean `9cbf503` frozen five-witness rerun is [valid public report
evidence](../evidence/runs/p5-m4-6-e-step13-five-witness-seed7-9cbf503-prompt-alignment/report.json):

- 5/5 cases completed, 3/5 succeeded, and the bounded visual gate accepted;
- every provider response used a schema-valid, privately resolvable action
  tool call, with zero schema repair and zero invalid-tool-argument events;
- the grid and both pie witnesses succeeded through structural identities;
- the set witness selected Submit as its first and only action and received an
  authoritative terminal task failure;
- the visual aggregate witness filled the textbox, then selected Submit and
  received an authoritative terminal task failure.

This result measures the prompt change and falsifies the claim that an explicit
GUI role, deliberate-order instruction, and role-before-schema transport are
alone sufficient to close the residual. Those changes remain a clearer public
agent contract, but the score is the same as the clean `b354398` run and must
not be presented as an improvement. The next change must address a shared
agent-semantic control boundary and be evaluated on predeclared held-out or
multi-seed evidence; it may not add task-, label-, answer-, selector- or
benchmark-shaped logic.

## Same-protocol GLM-4.6V probe

At the user's request, the exact frozen five-witness profile was run once at
clean `22552cf` with only the configured model changed from
`glm-4.1v-thinking-flashx` to `glm-4.6v`. The [valid report
evidence](../evidence/runs/p5-m4-6-e-step13-five-witness-seed7-22552cf-glm-4.6v/report.json)
records 5/5 completed, 4/5 succeeded, and an accepted bounded visual gate.

The behavioral difference is material but bounded. GLM-4.6V selected all five
currently blue entities and then Submit in six turns, closing the set witness
that GLM-4.1V had finalized immediately. The grid and both pie witnesses also
succeeded. The visual aggregate witness still filled the textbox and then
received an authoritative terminal failure after Submit. The persisted public
trace does not retain the fill parameter, so this report cannot honestly state
which aggregate value the model entered.

This is evidence that GLM-4.1V capability is a partial bottleneck, not proof of
a stable model-ordering claim. It is one seed and one stochastic run. GLM-4.6V
also cost more in this probe: model latency was 76,978 ms versus 38,742 ms,
provider attempts were 16 versus 8, and total tokens were 29,716 versus 18,927.
Three GLM-4.6V turns required bounded schema repair, while every selected action
still resolved and dispatched through the same existing protocol. No product
branch, reviewer, task semantic rule, or benchmark-specific behavior was added.

### Screenshot-only numeric ablation

A follow-up private diagnostic removed the action menu, DOM/world projection,
history, binding and execution entirely. Both models received the exact same
seed-7 initial screenshot and original goal, and were asked only which integer
should be entered. The expected visible aggregate was 10. In the paired call,
`glm-4.1v-thinking-flashx` returned 10 while `glm-4.6v` returned 11. A separate
4.1V structured-output attempt had also semantically returned 11, although its
thinking/answer wrapper failed the requested JSON format.

This ablation demonstrates two bounded facts. First, the aggregate error can
occur without GUI tools or finalization choice, so action-protocol complexity is
not necessary for the failure. Second, neither this probe nor the five-case run
establishes a deterministic 4.6V-over-4.1V ordering: visual counting is
stochastic for this screenshot even at nominal temperature zero. The probe is
diagnostic only, is not a benchmark score, and adds no production behavior.

## Structure-first correction: reuse the existing Unified World

A real seed-7 `visual-addition` reset was inspected through the same
BrowserGym projection and grounded catalog used by the target runner. It
establishes the actual boundary rather than inferring it from screenshots:

- `task_brief.instruction` contains the original BrowserGym goal unchanged;
- the structural Unified World contains 24 public entities and two executable
  bindings (`fill` and `click`);
- ten read-only `generic` leaf entities already carry
  `appearance.color_family=blue`;
- their public parent/child relations preserve the visible 8+2 grouping; and
- the initial source is explicitly `structural`.

The repository therefore did not need another DOM parser, a repeated-leaf
counter, a visual-addition rule, or a parallel perception chain. The general
AX projection already owned the useful facts. The remaining architectural bug
was in the model adapter: `grounded_tools.v2` rejected every perception profile
except `screenshot-ax.v1`, always transmitted image bytes already attached to
the structural observation, and hard-coded screenshot metadata. Protocol,
acquisition policy and transport modality were incorrectly coupled.

The current in-place correction adds `structure-first.v1` as a perception
profile while retaining `grounded_tools.v2`, the existing grounded catalog,
the existing `RequestObservation` decision, the existing observation
orchestrator and the same Runtime execution path. Its contract is:

```text
initial current Unified World (structural source)
-> one grounded action/observation tool call with no image
-> if public evidence is insufficient, agent selects observe_visual
-> environment acquires and fuses a current visual source
-> next call carries the corresponding marked image
```

When no image is transmitted, call-local `marked` flags are set to false so
the model is never told that screenshot marks are visible when they are not.
The adapter compatibility key and metadata now include the selected perception
profile. The primary benchmark runner selects this profile explicitly; legacy
text-only and always-screenshot profiles remain comparison configurations, not
separate execution chains.

Targeted evidence for this implementation is 18 passing grounded-protocol and
composition tests, touched-file Ruff success, and Mypy success for the seven
changed source files. Live benchmark evidence remains pending and no score or
generalization improvement is claimed yet.

## Clean structure-first run and residual control-context defect

The clean `d325360` GLM-4.6V run is recorded in the
[structure-first evidence note](../evidence/2026-08-14-structure-first-five-witness-d325360.md).
It completed 5/5, succeeded 4/5, remained evidence-valid, and invoked no visual
source or auxiliary visual provider in any case. Grid coordinate, both pie
witnesses and the multi-target color witness completed from structural public
facts alone.

The residual did not submit a wrong aggregate. `visual-addition` selected
`RequestObservation` twice, received only the already-current structural source
both times, and executed no action. Runtime correctly returned typed no-gain
feedback after the first request and stopped the repeated control decision.

The shared context defect is now narrower. `AgentTurnView.semantic_summary`
already retained the requested observation modality, but the grounded catalog's
compact `previous_tool_result` dropped the whole semantic summary. The model
therefore saw the failed decision kind and no-gain feedback without the modality
that had produced it. Observation-tool descriptions also failed to distinguish
an already-current modality refresh from acquisition of an absent modality.
The in-place remediation preserves non-action decision details in the same
bounded history and derives each observation-tool description from public
current source summaries. It does not suppress observation through task logic
or infer which modality a task ought to use.

The run also falsified one benchmark attestation detail. Diagnostic
`selected_grounding.marked` reflected marks available in the Context even when
the structure-first adapter did not transmit image bytes. The next trace schema
records the adapter's actual image input count and reports a selected entity as
marked only when an image was sent. The structure-first gate requires zero
images on the initial call and requires a current visual source for every later
image-bearing call. Score and authoritative environment outcomes at `d325360`
remain valid; its marked-selection evidence does not.

## Control-context revalidation and exact selected-tool repair

The clean `ccea342` rerun is recorded in the
[control-context evidence note](../evidence/2026-08-14-structure-first-control-context-ccea342.md).
It again completed 5/5 and succeeded 4/5. The previous repeated-control failure
did not recur. Instead, the residual reached selected-tool argument repair and
failed there as `invalid_tool_arguments`; no action or visual acquisition was
admitted.

Inspection found a protocol contradiction independent of GUI task semantics.
Native first-pass calls repaired through a flat structured payload rather than
the same native tool transport. For a single selected operation,
`_command_payload_type` returned the unconstrained base payload, so the schema
did not enforce the prompt's `operation_must_remain` rule. The corrective slice
keeps native repair native with exactly one offered ToolSpec and constrains a
single compact operation with Literal just like a multi-operation catalog.
Argument validation, one-repair budget and Runtime resolution remain unchanged.

## Stable entity-action envelope after safe violation tracing

The next clean diagnostic at `97918e1` demonstrated substantial stochastic
variance: a focused structural `visual-addition` run succeeded in two actions,
while the same-profile full five-case run was evidence-valid at only 1/5. The
new safe paths made three failures comparable: two selected `click` calls
violated `parameters.target`, and `observe_visual` violated
`parameters.assurance`.

This uncovered another shared protocol ambiguity. Action prose told the model
to copy E-refs, but the schema removed `target` for singleton verb groups and
Runtime inferred it privately. Observation prose exposed assurance even though
the tool accepted no arguments. The correction closes the public envelope:
every entity action explicitly requires a current public E-ref, while
observation is explicitly a no-argument selection whose assurance is supplied
by Runtime capability authority. No model-visible action ID, selector or
binding is exposed.

The same full run also selected four blue entities and then Submit, causing an
authoritative terminal failure. That is a distinct agent set-completeness
error. It remains open and is not converted into a color counter, singleton
heuristic, Submit rule or benchmark-specific verifier.

The clean corrected-SHA `b2f3dac` revalidation completed 5/5, succeeded 4/5,
and removed every argument violation and repair from the cohort. All four
successes consumed structural sources only. This is direct evidence that the
stable explicit-target envelope corrected the shared tool failure rather than
merely moving it.

The residual made two `RequestObservation` decisions, received no-information-
gain feedback and ended in the existing control-repetition guard without an
execution. The current persisted policy trace omits modality/assurance for a
successfully resolved observation decision. Until that typed public decision
is retained, evidence cannot attribute the repetition to model strategy or
acquisition output. The next admitted change is observability only.
