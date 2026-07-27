# M8.2A PR breadth rerun after V-PRB-3

This run is the clean committed PR breadth rerun after the narrow V-PRB-3
typed semantic action constraints repair.

It is diagnostic evidence only:

- official_score_claimed=false
- promotion eligible: no
- nightly/release claim: no
- formal benchmark score claim: no

## Run identity

- revision:
  `9b951ed968314aa7a139611d00256adb17b3cbb7`
- source tree: clean at run start
- source tree identity:
  `git-tree:74a5169368a6eda625479cd6d3ca6aeb1d6ad709`
- profile: `pr`
- planner profile: `strict-generalist`
- BrowserGym MiniWoB: `0.14.3`
- Playwright: `1.44.0`
- Python: `3.12.3`
- model provider/profile: local Ollama `qwen2.5:7b`
- output source:
  `/tmp/affordance-pr-breadth-9b951ed-20260727-235739`

## Matrix

- tasks: `click-button`, `enter-text`, `choose-list`, `click-dialog`,
  `click-button-sequence`, `form-sequence`
- seeds: `0`, `1`
- expected episodes: 12
- observed episodes: 12
- passed: 8
- failed: 4
- missing: 0
- unrun: 0
- invalidated: 0
- provider failures: 0

## Impact of V-PRB-3

V-PRB-3 closed the typed semantic action constraint cluster for the protected
PR breadth matrix. The prior strict-planner empty-clarification cases now
resolve from TaskSpec fields plus current typed `PlannerContext` affordance
summaries, without task-name, URL, selector, coordinate, prompt, budget,
Coordinator, StateKernel, PlannerPort, provider graph normalization, or
benchmark-specific changes.

The PR breadth ability gate remains failed:

- `invalid_provider_graph`: 4 official-failed episodes
  - `click-button-sequence:seed-0`
  - `click-button-sequence:seed-1`
  - `form-sequence:seed-0`
  - `form-sequence:seed-1`
- `planner_terminal_completion_guard`: 1 runtime guard observation
  - `enter-text:seed-1`
  - This episode has `official_reward=1.0`; it is not counted as an official
    BrowserGym failure, but it remains runtime evidence to classify before any
    promotion claim.

## Next selectable repair

next selectable repair: V-PRB-2 provider graph proposal normalization

Reason: after V-PRB-3, all remaining official-failed episodes are rejected
before TaskSpec creation by invalid provider obligation graphs in
multi-effect/button-sequence and form-sequence tasks. The next repair must be a
generic source-bound multi-effect proposal normalization/canonical compiler
slice with non-BrowserGym reproduction. It must not be a task-name, prompt-only,
budget-expansion, Coordinator, StateKernel, or benchmark-specific patch.

## Artifact hashes

- `browsergym-report.json`:
  `sha256:7e502c1fc7f686d6f2e4093ed4898026f8f34ded8ce27c7221cd09dd670b84c3`
- `matrix-metadata.json`:
  `sha256:ffbf4f7876eed83310ca742efaa233b0200d18bc8492c27fdb5938d62926ac5e`
- `browsergym-runtime-preflight.json`:
  `sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47`
- `ollama-gpu-preflight.json`:
  `sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d`
