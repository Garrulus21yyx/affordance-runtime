# Structure-first control-context revalidation at `ccea342`

> Status: valid negative diagnostic; selected-operation repair correction pending

## Result

- implementation: `ccea342cc6a21398c531a5eb05252173e32b1641`
- model: `glm-4.6v`
- protocol/profile: `grounded_tools.v2 / structure-first.v1`
- completed: `5/5`
- succeeded: `4/5`
- run evidence valid: `true`
- bounded visual gate: rejected because one tool argument repair failed

The same four structural witnesses succeeded. `visual-addition` no longer
repeated an observation decision: the first call requested an observation with
zero image inputs, and the next policy call received the preserved no-gain
feedback and observation decision details. The second call failed inside
selected-tool argument repair before Runtime admitted another decision.

The trace reports `model_image_input_count=0` for both calls, so the new image
transport evidence is truthful. No visual source was acquired and no action was
executed.

## Shared repair defect

The initial response used the provider-native tool transport. After its
arguments violated the selected tool schema, the adapter changed transport for
repair: it asked the model for a broad flat structured payload. That payload's
`op` remained an unconstrained string for a one-operation repair and its base
schema exposed generic `target/text/value` fields rather than the selected
tool's exact input schema. The prompt said the operation was fixed while the
machine schema did not enforce it.

The admitted correction keeps native repairs on the same native tool-call
transport and offers exactly the already-selected `ToolSpec`. Compact-JSON
repairs retain their existing path but constrain even a single operation with a
Literal `op`. Retry count remains one; no new planner, adapter, task branch or
provider fallback is introduced.
