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
