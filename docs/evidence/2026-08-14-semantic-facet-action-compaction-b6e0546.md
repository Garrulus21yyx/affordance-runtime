# Semantic facet action compaction focused evidence

Date: 2026-08-14

Status: `FOCUSED_LIVE_PASS / FULL_FIVE_PENDING / GENERALIZATION_OPEN`

## Implemented boundary

Current Runtime action options remain the sole legal action authority. The
model boundary now derives a bounded public semantic record for each target,
groups options by operation and parameter shape, hoists fields shared by all
members, and exposes only the smallest public facet subset that uniquely
distinguishes the members.

For two equal child controls under different public parents, the provider view
has this shape:

```json
{
  "operation": "click",
  "shared_target": {
    "role": "button",
    "label": "加入购物车",
    "within": {"role": "product"}
  },
  "choose_by": ["within.label"],
  "choices": ["MacBook Air", "MacBook Pro"]
}
```

The Actor returns only one enum value. Runtime maps that value through the
catalog's opaque binding table to the still-current `action_id`. It never
reconstructs Runtime state from the projected semantics. Verified domain grid
coordinates use the same generic state-facet rule, producing values such as
`(1,-2)`. E-ref remains only the deterministic fallback when the supported
public facets cannot distinguish candidates.

This adds no task parser, site vocabulary, benchmark branch, coordinate
executor argument, model call, memory, ActionSpace duplicate, or open
model-authored selector language.

## Verification

Local verification on the working tree:

```text
Ruff: passed
mypy src: passed (499 source files)
pytest: 2487 passed, 27 skipped
focused semantic-facet/grounding/architecture set: 84 passed
```

A clean synthetic snapshot of that exact implementation was created without
changing the branch:

```text
b6e054630c013fd1889d961becde83896290b3f7
```

Exactly one live case was then run: `miniwob-60-05`,
`browsergym/miniwob.grid-coordinate`, seed 7, provider/model
`zhipu/glm-4.1v-thinking-flashx`, `structure-first.v1`,
`grounded_tools.v2`.

```text
outcome: success
policy calls: 1
provider attempts: 1
model calls in the policy turn: 1
argument repairs: 0
tool resolution: accepted
GUI executions: 1
selected Runtime grounding: E38, semantic coordinate (1,-2)
Runtime task evaluation: complete
run_evidence_valid: true
total tokens: 3335
model latency: 5752.048 ms
```

Raw evidence:

- [`report.json`](runs/p5-m4-6-e-semantic-facet-grid-focused-b6e0546/report.json)
- [`miniwob-60-05.json`](runs/p5-m4-6-e-semantic-facet-grid-focused-b6e0546/miniwob-60-05.json)
- [`progress.json`](runs/p5-m4-6-e-semantic-facet-grid-focused-b6e0546/progress.json)

Artifact SHA-256 values:

- case: `c7fc8513952d6828cdbd323747eff00c9c92f978360d11b9e46cae57d45a4d1a`;
- progress: `e774e7f477725328409e2dc07eb83b69c21dc619c720d8664f70dedae4a49afa`;
- report: `cacf4febff71eece897e1063377eb1bc6bc9caef08d0d5724c2c4caa39cb9815`.

The preceding focused implementation recorded 4907 total tokens for the same
case and seed. The new run recorded 3335. This is a useful observed reduction,
not a latency/token guarantee or a controlled multi-run performance claim.

## SOTA comparison and inference boundary

[UI-TARS](https://arxiv.org/abs/2501.12326) standardizes GUI operations while
treating grounding/localization as a distinct capability. [GUI-Actor](https://arxiv.org/abs/2506.03143)
argues that generating raw coordinates as language tokens weakens
spatial-semantic alignment and instead grounds a semantic action through a
dedicated localization mechanism. The repository design is consistent with
that separation, but neither paper is evidence for this exact facet schema.
The engineering inference used here is narrower: let the general Actor choose
the meaningful public difference, and let Runtime retain exact entity,
currentness, binding and execution authority.

## Claim boundary

This evidence closes only the focused seed-7 coordinate regression for the new
compact semantic-choice representation. It does not establish five-case or
multi-seed generalization, shopping-site performance, arbitrary relation-depth
grounding, or a benchmark improvement. The full unchanged five-witness gate
remains pending under the convergence protocol.
