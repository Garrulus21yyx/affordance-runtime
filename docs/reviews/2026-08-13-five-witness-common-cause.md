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
to add task-shaped prompts or more schema branches is prohibited. The objective
semantics stay reopened pending an architecture decision between:

- retaining the DSL only as an explicitly requested advanced capability; or
- shrinking the existing objective role to bounded agent-authored plan/working
  state while Runtime retains only lifecycle, authority and execution checks.

That decision must reuse the existing proposer/AgentLoop boundary or delete it;
it does not authorize a parallel planner or another execution chain.
