# M8.2B Strict Diagnostic Evidence

This directory publishes the compact, secret-free evidence for the strict
BrowserGym diagnostic executed on 2026-07-24.

- implementation git SHA: `351dbdfe0ec55da3c47e55a8b013cabe75d146b8`
- evaluation identity: `sha256:3aa97d5b485fdb942dcd5639c427fbc3d0b2e666bf211c58aa45d121d2c21d19`
- protocol: `three-layer-breadth-first-audit-v2`
- task manifest: `miniwob-action-family-v1`
- schedule: all 30 tasks at seed 0, then all 30 tasks at seed 1
- accounting: 60 observed, 19 passed, 41 failed, 0 unrun, 0 invalidated
- provider health: 251 calls, 0 provider failures, 0 rate-limit retries, 0 transient retries
- score boundary: `official_score_claimed=false`; this is diagnostic evidence,
  not a promoted nightly score

The report is complete and repair-selection-ready, but frozen nightly remains
held because 26 failure envelopes collapse unlike precondition, approval,
routing-target, and terminal-action failures into generic `RECOVERY`. Repair
must close that attribution gap before treating the largest cluster as one
owning-layer signal.

## File digests

- `browsergym-report.json`: `sha256:d0c15f95e514f6d77f69faf466cdd7253624022888e0c44c64aab9cb90f22396`
- `matrix-metadata.json`: `sha256:b726d886d12787115a7716a298895808ecd7e5ca8b40d208744c90898f898d96`
- `browsergym-runtime-preflight.json`: `sha256:71d5e7f52f7c51f635b09df06078381c1b188d1dcaf47b8fbe87d8b29a5c9b47`
- `ollama-gpu-preflight.json`: `sha256:511ca8f236e544aeee1fbffc25e82c620dc2c8c8fe23661fde4745d74d4e539d`

Full per-step traces and screenshots remain in the local run directory because
they are execution diagnostics, not stable repository fixtures. No `.env`, API
key, authorization header, or provider response body is included here.
