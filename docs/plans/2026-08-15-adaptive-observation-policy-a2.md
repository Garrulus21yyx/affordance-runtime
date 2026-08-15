# Wave A.2 adaptive observation policy and bounded world lens

Status: `DESIGN_ACCEPTED / WORLD_GRAPH_A.1_CLOSURE_ADMITTED /
A.2_IMPLEMENTED / SELECTOR_OWNER_CONVERGED / ACQUISITION_PORT_CONVERGED /
GENERIC_STAGE2_CONNECTED / POST_ACTION_FALLBACK_NEEDS_CONSERVED /
PROPERTY_VERIFIED / INDEPENDENT_FRESH_CONTEXT_REVIEW_PENDING / LIVE_NOT_RUN`

Scope: select which available observation sources are semantically activated
for one acquisition, fuse only those source observations, and project one
bounded canonical world lens to the Actor. This slice adds no extraction,
automation, OCR, grounding-model, graph-database, interaction, or evaluator
engine.

## 1. Decision

The Runtime must not acquire, semantically process, fuse, and expose every
available source on every turn. A.2 closes one policy boundary:

```text
typed observation need + current coverage/freshness + source offers + budget
                                |
                                v
                     ObservationOrchestrator
                     sole source-selection owner
                                |
                                v
                     ObservationSelectionPlan
                                |
                acquire/project only selected sources
                                |
                                v
                WorldFusion(selected observations only)
                                |
                                v
                       WorldObservation
                                |
                                v
             ActorWorldSnapshot bounded canonical lens
```

A.1 owns how a selected set of `SurfaceObservation`s becomes one accepted
world. A.2 owns which sources enter that set for this acquisition. `WorldFusion`
never chooses, acquires, or escalates a source. An adapter never mutates a
selection plan. The Actor projector never decides that another source should be
called.

## 2. Four layers that must not be conflated

BrowserGym/Playwright may physically capture screenshot, DOM and AX data in one
upstream read. That does not require every channel to become a semantic source,
enter fusion, or reach the model.

| Layer | Meaning | Owner |
|---|---|---|
| physical capture | obtain one backend snapshot/capture group, possibly containing several raw channels | established backend through thin adapter |
| semantic provider activation | normalize a selected raw channel or invoke OCR/VLM/region provider | selected surface/provider adapter |
| world fusion | adjudicate only the selected normalized observations | `WorldFusion` |
| Actor delivery | render one bounded canonical primary/novel lens and only selected media | Actor projector |

One raw capture can therefore support DOM-only semantics now and a later
targeted visual augmentation without pretending that raw screenshot
availability was already visual evidence. Views from the same capture group
share lineage and are not independent agreement.

## 3. Sole owner and contracts

The existing `ObservationOrchestrator` remains the owner. A.2 extends and
converges it; it does not add a second `ObservationPolicy` implementation.

Lifecycle intent and epistemic need are separate:

```python
class ObservationPurpose(StrEnum):
    WORLD_GROUNDING = "world_grounding"
    ENTITY_DISCOVERY = "entity_discovery"
    TARGET_DISAMBIGUATION = "target_disambiguation"
    EFFECT_VERIFICATION = "effect_verification"
    CRITERION_VERIFICATION = "criterion_verification"
    CURRENTNESS_REFRESH = "currentness_refresh"


@dataclass(frozen=True)
class ObservationNeed:
    need_id: str
    purpose: ObservationPurpose
    subject_ids: tuple[str, ...]
    required_modality: ObservationModality | None
    required_assurance: ObservationAssurance
    freshness: FreshnessRequirement


@dataclass(frozen=True)
class ObservationSelectionPlan:
    need_ids: tuple[str, ...]
    selected: tuple[SelectedObservationOffer, ...]
    unselected: tuple[UnselectedObservationOffer, ...]
    acquisition_budget: int
    reason_codes: tuple[str, ...]
```

The exact enum names may reuse existing request/offer types, but these
properties are mandatory:

- `WorldObservationRequest` continues to express reset, independent capture,
  post-action, or explicit observation lifecycle;
- `ObservationNeed` expresses what evidence is missing and why;
- `ObservationOffer` remains a static/current backend offer with modality,
  assurance, cost and acquisition group;
- `ObservationSelectionPlan` is immutable, auditable, and already final when
  passed to adapters;
- selection failures are typed unavailable/insufficient outcomes, not implicit
  observe-all or adapter-local fallback.

### Inputs allowed to influence selection

- Runtime-mechanical coverage, freshness, currentness and conflict state;
- an admitted Agent observation need, never a backend/source name or private
  route;
- an evaluator's explicit verification obligation;
- current observation offers, assurance, acquisition group, cost and budget;
- bounded prior no-gain/escalation state for the same need.

Task slug, benchmark case, label keyword, selector, known page layout, provider
name, source order, or historical success list are forbidden selection inputs.

## 4. Deterministic selection policy

Default acquisition budget is one semantic source. A normal augmentation may
raise it to two. A third source requires a newly admitted typed unresolved
obligation and is outside the first A.2 implementation.

| Current need | Required plan |
|---|---|
| ordinary form/navigation/read with structurally complete target | one DOM/AX/native structural source |
| unique legal semantic action after canonical grouping | one structural source |
| native/API/WoT criterion whose authoritative state is available | authoritative state source; structural source only if control/navigation context is also needed |
| relevant entity absent from structural coverage, or canvas/image/icon/spatial property is required | structural + targeted visual, or visual required when structure is unavailable |
| candidates remain semantically indistinguishable after role/name/within/state/relation and current ActionSpace grouping | structural + targeted visual disambiguation |
| action contract is mechanically settled by route-owner post observation | route-owner source only |
| action/criterion contract remains unresolved and explicitly permits semantic visual evidence | route-owner/authoritative source + targeted visual |
| sources conflict | preserve typed conflict; do not automatically call a third source |
| current complete source already answers the same need | reuse or return typed no-gain; do not expose a redundant observe call |

The visual trigger is based on a typed evidence gap after canonical world and
current action analysis. Raw duplicate role/label pairs or an empty binding set
alone are not sufficient: read-only pages, terminal states, and candidates
already distinguished by `within`, state, relations, or tool choice would
otherwise cause unnecessary vision calls.

Post-action acquisition uses the executed route owner plus sources required by
the action's sealed verification obligation. It does not blindly reacquire all
sources that were previously marked required.

## 5. Two-stage acquisition without a second policy

Some needs are only knowable after a cheap baseline observation. The same
orchestrator therefore supports two bounded stages:

```text
stage 1: select cheapest sufficient structural/authoritative offer
         -> acquire/project/fuse
         -> compute typed residual need

stage 2: only if residual need remains and budget permits,
         select one targeted complementary offer
         -> acquire/project/fuse as the next authoritative observation
```

The adapter may map the generic selected offer to a backend-private mode, but
it cannot add visual, change required/optional status, or store a hidden
`last_visual_escalation` decision. Same-group raw channels should reuse the one
physical capture when the backend supports it.

## 6. Actor projection: preserve the world, expose only the useful lens

Runtime retains selected source envelopes, lineage, conflicts, canonical
entities, structure, facts/relations, media and truthful coverage. The Actor
does not receive parallel raw DOM, AXTree, SoM and visual-object dumps.

For a structural-only world, the model receives:

- one canonical hierarchy with E-refs;
- public role/name/state/facts/relations needed for the task;
- current coverage, uncertainty and conflicts;
- independent flat semantic tools from the current ActionSpace.

For a structural+visual world, the model receives:

- the same canonical entity once, with aggregated `source_refs`;
- a screenshot/mark manifest aligned to the same E-ref when useful;
- complementary visual content only when it is novel, unmatched, conflicting,
  or necessary for the admitted need;
- no repeated full structural tree, provider-local number, selector,
  coordinate, BID or private binding.

The primary/novel lens remains the single projection owner. Tools do not copy
entity structure, and world projection does not rebuild tool candidates. A
current tool may reference the same E-ref, but that shared call-local reference
does not make either projection authoritative over the other.

Observation tools are projected only when a currently missing, stale, partial,
or unresolved need can produce information gain. If public provider APIs force
modality-named tools, the name is a transport representation; Runtime still
resolves it to a typed need and current offer. A fresh, complete current source
must not be accompanied by a no-op `observe_<same modality>` tool.

## 7. Existing code to converge, reuse, and delete

The repository audit found useful pieces but also five concrete owner splits:

| Current path | Finding | A.2 disposition |
|---|---|---|
| `world/observation_orchestrator.py` | already ranks offers structure-first with an at-most-two-source budget | retain as sole selector |
| `surfaces/browsergym/environment.py::_evidence_gated_plan` | mutates the selected plan and stores `last_visual_escalation` | move decision input/output to orchestrator; delete mutation/side channel |
| `world/orchestrator.py::_compatibility_observe_all` | missing offers silently becomes observe-every-adapter | delete; missing declaration is typed unavailable |
| `world/surface_adapter.py` | port does not require offers although concrete adapters expose them | make offer declaration part of the port |
| `model/policy/grounded_tool_catalog.py` | observation tools are projected even when the current source is fresh/complete | project only an admitted residual observation need |
| post-action planning in `world/orchestrator.py` | route source is combined with previously required sources | derive sources from route owner plus verification obligation |

BrowserGym's direct environment and generic `UnifiedWorldEnvironment` also
assemble selection/acquisition differently. A.2 does not preserve both as
policy owners: backend-specific raw capture may remain private, but both must
consume the same final `ObservationSelectionPlan` and produce the same typed
acquisition results.

Reuse:

- current `WorldObservationRequest`, `ObservationOffer`,
  `ObservationSelectionPlan`, and `ObservationOrchestrator`;
- the existing structure-first and at-most-two-source selection behavior;
- `VisionEvidenceNeed` concepts after moving their final decision into the
  orchestrator contract;
- BrowserGym/Playwright synchronous DOM/AX/screenshot capture and BIDs;
- current `WorldFusion`, source lineage, Actor primary/novel lens, and
  provider image gating;
- replaceable OmniParser/OCR/grounding providers only where a typed need calls
  them.

Converge/delete in the same implementation slice:

- delete `_compatibility_observe_all`; `observation_offers` becomes mandatory
  on the environment/surface port and absence returns typed unavailable;
- remove BrowserGym `_evidence_gated_plan` plan mutation and mutable
  `last_visual_escalation` authority; emit the decision in the plan/trace;
- remove adapter-specific selection branches that duplicate orchestrator
  policy;
- replace always-visible modality observation tools with need/availability-
  gated projection;
- select post-action sources from verification obligations rather than prior
  plan membership;
- keep no read-new/fallback-old, dual policy, or shadow owner after cutover.

No new source provider is required to close A.2. The first implementation is a
convergence of code already present in the repository.

## 8. SOTA alignment and reuse boundary

- [BrowserGym's observation implementation (reviewed 2026-08-15 at commit `9e779f0`)](https://github.com/ServiceNow/BrowserGym/blob/9e779f087de9a65668b6974d11f9ce9816026e96/browsergym/core/src/browsergym/core/env.py)
  captures DOM, AXTree, element properties, focus and screenshot together and
  injects shared BIDs before extraction. A.2 reuses that upstream capture and
  shared identity instead of post-hoc label/IoU matching.
- [SeeAct](https://proceedings.mlr.press/v235/zheng24e.html) separates semantic
  action generation from grounding and reports that its best grounding combines
  HTML structure and visual evidence. A.2 keeps semantic choice distinct from
  private binding and requests visual grounding only for a typed residual gap.
- [OmniParser](https://github.com/microsoft/OmniParser) is an established visual
  screen parser producing regions/interactivity/icon descriptions. It remains
  a replaceable visual `SurfaceObservation` producer, never canonical-world or
  action authority.
- [OSWorld](https://proceedings.neurips.cc/paper_files/paper/2024/hash/5d413e48f84dc61244b6be550f1cd8f5-Abstract-Datasets_and_Benchmarks_Track.html)
  and its baseline studies motivate preserving multimodal capability without
  assuming that more simultaneous representations always help the model.
- [DiMo-GUI](https://aclanthology.org/2025.emnlp-main.1334/) uses dynamic focal
  refinement when grounding remains ambiguous. A.2 adopts the general
  ambiguity-triggered, targeted-refinement principle, not its benchmark or
  inference pipeline.

There is no upstream project that supplies the whole cross-surface canonical
world authority required here. The repository owns only typed need selection,
proposal adjudication, canonical mapping, evidence lineage, action legality and
bounded projection. It delegates extraction, screenshots, browser control,
accessibility APIs, OCR and visual parsing to established libraries/providers.

## 9. Contradiction audit

The design introduces no new owner cycle:

```text
ObservationOrchestrator selects
-> Adapter captures/projects selected offers
-> WorldFusion adjudicates selected observations
-> WorldObservation owns accepted current truth
-> Actor projector renders bounded truth
-> ActionSpace independently exposes current legal interactions
```

Explicit non-overlap:

- A.1 repairs fusion/output/world/projection correctness; A.2 never changes
  alignment acceptance.
- A.2 selects evidence; it does not create canonical identity, bindings,
  actions, task truth, or effect truth.
- Step 15 owns facts-first state, typed general relations and
  `SemanticDelta`; A.2 consumes their future public results but does not
  preimplement them.
- the capability registry describes interaction support, not observation
  offers or evidence sufficiency;
- tool registry/compiler exposes current semantic actions, not source
  acquisition authority;
- evaluator obligations may request evidence but cannot select a private
  provider or mutate the world.

The only intentional shared values are immutable inputs across one-way ports:
current canonical subject IDs, need IDs, source-instance IDs, capture-group
lineage and ActionSpace E-refs. No downstream component reconstructs an
upstream owner from these values.

## 10. Implementation and exit gates

Implementation begins only after A.1 repair restores trustworthy selected-set
fusion. A.2 then proceeds as one owner-convergence slice:

1. make offers and typed needs explicit at the world/environment port;
2. move all final source-selection logic into `ObservationOrchestrator`;
3. delete observe-all and adapter plan mutation;
4. connect verification obligations and admitted Agent needs;
5. gate observation-tool and image projection by residual information need;
6. add invariant/property and representative integration tests;
7. delete displaced compatibility/test fixtures and update status together.

Exit properties:

- structural-complete ordinary turns activate exactly one semantic source;
- typed ambiguity/coverage/visual-property gaps activate at most one targeted
  complementary source under the first-version budget;
- source selection is invariant to offer input order and contains reason/need
  lineage;
- same capture group is physically acquired once when multiple selected views
  share it;
- no adapter can add or silently require a source after plan selection;
- missing offers and exhausted budget produce typed deterministic outcomes;
- the model receives one canonical E-ref/entity and no repeated raw source
  dumps or redundant current observation tool;
- ActionSpace, admission, currentness, binding, dispatch, evaluation, and task
  truth remain independent;
- held-out structural-only, visual-required, conflict, post-action, and
  no-information-gain cases pass without task/site/benchmark branches.

Fresh benchmark evidence follows the bounded architecture gate; it does not
replace the invariant tests and is not part of A.1 repair.

## 11. Reopened implementation record

The earlier `A.2_IMPLEMENTED / PROPERTY_VERIFIED` attestation is withdrawn.
Held-out review showed that selection authority converged, but the immutable
plan did not cross the provider acquisition port: generic adapters still
received only a reason string, offer source identity was implicitly equated to
`adapter.surface`, generic acquisition did not run residual stage two, and the
independent post-action fallback dropped verification needs. BrowserGym
therefore had a richer acquisition contract than the generic world path. The
earlier green suite did not cover those invariants and is historical execution
evidence, not A.2 closure evidence.

A.2's selector portion was implemented as an atomic owner convergence. `WorldObservationRequest`
now carries lifecycle kind separately from immutable typed `ObservationNeed`s;
every surface port declares `observation_offers`; and
`ObservationOrchestrator` is the only production constructor of an immutable
`ObservationSelectionPlan`. Offer ordering cannot change selection, ordinary
grounding uses one cheapest sufficient source, an explicit or residual need may
raise the bounded plan to two sources, and a third-source requirement fails
with typed `CAPABILITY_UNAVAILABLE`.

The generic world environment no longer has observe-all compatibility or
synthetic offers. BrowserGym no longer mutates a selected plan or retains a
hidden visual escalation decision: the same orchestrator selects the baseline
and derives the one permitted residual visual need after structural projection.
BrowserGym's same-group DOM/AX/screenshot raw capture remains one physical
read, while only selected semantic sources enter `WorldFusion`. Generic DOM
and visual adapters no longer advertise a shared acquisition group they cannot
physically prove. Post-action planning uses the executed route owner plus
sealed evaluator verification needs, never prior plan membership.

The reopened repair now carries an immutable `SelectedObservationRequest`
through each provider activation, including acquisition identity, lifecycle,
selected offer, assigned needs and acquisition group. Providers report
per-need fulfilled/unfulfilled IDs. Source aliases resolve through explicit
source-to-owner registration rather than `adapter.surface`. The generic
environment acquires a structural baseline, asks the same orchestrator for
residual needs, and activates at most one complementary source. Its typed group
port conserves acquisition identity across both stages.

The model has one provider-neutral `request_evidence` ingress carrying a
closed semantic purpose, current subject and optional visual property. Runtime
maps it into the sole `ObservationNeed` algebra, derives assurance from
task/evaluator obligations, and privately selects provider/source/group.
Equivalent Agent requests after a no-gain result are rejected before another
provider call when purpose, canonical subject and current semantic result
fingerprint remain unchanged. Post-action independent fallback conserves the
original verification needs; the competing unused fallback lifecycle was
deleted.

Existing architecture redlines make the deleted owner paths physically absent and make
`ObservationOrchestrator` the sole plan constructor. Property and integration
coverage verifies order invariance, plan immutability, two-source budget
failure, residual ambiguity versus public state distinction, explicit-offer
fail-closed behavior, selected-source-only fusion, shared capture reuse,
required-source failure, and post-action non-reuse. The superseded `1642
passed, 27 skipped` result remains historical only. The repair adds held-out
source-alias, generic residual stage-two, acquisition-ID, per-need
conservation, fallback need and semantic no-gain witnesses. The final clean
run is `1640 passed, 27 skipped`; the A.2 focused gate is `117 passed`, the
documentation-governance gate is `15 passed`, and Ruff, mypy over 336 source
files, and `git diff --check` pass. A fresh-context independent review is still
required before A.2 closure can be admitted. No live benchmark was run.
