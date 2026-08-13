# Grounded-tool schema alignment evidence after `97918e1`

> Status: shared protocol contradiction reproduced; generic correction implemented, live revalidation pending

## Clean GLM-4.6V evidence

The safe violation-path instrumentation at clean
`97918e1f5eb25df0db41ba6bddd5bb37cea3da7f` produced both a focused positive
witness and a complete negative five-case run with the same
`grounded_tools.v2 / structure-first.v1` profile.

The focused `visual-addition` run succeeded in two structural actions:
`fill` followed by `activate`. It used two policy calls, two executions, zero
image inputs, zero visual sources, zero visual provider calls and zero schema
repairs. This proves the existing structural Unified World can expose enough
public evidence for this witness; neither a new DOM parser nor mandatory
vision is justified.

The subsequent clean five-case run completed all five cases with valid
evidence but succeeded only once:

| Case | Outcome | Relevant trace evidence |
|---|---|---|
| `miniwob-60-05` | success | one structural action; no image or repair |
| `miniwob-60-34` | structured output failure | selected `click`; violation path `parameters.target`; repaired operation changed |
| `miniwob-60-42` | task failed | four blue structural targets selected, then Submit; authoritative terminal failure |
| `miniwob-60-49` | structured output failure | selected `click`; violation path `parameters.target`; repair retained operation but remained invalid |
| `miniwob-60-60` | structured output failure | structural observation then `observe_visual`; violation path `parameters.assurance` |

Totals were 13 provider attempts, 16,841 tokens and 33,087.823 ms model
latency. No case sent an image or acquired a visual source. The score variance
between the focused success, earlier valid 4/5 runs and this 1/5 run means no
single run is closure evidence.

## Shared contract contradiction

The failures expose one generic model-facing contract defect. Entity tool
descriptions and the system prompt told the model to copy a public E-ref, but
`_verb_schema` omitted `target` whenever the current verb group contained one
entity. Runtime then silently inferred that singleton. Likewise observation
descriptions exposed an assurance value while the observation tool schema was
intentionally empty. The natural-language contract therefore encouraged
arguments that the machine schema rejected. A repair call received the same
contradictory workspace, explaining why its result was unstable.

The in-place correction makes every entity action use one stable envelope:

```text
semantic tool + required current public target E-ref + verb parameters
-> Runtime-owned ephemeral E-ref binding
-> private action_id
-> existing admission and execution path
```

There is no singleton inference. `click` always requires `target`; `fill`
always requires `target` and `text`; `select` always requires `target` and its
declared value. Observation remains a no-argument capability selection, and
its description now says that Runtime supplies the declared assurance. The
system prompt says to follow the selected tool schema and not invent arguments.

This is a protocol invariant, not a MiniWoB rule: no task ID, instruction
keyword, page label, selector, expected value, element count or benchmark
result enters production behavior. The existing AgentPolicy, Unified World,
grounded catalog, `RequestObservation`, Runtime binding and executor chain are
unchanged.

The multi-target color terminal failure is deliberately not patched in this
slice. It is evidence of stochastic set-completeness reasoning: the model
selected four blue entities and finalized while another requirement remained.
It needs separate agent-level evidence and cannot justify a Runtime color
counter or Submit guard.

Targeted verification for the correction is 15 grounded-protocol tests, Ruff
on the touched files and Mypy on both changed source modules.

## Clean corrected-SHA revalidation

The exact pushed correction `b2f3dace3f29a5012e970fb965f1564cdc401ada`
completed the five-case run with valid evidence, 4/5 success and an accepted
bounded gate. All three earlier argument failures disappeared: every case
recorded zero invalid arguments and zero repairs. Grid coordinate, both pie
witnesses and the five-member blue set succeeded entirely from structural
sources with zero image inputs and zero visual acquisitions.

The remaining `visual-addition` case made two `RequestObservation` decisions,
received typed `observation_no_information_gain` feedback, executed no action
and stopped at `no_progress_control_repetition`. The persisted trace shows that
the model context remained structural, but does not retain the modality of a
successfully resolved control decision. It therefore cannot yet distinguish a
repeated structural request from a visual request whose acquisition failed to
produce a visual source. That generic trace gap must be closed before another
behavior change is admitted.

Run totals were 13 provider attempts, 30,639 tokens and 102,726.072 ms model
latency. The result closes only the grounded argument-envelope defect. Agent
observation strategy and set/aggregate completion stability remain open; the
five witnesses still prohibit a generalization claim.

## Default-model focused result at `f28779f`

Subsequent live diagnostics returned to the project default
`glm-4.1v-thinking-flashx`. A focused clean-SHA `visual-addition` run at
`f28779f` completed with valid evidence and an authoritative terminal task
failure. The model immediately selected structural `fill` and then Submit:
two policy calls, two dispatched actions, zero images, zero visual sources,
zero argument violations and zero repairs.

This run did not exercise the new observation-decision trace because no
observation was requested. It nevertheless separates the remaining issue from
grounding and acquisition: the default model can select and execute the right
action kinds from the structural world, but its aggregate answer was not
accepted by the environment. Parameter values are intentionally absent from
the public trace, so the evidence cannot state which wrong value was entered.
No arithmetic rule or task-specific counter is admitted from this result.

Inspection of the existing native request found a separate generic context
defect: each ToolSpec is sent once through the provider-native `tools` field and
again as a full `tool_menu` inside the user JSON. Entity ref/role/label tuples
are also repeated from `grounding_index` inside every verb description. This is
non-authoritative duplicate projection and unnecessary context load. The next
slice will preserve one Unified World projection and one transport-owned tool
catalog: native transport uses native ToolSpecs, while compact transport keeps
the inline menu it actually needs.
