# ODG-1 Obligation Execution-Role Audit

Baseline: `fa1037e2788261a1c76edce96a80b02df1461a3d`

This audit supports `docs/change-admission/odg-0-obligation-driven-progress-architecture.yaml`.
It does not change production behavior or public `TaskSpec` schema. Its purpose
is to classify existing canonical obligations into runtime execution roles
before any obligation-ledger or finish-gate migration.

Evidence sources:

- Clean PR breadth evidence at `docs/evidence/runs/m8.2a-pr-breadth-407133d/`
  and raw traces under
  `/tmp/affordance-pr-breadth-407133d-20260728-164614/artifacts/runs/`.
- Clean SG7 targeted evidence at `docs/evidence/runs/m8.2a-sg7-3d44a9d/`
  and raw traces under
  `/tmp/affordance-sg7-3d44a9d-20260727-184535/artifacts/runs/`.

## Role definitions

| Role | Enters progress ledger | Runtime use |
| --- | --- | --- |
| `PRECONDITION` | no | Verify before contract execution or preflight; failure blocks/repairs the action, not task progress. |
| `PROGRESS_EFFECT` | yes | A non-terminal requested effect that unlocks dependent obligations after verifier-backed evidence. |
| `TERMINAL_EFFECT` | yes | A requested effect required for task completion. |
| `EVIDENCE_ONLY` | no | Evidence requirement or verifier constraint that narrows proof but is not itself progress. |

If the role cannot be derived from canonical graph fields and source lineage
without task names, URLs, selectors, coordinates, or benchmark families, the
role decision is `fail_closed_pending_rule`.

## Audited obligation samples

### enter-text

Source: `browsergym-generalist-enter-text-seed-0`

| Field | Value |
| --- | --- |
| objective | `Enter 'Myron' into the text field and press Submit.` |
| obligation_id | `obligation:9506b551d2edefa86bd35630` |
| source_unit_ids | `browsergym-generalist-enter-text-seed-0:source:request:whole` |
| requested_effect | text field has changed to the requested text, then submit |
| kind | `effect` |
| relation | `has_changed` |
| blocking | `true` |
| terminal | `true` |
| derived_execution_role | `TERMINAL_EFFECT` |
| reason | The user-requested durable outcome is the text entry. Current schema also treats it as terminal because no distinct canonical submit obligation exists in this sample. |
| expected_runtime_owner | post-verification obligation attributor, then Coordinator commit |

Audit note: earlier rejected V-PRB-6B attempts showed that broadening concrete
text evidence in the BrowserGym adapter is not sufficient. The standard path
should attribute verifier-backed text facts to this obligation, not infer
completion from receipt success or external reward.

### form-sequence

Source: `browsergym-generalist-form-sequence-seed-0`

| obligation_id | source_unit_ids | requested_effect | kind | relation | blocking | terminal | derived_execution_role | reason | expected_runtime_owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `obligation:e515e21388bc6a4f91fca0a7` | `browsergym-generalist-form-sequence-seed-0:source:request:clause:0` | select 7 with the slider | `effect` | `has_changed` | `true` | `false` | `PROGRESS_EFFECT` | It is a requested non-terminal effect and unlocks the checkbox obligation. | post-verification obligation attributor |
| `obligation:847ff8b7ec9e70c6612c7cf8` | `browsergym-generalist-form-sequence-seed-0:source:request:clause:0` | click the 3rd checkbox | `effect` | `has_changed` | `true` | `false` | `PROGRESS_EFFECT` | It is a requested non-terminal effect with dependency on the slider effect. | post-verification obligation attributor |
| `obligation:a04b4a88e7983c0781e57c3b` | `browsergym-generalist-form-sequence-seed-0:source:request:clause:0` | hit Submit | `effect` | `has_changed` | `true` | `true` | `TERMINAL_EFFECT` | It is the final requested effect and depends on checkbox progress. | post-verification obligation attributor |

Audit note: this is the residual V-PRB-6A shape. The rejected pre-action
TaskPlan progress target foundation should not be expanded. The next authority
must bind post-verification facts to canonical obligations.

### click-button-sequence

Source: `browsergym-generalist-click-button-sequence-seed-0`

| obligation_id | source_unit_ids | requested_effect | kind | relation | blocking | terminal | derived_execution_role | reason | expected_runtime_owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `obligation:46d89a34d3a0004b1603b9ae` | `browsergym-generalist-click-button-sequence-seed-0:source:request:clause:0` | click button ONE | `effect` | `is_completed` | `true` | `false` | `PROGRESS_EFFECT` | It is the first requested click effect and unlocks the second click. | post-verification obligation attributor |
| `obligation:bc2b74eaee987f1cc130f773` | `browsergym-generalist-click-button-sequence-seed-0:source:request:clause:0` | click button TWO | `effect` | `is_completed` | `true` | `true` | `TERMINAL_EFFECT` | It is the final requested click effect. | post-verification obligation attributor |

### choose-list

Source: `browsergym-generalist-choose-list-seed-0`

| Field | Value |
| --- | --- |
| objective | `Select Ertha from the list and click Submit.` |
| obligation_id | `obligation:b8398a288c7e4b05caa6416a` |
| source_unit_ids | `browsergym-generalist-choose-list-seed-0:source:request:clause:0` |
| requested_effect | selected option is available / selectable under the current canonical form |
| kind | `predicate` |
| relation | `is_available` |
| blocking | `true` |
| terminal | `true` |
| derived_execution_role | `fail_closed_pending_rule` |
| reason | The current canonical graph collapses a select-and-submit instruction into a terminal availability predicate. This may describe an action precondition rather than the requested selected-value effect. ODG must not treat lexical availability as terminal progress without a source-derived role rule. |
| expected_runtime_owner | ODG-1 role rule, then either precondition validator or post-verification obligation attributor |

### click-dialog

Source: `browsergym-generalist-click-dialog-seed-0`

| Field | Value |
| --- | --- |
| objective | `Close the dialog box by clicking the 'x'.` |
| obligation_id | `obligation:694d1e54fbbce5c9817cade3` |
| source_unit_ids | `browsergym-generalist-click-dialog-seed-0:source:request:clause:0` |
| requested_effect | close control is available under the current canonical form |
| kind | `predicate` |
| relation | `is_available` |
| blocking | `true` |
| terminal | `true` |
| derived_execution_role | `fail_closed_pending_rule` |
| reason | The user-requested effect is closing the dialog, while the current graph records availability of the close button. Availability is normally a precondition/evidence fact, not task completion. |
| expected_runtime_owner | ODG-1 role rule, then precondition validator or a corrected terminal close effect |

### enter-date

Source: `browsergym-generalist-enter-date-seed-0`

| Field | Value |
| --- | --- |
| objective | `Enter 02/04/2012 as the date and hit submit.` |
| obligation_id | `obligation:c5e81157b805c2515f88e3ee` |
| source_unit_ids | `browsergym-generalist-enter-date-seed-0:source:request:clause:0` |
| requested_effect | date field equals `02/04/2012` |
| kind | `effect` |
| relation | `equals` |
| blocking | `true` |
| terminal | `true` |
| derived_execution_role | `TERMINAL_EFFECT` |
| reason | The exact literal date value is a requested effect and can be verified after action. |
| expected_runtime_owner | post-verification obligation attributor |

### text-transform

Source: `browsergym-generalist-text-transform-seed-0`

| Field | Value |
| --- | --- |
| objective | `Type the text below into the text field and press Submit.` |
| obligation_id | `obligation:4623f3621026bc4ffeea1956` |
| source_unit_ids | `browsergym-generalist-text-transform-seed-0:source:request:clause:0` |
| requested_effect | text field has changed to the page-sourced text |
| kind | `effect` |
| relation | `has_changed` |
| blocking | `true` |
| terminal | `true` |
| derived_execution_role | `TERMINAL_EFFECT` |
| reason | The typed page-sourced value is the requested durable effect; model/agent text is not authority for the literal value. |
| expected_runtime_owner | post-verification obligation attributor |

## Special decision: submit button availability

The `enter-text:seed-1` residual before the V-PRB-6B close exposed a required
read-only subgoal shaped as `submit_button is available`. Under the ODG model,
that fact must not be deleted from an authoritative plan and must not become a
second completion authority through TaskPlan. The role audit decision is:

```yaml
submit_button_is_available:
  current_schema_shape: blocking terminal predicate in some TaskPlan paths
  odg_role: fail_closed_pending_rule
  preferred_classification: PRECONDITION
  alternative_if_user_source_explicitly_requests_availability: PROGRESS_EFFECT
  prohibited:
    - delete required obligation/subgoal
    - complete from external reward
    - complete from receipt success
    - broaden BrowserGym ACTIVE_SUBGOAL evidence
```

This means the next production slice must first define a source-derived role
rule. If `submit_button is available` is merely necessary before clicking
Submit, it is a precondition and does not enter the progress ledger. If a user
request actually asks to make a control available/visible, it may become a
progress effect, but only with independent observation evidence.

## ODG-1 completion criteria

- The audited PR-breadth and SG7 obligations have an explicit role decision or
  a fail-closed pending rule.
- No role is inferred from task name, URL, selector, coordinate, or benchmark
  family.
- Ambiguous availability predicates are not allowed to complete task progress
  until the source-derived role rule is implemented.
- The next production slice must start with non-BrowserGym REDs for role
  projection, ready-obligation scheduling, or post-verification attribution.
