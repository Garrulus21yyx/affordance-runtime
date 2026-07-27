# M8.2A PR breadth rerun after V-PRB-1

This run is the clean committed PR breadth rerun after the narrow
V-PRB-1 invalid coverage audit handling repair.

It is negative diagnostic evidence only:

- official_score_claimed=false
- promotion eligible: no
- nightly/release claim: no
- formal benchmark score claim: no

## Run identity

- revision:
  `d40f8f1792e85f391fe6c94dd88f9b5e0235d481`
- source tree: clean
- source tree digest:
  `sha256:e3ac0667624c526cbcb592bd6dbaf0bba8ca781c84222449ec4b69489efde377`
- profile: `pr`
- planner profile: `strict-generalist`
- BrowserGym MiniWoB: `0.14.3`
- Playwright: `1.44.0`
- Python: `3.12.3`
- model provider/profile: local Ollama `qwen2.5:7b`
- output source:
  `/tmp/affordance-pr-breadth-d40f8f1-20260727-234649`

## Matrix

- tasks: `click-button`, `enter-text`, `choose-list`, `click-dialog`,
  `click-button-sequence`, `form-sequence`
- seeds: `0`, `1`
- expected episodes: 12
- observed episodes: 12
- passed: 0
- failed: 12
- missing: 0
- unrun: 0
- invalidated: 0
- provider failures: 0

## Impact of V-PRB-1

V-PRB-1 closed the invalid coverage-audit veto mechanism for this matrix.
The prior `click-dialog:seed-0` and `enter-text:seed-0`
`coverage_review_invalid_quote` failures no longer stop intent compilation.
Both now reach the same downstream `planner_waiting_clarification` mechanism as
their paired seeds.

The PR breadth ability gate remains failed:

- `planner_waiting_clarification`: 7 episodes
- `intent_compilation_rejected`: 4 episodes
- `schema_incompatible`: 1 episode

## Next selectable repair

next selectable repair: V-PRB-3 typed semantic action constraints

Reason: it is now the largest cluster and includes the two episodes V-PRB-1
advanced past invalid coverage audit handling. V-PRB-2 remains the next
alternative if the team prioritizes graph proposal normalization first.

## Artifact hashes

- `browsergym-report.json`:
  `sha256:f483d99383cdc8213da80b591927ff1970e02e0ed77956e63325f44c45d3fa97`
- `matrix-metadata.json`:
  `sha256:3a399b79c12fd4be3027186375f595a198965c7189c5672a5d1987df5f7155a8`
- `browsergym-runtime-preflight.json`:
  `sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47`
- `ollama-gpu-preflight.json`:
  `sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d`
