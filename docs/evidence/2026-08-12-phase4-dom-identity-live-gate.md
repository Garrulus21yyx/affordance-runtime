# Phase-4 DOM-Identity Live Gate — 2026-08-12

> **Lifecycle:** CURRENT BOUNDED LIVE EVIDENCE
> **Claim:** architecture/authority gate only; performance and generalization
> remain unclaimed

This frozen record remains exact for `331ac0d`. Its residual diagnosis was
superseded by the later
[visual-value and multi-target remediation record](2026-08-12-visual-value-and-multitarget-remediation.md);
the original measurements below are intentionally unchanged.

## Frozen run

- implementation: `331ac0d94af0db77e0ebaabfb4891e3f9d279e2d`;
- provider/model: `zhipu / glm-4.1v-thinking-flashx`;
- profile: `screenshot-ax.v1 / grounded_tools.v2`;
- BrowserGym MiniWoB seed: `7`;
- clean detached worktree, output outside the repository;
- durable progress: `5/5`, `complete=true`;
- result: evidence-valid `3/5`;
- outcome counts: `success=3`, `task_failed=1`, `case_timeout=1`;
- architecture acceptance: `true`, errors `[]`.

## Per-case result

| Case | Witness | Outcome | Structural dispatches | E-ref chooser | Point calls | Invalid tool args |
|---|---|---:|---:|---:|---:|---:|
| `miniwob-60-05` | `grid-coordinate` | success | 1 | 1/1 selected | 0 | 0 |
| `miniwob-60-34` | `click-pie-nodelay` | success | 2 | not needed | 0 | 0 |
| `miniwob-60-42` | `click-shades` | case timeout | 9 | 10/10 selected | 0 | 0 |
| `miniwob-60-49` | `click-pie` | success | 2 | not needed | 0 | 0 |
| `miniwob-60-60` | `visual-addition` | task failed | 4 | not applicable | 0 | 0 |

Across all five witnesses, `visual_binding_acquired_count=0` and
`visual_binding_dispatch_count=0`. Every dispatched GUI action used a current
structural BrowserGym binding. The main Agent trace records the selected public
E-ref and semantic action; it contains no point, bbox, selector, BID or backend
node identity.

The grid witness also received a separate real provider probe before the
frozen run. For instruction `Click on the grid coordinate (1,-2).`, the revised
reading-order/external-label SoM projection let GLM select `E24`, whose current
DOM bbox was `(157,277,14,14)`. Runtime retained one DOM binding and made zero
point calls. The frozen run then completed the same witness successfully.

## Residual performance gaps

`click-shades` made nine valid, effect-confirmed DOM dispatches and had no
schema or coordinate failure, but the case watchdog expired. Its current path
performs a gated E-ref model call and a second main-policy model call for each
atomic target. The next bounded optimization is to combine E-ref choice and
semantic operation in one main multimodal decision, not to restore point
grounding.

`visual-addition` used valid structural textbox and submit identities but
submitted the wrong visually derived value. This is visual value extraction /
reasoning quality, not target identity or pixel execution. No provider or
Runtime branch should convert that failure into coordinate authority.

## Artifact integrity

- `report.json`:
  `sha256:85714f3023056fdbf1f9bfaec16e88e74baa0fbd5981050800e1f5ff728d6004`;
- `progress.json`:
  `sha256:be2e0e6a144d1de64e87917f00477adce78910a31b00f07a1235b17131c47d9c`;
- atomic case hashes, in case-ID order:
  `ebb7365d2e8c5f8230b090a098032e420c4b64661182186605a693564455944f`,
  `13d7c91e9c7f30e137816426208624e599dd88d132cbfe0a803ba24276a4f984`,
  `1e617b8539c31345b31bc6091f0cf4b408da188c6edf20a31838164ef814b5de`,
  `33b0c9271080fa62cd4dd5640e43ad15da2fe9701d3e940cd2bdb7214a0e431e`,
  `ec485ea9222291e9c187304d02ae012255576affbdc31ee2d71277361edfa9c5`.

The report sets `generalization_claim_prohibited=true`. This five-case result
does not attest MiniWoB-wide, multi-seed or external-GUI performance.
