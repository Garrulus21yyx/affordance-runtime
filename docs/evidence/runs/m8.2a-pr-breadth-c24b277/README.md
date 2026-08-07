# M8.2A PR breadth rerun after V-PRB-2

This run is the clean committed PR breadth rerun after the narrow V-PRB-2
provider graph proposal normalization repair.

It is diagnostic evidence only:

- official_score_claimed=false
- promotion eligible: no
- nightly/release claim: no
- formal benchmark score claim: no

## Run identity

- revision:
  `c24b277a93712191c626a1db87cc1f3fc1c166bd`
- source tree: clean at run start
- source tree digest:
  `sha256:0c37e5abf281acb8a01f102492da1bb5e995c895607aaf2486cbc54eb652bc18`
- evaluation identity:
  `sha256:fe18dec7bfc35ab81dd324bde407c2e5d68fd1c5b92b5a07b1f31e3ddd851737`
- profile: `pr`
- planner profile: `strict-generalist`
- BrowserGym MiniWoB: `0.14.3`
- Playwright: `1.44.0`
- Python: `3.12.3`
- model provider/profile: local Ollama `qwen2.5:7b`
- output source:
  `/tmp/affordance-pr-breadth-c24b277-20260728-000914`

## Matrix

- tasks: `click-button`, `enter-text`, `choose-list`, `click-dialog`,
  `click-button-sequence`, `form-sequence`
- seeds: `0`, `1`
- expected episodes: 12
- observed episodes: 12
- passed: 8
- failed: 4
- runtime failed: 5
- missing: 0
- unrun: 0
- invalidated: 0
- provider failures: 0

## Impact of V-PRB-2

invalid_provider_graph closed: yes

The four prior official-failed invalid provider graph episodes no longer fail
before TaskSpec creation. Runtime now canonicalizes source-bound multi-effect
drafts with incomplete provider graphs through Runtime-owned requested-effect
graph construction, without copying provider graph ids or granting provider
READY authority.

The PR breadth ability gate remains failed:

- `planner_waiting_clarification`: 2 official-failed episodes
  - `click-button-sequence:seed-0`
  - `click-button-sequence:seed-1`
- `entry_action_family_unavailable`: 2 official-failed episodes
  - `form-sequence:seed-0`
  - `form-sequence:seed-1`
- `planner_terminal_completion_guard`: 1 runtime guard observation
  - `enter-text:seed-1`
  - This episode has `official_reward=1.0`; it is not counted as an official
    BrowserGym failure, but it remains runtime evidence to classify before any
    promotion claim.

## Next selectable repair

next selectable repair: V-PRB-5 task planning / planner constraint follow-up

Reason: after V-PRB-2, the remaining official failures are no longer
pre-TaskSpec provider graph construction failures. They have advanced to
downstream planning/admission failures: sequence-button planning asks for
clarification after one click, and form-sequence task planning rejects because
the expected entry action family is unavailable. The next repair must start
with non-BrowserGym reproduction and exact owner classification. It must not be
a task-name, prompt-only, budget-expansion, Coordinator, StateKernel,
PlanningRequest, or benchmark-specific patch.

## Artifact hashes

- `browsergym-report.json`:
  `sha256:8072539992ad0b197cbd46102134c323788e34e51494d98766402ac8b66d9547`
- `matrix-metadata.json`:
  `sha256:e12f5ed5c483403cac9ad0334c4d6602483400362751dff554c0f9a712ad9b1b`
- `browsergym-runtime-preflight.json`:
  `sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47`
- `ollama-gpu-preflight.json`:
  `sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d`
