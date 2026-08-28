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

### Phase 2 — pinned cosmetic filtering and acquisition attestation (`in_progress`)

- Verify the exact installed Steel extension admission mechanism against the deployed Steel API.
- Pin the selected uBO Lite artifact/version/digest; do not auto-update during benchmark runs.
- Activate and attest the extension before navigation.
- Carry private filter metadata into acquisition tracing/Labs without adding it to Agent World.
- Ensure strict activation failure occurs before capture, ActionPolicy, or VLM activation.
- Add fixture coverage for third-party and same-origin cosmetic ads.
- Commit and push.

### Phase 3 — single filtered frame and compatibility gates (`pending`)

- Prove DOM/AX projection and screenshot derive from one post-filter CaptureFrame.
- Verify popups/new pages inherit the session filter.
- Add exact `off`-profile parity gates for media, offers, image inputs, and provider-call counts.
- Add no-site-specialization source checks and provider-free regression gates.
- Commit and push.

### Phase 4 — visual capability evaluation matrix (`pending`)

- Keep controlled visual evaluations on filtering `off` to avoid confounding.
- Add/run provider-free fixture gates first, then the separately authorized live DeepSeek VLM arm.
- Evaluate ScreenSpot point-in-box, MiniWoB adaptive vision, text-in-image, SVG, same-name controls,
  visual selected state, stale coordinate rejection, and unknown/ambiguous calibration.
- Persist profile/model/ruleset/config identity with results.
- Commit and push code/evaluation manifests; live results only after explicit authorization.

### Phase 5 — controlled flagship and public read-only shadow (`pending`)

- Validate the generic contract composition on a controlled shopping task with no commerce-specific production types.
- Add chart/map/file-list held-out cases.
- Use Steel strict filtering only for public read-only shadow runs; no login, payment, or irreversible submission.
- Keep public-page drift results separate from formal benchmark truth.
- Commit and push code/manifests; run live only with explicit authorization.

## Progress log

- 2026-08-28: Started from pushed feature branch. Detected unrelated dirty worktree; all phase commits will use
  explicit pathspecs and pre-commit staged-diff inspection.
- 2026-08-28: Phase 1 implemented at the Shell browser-session owner. `off` and `network_ads.v1` map to explicit
  Steel `blockAds` booleans; strict mode fails with `content_filter_unavailable` before provider activation. Shell
  backend and architecture gate: 104 passed. Targeted pyright retained one pre-existing deployment adapter type error.

## Files changed by this plan

- `.codex-plans/content-filter-visual-validation.md`
- `external/interaction-shell/backend/interaction_shell/content_filtering.py`
- `external/interaction-shell/backend/interaction_shell/deployment_app.py`
- `external/interaction-shell/backend/interaction_shell/steel_viewer.py`
- `external/interaction-shell/tests/backend/test_deployment_app.py`
- `external/interaction-shell/tests/backend/test_steel_viewer.py`
