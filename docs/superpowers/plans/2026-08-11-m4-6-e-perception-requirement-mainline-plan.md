# Task-Grounded Perception and Frontier Convergence Plan

Status: `IN_PROGRESS / GROUNDED_TOOLS_V2_TARGETED_VERIFIED / VISUAL_BINDING_NEXT`.

Goal: remove irreversible loss between acquired GUI observations and bounded
model presentation, then add incremental non-authoritative requirement
hypotheses without creating a second observation, task, action or completion
authority. The current convergence slice also makes the policy surface
referentially closed: one call-local public entity reference must identify the
same target in text, screenshot marks, tools and the previous tool result.

## Frozen constraints

- Screenshot bytes are observation evidence, never execution authority.
- `WorldObservation`/`SurfaceObservation` remain the sole observation truth.
  Their bounded full `EntityInventory` is projected by `ObservationPager`; no
  parallel `ObservationSpace` authority is introduced.
- `ObservedEntity`, `CandidateTarget`, `ActionTarget` and `VerifiedSubject` are
  roles over one canonical public `entity_id`, not four duplicated entity
  records. Hypotheses, actions and evidence reference that identity.
- Stable entity identity and current execution are separate: an
  `EntityObservationRef` binds entity + snapshot/revision, while every
  `ActionOption`/binding remains strictly current-epoch and stale use is
  zero-dispatch.
- `ActionSpace` remains the only legal-action authority; visual/AX aliases can
  only reference current public targets/actions and expire with the context.
- Existing SoM drawing utilities are reused as a deterministic projection over
  the current screenshot and current ActionPage. SoM marks do not create an
  entity, binding, action, or execution permission and do not restore the
  legacy `Affordance` path as an authority.
- Runtime state remains lossless and authoritative. The model-facing tool view
  may be bounded, but it must be allowlist-built, decision-sufficient and
  referentially closed; it must not be produced by blacklist-scrubbing a full
  `AgentContext`.
- Model transport must carry real typed image content; artifact summaries are
  not a substitute for image transport.
- Public semantic breadth may expose read-only structure without making every
  observed role executable.
- Requirement proposal produces bounded hypotheses only. Runtime assigns
  hypothesis IDs and owns admission/revision/retirement; verifier assessment
  owns only predicate `SATISFIED/CONTRADICTED/UNKNOWN`. Only `TaskGoal`, user
  input or existing criteria define authoritative task requirements, and only
  `TaskEvaluator` owns terminal task truth.
- Losslessness is scoped to the finite acquired snapshot, declared semantic
  profile and hard inventory cap. Capacity exhaustion/partial acquisition fail
  typed; infinite GUI, canvas and scroll-space completeness is not claimed.
- Source acquisition coverage, inventory completeness and model-presentation
  traversal are separate axes. Negative-claim coverage gates never overwrite
  authoritative source/evaluator facts.
- No static full-task DAG, task-name production branches, hidden benchmark
  answers, selectors, coordinates, credentials, or oracle state.
- The product goal is general GUI success in real environments. MiniWoB is a
  falsification and measurement instrument, never a source of Runtime behavior.
  Case IDs, task slugs, readiness cohorts, source-review rules, reward and
  reference answers may exist only in benchmark/test owners; they must not enter
  Runtime state, policy context, grounding, tool construction, admission,
  execution or evaluator inputs except through the ordinary public TaskGoal and
  environment observation/evaluator contracts used by every environment.
- Environment adapters may specialize in BrowserGym, Playwright, desktop or
  device mechanics. Capability semantics above those adapters must remain
  surface-neutral where the operation is shared; adapter specialization is not
  authorization for a MiniWoB task branch.
- Benchmark reports separate `capability_covered`, `unassessed` and
  `declared_gap` cohorts; mixed-denominator success is prohibited.

## Steps

| Step | Status | Work | Files |
|---|---|---|---|
| 0 | completed | Freeze revised terminology, authority split, scoped completeness and honest implementation statuses. | this plan; implementation status; current queue |
| 1 | completed | Replace role/label/ordinal identity with run/page-incarnation-scoped opaque entity identity while keeping action bindings epoch-bound. | `browsergym_entity_identity.py`; BrowserGym projection/environment; identity/execution tests |
| 2 | completed | Retain a bounded full entity/state/fact/relation/option-domain inventory inside `SurfaceObservation`; hard-cap overflow returns typed partial/capacity outcomes. | world contracts and BrowserGym projection |
| 3 | completed | Add `ObservationPager` and bounded traversal state over one frozen snapshot, with pinned header plus fair exploration slots. | model boundary and loop state |
| 4 | completed | Add `NegativeClaimCoverageGate` for absence/no-progress/infeasible/unsupported/unsupported-ProposeDone claims only; authoritative success and normal actions bypass it. | decision/progress control |
| 5 | completed | Run a clean current-SHA text-only versus screenshot+AX baseline on the intersection capability-covered cohort, separating run validity, comparison validity and inconclusive pairs. | benchmark profile and fresh evidence |
| 6 | completed | Add bounded instruction-first incremental `RequirementHypothesis` proposals with optional candidate entity references and unknown set completeness. | model/task hypothesis contracts |
| 7 | completed | Add atomic Runtime hypothesis admission/lifecycle plus verifier predicate assessment without creating task requirements or terminal truth. | task frontier/runtime admission/evaluation |
| 8 | completed | Add bounded hypothesis pinning to existing rolling objectives while preserving fair cursor enumeration and ActionSpace authority. | context projection/action relevance |
| 9 | diagnostic_complete / archived | Preserve the stopped `7c14190` dynamic-tools run as an incomplete mixed-cohort diagnostic: 8/60 completed, 0/8 success, one capability-covered, one unassessed and six declared-gap cases; make no performance claim and do not resume it. Its supported `login-user` witness proves that raw screenshot content and anonymous `act_NN` tools lack a shared grounding reference. | `docs/evidence/runs/p5-e-zhipu-dynamic-tools-60-seed7-7c14190-stopped/report.json` |
| 10 | implemented_and_tested | Implement `grounded_tools.v2`: an allowlist `ToolPolicyView`, one call-local `GroundingIndex(E1...)`, reuse of the existing SoM renderer on the current screenshot, the same refs in text/tools/results, schema-equivalent verb tools, and a private current-epoch resolver into existing `ActionOption`/bindings. Disable the requirement proposer in the short-loop profile. | BrowserGym physical geometry; grounding projection; tool catalog/transport bridge; short-loop profile |
| 11 | targeted_verified | Deterministic properties cover shared-ref alignment, duplicate-label distinction/typed gap, stale zero-dispatch, task-ID invariance, no ActionSpace expansion and one normal call per turn. The clean-`b9ad39a` Zhipu gate completed `login-user`, tab and both collapsible witnesses at 4/4 success with zero hypothesis calls, schema/argument repairs, grounding gaps and safety errors. | `docs/evidence/runs/m4-6-e-grounded-tools-v2-targeted-zhipu-b9ad39a/report.json` |
| 12 | next / required | Bridge the existing `VisualSurfaceAdapter`/`VisualRegionBinding` capability into the current BrowserGym target loop: screenshot region proposal or trusted visual geometry -> current observed entity -> private screenshot/viewport-bound point -> legal `ActionOption` -> existing admission/currentness/pointer execution. Use `grid-coordinate`, `click-pie*`, `click-shades` and `visual-addition` only as held-out witnesses for the generic capability; no task identity may reach production selection or dispatch. SoM marks alone never grant execution. | existing visual contracts/adapter/executor; BrowserGym environment/projection; visual targeted evidence |
| 13 | pending / required | Add current BrowserGym interaction breadth for viewport scroll and focus-aware keypress, with public scroll/focus state, bounded arguments, post-action observation and typed unavailable/stale outcomes. Reuse existing browser session/executor primitives where their contracts fit. | BrowserGym semantic/action profile, execution adapter, public state projection |
| 14 | pending / required | Make relational and changing state decision-sufficient: owner-preserving table/row/cell and list/item relations, bounded dynamic before/after delta, and current selection/checked/focus/scroll state. This is perception truth for table, list, inbox, form-sequence and game tasks, not task-specific solving code. | BrowserGym semantics/projection; world/model projection; semantic-delta owner |
| 15 | pending / required | Close general multi-step task control on top of the concise tool workspace: retain verified useful values and completed effects, expose unresolved task frontier and bounded recent deltas, and roll the current objective after verified progress. The policy performs compare/sort/arithmetic/text transformation and next-step choice; Runtime does not add per-task solvers. Add a typed value-reference transfer path for copy/clipboard-style tasks without exposing private routes. | task frontier/progress projection; tool result/workspace; value-reference binding |
| 16 | pending / required | Review the 14 readiness-unassessed cases against the pinned source and fresh observation traces, then either map them to an existing shared capability or add one bounded shared capability. No task-name production branch is allowed. | capability inventory v3 and targeted probes |
| 17 | pending | After each capability slice, run its targeted cohort plus a small previously supported no-regression witness. When steps 10-16 pass, run the frozen MiniWoB-60 with one exact profile and report supported, newly-covered, unassessed and remaining-gap outcomes separately as well as the honest aggregate. | benchmark reports/evidence |
| 18 | pending / post-60 breadth | Extend beyond the frozen 60 to the registry interaction families deliberately excluded by the old activate/fill/select selection: drag/drop, slider/spinbutton, hover, multi-select, general canvas gestures and multi-viewport/scroll coverage. Reuse existing DOM/visual gesture foundations before adding new execution machinery. | registry capability inventory and family-specific adapters |

## Next slice: `grounded_tools.v2`

### Trigger and causal scope

`dynamic_tools.v1` simplified the response envelope but retained nearly the
full model context, added a separate requirement-hypothesis call, and removed
the public target linkage needed to relate a screenshot control to `act_NN`.
The stopped clean-`7c14190` mixed-cohort run is diagnostic only, but its sole
capability-covered `login-user` case is a direct witness: two fill tools were
presented as indistinguishable visible targets, so the model filled both fields
with the username before activating Login. This is a model-facing grounding
projection defect, not evidence that the Runtime binding or ActionSpace
authority was lost.

The repository already contains `BoundingBox`, `VisualMark`, screenshot overlay
and observation-bound SoM utilities in `adapters/som.py`. The missing work is a
bridge into the current
`BrowserGym -> WorldObservation -> ActionPage -> tool policy` path. Do not
implement a second SoM system and do not route current execution back through
the legacy `SomAdapter.parse() -> Affordance/AffordanceLease` surface.

### Target data flow

```text
current WorldObservation + current ActionPage + raw screenshot
        + private current BrowserGym geometry
                         |
                         v
                 GroundingProjection
             public E1/E2/E3 + private resolver
               |            |             |
               v            v             v
       marked screenshot  entity index  verb tools
               \            |            /
                +------ ToolPolicyView --+
                         |
                         v
                 one model command
                         |
                         v
             existing SelectAction/admission
                         |
                         v
              binding/currentness/execution
```

One call-local alias namespace is mandatory. Use the same `E1`, `E2`, ... in:

- the copied and annotated screenshot;
- the concise public `GroundingIndex` with role, accessible label, current
  public state and bounded relation hints;
- tool target parameters and descriptions;
- the immediately following typed tool result and recovery feedback.

Do not expose BID, selector, DOM path, private target/binding ID, bbox or raw
coordinates. The grounding projection retains `E* -> current observed entity`;
for actionable aliases only, the private tool resolver additionally retains
`E* + verb -> context/observation/action/target/binding/schema/currentness`.
Both expire with the policy context. A model-provided alias is only a proposal;
every accepted command still becomes the existing typed decision and passes
current ActionSpace admission, risk/confirmation, binding, execution and
evaluation.

### SoM reuse boundary

- BrowserGym backend owns an owner-thread, read-only viewport-geometry read for
  the current BID and binds it to the current observation/page identity.
- A small grounding-projection owner assigns `E*`, selects the bounded marks
  and calls the existing image annotation primitive on copied PNG bytes.
- Prefer marks for current ActionPage targets, active-objective/pinned
  candidates and the minimum related entities needed to disambiguate them;
  do not paint the full retained inventory onto one screenshot.
- If a current entity has no reliable bbox, retain its AX/text reference. If
  two legal targets still have no public distinguishing evidence, return typed
  `tool_grounding_gap` with zero dispatch rather than guessing.
- SoM adds no provider call and never mutates the page. A mark is a grounding
  aid, not an `ActionOption`; visual-only tasks such as grid-coordinate still
  require a separately admitted visual binding before they become executable.

### Policy and transport simplification

- Build `ToolPolicyView` directly from typed Runtime projections using an
  allowlist: task brief, current grounding index, bounded current state,
  previous tool result, current action menu and the marked screenshot. Remove
  JSON round-trip plus blacklist scrubbing from the active v2 path.
- Group targets under schema-equivalent verbs where their parameter contract is
  identical, for example `fill(target: E1|E2, text)` and
  `click(target: E3|E7)`. Keep a target-specific tool only when its value or
  destination domain differs. Do not use either dozens of anonymous `act_NN`
  tools or one `execute_action(parameters: any)` escape hatch.
- In the short-loop benchmark profile, disable the requirement-hypothesis
  proposer. The normal path must contain one policy call per GUI turn. Preserve
  the proposer only as an explicit long-horizon option invoked at task start or
  after a verified frontier/coverage change, never merely because the
  observation ID changed.
- Use native tool calls where the exact provider/model profile supports the
  required contract. For the compact GLM fallback, expose one flat command such
  as `{"op":"fill","target":"E2","text":"UV"}`. Do not add another
  nested repair protocol if that bounded contract remains incompatible; report
  the model/protocol incompatibility typed.

### Owners and non-goals

- BrowserGym backend: physical bbox acquisition only.
- Grounding projection: public aliases, bounded descriptions and annotated
  screenshot only.
- Tool catalog compiler: schema-equivalent verbs over current aliases.
- Private catalog resolver: alias to existing Runtime action/binding identity.
- Provider adapter: native-tool or flat-command transport only.
- Runtime admission/evaluators: unchanged execution and truth authorities.

Do not add a planner, a second observation inventory, a second action registry,
an LLM SoM call, event sourcing, replay, arbitrary coordinate execution, or a
new production branch per MiniWoB task. Do not treat LOC reduction as the goal;
remove or bypass duplicated responsibilities and judge the result by owner
clarity, call topology and benchmark behavior.

### Build, reuse and outsource boundary

The project must implement only the authority-bearing integration seam. It
must not reimplement mature acquisition, browser, model-transport or telemetry
mechanisms merely to keep them in-repository:

| Capability | Decision | Runtime responsibility retained |
|---|---|---|
| Browser screenshot, AX tree, DOM/element handles, pointer/keyboard/scroll mechanics | outsource to BrowserGym/Playwright or the environment-native accessibility/input API | validate source identity, current epoch, capability and returned acquisition/dispatch facts |
| Accessible role/name/state computation | outsource to the browser/OS accessibility engine | canonicalize the returned public semantic fields once; never rebuild AX semantics with a second heuristic owner |
| SoM box/label rendering | reuse `adapters/som.py` and Pillow image annotation | choose current model-visible refs/marks and bind the annotated copy to the current observation |
| Visual region/point proposal, OCR and optional detector/VLM grounding | pluggable external/local port; select by declared environment/profile capability, never task identity | validate bounded output, screenshot/viewport lineage, confidence policy and current private binding before ActionSpace offer |
| Visual currentness and pointer dispatch | reuse `VisualSurfaceAdapter`, `VisualRegionBinding`, visual currentness and executor foundations | integrate them into the current World/ActionSpace path and retain stale/no-replay semantics |
| Native function/tool calling and tool-call history | use the provider SDK/API when the exact model profile supports it | publish the bounded current catalog, validate one returned call and map it to the private current resolver |
| Compact fallback transport | one small provider adapter for models without reliable native tools | parse/validate one flat command and emit typed incompatibility after the bounded transport repair policy |
| Model reasoning: target choice, compare, sort, arithmetic, text transform and next-step proposal | outsource to the selected policy model | provide decision-sufficient public state; never promote model claims into Runtime truth without admission/evidence |
| Retry/backoff and HTTP mechanics | reuse provider/HTTP client facilities behind the existing bounded provider orchestrator | own total attempt/deadline budget, the single accepted response and typed exhaustion; never replay a GUI dispatch |
| Task success for BrowserGym/MiniWoB | use the official environment verifier | validate lineage and map official facts into canonical `TaskEvaluation`; reward/oracle values never enter policy input |
| Trace storage, query and visualization | outsource to OpenTelemetry/Langfuse or simple JSON artifacts | emit committed canonical facts one-way; telemetry failure cannot change Runtime outcome |

The following cannot be outsourced because they define the product's authority
kernel: current observation/epoch, ActionSpace membership, public-ref to private
binding resolution, admission, risk/confirmation, `NOT_SENT/SENT/SENT_UNKNOWN`,
no-replay, evidence validation, verified working state and terminal task
disposition. External candidates and SDK results are inputs to those owners,
not substitutes for them.

### Complexity convergence: v2 replaces v1 layers

The diagnosed v1 call path is:

```text
full AgentContext
+ requirement-hypothesis call
+ per-ActionOption anonymous tool catalog
+ compact {tool,args}
+ outer/schema/selected-argument repair
+ conversion back to AgentDecisionPackage
```

`grounded_tools.v2` is accepted only if the active short-loop path becomes:

```text
typed Runtime state
→ allowlist ToolPolicyView + current GroundingIndex + current verb catalog
→ one provider transport boundary
→ one validated model command
→ one adapter to the existing Runtime decision/admission path
```

This is a replacement contract, not an additional facade:

- stop serializing the full `AgentContext` and blacklist-scrubbing IDs on the
  active v2 path;
- disable the requirement proposer for the short-loop profile instead of
  calling it and ignoring or repairing its result;
- replace anonymous one-option-per-tool catalogs with schema-equivalent verb
  tools and target refs, retaining a specialized tool only for a genuinely
  target-dependent parameter domain;
- keep exactly one provider decode/validation owner. Provider-specific syntax
  recovery may be bounded and measured, but it cannot create another policy or
  objective-repair loop;
- keep exactly one conversion from the model command into the existing typed
  Runtime decision. Do not duplicate admission, risk, execution or evaluation
  semantics in the facade;
- freeze `dynamic_tools.v1` as comparison/rollback evidence during the targeted
  gate, then remove it from the active short-loop profile after v2 passes. Do
  not maintain two independently evolving tool/context definitions;
- locate grounding projection, tool catalog compilation, provider transport
  and Runtime resolution in separate cohesive owners. `ContextBuilder`,
  `ToolPolicyView` or a transport bridge must not become a new projection god
  file.

Complexity acceptance is behavioral and structural, not a raw LOC threshold:

1. one normal policy call per GUI turn and zero short-loop hypothesis calls;
2. one allowlist policy projection, one current tool catalog and one validation
   boundary in the active path;
3. no JSON round-trip/blacklist scrub and no duplicate action descriptions in
   both full context and tools;
4. adding a semantic verb or provider transport changes its catalog/adapter
   owner, not the Runtime loop, task frontier, benchmark classifier and several
   repair modules simultaneously;
5. benchmark evidence reports provider attempts, repair attempts, input tokens,
   latency and GUI dispatches so a shorter schema cannot conceal a longer call
   topology.

### Falsifiable acceptance

1. Every model-visible `E*` identifies exactly one current observed entity.
   Every tool-offered target ref additionally resolves to at least one current
   legal `ActionOption`; a read-only ref never gains that mapping merely from
   its mark. Every model-visible actionable mark uses the same ref as its tool.
2. Screenshot, entity index, tool menu and previous result agree on each ref;
   stale catalog/context use is typed and zero-dispatch.
3. SoM annotation causes zero additional provider calls, exposes no private
   geometry and creates no action permission.
4. The short-loop normal path makes one model call per GUI turn; requirement
   hypothesis calls are zero in that profile.
5. `login-user` exposes distinct Username, Password and Login refs and reaches
   the correct existing bindings. Duplicate-label witnesses either gain a
   bounded public relation/mark distinction or fail `tool_grounding_gap` before
   dispatch.
6. All accepted commands continue through existing ActionSpace admission,
   currentness, risk/confirmation, execution and effect/task evaluation.
7. Only after these properties and targeted live witnesses pass may a new
   capability-covered cohort run support a benchmark claim. The stopped 8/60
   diagnostic and declared-gap cases remain excluded from that denominator.
8. Renaming a benchmark case/task ID while preserving the same public goal,
   world and actions cannot change the produced policy workspace, available
   tools, admission result or execution route. Benchmark inventory/readiness
   metadata is absent from provider requests and canonical Runtime state.

## Real-environment capability backlog surfaced by benchmark

The frozen MiniWoB-60 inventory v2, evaluated against the currently declared
capabilities and pinned reviewed source, reports 15 declared-supported, 31
declared-unsupported and 14 readiness-unassessed tasks. Missing-capability
counts below overlap; they identify shared implementation families, not a new
branch per task:

| Capability family | Frozen-60 evidence | Required response |
|---|---:|---|
| Referentially closed screenshot/tool grounding | direct `login-user` witness | `grounded_tools.v2` with shared `E*` refs and existing SoM annotation |
| Visual geometry/spatial observation and executable binding | 5 tasks | current BrowserGym bridge to existing `VisualRegionBinding`; targeted point activation before general canvas work |
| Scroll action and scroll-state observation | 10 tasks | typed viewport scroll plus current scroll/coverage state |
| Focus-aware keypress | 6 tasks | bounded current-focus key action and post-action verification |
| Dynamic-change observation | 13 tasks | bounded public before/after semantic delta over current epochs |
| Multi-target sequence control | 12 tasks | verified rolling frontier, useful-value memory and next-objective projection |
| Table extraction and structural relations | 4 tasks | owner-preserving table/row/cell projection and concise policy rendering |
| List relation | 2 tasks | ordered list/item relations and stable public identity |
| Compare | 5 tasks | adequate structured values/relations for policy reasoning; no task-specific comparator branch |
| Clipboard/value transfer | 2 tasks | typed public value reference carried into an admitted fill action |
| Game loop and memory across turns | 2 tasks | current board/state delta plus bounded verified run memory |
| Arithmetic, sort and text transform | 1 task each | policy reasoning over visible typed values; reconsider model/profile only after decision-sufficient input is proven |
| Unknown semantic/control axes | 14 readiness-unassessed tasks | pinned-source review and fresh trace classification before claiming support |

This queue changes the earlier gate interpretation. `capability_covered` remains
the clean regression denominator, but it is not the product boundary. Proven
declared gaps are implementation work, not cases to exclude indefinitely. Each
new shared capability graduates tasks into a newly-covered cohort, after which
the inventory declaration and benchmark denominator are updated together.

The old visual foundation is therefore not optional future research. It is a
required integration slice. What remains evidence-gated is the choice of extra
grounder (AX-derived geometry, deterministic CV/OCR, or VLM region proposal)
for surfaces where no reliable current region exists; regardless of producer,
Runtime must validate the resulting current visual binding before ActionSpace
offers it.

The named MiniWoB cases in this plan are acceptance witnesses only. A valid
implementation must behave identically if those case IDs and task slugs are
renamed while the public TaskGoal, observation and ActionSpace are unchanged.
Production modules must not import the MiniWoB breadth inventory or select a
grounder, tool, action, verifier or recovery rule by benchmark identity.

## Exit criteria

- A provider receives actual screenshot image content plus the same bounded
  public context, and text-only mode remains deterministic and compatible.
- Missing/oversized/unsupported image content fails typed before a provider
  call; private capture can retain exact exchanges outside public evidence.
- Observable roles and structural nodes can inform policy without silently
  becoming executable actions.
- Finite-snapshot losslessness: within the declared profile/cap, every retained
  entity is reachable through bounded paging or traversal ends typed unknown.
- Scoped stable identity: irrelevant AX order changes do not change an entity
  ID, while old action bindings remain stale after epoch change.
- Non-amplification: observation/hypothesis/pinning never creates or legalizes an
  ActionOption.
- Negative-claim coverage safety: incomplete model traversal cannot justify an
  absence/no-progress/infeasible/unsupported conclusion.
- Hypothesis non-authority: predicate assessment cannot define task necessity,
  hypothesis-set completeness or terminal success.
- Bounded traversal liveness: every traversal terminates complete or typed
  unknown within declared page/byte/policy-call budgets.
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
- 2026-08-11: a clean-SHA directed `click-tab-2` rerun proved that Mistral
  received the corrected fields but repeated the exact objective/action package.
  The remaining contract gap was actionable replacement data: “change this
  predicate” did not identify a currently admissible replacement. Recovery now
  projects bounded Runtime-derived `admissible_objective_operations`: no
  objective operation, or a proposal for the current frontier with
  `task_outcome_is: complete`. The model is told to copy one complete candidate;
  Runtime still independently admits the objective and current ActionSpace
  remains the only action authority. Full validation remains 2220 passed and 27
  skipped; Ruff and mypy pass. A fresh clean-SHA directed rerun is required.
- 2026-08-11: that rerun still returned the exact rejected package despite the
  typed candidates, proving prompt compliance alone is insufficient for this
  model. The bridge now narrows only an `objective_already_satisfied` repair
  call's provider JSON Schema to the Runtime-projected objective candidates and
  revalidates the same subset locally. The canonical package schema and action
  schema are otherwise unchanged, and Runtime admission remains final. Full
  validation is 2221 passed and 27 skipped; Ruff and mypy pass. A fresh
  clean-SHA directed rerun is required to verify provider schema compatibility
  and actual dispatch.
- 2026-08-11: the clean-SHA `60e9771` directed rerun passed. Call 1 proposed an
  already-satisfied `target_present` objective and was rejected with zero
  dispatch. Call 2 received both typed repair candidates; the provider schema
  selected `objective_operation: none`, retained the legal click decision, and
  Runtime independently admitted and dispatched it. The external verifier
  returned `terminal_success/verified_success`. The run used two policy calls,
  two provider attempts and one execution, with no evidence/harness errors.
  Public trace and mode-0600 raw exchanges are retained under the local
  `artifacts/m4-6-e-objective-feedback-click-tab-60e9771` diagnostic tree.
- 2026-08-12: architecture-first convergence review froze the shared
  task-grounded perception/frontier cause while retaining separate authorities.
  Screenshot transport, first semantic breadth, diagnostic A/B and the P5-E
  rolling-objective vertical slice exist; stable entity identity, non-lossy
  bounded inventory, observation traversal/negative-claim gating and an
  incremental requirement-hypothesis producer do not. Viewport tiling, OCR, SoM
  and automatic scrolling are explicitly deferred until fresh evidence makes
  them the next blocker. Step 1 started.
- 2026-08-12: step 1 implemented. A Runtime-private keyed identity mapper now
  derives opaque `entity:*` IDs from page/episode incarnation plus stable
  private BID/node identity. AX permutation and unrelated insertion preserve
  IDs; same-label controls remain distinct; page-incarnation changes mint new
  IDs. Independent capture preserves entity identity while replacing bindings,
  and replaying the old binding remains zero-dispatch. Modified files:
  `browsergym_entity_identity.py`, BrowserGym projection/environment and focused
  identity/execution tests. Validation: 71 focused tests passed, Ruff and mypy
  passed, and the full suite passed 2224 with 27 skipped. Step 2 started.
- 2026-08-12: steps 2-4 implemented as one bounded observation slice. BrowserGym
  now retains up to 512 canonical entities and 4096 facts before any model
  projection; option domains, relation counts and typed capacity reasons are
  conserved by `EntityInventorySummary`. The 64-target model limit is now a
  page size only. `ObservationPager` binds opaque cursors to one frozen
  snapshot, preserves current action targets in a bounded header and reserves
  fair exploration slots. A `RequestObservation.cursor` advances only the
  in-memory page and consumes no acquisition. `NegativeClaimCoverageGate`
  intercepts absence/no-progress/unsupported and evidence-free completion
  claims while traversal is partial; incomplete acquisition/inventory becomes
  typed unknown. Ordinary actions and authoritative evaluator success bypass
  the gate. Adversarial tests put 70 distractors before a critical action target
  and retain both the target and a usable exploration cursor. Validation:
  Ruff passed, mypy passed across 451 source files, the full suite passed 2229
  with 27 skipped, and all 15 documentation-governance checks passed. The
  current-SHA perception A/B is the next gate.
- 2026-08-12: before executing step 5, upgraded the A/B report contract to
  `miniwob-perception-ab.v2`. Public cohort naming is now
  `capability_covered`, the primary metric is explicitly the
  declared-capability-covered cohort success rate, and
  `run_evidence_valid`, `comparison_valid`, and `inconclusive_pairs` are
  separate. A provider-contaminated pair can no longer be presented as a valid
  perception comparison even when its archived run evidence is structurally
  valid.
- 2026-08-12: step 5 ran from clean implementation SHA `b892c3a` on 15
  capability-covered paired cases. The archive is structurally valid, but the
  overall comparison is invalid because 7 pairs contain provider failures.
  Text-only produced 11 success and 4 provider-unavailable outcomes;
  screenshot+AX produced 9 success, 5 provider-unavailable and 1
  no-progress-control-repetition outcome. Among the 8 uncontaminated pairs,
  text-only was 8/8 and screenshot+AX was 7/8; this neither demonstrates a
  screenshot gain nor supports a clean overall regression claim. Every one of
  37 captured screenshot-arm requests contained an image part, while 0/32
  text-only requests did. Public evidence is under
  `docs/evidence/runs/m4-6-e-perception-ab-capability-covered-b892c3a`; exact
  raw exchanges remain private outside the repository with directory mode 0700
  and file mode 0600. Step 6 started; viewport/OCR/SoM remains deferred.
- 2026-08-12: steps 6-8 implemented as a non-authoritative hypothesis slice.
  A model proposer receives only public instruction, bounded world/action views
  and an optional real screenshot; output is limited to eight closed typed
  predicates and always declares set completeness `unknown`. Runtime validates
  all references atomically, assigns opaque `hypothesis:N` IDs and owns
  revision/retirement. Any invalid member causes zero installation. Verifier
  assessment is limited to `satisfied/contradicted/unknown`; incomplete or
  unassessed inventory cannot prove absence. Active unknown hypotheses may pin
  at most eight candidate entities while `ObservationPager` retains reserved
  fair-enumeration slots. An adversarial test places 70 distractors before a
  read-only required heading and proves it remains visible without creating an
  `ActionOption`. The proposer is optional and its provider/invalid-response
  failure is nonterminal metadata, not a GUI turn or task failure. Step 9 is
  now the remaining benchmark gate; implementation is not a success claim.
- 2026-08-12: closed the first-page hypothesis loop before benchmark work. The
  proposer now receives the current opaque observation cursor and reads the
  same frozen inventory page that triggered augmentation. Calls are limited to
  one initial proposal plus changed-snapshot/page augmentation, with four calls
  maximum per run. Target-loop evidence reports
  `requirement_hypothesis_calls` separately from GUI `policy_calls`; both paths
  share benchmark pacing, and hypothesis calls create no GUI turn. Cohort
  partitioning now exhaustively and disjointly reports `capability_covered`,
  `unassessed` and `declared_gap`. Live separated-cohort execution remains step
  9 and requires a clean implementation SHA.
- 2026-08-12: provider recovery also wraps the task-start/page-augment model
  call. Retryable rate-limit, capacity and outer timeout failures receive the
  same bounded attempt/deadline policy before one typed nonterminal hypothesis
  failure is exposed; retries do not create GUI turns. Benchmark
  `provider_attempts` and `provider_retry_count` include these attempts.
- 2026-08-12: the first clean-SHA capability-covered live run at `6ee97e9`
  completed 15/15 with 9 success, 4 provider-unavailable, 1 control repetition
  and 1 case timeout. It exposed a benchmark projection defect:
  `requirement_hypothesis_calls` existed in canonical target-loop evidence but
  was removed by the breadth `REQUIRED_METRICS` whitelist, so the generated
  archive incorrectly reported zero calls. The archive is retained and marked
  `run_evidence_valid=false`; it is diagnostic execution fact, not comparison
  evidence. The metric is now required by the breadth profile and an enabled
  hypothesis arm fails its evidence gate if any case lacks at least one
  hypothesis call. Full validation after the repair is 2246 passed and 27
  skipped. A fresh clean-SHA rerun is required before continuing other cohorts.
- 2026-08-12: cross-provider execution remains a separate cohort profile. The
  frozen Mistral perception A/B still rejects any other provider identity;
  `run_provider_cohort_arm` admits a canonical bridge with an explicitly
  reported provider/model solely for provider-comparison evidence. Focused and
  full validation pass (2247 passed, 27 skipped) before the Zhipu run.
- 2026-08-12: `dynamic_tools.v1` A/B and the selected-tool argument-repair
  rerun were archived through clean HEAD `7c14190`. The facade reduced tokens,
  latency and decision-schema repair on the two-case comparison, but case 15
  remained a structured-output failure because the compact outer object did
  not constrain the selected tool's arguments. The comparison did not prove a
  success-rate gain.
- 2026-08-12: the subsequent MiniWoB-60 dynamic-tools run was deliberately
  stopped after 8 completed cases. It was 0/8 across a mixed cohort containing
  one capability-covered, one unassessed and six declared-gap cases and is
  retained only as `INCOMPLETE_DIAGNOSTIC`; no success-rate or generalization
  claim is permitted. The supported `login-user` trace provided the decisive
  witness: the screenshot contained distinguishable Username/Password fields,
  but the model received anonymous fill tools with no shared screenshot ref and
  filled both with the username. The same partial run also showed that the
  requirement proposer was effectively adding a call and repair path per GUI
  turn.
- 2026-08-12: the fresh evidence ends the earlier SoM deferral for this bounded
  purpose. Step 10 is now `grounded_tools.v2`: reuse the already implemented
  SoM annotation primitives through a thin current-path grounding projection,
  share one call-local `E*` namespace across screenshot/text/tools/results,
  construct an allowlist policy view, group schema-equivalent verb tools and
  disable the proposer in the short-loop profile. SoM remains non-authoritative
  and cannot create an ActionOption or make a visual-only target executable.
- 2026-08-12: corrected the next-queue scope after reviewing the frozen 60
  against capability inventory v2 and pinned source. The previous wording made
  visual-only binding conditional even though `grid-coordinate` had already
  supplied a direct zero-action witness. The inventory reports 15
  declared-supported, 31 declared-unsupported and 14 readiness-unassessed
  cases. Steps 12-18 now explicitly schedule reuse of the existing visual
  binding foundation, scroll/keypress, relational and dynamic perception,
  verified multi-step working state, unassessed-case review, the exact-profile
  60 rerun and post-60 interaction breadth. Cohort separation remains an
  attribution rule, not permission to leave proven capability gaps unfixed.
