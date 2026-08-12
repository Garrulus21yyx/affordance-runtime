# Visual Value and Multi-target Remediation — 2026-08-12

> **Lifecycle:** CURRENT BOUNDED FOLLOW-UP EVIDENCE
> **Claim:** the two named seed-7 regressions are fixed; broad performance and
> multi-seed generalization remain unclaimed

## Corrected causal diagnosis

The earlier `click-shades` timeout was caused by a redundant visual E-ref model
call before every main-policy call. Removing that duplicate call exposed a
second issue: after each click the E-ref inventory changed, while the main Agent
did not receive a sufficiently explicit current selected state or bounded color
candidate set.

The earlier `visual-addition` failure was not evidence that GLM could not count
the shapes. Its trace first filled `10`, then made a later policy call that
overwrote the settled field with `14` before submit. The shared defects were
model-facing observation/action closure, not DOM identity or point accuracy.

## Bounded implementation

- A screenshot+AX main policy now owns semantic action plus marked E-ref choice
  in one call. The optional E-ref disambiguator is skipped on this path.
- Model-facing catalogs omit settled fill/select actions and already-selected
  toggles; Runtime legality and admission remain unchanged.
- Repeated visible DOM leaf groups publish observation-only `count` facts. They
  carry no binding, selector, class name, or fixture answer.
- DOM controls publish current `selected=true` and a normalized `color_family`
  derived from visible computed style, never from `data-color` or task metadata.
- When an instruction explicitly names one bounded color family, only
  mismatching unlabeled visual click candidates are removed from the
  model-facing catalog. Labeled controls such as Submit remain available.
- Singleton tools privately close their sole operation/identity, so harmless
  redundant model serialization cannot invalidate the action.

No point output, visual coordinate binding, task-slug branch, hidden expected
answer, new model, or `ActionBatch` protocol was introduced.

## Live evidence

At clean implementation `8741890`, the full five-witness GLM gate was
evidence-valid and architecture-accepted at `3/5`. `visual-addition` completed
in two actions (fill, Submit). `click-shades` still selected one red control
after an E-ref reflow; that run motivated the final computed-style relevance
filter. `grid-coordinate` was the other task failure in that run.

At clean implementation `7fae859`, a focused real BrowserGym/GLM run of
`miniwob-60-42` (`click-shades`, seed 7) succeeded in six turns: five current
DOM controls whose public state was `color_family=blue` (`E1`, `E6`, `E8`,
`E11`, `E12`), followed by labeled Submit (`E13`). It recorded:

- `provider_attempts=6` and `policy_calls=6`;
- `visual_disambiguator_calls=0`;
- `visual_point_grounder_calls=0`;
- `visual_binding_acquired_count=0` and
  `visual_binding_dispatch_count=0`;
- `invalid_tool_argument_count=0`;
- six structural BrowserGym dispatches and terminal verified success.

The final repository suite passes: `2373 passed, 24 skipped`.

## Artifact integrity and claim limit

- focused `click-shades` case:
  `sha256:f6451a492f5c7aeb69e6516c61153360335027dd4d06dcdc5f1fd512d7f8937f`;
- focused progress index:
  `sha256:445602d181e277472d2150687c1aeb5439c34d144eecaccc876fd700f7ccba79`;
- `8741890` five-witness report:
  `sha256:8c0d4ca8b0c81f0b91bb123eb8881d14d4ada0ce8f8416c13d9e8ba367ab17ce`.

The final color filter was validated by the focused real case, not by another
full five-case rerun. Canvas/image-only controls still lack computed DOM style
and must continue through evidence-gated visual observation. The remaining
five-witness performance uncertainty is chiefly stochastic `grid-coordinate`
E-ref selection; neither MiniWoB-wide nor multi-seed generalization is claimed.
