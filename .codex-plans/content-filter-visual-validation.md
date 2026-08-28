# Content filtering and visual validation implementation

## Goal

Add a browser-owned, typed content-filter profile for public Surface acquisition while preserving the existing
benchmark path exactly, then validate the already-general visual observation capability in controlled and public
settings. Filtering is not an ActionPolicy tool and never becomes a second task-semantic authority.

## Invariants

- `ContentFilterProfile` and the model-facing observation profile are independent configuration axes.
- Compatibility benchmarks use content filtering `off`; their browser lifecycle and model-visible offer remain
  unchanged.
- Filtering is activated by the browser/session owner before navigation and before the single shared CaptureFrame.
- A strict filtering request never silently falls back to a weaker mode.
- CoreLoop, ActionPolicy, VisualProvider, and public World do not parse provider-specific Steel configuration.
- No production rule keys off a site, benchmark case, selector, page label, or task keyword.
- Existing unrelated dirty-worktree changes are not included in commits.
- Each completed phase is committed and pushed to `origin/codex/supervised-gui-agent-ui`.

## Phases

### Phase 1 — typed profile and explicit Steel network filtering (`done`)

- Establish the authoritative profile/config owner.
- Add `off | network_ads.v1 | ads_and_cosmetic.v1` as a closed typed contract.
- Parse deployment configuration with compatibility-safe default `off`.
- Make Steel session creation send `blockAds=false|true` explicitly; never rely on the upstream default.
- Reject unsupported strict cosmetic filtering as a typed open failure until an attested extension is wired.
- Add focused backend tests for parsing, request bodies, and fail-closed behavior.
- Commit and push.

### Phase 2 — pinned cosmetic filtering and acquisition attestation (`done`)

- Verify the exact installed Steel extension admission mechanism against the deployed Steel API.
- Pin the selected uBO Lite artifact/version/digest; do not auto-update during benchmark runs.
- Activate and attest the extension before navigation.
- Carry private filter metadata into acquisition tracing/Labs without adding it to Agent World.
- Ensure strict activation failure occurs before capture, ActionPolicy, or VLM activation.
- Add fixture coverage for third-party and same-origin cosmetic ads.
- Commit and push.

### Phase 3 — single filtered frame and compatibility gates (`done`)

- Prove DOM/AX projection and screenshot derive from one post-filter CaptureFrame.
- Verify popups/new pages inherit the session filter.
- Add exact `off`-profile parity gates for media, offers, image inputs, and provider-call counts.
- Add no-site-specialization source checks and provider-free regression gates.
- Commit and push.

### Phase 4 — visual capability evaluation matrix (`done`)

- Keep controlled visual evaluations on filtering `off` to avoid confounding.
- Add/run provider-free fixture gates first, then the separately authorized live DeepSeek VLM arm.
- Evaluate ScreenSpot point-in-box, MiniWoB adaptive vision, text-in-image, SVG, same-name controls,
  visual selected state, stale coordinate rejection, and unknown/ambiguous calibration.
- Persist profile/model/ruleset/config identity with results.
- Commit and push code/evaluation manifests; live results only after explicit authorization.

### Phase 5 — controlled flagship and public read-only shadow (`done`)

- Validate the generic contract composition on a controlled shopping task with no commerce-specific production types.
- Add chart/map/file-list held-out cases.
- Use Steel strict filtering only for public read-only shadow runs; no login, payment, or irreversible submission.
- Keep public-page drift results separate from formal benchmark truth.
- Commit and push code/manifests; run live only with explicit authorization.

### Phase 6 — authorized live visual evidence (`in_progress`)

- Treat the user's 2026-08-28 “继续” as authorization for the frozen live visual arm.
- Run one controlled DeepSeek point-grounding smoke before any broader provider spend.
- Acquire ScreenSpot only from the original SeeClick release, bind source commit/digests, and report point-in-box
  accuracy separately from transport or structured-output failures.
- Run the frozen MiniWoB `visual-addition` case through `run-visual-case`; retain the existing ActionPolicy and native
  evaluator, and persist the redacted ActionPolicy/VLM configuration identity.
- Keep public-page shadow navigation pending concrete user-supplied URLs; do not infer a shopping or content site.
- Commit and push live manifests/results only after source and reporting validation.

### Phase 7 — structure-first visual escalation convergence (`in_progress`)

- Preserve the product invariant that ordinary structure-sufficient turns activate no visual provider; a configured
  VLM or available screenshot never triggers acquisition by itself.
- Treat the clean MiniWoB live run as two separate witnesses: recursively project immutable diagnostic trace at the
  benchmark-report boundary, and diagnose the policy's unnecessary point-grounding request without reclassifying the
  reporting failure as a GUI failure.
- Keep the existing Runtime applicability gate and compatibility profile; do not make entity discovery available
  merely because current media exists.
- Replace the dynamic `request_evidence` variants' shared broad query description with purpose-specific, concise
  model-facing fields and positive use/not-use/result contracts. Map those fields deterministically in the existing
  Catalog binding to the single internal `RequestObservation`; do not add a semantic rewrite path or second planner.
- Ensure a legitimately admitted point-grounding request activates only its target-specific grounding provider, not
  an automatic full-screen entity-discovery provider first. Entity discovery remains a separately selected,
  observation-only purpose.
- Add provider-free gates for structure-sufficient zero visual calls, exact dynamic Catalog schemas/binding, stale or
  unoffered zero-call rejection, and one-call point grounding. Preserve compatibility Catalog bytes and target-loop
  benchmark identity where declared.
- Commit and push the reporting repair and the escalation/tool-contract repair separately before another clean live
  run.

## Progress log

- 2026-08-28: Started from pushed feature branch. Detected unrelated dirty worktree; all phase commits will use
  explicit pathspecs and pre-commit staged-diff inspection.
- 2026-08-28: Phase 1 implemented at the Shell browser-session owner. `off` and `network_ads.v1` map to explicit
  Steel `blockAds` booleans; strict mode fails with `content_filter_unavailable` before provider activation. Shell
  backend and architecture gate: 104 passed. Targeted pyright retained one pre-existing deployment adapter type error.
- 2026-08-28: Phase 2 pinned uBO Lite `2026.825.1619` at official artifact SHA-256
  `9f0acbe3eabd4ba1c1c0629438cfacafbdaf04cd150769932d5d265b2fac117e`. The provisioner verified the downloaded
  artifact, uploaded it once through Steel Extensions API, and stored the returned non-secret attestation in local
  `.env` while keeping the active profile `off`. Runtime verifies exact Steel extension metadata before strict session
  creation, adds only that `extensionId`, and carries private engine/version/digest/latency metadata on the lease and
  trace identity. Live metadata lookup and create/release smoke succeeded; no page navigation or benchmark ran.
  Shell backend and architecture gate: 114 passed.
- 2026-08-28: Phase 3 corrected the strict semantic contract after the upstream FAQ showed that uBO Lite defaults to
  Optimal and does not enable generic cosmetic filtering. Provisioning now applies one deterministic
  `default-filtering-complete.v1` owner patch; upstream SHA remains pinned and the derived SHA
  `16b3548cc7c975c73e328d2bf66af3437d0f1a0d8d0ec12846e57456ab0f63ab` is attested in `.env` and trace metadata.
  Strict Surface acquisition projects rendered DOM only, so CSS-hidden nodes cannot remain visible through raw HTML;
  `off` preserves the old raw projection exactly. Provider-free gates: Shell backend/architecture 117 passed, core
  full repository 2004 passed / 19 skipped / 1 warning. Live non-Agent fixtures proved: off ad script HTTP 200,
  network profile browser-level failure, and strict cosmetic removal from computed style, visible text, AX, rendered
  DOM, and screenshot across current and newly opened tabs. One earlier 3-minute smoke lease could not be explicitly
  released after a local Sync Playwright startup error and expired by its provider timeout; all subsequent leases were
  released in `finally`.
- 2026-08-28: Phase 4 added the frozen, filter-off visual capability matrix and an explicit `run-visual-case` entry;
  the existing `run-case` and formal campaign remain provider-compatible and never activate VLM roles merely because
  `.env` contains a visual profile. The visual entry composes region, point, disambiguation, predicate, OCR, spatial,
  and change roles over one DeepSeek PydanticAI inference owner, validates `dynamic-visual.v1` before any live call,
  and persists a redacted provider/model/prompt/config identity with each cohort report. BrowserGym benchmark
  composition now forwards and counts all seven visual roles. The committed matrix binds ScreenSpot point-in-box,
  paired MiniWoB adaptive vision, and controlled text/SVG/same-name/selected/stale/unknown gates. Provider-free
  focused gates: 50 passed. The isolated staged tree preserved the compatibility target-manifest digest exactly at
  `f9326cbb02ae5a0238603dedae253ac8a44ac28138d82427800b4468b75e67ab`; its fixed-interpreter full suite reported
  1,992 passed / 19 skipped and one unrelated missing archived trace fixture. No ScreenSpot, MiniWoB, or other live
  VLM benchmark was run.
- 2026-08-28: Phase 5 added a generic, provider-free supervised-GUI acceptance gate: one candidate-comparison
  flagship and chart/map/file-list held-out fixtures. Product `BrowserSession` capture plus normal DOM projection and
  World fusion preserved repeated same-label controls and admitted the existing generic option response and
  current-evidence artifact contract on all four pages with zero Agent/VLM calls. Existing Runtime tests cover
  takeover, lease fencing, fresh-World return, and failure retention without a scenario branch. The public shadow
  path is preflight-only: two environment URL slots, strict filtering, read-only/no-effects policy, credential
  rejection, redacted origins, and explicit live authorization. The preflight cannot attest filter activation and
  leaves `live_execution_ready=false`; only the Shell Surface owner can admit and attest strict filtering before
  navigation. Focused gates passed 53 tests; targeted Ruff and mypy passed. Playwright CLI independently confirmed
  candidate pressed-state transfer, and the formal MiniWoB target manifest digest remained
  `f9326cbb02ae5a0238603dedae253ac8a44ac28138d82427800b4468b75e67ab`.
  The isolated staged-tree full suite reported 1,997 passed / 19 skipped / 1 warning and the same single pre-existing
  missing archived-trace fixture failure as Phase 4. No public page or live benchmark was opened.
- 2026-08-28: The authorized ScreenSpot diagnostic completed 23/30 point-in-box (text 14/15, icon 9/15) with one
  correctly rejected invalid structured coordinate. Three clean MiniWoB attempts exposed, in order, an empty public
  ref schema, a provider-incompatible root union, and a nested immutable trace reporting failure; the first two are
  fixed and pushed. The latest GUI run itself ended blocked after the ActionPolicy repeatedly requested point
  grounding for a structure-readable counting question, with zero GUI executions. Phase 7 now protects the original
  structure-first zero-VLM invariant and forbids using that witness to broaden visual availability.
- 2026-08-28: Phase 7 replaced the dynamic observation tool's shared `atomic_query` with purpose-specific public
  fields while keeping one `request_evidence` tool and one internal `RequestObservation` binding. A legal point request
  now calls only the point grounder; entity discovery remains a separate ActionPolicy decision. A post-commit audit
  caught and removed an accidental media-only entity-discovery applicability relaxation before live rerun; complete
  structural projection continues to suppress that purpose, and the provider-free regression records the boundary.
- 2026-08-28: Clean live run `phase7-clean4` proved the point contract no longer accepted the counting question, but
  falsified the generic ref domain by admitting `text_in_image` over ordinary generic/control refs; the ActionPolicy
  used OCR to guess `17` and native evaluation failed. Catalog now intersects each purpose with a stable current-World
  ref domain, so OCR accepts only image/canvas/graphics-document-like pixel containers. No TaskGoal parser, keyword
  filter, CoreLoop branch, or provider-side semantic rewrite was added.

## Files changed by this plan

- `.codex-plans/content-filter-visual-validation.md`
- `external/interaction-shell/backend/interaction_shell/content_filtering.py`
- `external/interaction-shell/backend/interaction_shell/deployment_app.py`
- `external/interaction-shell/backend/interaction_shell/provision_content_filter.py`
- `external/interaction-shell/backend/interaction_shell/steel_viewer.py`
- `external/interaction-shell/tests/backend/test_content_filtering.py`
- `external/interaction-shell/tests/backend/test_deployment_app.py`
- `external/interaction-shell/tests/backend/test_steel_viewer.py`
- `src/affordance_runtime/surfaces/dom/browser_session.py`
- `src/affordance_runtime/surfaces/dom/thread_session.py`
- `tests/unit/agent/test_browser_session.py`
- `docs/benchmarks/visual-capability-evaluation-v1.json`
- `src/affordance_runtime/benchmarks/visual_capability.py`
- `src/affordance_runtime/surfaces/visual/role_set.py`
- `docs/benchmarks/supervised-gui-acceptance-v1.json`
- `docs/benchmarks/fixtures/supervised-gui/*.html`
- `src/affordance_runtime/benchmarks/supervised_gui_acceptance.py`
- `src/affordance_runtime/benchmarks/cli.py`
- `tests/benchmarks/runtime/test_supervised_gui_acceptance.py`
- `tests/benchmarks/runtime/test_cli.py`
- `src/affordance_runtime/benchmarks/external_breadth/runner.py`
- `tests/benchmarks/runtime/test_miniwob_breadth_runner.py`
- `src/affordance_runtime/model/policy/grounded_tool_catalog.py`
- `src/affordance_runtime/surfaces/browsergym/environment.py`
- `src/affordance_runtime/surfaces/browsergym/visual_projection.py`
- `src/affordance_runtime/surfaces/visual/grounding.py`
- `tests/benchmarks/model/test_grounded_tools_v2.py`
- `tests/unit/surfaces/browsergym/test_browsergym_visual_binding.py`
