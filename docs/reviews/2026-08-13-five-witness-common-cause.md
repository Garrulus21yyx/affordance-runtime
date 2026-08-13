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
