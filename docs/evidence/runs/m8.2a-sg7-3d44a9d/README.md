# M8.2A SG7 Targeted Protected-Family Evidence

This directory publishes the compact, secret-free evidence for the SG7
targeted protected-family confirmation executed on 2026-07-27 after the generic
intent/planning repair was committed.

- implementation git SHA: `3d44a9d222decd1de272d7a4d3eb14b025a8738a`
- evaluation identity: `sha256:d09d403f6976b246ff614f5f288e8bc7a7bca6719529e934919973ade608309d`
- source tree digest: `sha256:cb4dd50f8cf2376fce30673d813e1ca895f44b67a2c46860022902c163fa8403`
- worktree state: clean
- protocol: `three-layer-breadth-first-audit-v2`
- task manifest: `miniwob-action-family-v1`
- selected tasks: `enter-date`, `text-transform`
- selected seeds: `0`, `1`
- accounting: 4 scheduled, 4 observed, 4 passed, 0 failed, 0 unrun, 0 invalidated
- provider health: 16 calls, 0 provider failures, 0 rate-limit retries, 0 transient retries
- runtime health: 0 runtime failures, 0 unsupported actions
- score boundary: `official_score_claimed=false`; this is targeted SG7
  protected-family confirmation, not PR breadth, not nightly/release evidence,
  and not a promoted benchmark score.

The run confirms that the generic repair closes the previously observed
protected-family INTENT / PLANNING failures for this narrow SG7 matrix. It does
not prove cross-family planner generalization or M8.2B promotion readiness.

## File digests

- `browsergym-report.json`: `sha256:cea708f3971a85bf231448b5f5cdab182629d54c2449694c8c69cb9f0ff84eed`
- `matrix-metadata.json`: `sha256:0ad2bb171b6d8d41aa2c827057e07ba2a8c185fcc6c45cfba10d0ce0936171a1`
- `browsergym-runtime-preflight.json`: `sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47`
- `ollama-gpu-preflight.json`: `sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d`

Full per-step traces and screenshots remain in the local run directory because
they are execution diagnostics, not stable repository fixtures. No `.env`, API
key, authorization header, or provider response body is included here.
