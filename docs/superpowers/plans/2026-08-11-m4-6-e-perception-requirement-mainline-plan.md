# M4.6-E Perception and Requirement Mainline Plan

Goal: restore a complete enough public GUI observation path before evaluating
task-frontier competence, then add one bounded task-start requirement proposer
without creating a second task or action authority.

## Frozen constraints

- Screenshot bytes are observation evidence, never execution authority.
- `ActionSpace` remains the only legal-action authority; visual/AX aliases can
  only reference current public targets/actions and expire with the context.
- Model transport must carry real typed image content; artifact summaries are
  not a substitute for image transport.
- Public semantic breadth may expose read-only structure without making every
  observed role executable.
- Requirement initialization produces hypotheses only. Runtime validates the
  bounded algebra/references, and verifier-owned state transitions remain the
  only way to verify or invalidate progress.
- No static full-task DAG, task-name production branches, hidden benchmark
  answers, selectors, coordinates, credentials, or oracle state.
- Benchmark reports separate declared-supported, unassessed and unsupported
  cohorts; mixed-denominator success is diagnostic only.

## Steps

| Step | Status | Work | Files |
|---|---|---|---|
| 1 | completed | Map screenshot acquisition/artifact ownership, model request/transport schemas, BrowserGym AX projection and current benchmark cohort authority; freeze the smallest message/image contract. | this plan and owner notes |
| 2 | completed | Add typed multimodal `ModelMessage` content with bounded image parts, provider serialization, privacy/private-capture handling and text-only compatibility. | model transport and policy bridge |
| 3 | completed | Bind current public screenshot evidence into each model decision request without exposing runtime-private routes or hidden benchmark state. | context/request composition |
| 4 | completed | Expand public BrowserGym observation semantics for checkbox/radio/tab/menuitem and read-only table/list/heading/static-text relations while keeping execution eligibility separate. | BrowserGym semantic profile/projection |
| 5 | in_progress | Add explicit text-only, screenshot+AX and screenshot+AX+SoM-compatible grounding profiles; SoM remains optional and is not required for the first transport slice. | grounding/profile contracts |
| 6 | pending | Add task-start bounded requirement hypotheses from public instruction + initial observation; atomically admit references and preserve verifier-only lifecycle authority. | task frontier/initializer |
| 7 | pending | Add invariant/privacy/unit/integration tests and run Ruff, mypy and full pytest. | tests |
| 8 | pending | Run predeclared same-model A/B on declared-supported cases first, then report challenge cohorts separately with complete public/private traces. | fresh evidence |

## Exit criteria

- A provider receives actual screenshot image content plus the same bounded
  public context, and text-only mode remains deterministic and compatible.
- Missing/oversized/unsupported image content fails typed before a provider
  call; private capture can retain exact exchanges outside public evidence.
- Observable roles and structural nodes can inform policy without silently
  becoming executable actions.
- Every image/AX/action alias is bound to one context/observation and stale use
  fails closed through existing admission.
- Requirement hypotheses are bounded, non-authoritative and independently
  verifier-updated.
- A/B manifests declare perception profile and readiness cohort before model
  execution; reports do not conflate supported and challenge success rates.

## Progress log

- 2026-08-11: plan created after the 25-case diagnostic showed 8 terminal
  zero-target/zero-action cases, 5 one-target/one-action terminal failures, and
  only 2 declared-supported cases in the reviewed-rule inventory-v2 profile.
  The prior task-frontier implementation remains useful verified memory, but is
  not treated as a substitute for perception or requirement production.
- 2026-08-11: implemented the first perception vertical: BrowserGym screenshots
  are encoded as bounded typed PNG evidence, excluded from public semantic JSON,
  and sent as standard multimodal message parts under `screenshot-ax.v1`.
  Expanded AX v2 projection with checkbox/radio/tab/menuitem actions and bounded
  read-only table/list/heading/static-text relations. Targeted tests passed;
  the first full run was 2215 passed with only this new plan missing from the
  documentation lifecycle manifest, which is now corrected.
- 2026-08-11: same-model A/B on the two inventory-v2 declared-supported cases
  completed with valid public evidence and private raw exchanges. Text-only was
  0/2 control repetition; screenshot+AX was 0/2 with one control repetition and
  one provider exhaustion after one actual dispatch. The run falsified success
  improvement but exposed a shared adapter gap: `click-link` used BrowserGym
  `generic` nodes with `clickable=true`, producing zero actions. Added a bounded
  normalization to public `clickable` targets with descendant text labels. A
  fresh live reset now projects 22/22 targets, 7 actionable and 15 read-only,
  with zero omissions. Full validation after this repair is 2218 passed and 27
  skipped; Ruff and mypy pass. A fresh A/B remains required for this new SHA.
- 2026-08-11: fresh A/B on clickable-normalization SHA `b853a5e` is valid and
  privacy-clean. Both arms reached 1/2: `click-link` succeeded in text-only and
  screenshot+AX, proving candidate projection was the gating change. Text-only
  `click-tab-2` repeated already-satisfied `target_present` objectives;
  screenshot+AX received three rate-limit attempts before provider exhaustion.
  The screenshot arm carried one image part on every recorded request and
  completed `click-link` in one policy call/one execution. This does not show a
  screenshot success-rate advantage on the two-case cohort.
- 2026-08-11: corrected the `click-tab-2` objective-repair diagnosis. The model
  projection already carried `recovery.strategy_change_required=true`, but the
  benchmark trace mislabeled the top-level transition flag as that recovery
  field. More importantly, objective issue identity omitted the rejected typed
  predicate, so two different already-satisfied predicates collided and the
  second repair was terminated as repetition. Issue identity now includes the
  public predicate, the trace records both flags plus `must_change_fields`, and
  the feedback contract requires predicate replacement for this code. Paired
  regression properties prove that a changed predicate receives the next
  bounded repair turn while an identical predicate is still mechanically
  terminated. Full validation is 2220 passed and 27 skipped; Ruff and mypy pass.
