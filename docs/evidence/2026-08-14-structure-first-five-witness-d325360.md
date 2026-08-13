# Structure-first five-witness evidence at `d325360`

> Status: valid diagnostic; control-context remediation and revalidation open

## Configuration and result

- implementation: `d3253605eca60d3744a6aa10916e7b43cd3fe909`
- model: `glm-4.6v`
- action protocol: `grounded_tools.v2`
- perception profile: `structure-first.v1`
- completed: `5/5`
- succeeded: `4/5`
- run evidence valid: `true`
- visual authority gate accepted: `true`
- provider attempts: `17`
- total tokens: `32,546`
- model latency: `97,844.808 ms`

| Case | Capability witness | Outcome | Policy calls | Executions | Visual sources | Schema repairs |
|---|---|---|---:|---:|---:|---:|
| `miniwob-60-05` | grid coordinate | success | 1 | 1 | 0 | 0 |
| `miniwob-60-34` | pie/no-delay | success | 2 | 2 | 0 | 1 |
| `miniwob-60-42` | multi-target color | success | 8 | 8 | 0 | 0 |
| `miniwob-60-49` | pie | success | 2 | 2 | 0 | 1 |
| `miniwob-60-60` | visual addition | `no_progress_control_repetition` | 2 | 0 | 0 | 0 |

The four successful cases used only the structural source. No visual proposer,
point grounder, disambiguator, classifier, visual binding or visual source was
invoked. This is evidence that DOM/AX-first execution is viable for these
witnesses; it is not a broad generalization claim.

## Remaining failure

`visual-addition` did not reach `fill` or `click`. The model selected
`RequestObservation` twice. Both acquisitions returned only the already-current
structural source. The first transition returned typed
`observation_no_information_gain`, with retry disallowed and a strategy change
required. The second repeated observation decision was terminated by the
existing control repetition guard.

The canonical `AgentTurnView.semantic_summary` already retained the observation
subject, modality, assurance and reason. `grounded_tools.v2` discarded that
summary when constructing `previous_tool_result`, so the model saw that an
observation request had failed without seeing which modality it had requested.
The catalog also described every observation capability as a generic fresh
acquisition even when a current source of the same modality was already
present. These are shared context/protocol defects, not arithmetic-task rules.

## Evidence caveat found after the run

At `d325360`, diagnostic `selected_grounding.marked` came from the Context's
available screenshot marks, not from the adapter's actual image transport.
The structure-first adapter did not transmit an image while only a structural
source was current, but the trace still reported selected entities as marked.
The score, authoritative BrowserGym outcomes and zero visual-source/call metrics
remain valid. The marked-selection attestation is not valid for this run and is
being corrected before revalidation.

No task ID, task wording, expected answer, color-loop, repeated-leaf counter or
submit guard is admitted by the remediation.
