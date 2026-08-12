# Step 13 Unified Visual Binding Implementation

Status: `SUPERSEDED_IN_TRIGGER_AND_BINDING_AUTHORITY_SCOPE / HISTORICAL_RECORD`

Superseded by:
`docs/superpowers/plans/2026-08-12-dom-first-evidence-gated-vision-convergence.md`.
The visual adapter/currentness work below remains historical implementation
context. Configure-time initial augmentation, sticky post-action selection,
and coordinate binding before explicit DOM correspondence are not current
target behavior and must not be restored from this record.

Scope boundary: connect generic screenshot-region observation and pointer
activation through the Step-12 Unified source/fusion/route seam into the
BrowserGym target loop. Scroll, keypress, task-specific solvers and benchmark
slug routing remain out of scope.

## Work items

1. `completed` — inspect BrowserGym capture/projection/execution lineage and
   existing VisualRegionBinding/currentness/pointer contracts.
2. `completed` — define a bounded generic BrowserGym visual-source offer and
   trusted region-proposal intake over the same raw screenshot capture.
3. `completed` — create source-local visual entities and private current-epoch
   bindings, with explicit canonical correspondence only when trusted.
4. `completed` — feed BrowserGym structural and visual observations through
   Step-12 selection/fusion/ActionSpace/RouteSelector without a visual bypass.
5. `completed` — execute admitted visual bindings through typed pointer dispatch,
   preserving currentness, risk, confirmation and no-replay semantics.
6. `property_verified / live_pending` — add generic properties plus held-out visual witnesses and
   previously supported no-regression cases.
7. `completed` — align status/docs, commit, and stop before Step 14.

## Implemented owner path

```text
grounded observe_visual
-> typed RequestObservation(visual, weak)
-> BrowserGym structural(required) + visual(optional) selection
-> one shared raw capture
-> source-local VisualRegionBinding and route-free public entity
-> WorldFusion
-> existing ActionSpace / admission / RouteSelector
-> exact screenshot + viewport + page + episode currentness
-> BrowserGym mouse_click integer point
-> current post-action selection reacquisition
```

The visual proposer is injected explicitly into the environment/benchmark
runner. Without one, the visual offer and `observe_visual` tool do not exist.
Unsupported region primitives remain observable but create no binding. Public
world, tool and intent values contain no bbox, point or backend route.

Shared-capture screenshots are deduplicated by public image digest at the model
boundary and their canonical grounding regions are unioned, so one model call
receives one marked image rather than conflicting structural and visual copies.

## Superseded bounded live-path remediation

This implementation previously performed one optional visual augmentation
whenever the environment was configured with a bounded proposer and retained
visual selection after acquisition. That trigger policy was incorrect: provider
configuration is capability, not evidence. The replacement starts with DOM/AX,
recomputes a typed evidence gate for every current observation, and never makes
visual selection sticky.

Visual proposals distinguish observation from action authority. Public entities
may carry bounded `color`, `text`, `shape`, `row`, `column`, and `selected`
facts. In this historical version, an explicitly actionable point region above
the confidence floor was sufficient for a pointer binding. The replacement
additionally requires explicit unmatched visual-only identity. A region
corresponded to DOM merges into the DOM identity and gets no coordinate binding;
ambiguous or conflicting correspondence also remains non-executable.

`activate` evaluation now compares current public target semantics and the
before/after screenshot state. The validation boundary recomputes the change
against current evidence instead of trusting evaluator claims. A confirmed
unchanged click enters the existing strategy-feedback path, forbids identical
retry, and is zero-dispatch bounded by the existing progress controller.

Targeted evidence now records selected source modalities, proposer calls,
structural versus visual binding dispatch counts, selected public E-ref
role/label/state, and expected/observed effect evidence. The live gate applies
per-case route requirements rather than accepting one aggregate visual dispatch.

## Verification record

- `tests/test_browsergym_visual_binding.py`: shared capture, typed optional gap,
  visual request from a zero-action workspace, non-amplification, private route,
  exact stale zero-dispatch and pointer execution.
- BrowserGym/grounded/Unified/Visual focused suite: `326 passed, 22 skipped`
  before the final media-dedup and currentness additions; affected focused
  suites were rerun green afterward.
- Live held-out `grid-coordinate`/`click-pie*`/`click-shades`/`visual-addition`
  evidence is pending on the clean implementation SHA. The runner reuses the
  repository `.env`, pinned BrowserGym 3.12 runtime and MiniWoB source; the
  `glm-4.1v-thinking-flashx` multimodal profile is explicitly admitted for this
  diagnostic rather than inferred from the parent shell's exported variables.
- Step 14 scroll/keypress product code was not started.
