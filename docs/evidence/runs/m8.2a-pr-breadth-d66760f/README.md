# M8.2A PR Breadth Diagnostic at d66760f

Date: 2026-07-27

This is a local diagnostic protected cross-family / PR breadth run. It is
negative evidence, not a promotion or score claim.

## Run identity

- git SHA: `d66760f76bb4668f610d2ebfac2c8ba0bf83c71a`
- source tree digest: `sha256:873d29a34b954b1234407db0069d1f0dacda646d79b00a2e9ae4f7d98260071c`
- working tree clean: yes
- BrowserGym MiniWoB: `0.14.3`
- Playwright: `1.44.0`
- Python: `3.12.3`
- runtime Python: `/home/yang/.venvs/affordance-browsergym-py312/bin/python`
- model provider: local Ollama
- model: `qwen2.5:7b`
- planner profile: `strict-generalist`
- profile: `pr`
- seeds: `0`, `1`
- selected tasks: `click-button`, `enter-text`, `choose-list`,
  `click-dialog`, `click-button-sequence`, `form-sequence`
- output directory: `/tmp/affordance-pr-breadth-d66760f-20260727-201632`

## Preflight

- BrowserGym runtime preflight: ready
- Ollama GPU preflight: ready
- GPU: NVIDIA GeForce RTX 3080
- model digest: `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`

## Result

- expected episodes: 12
- observed episodes: 12
- missing: 0
- unrun: 0
- invalidated: 0
- provider failures: 0
- rate-limit retries: 0
- transient retries: 0
- passed: 0
- failed: 12
- official success rate: 0.0
- mean official reward: 0.0
- `official_score_claimed=false`
- promotion eligible: no

## Failure clusters

The run completed and produced clusterable ordinary runtime failures. It did
not fail due to provider or BrowserGym provisioning.

| Root layer | Signature | Episode count | Episodes |
| --- | --- | ---: | --- |
| CONTRACT / FIELD_BINDING | `schema_incompatible` | 1 | `click-button:seed-1` |
| INTENT / PLANNING | `intent_compilation_rejected` | 6 | `click-button-sequence:seed-0`, `click-button-sequence:seed-1`, `click-dialog:seed-0`, `enter-text:seed-0`, `form-sequence:seed-0`, `form-sequence:seed-1` |
| INTENT / PLANNING | `planner_waiting_clarification` | 5 | `choose-list:seed-0`, `choose-list:seed-1`, `click-button:seed-0`, `click-dialog:seed-1`, `enter-text:seed-1` |

## Artifact digests

- report: `/tmp/affordance-pr-breadth-d66760f-20260727-201632/browsergym-report.json`
  - sha256: `8eb97464b390b55c2cf65449f2d3fa2517d526c7588709a2cd333cc4faca521c`
- matrix metadata:
  `/tmp/affordance-pr-breadth-d66760f-20260727-201632/episodes/matrix-metadata.json`
  - sha256: `cd8061c28215743d9e1ff6a14d30ebf4807e4134e31162898d245279361b2d81`
- BrowserGym runtime preflight:
  `/tmp/affordance-pr-breadth-d66760f-20260727-201632/browsergym-runtime-preflight.json`
  - sha256: `71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47`
- Ollama GPU preflight:
  `/tmp/affordance-pr-breadth-d66760f-20260727-201632/ollama-gpu-preflight.json`
  - sha256: `511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d`

## Governance interpretation

This disproves PR breadth readiness for the current line. SG7 targeted
confirmation remains valid only for its original 2-task x 2-seed scope. The
next repair must be generic and owned by the reported root layer. The evidence
points first to INTENT / PLANNING, with one separate CONTRACT / FIELD_BINDING
schema-incompatibility case. This result does not authorize task-name, URL,
selector, coordinate, Prompt-only, budget-expansion, or benchmark-family
branches.
