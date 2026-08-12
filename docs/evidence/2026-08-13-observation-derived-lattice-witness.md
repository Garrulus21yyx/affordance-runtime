# Observation-derived Lattice Witness — 2026-08-13

> **Lifecycle:** CURRENT BOUNDED LIVE EVIDENCE
> **Claim:** the named seed-7 grid correspondence regression is fixed;
> multi-seed and broader layout generalization remain unclaimed

## Contract exercised

The implementation does not branch on a MiniWoB task ID, assume a 5x5 grid, or
read an expected answer. From one current observation it:

1. groups executable DOM/SVG element centers by structural parent;
2. accepts only a complete, regularly spaced Cartesian product with one node
   per cell;
3. reads bounded visible numeric AX-label geometry and fits independent x/y
   value mappings, including the sign of the screen-down y relation;
4. publishes `grid_membership`, `grid_coordinate` and derivation confidence as
   observation facts on the existing DOM entity;
5. parses one explicit coordinate from the public TaskGoal and exact-closes the
   grounded model catalog only when one current `activate` action matches;
6. resolves the singleton tool to the unchanged DOM binding.

No point, bbox, selector, BID, model-produced coordinate, visual execution
binding or verifier answer enters the policy decision. Missing axes,
irregular/duplicate cells, ambiguous mapping and multiple candidate lattices
produce typed non-results and publish no coordinate.

## Clean live result

- implementation: `3ccb267c7958d2e02634f8aebcfe8284199e491d`;
- provider/model: `zhipu / glm-4.1v-thinking-flashx`;
- profile: `screenshot-ax.v1 / grounded_tools.v2`;
- witness: `miniwob-60-05`, `grid-coordinate`, seed `7`;
- outcome: terminal verified success;
- progress: `1/1`, `complete=true`;
- turns/model calls/provider attempts/browser steps: `1/1/1/1`;
- structural binding dispatches: `1`;
- auxiliary E-ref disambiguator calls: `0`;
- visual point-grounder calls: `0`;
- visual binding acquisitions/dispatches: `0/0`;
- invalid tool arguments: `0`.

The chosen display ref was `E25`, marked and backed by the current DOM entity.
Its derived membership was row `4`, column `3`, which maps to requested
Cartesian coordinate `(1,-2)`. An earlier successful implementation happened
to display the same logical node as `E24`; this difference is positive evidence
that volatile SoM numbering is no longer the relation authority.

Unit/invariant evidence covers AX/DOM order permutation, inverse y orientation,
missing axes, duplicate cells, multiple lattices, bounded task parsing, exact
singleton closure and DOM-only closure without screenshot marks. Final full
repository verification is `2379 passed, 24 skipped`.

## Artifact integrity

- `report.json`:
  `sha256:0f3db7b51b416ee10393682689c4db7d81aa77dbbd33abb0f01db0fbe4957fdb`;
- `progress.json`:
  `sha256:e79418fc85d61a6b00d9d51a2871abfb7e20627b250ea8f24328dd722a0284f5`;
- atomic case artifact:
  `sha256:d31720b56b8e8084f57ede6a58b2b7c207b450649a5377f5e749f3a2c954ea12`.

This single seed/witness is sufficient to falsify the prior claim that the main
Agent must perform 25-way SoM correspondence, but it is not a performance or
generalization benchmark.
