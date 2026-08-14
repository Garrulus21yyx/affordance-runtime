# Grid semantic selection key focused evidence

Date: 2026-08-14

Status: `FOCUSED_LIVE_PASS / FIVE_CASE_REVALIDATION_PENDING / GENERALIZATION_OPEN`

## Contract change

The action candidate remains a one-way projection of the current Runtime
ActionSpace, but its model-call handle no longer has to be an opaque E-ref when
the public target already owns a unique semantic coordinate. The seed-7 grid
candidate is rendered as:

```json
{
  "operation": "click",
  "target": {
    "ref": "E38",
    "selection_key": "semantic-grid-coordinate:x=1,y=-2",
    "state": {"semantic_grid_coordinate": [1, -2]}
  }
}
```

The tool accepts `selection_key`; `ref` remains grounding evidence and is not a
second callable identity. Runtime maps the admitted current key to the existing
opaque action binding. This adds no task parser, coordinate oracle, provider
call, alternate ActionSpace or execution route.

The binder now preserves its explicit task-first section order instead of
alphabetically sorting the provider JSON. Facts already represented by current
action candidates are omitted only from the grounded actor rendering. The
canonical `AgentContext.world` remains unchanged for evaluators and other
consumers, while the rendered section preserves its canonical total and marks
the omitted projection as truncated. All 25 current action candidates remain.

## Negative migration witness

The first focused snapshot, `1ce6a5c550ce5517bd8008a9662d764a0a384715`,
ended before GUI execution with one `structured_output_failure`, two provider
attempts and one schema repair. The cause was deterministic: the dynamic
payload `Literal` admitted the semantic selection keys, but the superseded base
validator independently required every target to match `E[0-9]+`. Therefore no
semantic key could pass local validation, including after repair.

The fix removed that duplicated representation rule. The dynamic current-menu
`Literal` remains the sole candidate-membership authority; the base field only
bounds length and control characters. The negative raw evidence is retained in
[`runs/p5-m4-6-e-grid-selection-key-validator-negative-1ce6a5c/`](runs/p5-m4-6-e-grid-selection-key-validator-negative-1ce6a5c/).

## Intermediate positive witness and full-suite correction

The first corrected snapshot, `7101a847ef8320a962e4395227403c1a490be4c1`,
passed the focused live case, but full verification then found that its fact
deduplication had been applied to canonical `AgentContext.world`. Thirteen
tests sharing the completion/evidence consumer failed. That snapshot is an
intermediate positive witness, not final implementation evidence. The fix
moved deduplication to the grounded provider projection and restored canonical
facts for every other consumer. The resulting full suite passed:

```text
2489 passed, 24 skipped
Ruff: passed
mypy src: passed (499 source files)
```

## Exact-final focused live result

The final clean working-tree snapshot was
`0c36f67758459e99679281a9df3909bae380c5c7`. Exactly one declared case was run:
`miniwob-60-05`, `browsergym/miniwob.grid-coordinate`, seed 7, default
`glm-4.1v-thinking-flashx`, `structure-first.v1`, `grounded_tools.v2`.

```text
outcome: success
policy calls: 1
provider attempts: 1
schema repairs: 0
invalid tool arguments: 0
GUI executions: 1
structural binding dispatches: 1
selected grounding: E38, semantic coordinate (1,-2)
Runtime task status: complete
run_evidence_valid: true
```

The positive raw evidence is retained in
[`runs/p5-m4-6-e-grid-selection-key-focused-final-0c36f67/`](runs/p5-m4-6-e-grid-selection-key-focused-final-0c36f67/).

Artifact SHA-256 values:

- case: `9c2545e2410ef89e801b0e21578c2dc9c0230f7d43d75f01587029d8562c0103`;
- progress: `ec557d30a011558adcef036d3be5c16043db9f1cceea1fd5847078f1051b85e1`;
- report: `4883887ead6602dd2065c55f35cc608fc3ee004178abf4a4f7054614217b6787`.

## Claim boundary

This closes only the observed seed-7 semantic-coordinate-to-current-action
binding regression. It does not establish five-case performance, multi-seed
generalization, aggregate reasoning, or latest-transition effectiveness. The
next live evidence step remains one unchanged five-witness run; this focused
success must not be counted as a favorable replacement for that gate.
