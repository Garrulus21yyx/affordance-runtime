# DOM-First Evidence-Gated Vision Convergence Plan

Status: `PHASE_5_BOUNDED_WITNESS_VERIFIED / GENERALIZATION_OPEN`

Date: 2026-08-12

## 2026-08-13 Phase 6 — scope-relative set completion convergence

Status: `IN_PROGRESS / DEPENDENT_SET_CLOSURE_UNVERIFIED`

Repeated live runs exposed one shared contract gap after local color/grid
filters had each appeared closed: the model-facing catalog can expose a
successor action before an `ALL` objective's item obligations are effect-
confirmed. This phase replaces those witness filters with a generic,
scope-relative and evidence-bounded set-completion algebra. No dependent work
may claim set completion until the certificate path is verified.

Causal model:

- architecture defect: task quantification, candidate-scope closure,
  predicate membership and per-item action obligation are not represented as
  separate authoritative state;
- duplicated/implicit truth: the main VLM currently guesses both membership
  and completion while catalog helpers separately infer colors/coordinates;
- verification defect: dispatch/effect history is available, but no reducer
  requires every discovered true member to reach item-level
  `EFFECT_CONFIRMED` before successor admission;
- boundary defect: parser/VLM outputs have no contract preventing them from
  implying universe coverage;
- current witness: clean five-case `e31ee40` is evidence-valid at `4/5`;
  `click-shades` selected three blue controls and then Submit while two current
  blue members remained.

Bounded implementation plan:

1. `completed` — define immutable `ScopeSpec`, predicate AST/three-valued
   evaluation, `CandidateUniverse`, `PredicateAssessment`, independent member
   obligations, scheduler policy, reducer disposition and completion
   certificate contracts.
2. `completed` — implement a deterministic reducer with explicit legal
   transitions, epoch invalidation after effects, classification/scope
   separation, item-effect closure and stability check.
3. `completed` — add structural fact evaluators and a bounded TaskGoal-to-set-
   objective compiler; color/grid are evidence inputs, never Catalog branches.
4. `completed` — make grounded Catalog consume only reducer disposition; remove
   direct color/grid task parsing and prevent successor exposure until the
   generic objective permits it.
5. `completed` — add a provider-neutral bounded E-ref batch assessment contract;
   omitted/duplicate/unknown refs fail typed and providers cannot declare scope
   coverage. Integrate GLM only behind that port when structural evidence is
   insufficient.
6. `in_progress` — verify reducer properties across permutation, stale epochs,
   dynamic membership, no/effect-unknown paths, ambiguous scope and scheduling
   authority; then run focused/full tests and a clean real five-case gate.
7. `pending` — update maintained architecture/evidence, remove temporary
   witness-only catalog helpers after behavioral parity, and obtain a fresh-
   context review before restoring a closed status.

Non-goals: proof over an open world; parser/VLM-owned completeness; automatic
scroll/pagination closure in the first slice; runtime scheduling when order,
parameters, risk or member semantics are not independent; task slug/case ID
branches; or importing another agent runtime.

Current verification: focused objective/Vision/Catalog tests pass (`42 passed`)
and the full repository suite passes (`2381 passed, 27 skipped`). The clean
real five-case gate and fresh-context review remain required before this phase
can move from `DEPENDENT_SET_CLOSURE_UNVERIFIED`.

## 2026-08-13 Phase 5 — observation-derived lattice semantics

Status: `BOUNDED_WITNESS_VERIFIED / GENERALIZATION_OPEN`

Objective: remove the remaining `grid-coordinate` 25-way SoM selection burden
without introducing point grounding or a benchmark-task branch. Mechanically
derive regular-lattice membership and visible axis-value mappings from one
current BrowserGym observation, attach the resulting coordinate as public
observation evidence to the existing DOM target, parse the requested coordinate
from the public TaskGoal, and narrow the model-facing action catalog only when
that relation yields one exact current executable match.

Plan:

1. `completed` — locate the existing geometry, semantic-target, task and
   grounded-catalog boundaries; record the smallest authority-preserving seam.
2. `completed` — implement a generic regular-lattice/axis enricher over current
   page-space geometry and visible labels, with typed ambiguous/unsupported
   outcomes and no new bindings.
3. `completed` — project derived lattice facts onto existing DOM entities and
   exact-match a public requested coordinate to one model-facing action while
   retaining the unchanged Runtime ActionSpace.
4. `completed` — add invariant/property regressions for order independence,
   orientation inference, uniqueness, ambiguity and fail-closed behavior.
5. `completed` — run focused/full tests and a clean real BrowserGym/GLM witness;
   persist per-case evidence and update maintained status from measured facts.

Non-goals: MiniWoB slug/case branches, fixed 5x5 or `-2..2` assumptions,
model-produced coordinates, coordinate execution bindings, verifier answer
inference, or a generalized table/calendar platform beyond the proven regular
lattice contract.

Verification:

- focused lattice/projection/catalog suite: `22 passed`; broader affected suite:
  `98 passed` before the final DOM-only closure regression;
- full repository suite: `2379 passed, 24 skipped`;
- clean `3ccb267c7958d2e02634f8aebcfe8284199e491d` real
  BrowserGym/GLM seed-7 witness: `grid-coordinate` succeeded in one turn and
  one structural dispatch, with one main-policy call and zero auxiliary E-ref,
  point-grounder, visual-binding or invalid-tool-argument events;
- the selected display ref was `E25`, while the observation-derived membership
  was invariantly row `4`, column `3`. This is intentionally different from a
  historical successful `E24` display ref and demonstrates that execution no
  longer depends on volatile SoM numbering;
- evidence record:
  `docs/evidence/2026-08-13-observation-derived-lattice-witness.md`.

This closes the named seed-7 correspondence regression only. Multi-seed,
multiple-grid UI families, calendars/tables and broader generalization remain
unclaimed.

Scope: replace the Step-13 configure-and-stick visual acquisition behavior with
a DOM/AX-first control plane, evidence-gated visual augmentation, explicit
entity correspondence, and coordinate execution only for current visual-only
entities. Reuse external perception and grounding implementations behind the
existing ports instead of importing another agent runtime.

Supersedes in this scope:
`docs/superpowers/plans/2026-08-12-step13-visual-binding-implementation.md`.
That record remains useful implementation history, but its initial automatic
visual augmentation and sticky post-action selection are not target behavior.

## 1. Objective and bounded contract

The supported control algebra is:

```text
fresh DOM/AX observation
-> sufficient structured evidence
   -> DOM identity + DOM binding only
-> typed evidence gap
   -> one bounded visual acquisition for the current epoch
      -> visual evidence explicitly corresponds to DOM identity
         -> merge evidence into the DOM canonical target; DOM binding remains authoritative
      -> visual evidence is explicitly unmatched
         -> retain an observation-only visual target; no BrowserGym execution binding
      -> ambiguous, conflicting, stale, unsupported, or low-confidence
         -> no executable visual binding; reobserve or fail closed
```

Vision availability never implies Vision selection. Screenshot capture never
implies a VLM call. A prior visual acquisition never makes the next acquisition
visual. Every visual call is justified by current typed evidence and consumes a
bounded current-epoch budget.

## 2. Root causes being corrected

1. `BrowserGymMiniWobEnvironment.reset()` currently selects visual augmentation
   whenever a proposer is configured, before policy or runtime evidence shows a
   gap.
2. `_visual_selected` turns a successful visual acquisition into sticky
   post-action selection, so provider configuration becomes an implicit
   per-frame policy.
3. the visual proposer receives screenshot plus task instruction but no DOM
   candidates, and publishes source-local `visual-region:*` entities without
   producing `EntityCorrespondence`.
4. source fusion therefore unions DOM and visual entities rather than merging
   representations of the same entity.
5. every admitted actionable visual region currently receives a coordinate
   binding before DOM correspondence is established. Observation authority and
   execution authority are conflated.
6. BrowserSession and the target-loop BrowserGym environment use different
   visual-trigger policies, leaving two contradictory production semantics.

## 3. Responsibility and externalization decisions

| Capability | Owner / reused implementation | Decision |
|---|---|---|
| DOM/AX, bbox, stable browser identity | BrowserGym/Playwright | retain; authoritative browser control plane |
| DOM bbox to same-ID marks | current BrowserGym grounding regions and mark projection | retain; correspondence exists by construction |
| open-world visual entity proposal | `VisualRegionProposerPort`; add an OmniParser-compatible adapter seam | outsource parser/model; do not import OmniTool or another agent loop |
| DOM-candidate visual disambiguation | main VLM with bounded E-ref/SoM choice | output an existing E-ref, never a coordinate |
| visual-only query to point | GLM/ShowUI/GUI-Actor-style `VisualGrounderPort` arms | retain for isolated grounding benchmarks; no BrowserGym target-loop authority |
| on-demand acquisition pattern | browser-use/SenseAct reference semantics | borrow the evidence-gated pattern; Runtime remains decision owner |
| correspondence and execution authority | project `EntityCorrespondence`, fusion, action-space admission | project-owned because it binds current identities and private routes |

External projects are provider implementations, not architecture authorities.
OmniParser integration is optional and configuration-gated. The coherent first
implementation may continue using GLM through the existing proposer and
grounder ports while the external adapter is added or evaluated independently.

## 4. Typed visual escalation

Introduce one pure current-observation decision with these outcomes:

- `SKIP`: structured evidence is sufficient.
- `VERIFY_STRUCTURED_CANDIDATES`: DOM candidates exist but require visual
  disambiguation; expose same-ID marks and require an E-ref result.
- `DISCOVER_VISUAL_ENTITIES`: the relevant structured inventory/action space is
  missing or incomplete; call the bounded region proposer.
- `DIAGNOSE_POSTCONDITION`: a sent action lacks its expected current observable
  effect and visual evidence can discriminate the failure.
- `UNAVAILABLE`: no admitted visual source or budget exists.

Admission evidence is limited to current public facts:

- required visual/spatial property is absent from structured evidence;
- no current executable binding exists for the relevant target/action;
- several current structured candidates remain semantically ambiguous;
- relevant structured coverage/inventory is partial or conflicted;
- a sent action's expected postcondition is unresolved or contradicted.

Task slug, benchmark cohort, provider presence, prior visual success, and raw
request prose alone are not admission evidence.

## 5. Correspondence contract

Correspondence is evaluated only inside one coherent acquisition root and one
current screenshot/viewport identity.

1. DOM-derived marks retain their DOM target ID directly; no inferred match is
   required.
2. externally proposed visual regions are compared with DOM grounding regions
   using bounded geometry and compatible public semantics. A correspondence is
   emitted only for one deterministic unique match.
3. `MATCHED` visual entities publish `EntityCorrespondence(visual_id, dom_id)`
   and no coordinate binding. Fusion rewrites their evidence onto the DOM
   canonical target.
4. `UNMATCHED` is admissible only when no compatible DOM region meets the
   matching floor. It remains observation-only in the BrowserGym target loop;
   a future safe-region executor requires a separate contract.
5. `AMBIGUOUS`, `CONFLICT`, stale, low-confidence, and unsupported primitives
   remain observable but non-executable.

The first matcher is deterministic and bounded. It uses overlap/containment,
center inclusion, normalized text, and role compatibility. It does not add a
learned fusion model. If one-to-one global assignment becomes necessary,
standard assignment tooling may replace the bounded matcher without changing
the contract.

## 6. Implementation work items

1. `completed` — inventory all visual acquisition, projection, fusion,
   action-space, route, currentness, provider, benchmark, and documentation
   consumers; record contradictions.
2. `completed` — remove reset-time automatic visual selection and sticky
   post-action visual selection from the target-loop BrowserGym environment.
3. `completed` — introduce the typed pure visual-escalation decision and use it in
   the current target-loop acquisition path without task-family routing.
4. `completed` — add DOM/visual region correspondence projection for shared raw
   BrowserGym captures.
5. `superseded_by_phase_4` — the earlier unmatched-coordinate experiment was
   removed from the BrowserGym target loop. All proposer outputs are now
   observation-only; point execution remains an isolated benchmark surface.
6. `completed` — use the dedicated GLM grounder as the default visual-only
   point implementation; add a thin optional OmniParser proposer adapter behind
   `VisualRegionProposerPort`; and keep open-world proposal disabled unless its
   role is explicitly configured. No external runtime or dependency is added.
7. `completed` — add invariant, property, integration, and regression tests for
   call gating, correspondence, action authority, stale handling, and no-vision
   DOM cases.
8. `completed` — update authoritative, normative, status, and reference
   documentation and mark the old
   Step-13 automatic/sticky statements superseded.
9. `completed_for_non_live_scope` — focused tests, full repository tests,
   documentation checks, static checks, and the final contradiction search pass.
   Live provider/benchmark runs remain separate evidence and must not be
   fabricated from unit results.

## 7. Migration impact and compatibility

- `--visual-grounding` changes from "augment every selected frame" to "make an
  admitted visual capability available".
- explicit policy `RequestObservation(modality="visual")` remains supported,
  but Runtime may return typed unavailable/failed and still applies
  correspondence and execution-authority rules.
- existing DOM bindings, currentness probes, screenshot digest validation,
  action evaluation, and GLM provider configuration remain compatible.
- tests that asserted automatic reset/sticky calls must be replaced with
  evidence-gated expectations.
- visual-only benchmark cases need either an explicit current evidence gap or a
  runtime-derived discovery decision before a proposer call.

## 8. Observability

Record per acquisition/episode:

- visual gate outcome and reason code;
- relevant structured target/action/coverage counts;
- proposer and point-grounder call counts separately;
- matched, unmatched, ambiguous, conflicting, and non-executable visual counts;
- DOM versus visual-only binding admission and dispatch counts;
- coordinate execution ratio and whether every coordinate dispatch referenced
  an explicitly unmatched current visual identity;
- visual latency and currentness rejection counts.

## 9. Explicit non-goals

- no training or fine-tuning;
- no replacement of BrowserGym/Playwright, policy loop, fusion, or routing with
  ShowUI, OmniTool, browser-use, SeeAct, or another full agent framework;
- no probabilistic long-lived identity tracker;
- no automatic coordinate fallback for a target that has a DOM identity;
- no unrelated scroll, keypress, drag-generalization, or benchmark-specific
  solver work.

## 10. Falsifiable exit criteria

- zero provider calls on complete, uniquely actionable DOM-only witnesses;
- exactly one bounded visual call on witnesses with an admitted current gap;
- a prior visual call does not select Vision for the next post-action frame;
- same-frame DOM and overlapping visual proposals yield one canonical target
  with DOM execution authority and no visual coordinate binding;
- unique visual-only proposals yield a current coordinate binding;
- ambiguous/conflicting/stale/low-confidence proposals yield zero coordinate
  bindings and a typed non-success path;
- every coordinate dispatch is traceable to an explicitly unmatched current
  visual identity;
- GLM remains usable as the default point grounder without becoming acquisition
  or correspondence authority; enabling point grounding does not implicitly
  enable GLM region proposal;
- focused and full tests pass, maintained docs agree, and a fresh search finds
  no live code or normative prose that treats provider presence or prior visual
  selection as evidence.

## 11. Files changed by work item

| Work item | Files | Status |
|---|---|---|
| Plan creation | this file | done |
| Typed escalation | `world/vision_escalation.py`, BrowserGym target environment | full-suite verified |
| Explicit correspondence | BrowserGym visual projection, World contracts/fusion | full-suite verified |
| Coordinate authority | `SurfaceObservation.visual_only_target_ids`, fusion fail-closed checks | full-suite verified |
| Metrics | external smoke/breadth and target-loop metric contracts | full-suite verified |
| Regression properties | BrowserGym Vision and Unified fusion tests | full-suite verified |
| Documentation convergence | authoritative architecture/evolution, active perception, status/index/old Step 13 | governance tests passed |

Verification record:

- focused Vision/fusion/documentation suite: `70 passed`;
- full repository suite: `2340 passed, 27 skipped`;
- Phase 2 provider/authority/documentation suite: `98 passed`;
- Phase 2 full repository suite: `2348 passed, 27 skipped`;
- affected-source Ruff checks and `git diff --check`: passed;
- live GLM/BrowserGym five-witness rerun: not run in this change and still pending.

## 12. Residual audit and bounded follow-up

### Current non-default Unified path

- no live `_visual_selected` state or reset-time provider-presence trigger remains;
- BrowserGym structural projection precedes the visual gate on every acquisition;
- matched visual evidence has explicit correspondence and zero coordinate binding;
- visual-only coordinate binding requires a shared acquisition root and fails
  closed when its identity is unclassified, corresponded, unresolved, or from a
  different acquisition;
- gate and correspondence dispositions are observable as bounded counters.

### Known migration debt, not hidden closure

1. Legacy `BrowserSession` / generic perception coordination still derives
   task-level visual needs and performs heuristic semantic grouping. It is used
   by older/default compatibility and benchmark paths, but is not the Unified
   correspondence or execution authority. Migrate or delete it at default
   cutover; do not extend it with new Vision fusion semantics.
2. `VERIFY_STRUCTURED_CANDIDATES` now uses a bounded main-VLM E-ref/SoM chooser
   in the SeeAct `text_choice_som` style. Its successful output is one offered
   E-ref; coordinates and new identities are unrepresentable.
3. GLM is the default `visual-only query -> point` implementation. ShowUI and
   GUI-Actor remain optional benchmark adapters at the same port, not required
   dependencies.
4. The optional OmniParser HTTP adapter normalizes official parser output into
   bounded, observation-only source-local regions. OmniTool's agent loop,
   planner, memory, and executor remain out of scope.
5. Postcondition diagnosis is represented in the typed gate, but the current
   BrowserGym call site does not yet feed an unresolved-postcondition signal.
   Wire it only when evaluator evidence can supply that typed fact; request prose
   or prior failure alone is insufficient.

These items keep the status non-closed until the live gate passes. They
do not require replacing BrowserGym/Playwright, WorldFusion, or EntityCorrespondence.

## 13. Phase 2 provider completion

User-directed provider choice: GLM is the initial and default implementation of
`visual-only query -> point`. It must consume a current visual-only entity/query
and return a bounded point proposal; it must not decide whether Vision runs,
create DOM correspondence, merge identity, or grant execution authority.

Work items:

1. `completed` — inventory the current proposer/grounder/provider ports and
   identify the smallest production seams for open-world proposal and E-ref
   disambiguation.
2. `completed` — make the GLM point-grounder role explicit in configuration and
   route only admitted visual-only targets through it.
3. `completed` — add an OmniParser-compatible `VisualRegionProposerPort` adapter
   without importing OmniTool or another agent runtime.
4. `completed` — add a bounded DOM-candidate visual disambiguation port whose only
   successful output is one supplied E-ref; wire `VERIFY_STRUCTURED_CANDIDATES`
   to it without coordinate fallback.
5. `deferred_by_authority_boundary` — connect typed unresolved-postcondition
   evidence to `DIAGNOSE_POSTCONDITION` only when the current evaluator owns and
   supplies that fact. No such pre-acquisition owner exists in the BrowserGym
   call site; request prose and guessed failure state remain forbidden inputs.
6. `full_suite_verified / live_gate_failed_diagnostic` — configuration,
   privacy/authority, unit, integration and provider-contract tests pass; docs
   and status are aligned. The real five-witness GLM run completed with valid
   evidence at `0/5`; the bounded causal record is
   `docs/evidence/2026-08-12-provider-split-live-diagnostic.md`.

Phase 2 non-goals: training/fine-tuning, importing external planner/memory/
executor loops, making OmniParser mandatory, or allowing any provider output to
bypass `EntityCorrespondence`, `WorldFusion`, admission, currentness or route
selection.

| Audit | complete | provider roles and authority consumers enumerated |
| Implementation | complete | GLM point, optional OmniParser, E-ref chooser wired |
| Verification | full suite pass / live fail | `2348 passed, 27 skipped`; valid live diagnostic `0/5` |
| Documentation alignment | complete | normative, status, integration and plan docs updated |

## 14. Phase 3 live-gate remediation

Input evidence:
`docs/evidence/2026-08-12-provider-split-live-diagnostic.md` (`0/5`, valid
diagnostic failure evidence).

Work items:

1. `completed` — replace whole-task point requests with a current atomic
   visual objective derived from current structured evidence and task state,
   without task-family routing or hidden answers.
2. `completed` — replace the duplicate-label ambiguity heuristic with a typed
   visual-need algebra that distinguishes single-candidate verification,
   visual-only point discovery, multi-target visual selection and visual-value
   extraction; unsupported needs fail closed rather than entering E-ref.
3. `completed` — make GLM point/E-ref structured output compatible with thinking
   models using bounded final-answer capacity and typed abstention/error
   outcomes; never parse free-form reasoning as authority.
4. `completed` — preserve authoritative verifier source lineage across
   `WorldFusion` so optional visual augmentation cannot turn a valid verifier
   snapshot into `source_insufficient`.
5. `completed` — retain typed provider failure stage/code/class diagnostics and
   persist stage/code counters instead of swallowing validation errors.
6. `completed` — persist every completed case atomically during the live gate and
   maintain a durable progress index; aggregate reporting failure must not
   erase per-case evidence.
7. `completed_with_live_gate_still_failed` — add invariant/property/integration regressions, run the full
   repository gate, then rerun the exact five-witness live GLM gate. Keep
   OmniParser quality separately unclaimed while it is unconfigured.

Exit criteria:

- point providers receive an atomic current objective, never an unresolved
  compound instruction;
- E-ref is selected only for a typed candidate-verification need; multi-target
  selection uses an explicit one-current-target-at-a-time mode rather than
  pretending the overall task has one unique target;
- multi-target/value-extraction needs are typed and never silently coerced to
  ordinary single-target E-ref or point grounding;
- fused observations retain verifier-authoritative source lineage;
- provider validation failures retain typed stage/code/class diagnostics and
  persist attributable stage/code counters;
- after each case, a durable case artifact and progress record exist before the
  next case begins;
- the same live witness gate produces attributable results without a new
  benchmark-specific Runtime branch.

Verification record:

- focused remediation contracts: `67 passed`;
- full repository suite: `2355 passed, 27 skipped`;
- exact five-witness snapshot: `98ff366906ff92705b1db7f21cb45de159ea4ddc`;
- live result: evidence-valid `1/5`, with `visual-addition` successful;
- durable progress: `5/5`, `complete=true`, plus five atomic case artifacts;
- report hash: `sha256:aa72a41a9f3a189e10c17dadcfd9b8818a29c8791f36f1749464eb76bacb452e`.

The remediation closes the six diagnosed architecture/runner gaps but does not
close the live performance gate. Remaining failures are downstream model
grounding/tool-output quality: three GLM point witnesses did not complete, and
`click-shades` performed one visually constrained effective DOM selection before
the main policy emitted invalid tool arguments on the next turn. GLM therefore
remains a pluggable baseline, not an attested SOTA point grounder.

## 15. Phase 4 structural-identity completion and point de-authoring

Status: `ARCHITECTURE_GATE_ACCEPTED / NAMED_REGRESSIONS_FIXED / GENERALIZATION_OPEN`

New repository evidence invalidates the Phase-3 classification of
`grid-coordinate` and likely `click-pie` as inherently visual-only. The pinned
BrowserGym raw DOM snapshot exposes 25 clickable SVG nodes for the former and
clickable SVG nodes for the latter. The current AX-only semantic projection
drops those controls before the visual gate, creating a false evidence gap and
unnecessarily assigning pixel-level grounding work to the Agent/provider path.

The bounded replacement contract is:

```text
AX controls + visible raw-DOM clickable controls
-> one canonical E-ref inventory with private BrowserGym identity
-> optional screenshot/SoM evidence over those same E-refs
-> Agent selects semantic action + E-ref only
-> Runtime resolves the E-ref to the private DOM binding

no structural identity
-> optional OmniParser observation-only V-ref proposal
-> explicit correspondence may recover a DOM E-ref
-> unmatched V-ref remains non-executable in this phase
```

Point grounders remain isolated benchmark arms. They are not used as the sole
architecture and no main Agent contract accepts or emits coordinates or boxes.
Phase 4 does not delete generic visual-surface foundations or ScreenSpot
evaluation support; it removes point execution from the BrowserGym mainline
until a separately admitted safe-region executor exists.

Work items:

1. `completed_revised_to_smaller_native_bridge` — configure BrowserGym's native
   DOM marking with `tags_to_mark="all"`, then consume its DOMSnapshot-derived
   clickability/visibility/geometry through the existing AX BID bridge. This
   avoids a duplicate sparse-CDP parser while covering SVG descendants without
   benchmark/task-family branches.
2. `completed` — merge AX and raw-DOM controls before semantic projection, with
   one private DOM identity per canonical E-ref and DOM execution authority.
3. `completed` — ensure same-ID screenshot/SoM marks cover the merged structural
   inventory and vision escalation treats those objects as structured
   candidates rather than visual-only discovery targets.
4. `completed` — make open-world proposer output observation-only by default;
   unmatched V-refs receive no BrowserGym point binding in this phase, while
   matched V-refs retain correspondence to DOM authority.
5. `completed_for_target_loop` — remove point actions from the main Agent-facing BrowserGym
   catalog/path while retaining isolated benchmark ports and historical
   compatibility surfaces outside the BrowserGym mainline.
6. `completed` — add invariant/property/integration coverage for SVG identity,
   nested-control deduplication, no-coordinate public contracts, DOM execution,
   unmatched visual fail-closed behavior and zero point-provider calls.
7. `full_and_real_probe_verified / frozen_live_gate_accepted` — run focused/full tests, a held-out real BrowserGym probe and the
   relevant live benchmark witnesses; update maintained architecture/status
   documents from measured evidence only.

Verification so far:

- focused BrowserGym architecture suite: `50 passed`;
- full repository suite after the multi-target/value remediation:
  `2373 passed, 24 skipped`;
- Ruff on affected Python sources/tests and `git diff --check`: passed;
- real target-loop seed-7 probes: `grid-coordinate` success and two-step
  `click-pie` success, with zero point-grounder calls; evidence record:
  `docs/evidence/2026-08-12-svg-dom-identity-target-loop-probe.md`;
- real GLM E-ref probe: `grid-coordinate (1,-2)` selected the correct `E24`,
  retained one DOM binding, and made zero point calls;
- clean-SHA frozen five-witness gate at `331ac0d`: evidence-valid `3/5`, with
  architecture acceptance true, zero point calls, zero visual-binding
  acquisition/dispatch and zero invalid tool arguments; maintained evidence:
  `docs/evidence/2026-08-12-phase4-dom-identity-live-gate.md`.

Files changed by work item will be recorded here as implementation proceeds.

Exit criteria:

- every visible actionable raw-DOM control in the supported BrowserGym snapshot
  algebra is either represented once by E-ref or rejected with a typed reason;
- AX and DOM representations of one control do not create duplicate entities;
- nested SVG drawing nodes for one logical control do not create duplicate
  executable actions;
- structural SVG targets are executed through BrowserGym/Playwright identity,
  never a model-produced point;
- main Agent requests and tool calls contain semantic actions/E-refs and no
  coordinate, bbox, selector, backend node or provider route fields;
- OmniParser proposals cannot grant execution authority; unmatched proposals
  are observation-only and fail closed if selected for an action;
- focused, full and held-out real-browser evidence agree before this phase is
  marked verified.

The architectural exit criteria are satisfied for this bounded five-witness
gate. The two named residuals are now remediated without coordinate authority.
The screenshot+AX main policy owns candidate choice and semantic action in one
call, settled values/toggles are removed from its next catalog, repeated visible
DOM leaf groups expose observation-only counts, and current controls expose
selected state plus computed-style color family. `visual-addition` succeeds in
two actions in the clean `8741890` five-case run; focused clean `7fae859`
`click-shades` succeeds in six structural actions with zero auxiliary E-ref or
point calls. See
`docs/evidence/2026-08-12-visual-value-and-multitarget-remediation.md`.
The final color-family increment has not been rerun across all five witnesses.
At the Phase-4 boundary, `grid-coordinate` E-ref selection remained stochastic;
Phase 5 above supersedes that named correspondence diagnosis with a clean
single-witness exact-relation success. Multi-seed and broader
performance/generalization remain open. `ActionBatch` is deferred rather than
made a prerequisite for correctness.
