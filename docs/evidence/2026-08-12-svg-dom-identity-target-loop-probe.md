# SVG DOM Identity Target-Loop Probe — 2026-08-12

> **Lifecycle:** CURRENT IMPLEMENTATION EVIDENCE
> **Scope:** BrowserGym structural projection, E-ref selection, private DOM
> binding, currentness and execution; no model-quality/generalization claim

## Environment

- project `.env` loaded without printing credentials;
- interpreter:
  `/home/yang/.venvs/affordance-browsergym-py312/bin/python`;
- BrowserGym MiniWoB `0.14.3`, Playwright `1.44.0`;
- source URL: `http://127.0.0.1:18888/miniwob/`;
- seed: `7`.

The target-loop probe injected an exploding point-grounder fixture. Any point
call would therefore fail the run. For `grid-coordinate`, a bounded diagnostic
chooser selected one offered E-ref from public instruction plus candidate
geometry; it did not return a coordinate or access a private BID. This isolates
the Runtime identity route from provider/model quality.

## Results

| Witness | Structural observation | Agent-side selection | Runtime execution | Result |
|---|---|---|---|---|
| `grid-coordinate` | 25 visible clickable SVG circles, each with private BID and screenshot-aligned bbox | one supplied E-ref | `activate/click` through BrowserGym identity | `success`, point calls `0` |
| `click-pie` initial | one canonical `+` opener after tiny/low-visibility/overlapping SVG filtering | semantic label/E-ref | DOM `click` | menu expanded, point calls `0` |
| `click-pie` expanded | labels `Z, i, Y, 0, V, q, -`, each backed by DOM identity | label `0`/E-ref | DOM `click` | `success`, point calls `0` |

Both task results came from the official BrowserGym verifier. Direct backend
probing independently produced reward `1.0` for the same grid identity and the
two-step pie identity sequence.

## Verified properties

1. BrowserGym `tags_to_mark="all"` assigns BIDs to actionable SVG child nodes
   that the default `standard_html` marking omits.
2. CDP DOMSnapshot clickability plus AX records project those nodes as ordinary
   `clickable -> activate/click` entities; public world/action values contain no
   BID, selector, bbox, point or backend node identity.
3. BrowserGym-scaled DOMSnapshot boxes, not CSS-pixel locator boxes, supply the
   screenshot grounding geometry.
4. Low-visibility/tiny drawing nodes are non-actionable, and overlapping
   same-parent drawing nodes with one public label collapse to the labeled
   control.
5. E-ref visual disambiguation narrows the existing DOM binding catalog. It
   creates no coordinate binding.
6. A configured point grounder is neither advertised nor invoked by the
   BrowserGym target loop.

Repository verification after these changes: `2359 passed, 27 skipped`; the
affected-source Ruff check and `git diff --check` pass.

## Limits

- the diagnostic E-ref chooser is not model-performance evidence;
- only seed-7 `grid-coordinate` and `click-pie` are exercised here;
- the frozen five-witness provider gate remains separate and must use a clean
  implementation SHA;
- the older BrowserSession/generalist compatibility path and offline
  ScreenSpot point benchmark remain outside this target-loop authority claim.
