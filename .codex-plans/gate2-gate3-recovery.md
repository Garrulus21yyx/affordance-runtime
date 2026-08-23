# Gate 2 / Gate 3 recovery after vertical falsification

Status: gate_2_implemented_provider_free_verified_exit_review_pending;
gate_3_implemented_provider_free_verified_exit_review_pending;
gate_4_aborted_not_admitted;
overall_reopened_non_closed

## Goal

Repair and independently re-verify the two owner contracts falsified by the aborted Gate 4 attempt, commit each gate
separately, then perform a fresh read-only Gate 2/3 exit review. Gate 4 remains out of scope until both gates are
explicitly re-admitted.

## Constraints

- Baseline evidence commit: `6c6384b346a6124879a36fe0e7be6547343a7a51`.
- Preserve untracked `output/`; never modify, stage, or commit it.
- Provider-free only; no live benchmark, Task7 replay, external token counter, or external GUI side effect.
- Fix meaning at the owning boundary; no CoreLoop, Catalog, bridge, recorder, WebArena-probe, or test compensation.
- Gate 2 and Gate 3 receive independent implementation commits and independent verification evidence.
- Do not resume or claim Gate 4 until a fresh Gate 2/3 exit review passes.

## Gate 2 positive contract

The final attached-media value owns exact annotation and route meaning atomically:

```text
actual attached media
├── actual marks: public ref + in-frame bbox
├── exact route deltas: operation + source ref + optional destination ref
└── typed per-mark operand roles: source | destination
```

`DeliveryManifest.action_routes` is the ordered union of admitted text-fragment route deltas and actual attached-media
route deltas. A mark carries no authority by itself. Evidence-only, unavailable, out-of-frame, or unattached marks add
no route. Destination-only marks retain destination role and never create a unary route.

## Gate 3 positive contract

Every active request-breakdown field names its coordinate explicitly:

```text
estimated_input_tokens
full_candidate_input_tokens
lens_candidate_input_tokens
output_reserve_tokens
complete_request_tokens = estimated_input_tokens + output_reserve_tokens
```

Delete ambiguous/producerless prefit metrics. Every consumer compares like coordinates; the WebArena probe receives
owner-produced input coordinates and performs no conversion.

## Steps

1. [completed] Implement the Gate 2 final-media route/role owner and migrate Manifest/Envelope consumers.
2. [completed] Add unary, destination, evidence-only, undrawn/unavailable, and real Recording FunctionModel production gates.
3. [completed] Run Gate 2 focused/full/static/negative verification; update docs; commit Gate 2 independently.
4. [completed] Rename/delete Gate 3 breakdown fields at the owner and migrate every active consumer.
5. [completed] Add coordinate properties for default, soft target, exact fit, one-over, consumer comparisons, and zero attempts.
6. [completed] Run Gate 3 focused/full/static/negative verification; update docs; commit Gate 3 independently.
7. [in_progress] Perform a fresh read-only Gate 2/3 exit review and record admitted/reopened status without starting Gate 4.

## Files produced or modified

- `.codex-plans/gate2-gate3-recovery.md` — this persistent recovery record.

## Evidence log

- Gate 2 focused owner/production/architecture suite: `150 passed`.
- Full provider-free suite: `1604 passed, 24 skipped`.
- Ruff, compileall, `git diff --check`, and negative searches for mark-derived/post-hoc Manifest routes pass.
- Real annotated production turn proves JPEG→PNG bytes/MIME/digest/dimensions, actual mark, typed source role, exact
  media route delta, Manifest equality, Recording FunctionModel equality, resolver/Binder execution, and private
  binding exclusion from provider input.
- Generated owner cases cover unary, source+destination roles, destination-not-unary, evidence-only marks, and
  unavailable/undrawn marks. No real provider, live benchmark, or Task7 replay ran.
- Gate 2 independent commit: `28f3b5af` (`fix: conserve annotated media action routes`).
- Gate 3 focused request/delivery/Recording/WebArena/architecture suite: `167 passed, 2 skipped`.
- Gate 3 full provider-free suite: `1605 passed, 24 skipped`.
- Ruff, compileall, diff check, and production negative searches prove the old total/prefit/full/lens metric names and
  cross-coordinate comparisons are absent. No real provider, live benchmark, or Task7 replay ran.
- Fresh Gate 2 exit review held out a destination-only media mark and falsified the first repair's requirement that
  both operands be drawn in the same image. The owner now admits a media route when at least one of its exact operands
  is actually marked, while every marked operand retains its exact source/destination role. Source-only and
  destination-only binary-route cases pass without inventing a unary route.
- Corrected joint focused suite: `175 passed, 2 skipped`; corrected full provider-free suite: `1607 passed, 24 skipped`;
  Ruff, compileall, diff check, and both media-route and coordinate negative searches pass.
- The restarted review then falsified that correction again: `AgentImageInput` remained route-free and
  `_delivered_media` inferred routes from `mark refs ∩ rendered text routes`. The tests proved the resulting value but
  not its authority. The media-fragment owner now emits typed actual marks plus exact `AgentImageActionRoute` deltas
  after annotation and current action grounding; `ModelTurnDelivery` only preserves those deltas. A mark with no
  producer-owned delta cannot authorize a route, and media routes no longer depend on text-route membership.
- Post-owner-move focused suite: `175 passed, 2 skipped`; full suite: `1607 passed, 24 skipped`; Ruff, compileall,
  diff check, and negative searches pass. This is correction evidence, not exit-review admission; review restarts from
  the correction revision.
- The next serialization audit found that the new route's private resolver fields were `repr=False/compare=False` but
  not excluded by the repository's dataclass JSON projection. They are now explicitly `serialize=False`, with a
  property test proving only operation/source/destination survive. Focused owner/Recording/Admission/architecture
  verification is `122 passed`; review restarts again from this correction.
- Fresh Gate 3 review found one remaining producer-only ambiguous field, `fixed_request_tokens`. It was neither an
  Admission input nor consumed diagnostic and duplicated a partial input subtotal, so the breakdown owner deletes it
  and the old-name property now covers it. Gate 3 review restarts from that correction.
- The next consumer audit found three zero-only component-payload ghosts (`task_plan_tokens`, `working_set_tokens`,
  `evidence_tokens`) still projected through instrumentation and WebArena despite having no Envelope estimator
  producer. They are deleted with every consumer; no probe-side reconstruction replaces them.
