# Interaction Capability Onboarding Design

> **Lifecycle:** CURRENT REFERENCE — RECONCILED BOUNDED DESIGN
> **Updated:** 2026-08-15
> **Scope:** interaction vocabulary, adapter support, current action exposure,
> model-tool projection, execution translation, and action-effect verification
> **Authority:** [Target AgentLoop Authority Map](task-execution-authority-map.md)
> and [architecture evolution plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)
> remain authoritative
> **Implementation truth:** [Implementation Status](implementation-status.md)

The Wave-A closure foundation now includes restored generic WoT native-value
property writes, one bounded same-model tool-intent re-emission, corrected
normalization telemetry, and a sealed action-specific verification-contract
digest chain. Observed-world graph A.1 is repaired, property-verified, and
admitted after independent fresh-context review. Adaptive observation policy
A.2 is admitted but not started at that boundary. StateFact producer cutover
remains a separate open slice; no scroll/press/focus/drag/hover binding is
admitted and no live benchmark was run.

## 1. Decision

New GUI interactions enter the target Runtime through one capability-onboarding
chain:

```text
SemanticActionDefinition             static meaning and public shape
          +
AdapterInteractionProfile            backend support declaration
          +
adapter PrimitiveTranslator table    backend implementation
          |
          v
CapabilityComposer                    validated static support; grants no current action
          v
SurfaceObservation.ActionBinding     current private route for one semantic subject
          v
WorldFusion                          canonical target and destination identity
          v
ActionSpaceBuilder                   task-legal, current ActionOption authority
          v
ContextBuilder                       one closed public action-candidate projection
          v
GroundedToolCompiler                 shared skeleton + minimal semantic choice;
                                     disposable provider schema + private resolver
          v
ProviderCallNormalizer              wire normalization + bounded equivalence proof;
                                     otherwise typed model repair, never authorization
          v
exact resolver -> AgentDecision -> admission -> risk/confirmation -> refresh/re-admit if needed
          -> bind/currentness -> verification plan -> execute once
          v
fresh WorldObservation -> comparable SemanticDelta
          v
ActionVerificationPlan + ActionEvaluator -> ActionEvaluation
          v
TaskEvaluator -> exactly one root ControlTransition
```

This is registry-like, but it is not a general plugin or tool registry:

- the semantic registry defines what an action name means;
- an adapter profile declares what a backend can implement in principle;
- a current `ActionBinding` states what can be bound in one observation;
- `ActionSpace` alone states what is legal now;
- model tools are disposable projections of that current authority.

The word "registry" names three deliberately different lifetimes. They must
not be collapsed into one mutable tool service:

| Lifetime | Owner | Contents | Cannot do |
|---|---|---|---|
| code/version lifetime | `InteractionCapabilityRegistry` | closed semantic action definitions and schema families | declare backend support or current legality |
| adapter-composition lifetime | validated `AdapterInteractionProfile` | backend support plus primitive translators | create a current target, binding, or tool |
| observation/context lifetime | compiled grounded tool catalog | flat public `ToolSpec`s plus private exact rows for the current `ActionSpace` | persist capability, reconstruct world state, or authorize dispatch |

No layer may infer an upstream authority from a downstream projection. In
particular, registering `scroll` never makes scrolling legal, an adapter's
support declaration never creates an `ActionOption`, and a model tool never
becomes an execution route.

The initial contract must support the existing actions plus the next breadth
families without changing the AgentLoop:

```text
activate, type_text, select_option, read,
scroll, press_key, focus, drag_to, set_value, hover
```

Only `activate`, text entry, selection, read, and already implemented private
routes are current implementation truth. The remaining names are target
vocabulary; their adapter slices stay unimplemented until their phase gates
pass.

## 2. Problem being solved

The current short-loop authority chain is already clear after `ActionSpace` is
built. The missing chain is how a new interaction family reaches it.

Today that onboarding logic is distributed across:

- primitive-to-semantic maps;
- role profiles with one action per role;
- per-adapter binding construction;
- grounded-tool verb-specific schema construction;
- tool-call resolution;
- execution translators;
- evaluator action-name branches.

This distribution has four concrete consequences.

1. A new parameterized action such as `scroll` must be taught independently to
   the action vocabulary, role/profile logic, tool compiler, resolver,
   translator, and evaluator.
2. The public parameter schema is carried by `ActionBinding` and `ActionOption`
   but reconstructed by verb in the grounded-tool catalog, so the model may see
   a second, non-equivalent action contract.
3. `SemanticTarget.state` and `StateFact` can independently represent the same
   state, while open relation dictionaries require key-specific identity
   rewriting.
4. A broad before/after change can be mistaken for the requested effect even
   when it does not satisfy an action-specific verification obligation.
5. Provider wire tolerance, selected-tool argument repair, and semantic
   candidate choice are not yet represented by one closed reconciliation
   contract. A model can mix a compiler-generated tool name with a selector
   owned by another same-operation tool; the current implementation may repair
   that useful near miss, but it cannot yet prove that every authority-bearing
   field is equivalent or return a structured `did_you_mean` response when it
   is not.

The goal is not to add another framework. The goal is to make one bounded
extension seam so same-shaped capabilities require local adapter work and
tests, not core-loop restructuring.

### 2.1 Build-versus-integrate boundary

This repository owns the control plane and canonical fact plane. It does not
reimplement mature surface mechanics.

| Layer | Repository-owned responsibility | Reused or replaceable implementation |
|---|---|---|
| Runtime authority kernel | ActionSpace, admission, currentness, risk/confirmation, dispatch truth, effect/task evaluation | none; these are project authority |
| canonical semantic layer | action vocabulary, capability contracts, identity acceptance, StateFact/RelationFact, provenance, SemanticDelta | generic libraries may help implementation but do not own semantics |
| thin surface adapters | semantic-to-primitive translation, source-state normalization, typed receipt conversion | BrowserGym, Playwright, browser/desktop accessibility APIs, OS/device automation, ADB/HDC |
| external capability providers | typed ports, result validation, observation binding, confidence/provenance gates | OCR, OmniParser, ShowUI, GUI-Actor, GLM or other visual/grounding providers |
| optional strategies | explicit budget/state/stop contract | scroll coverage, viewport tiling, OCR escalation, visual escalation |

The decision rule for every capability is:

1. If it decides legality, identity/currentness, risk, dispatch truth, effect, or
   completion, Runtime owns it.
2. If it reads or manipulates a surface, use an existing backend primitive and
   write only a thin adapter/translator.
3. If it performs uncertain visual or semantic inference, expose a replaceable
   typed provider port. Provider results are proposals/evidence, never binding
   or execution authority.
4. If it decides how to explore, keep it as an explicit bounded optional
   strategy. It must use ordinary canonical actions and may not mutate the
   environment behind AgentLoop.

Consequently, the project must not build a browser layout engine, mouse/keyboard
injection engine, mobile driver, OCR engine, screenshot engine, or another
agent planner/loop merely to add an interaction. New low-level machinery is
admitted only after a repository-visible backend/provider gap is demonstrated.

Native semantics are preferred in this order:

```text
backend/DOM/AX/device native state or primitive
-> thin source-specific normalization/translation
-> bounded generic deterministic inference when native semantics are absent
-> replaceable model/CV provider only for open visual/semantic uncertainty
```

Fallback provenance and confidence are retained. Derived or model-proposed
evidence cannot silently replace conflicting native evidence.

### 2.2 SOTA alignment and inference boundary

As of 2026-08-14, the following production interfaces and research result
provide compatible evidence for two narrow observations, not one universal
JSON representation. Vendor documentation was accessed on that date; provider
tool versions remain the authority for their exact action sets.

- [OpenAI Computer Use](https://developers.openai.com/api/docs/guides/tools-computer-use)
  presents a small, flat action vocabulary such as click, type, keypress,
  scroll, and drag over screenshots; the application harness performs the
  actual execution and returns a fresh screenshot.
- [Anthropic Computer Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
  follows the same fixed-tool/harness pattern and keeps mouse, keyboard,
  screenshot, and coordinate mechanics outside model reasoning.
- [BrowserGym](https://browsergym.readthedocs.io/latest/core/action_space.html)
  exposes direct primitives such as `click(bid)`, `fill(bid, text)`,
  `press(bid, key)`, and `drag_and_drop(from_bid, to_bid)` rather than asking
  the policy to reconstruct an adapter command from a capability graph.
- [GUI-Actor](https://arxiv.org/abs/2506.03143) is research evidence that
  semantic action intent and spatial localization benefit from separate
  grounding machinery; it is not evidence for this repository's exact
  semantic-facet schema.

These sources support two bounded observations: production harnesses favor a
small direct action language, and grounding can remain separate from semantic
action choice. This design combines those observations with the stronger
Runtime authority already present here:

```text
model                         Runtime / provider boundary
-----                         ---------------------------
canonical operation          current legal ActionSpace
minimal semantic choice  ->  exact candidate resolution
declared business values     private binding/currentness
                              backend or model-backed grounding
```

The project-specific inference is bounded: compile the current legal
`ActionSpace` into flat tools whose descriptions contain one shared semantic
target skeleton and whose parameters contain only the minimal meaningful
difference among actual candidates. This is not claimed as a published SOTA
schema. It is the smallest extension that preserves current Runtime legality,
avoids coordinate/E-ref reasoning when public semantics already distinguish a
target, and still permits screenshot-native or specialist grounding when they
do not.

Consequently, normalized entity/capability tables may exist only as internal
compiler data. They must not be transmitted to the Actor. The Actor must not
be asked to join an entity table to an operation table before it can act.

#### 2.2.1 Multi-source observation alignment

The comparison target for observation design is not a vendor JSON shape. It is
the set of properties that survive across mature web, desktop, and visual GUI
systems:

- [BrowserGym](https://arxiv.org/abs/2412.05467) retains minimally altered DOM
  and AX objects, stable observation-local element IDs, bounding boxes and the
  raw screenshot. Its exact pixel alignment makes structure and media
  complementary observations; the agent implementation, not the environment,
  chooses the bounded textual representation.
- [Mind2Web](https://arxiv.org/abs/2306.06070) does not send a real page's raw
  HTML wholesale. It ranks candidate elements and retains their parent/child
  neighbourhood when constructing the LLM snippet. The useful unit is thus an
  element plus enough structure to explain it, not a flat element row.
- [UFO](https://aclanthology.org/2025.naacl-long.26/) combines native UIA
  control metadata with clean and annotated screenshots, and explicitly
  re-annotates a smaller control set when the full list clutters the view.
  Native control inspection remains the reliable action substrate; visual
  information supplies complementary rendering and fallback coverage.
- [OSWorld](https://arxiv.org/abs/2404.07972) exposes screenshot, filtered
  accessibility tree, their combination, and SoM as different observation
  modes. Its reported model-dependent results show that more aligned channels
  are not monotonically better: very large trees and dense marks can add
  inference burden or visual noise.
- [OmniParser](https://arxiv.org/abs/2408.00203) demonstrates the complementary
  case: when native structure is missing, OCR, interactable-region detection
  and local icon semantics can turn a screenshot into structured, grounded
  assertions. Those outputs are useful evidence, but they are model-derived
  observations rather than native control authority.

The project inference from these primary sources is deliberately narrower than
claiming a published universal fusion schema:

```text
retain source observations with lineage inside Runtime
        + align source-local entities/regions to canonical current entities
        + coalesce identical claims while retaining every evidence source
        + preserve disagreements as typed alternatives/conflicts
        + retain each source's structural lens without inventing one fake tree
        -> render one bounded, non-repeating Actor world
```

This is a **multi-source observed-world information graph**, not a graph
database, durable knowledge graph, event store, or replacement for existing
adapters and fusion. BrowserGym/Playwright, DOM/AX, UIA/device APIs, WoT, HTTP
and replaceable OCR/vision providers continue to collect their native data.
`WorldFusion` remains the only within-observation alignment and acceptance
boundary. The change is to make its conserved information and its Actor
projection explicit, not to rebuild collection or perception machinery.

The model must not receive a concatenation of full DOM + full AX + OCR list +
SoM list + tool target records. The Runtime keeps that evidence; the Actor sees
one canonical entity once, one useful structural context, one attached image
per distinct capture, and only novel, conflicting, uncertain, or otherwise
unmatched contributions from complementary sources.

### 2.3 Why the current shape exists

The current compiler and model boundary are the result of several falsifying
tests, not arbitrary indirection. The evidence explains both the changes that
must be preserved and the contradictions that the onboarding spine must close.

| Evidence | What failed | Correction and retained lesson |
|---|---|---|
| [five-witness common-cause review](reviews/2026-08-13-five-witness-common-cause.md) | an unconditional objective phase and action-shaped objective envelope stopped 5/5 cases before GUI execution | one ordinary GUI turn uses one `AgentContext` and one action-selection model role; schema repair is not a planner |
| [grounded-tool schema alignment](evidence/2026-08-14-grounded-tool-schema-alignment-97918e1.md) | prose told the model to send `target`/`assurance` while the selected tool schema rejected those fields; the clean correction removed the three observed argument failures | provider prose, wire envelope, and emitted JSON schema must describe the same contract; error feedback must retain the owning field path and code |
| [single-AgentContext convergence](evidence/2026-08-14-single-agent-context-convergence.md) | a second context-shaped view and mandatory updater introduced another schema gate and duplicate semantic owner | `AgentContext` and its one binder remain the sole model-context path; no memory/update sidecar is added for capability onboarding |
| [grid semantic-selection evidence](evidence/2026-08-14-grid-semantic-selection-key-7101a84.md) | the dynamic menu admitted a semantic coordinate but a superseded base validator still required an E-ref; a later optimization removed facts from canonical context and broke thirteen consumers | the current compiled schema owns model-call membership, while deduplication/compaction stays in the disposable provider projection and never mutates canonical world facts |
| [semantic-facet compaction](evidence/2026-08-14-semantic-facet-action-compaction-b6e0546.md) | repeated complete candidates made the model copy common structure and opaque refs | compiler-owned shared skeletons and minimal semantic differences are retained; the focused token reduction is useful evidence, not a general performance claim |
| [Actor world convergence](actor-world-snapshot-design.md) | flattening and action/tool dedup removed the public state that explained current E-refs and withheld an already available aligned screenshot | one canonical, source-lineage-preserving `ActorWorldSnapshot` remains independent from flat callable tools; world facts are not removed merely because a tool refers to the same entity |
| current `972fba8..df391b1` local increments | models use equivalent `name/op`, `arguments/args`, sometimes mix a same-operation shape-tool name with the uniquely identifying selector, or redundantly echo a singleton grounding ref | retain bounded transport and representation normalization, but make authority equivalence explicit and require model repair rather than silent semantic substitution when equivalence is not proven |

The causal pattern is consistent: a useful projection was treated as a second
authority, or two public descriptions of one interface diverged. The solution
is not stricter one-to-one copying by the model and not broader Runtime
guessing. It is one authoritative contract per concern, one-way projections,
and a typed reconciliation boundary that can distinguish harmless
representation variance from a different GUI decision.

## 3. Non-goals

This design does not introduce:

- runtime-loaded plugins or arbitrary third-party action registration;
- a second `ActionSpace`, action ledger, event store, or replay system;
- a model-authored selector, coordinate, backend route, or parameter schema;
- task-name, benchmark-case, page-copy, or known-selector branches;
- an ontology intended to enumerate every future GUI interaction;
- automatic retry, alternate-route execution after `SENT`/`SENT_UNKNOWN`, or
  Runtime-selected recovery actions;
- mechanical causality claims for open-world visual change;
- a durable `SemanticDelta` store or state reconstructed from deltas;
- a requirement that every observed entity be executable.

The supported algebra is finite and fail-closed. Extending that algebra is an
explicit contract change; adding another adapter implementation of an existing
shape is not.

## 4. Authority and projection invariants

### 4.1 Sole owners

| Concern | Sole owner | Derived consumers | Forbidden duplicate |
|---|---|---|---|
| semantic action meaning and public shape | `InteractionCapabilityRegistry` | adapter validation, schema compiler, verifier routing | tool-name or adapter-local semantic vocabulary |
| backend support declaration | `AdapterInteractionProfile` | capability composition, binding validation | core `if surface == ...` capability branches |
| backend primitive implementation | adapter-local `PrimitiveTranslator` table | validated composed capability | semantic meaning or current legality |
| usable composed backend support | `CapabilityComposer` validation result | observation/binding construction | profile claim treated as executable without a translator |
| current private route | `ActionBinding` | fusion, ActionSpace, Binder | model tool, E-ref, `ActionOption` payload |
| current legal membership | `ActionSpace` | ContextBuilder, admission | adapter profile or tool catalog treated as permission |
| public current action candidate | `AgentActionOptionView` built by `ContextBuilder` | grounded-tool compiler, provider messages | catalog rejoining world and action tables |
| concrete row expansion, semantic factoring, and private lookup construction | `GroundedToolCompiler` | public ToolSpec, exact resolver | ContextBuilder/provider binder recomputing selectors or candidate products |
| provider wire serialization | provider binder | model request | regrouping, new semantics, or private lookup data |
| provider-call reconciliation | `ProviderCallNormalizer` | exact resolver or bounded same-model repair | world/ActionSpace join, authority-changing silent substitution, admission |
| exact tool-choice lookup | grounded catalog resolver | typed `SelectAction` proposal | normalization, fuzzy search, repair, world lookup, authorization |
| source-local observation and structure | each `SurfaceObservation` produced by its thin adapter/provider | fusion input, diagnostics, bounded source lens | re-extracting DOM/AX/UIA/OCR inside fusion or ContextBuilder |
| within-observation canonical entity alignment | `WorldFusion` acceptance materialized as `WorldObservation.entity_source_links` | canonical facts, relations, media links, Actor projection | result sidecar or binder-local correspondence reconstruction |
| predicate/source-profile acceptance | immutable `ObservationPredicateRegistry` consumed by `WorldFusion` | accepted facts/target projection/conflicts | first-source wins or surface-name branches |
| accepted current observed-world graph | `WorldObservation` | evaluator, ContextBuilder, semantic differ | a second fused graph, graph database, or Actor-owned world state |
| Actor epistemic rendering | `ActorWorldSnapshot` built from the current `WorldObservation` | provider serialization only | concatenated full per-source dumps or tool-owned entity copies |
| primary/complementary source-lens rendering | `StructuralLensSelectionPolicy` in the Actor-world projector | bounded snapshot documents | provider-specific tree choice or prose novelty heuristic |
| current world state | `StateFact` in `WorldObservation` | target-state and model projections, evaluator | independently authored `SemanticTarget.state` |
| current relations | typed `RelationFact` in `WorldObservation` | fusion, model projection, semantic diff | open relation dictionaries with identity-bearing values |
| before/after semantic comparison | pure `SemanticDiffer` result | evaluator, bounded latest-transition projection, liveness | mutable or independently persisted delta authority |
| action-effect truth | validated `ActionEvaluation` | progress/control transition | receipt, screenshot change, model narration |
| task truth | validated `TaskEvaluation` | AgentLoopState/control transition | action evaluator, planner, benchmark reward |
| accepted-decision accounting | one root `ControlTransition` | bounded context/telemetry projections | separate transition digest state |

### 4.2 One-way rule

Every projection is disposable and one-way:

```text
Registry/Profile -> binding validation
SurfaceObservation(s) -> WorldFusion -> WorldObservation
WorldObservation -> ActorWorldSnapshot -> provider world message
World + ActionSpace -> AgentActionOptionView -> tools/provider tool message
raw provider call -> bounded normalization/repair -> exact current tool call
World(before, after) -> SemanticDelta -> evaluator/transition view
ControlTransition -> AgentContext.last_transition / recorder / benchmark facts
```

The reverse arrows do not exist. Runtime never reconstructs a binding from a
tool, state from a target-state view, relations from prose, or a transition
from a digest. `ProviderCallNormalizer` is deliberately downstream of the
compiled catalog: it may reconcile two representations of the same current
choice, but it cannot make a call legal, create a binding, or infer a candidate
from the Actor world.

Source retention does not create reverse authority either. A source-local
structure node, OCR region, SoM mark, DOM ID, AX node ID, UIA runtime ID, or
provider caption cannot authorize an action. `WorldFusion` may accept its
identity/evidence into the current canonical graph; `ActionBinding` and
`ActionSpace` remain the only route and legality owners.

### 4.3 No repeated semantic rendering

Within each compiled candidate group, complete target records are never
repeated. Its semantic content is factored as follows:

- fields shared by every candidate in a tool group appear once as constants in
  its `ToolSpec` description;
- the smallest public facet set that distinguishes the actual candidates
  appears once as bounded semantic selector parameters;
- business parameters appear once in the tool input schema;
- private action IDs, canonical target IDs, BIDs, backend/CSS selectors,
  coordinates, and bindings never appear.

There is no public `actions.entities -> actions.groups` join. A provider
transport may internally normalize tools through such tables, but it must erase
them before constructing the model request. The Actor receives direct callable
tools only. It does not copy a complete target record, choose an E-ref when
semantic facets are sufficient, or map a chosen semantic value back to a
screenshot mark.

Different canonical operation tools may repeat the minimum target cue required
to make each call self-contained, such as `Search textbox`; they may not repeat
complete target records or require the Actor to copy them. Tool schemas may
repeat selector values as mechanical enum constraints across provider-owned
schema/message channels, but they must not repeat execution data.
Observation-local E-refs remain screenshot/world grounding evidence and an
explicit last-resort selector only when no supported public semantic facet can
uniquely distinguish the current candidates.

The latest accepted decision appears only in `last_transition`; it does not
also appear as the newest history entry. Current state appears only in the
current world/progress/tool sections; the transition view reports changes, not
another current snapshot. Actionable nodes and facts remain in the sole
`ActorWorldSnapshot`; tool compilation never removes them. What is forbidden is
a second contextual action-entity/group table that repeats those facts and asks
the Actor to join it to the tools. Each flat tool may retain only the minimum
self-contained target cue and candidate difference needed to make a valid
semantic choice.

## 5. Static semantic action contract

### 5.1 Types

The registry is a small immutable composition dependency. It replaces the
primitive map as the semantic source of truth.

```python
class InteractionSubjectKind(StrEnum):
    ENTITY = "entity"
    VIEWPORT = "viewport"
    FOCUSED_CONTEXT = "focused_context"


class DestinationMode(StrEnum):
    FORBIDDEN = "forbidden"
    OPTIONAL = "optional"
    REQUIRED = "required"


class ParameterContractKind(StrEnum):
    EMPTY = "empty"
    TEXT = "text"
    OPTION_VALUE = "option_value"
    SCROLL = "scroll"
    KEY = "key"
    NUMERIC_VALUE = "numeric_value"


class VerificationFamily(StrEnum):
    TARGET_STATE = "target_state"
    NAVIGATION_CONTEXT = "navigation_context"
    FOCUS_STATE = "focus_state"
    SCROLL_STATE = "scroll_state"
    RELATION_CHANGE = "relation_change"
    VALUE_STATE = "value_state"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class SemanticActionDefinition:
    semantic_action: str
    subject_kinds: tuple[InteractionSubjectKind, ...]
    parameter_contract: ParameterContractKind
    destination_mode: DestinationMode
    verification_families: tuple[VerificationFamily, ...]


class InteractionCapabilityRegistry(Protocol):
    registry_id: str

    def resolve(self, semantic_action: str) -> SemanticActionDefinition | None: ...
    def require(self, semantic_action: str) -> SemanticActionDefinition: ...
    def validate_binding(
        self,
        binding: ActionBinding,
        subject: SemanticTarget,
        destinations: tuple[SemanticTarget, ...],
    ) -> None: ...
```

`require()` fails with a typed `UNSUPPORTED_SEMANTIC_ACTION`; it never falls
back to a similar verb. Unknown semantic actions cannot enter a world binding,
ActionSpace, model tool, or executor.

The registry is code-owned and versioned with the Runtime. Tests may construct a
small registry fixture, but adapters and benchmark manifests may not register
new production semantics at runtime.

The initial registry is closed as follows:

| Semantic action | Subjects | Parameters | Destination | Permitted verification families |
|---|---|---|---|---|
| `activate` | entity | empty | forbidden | target state, navigation context, semantic |
| `type_text` | entity | text | forbidden | value state |
| `select_option` | entity | option value | forbidden | value state, relation change |
| `read` | entity | empty | forbidden | target state, semantic |
| `scroll` | viewport | scroll | forbidden | scroll state |
| `press_key` | entity or focused context | key | forbidden | value, focus, navigation, semantic |
| `focus` | entity | empty | forbidden | focus state |
| `drag_to` | entity | empty | required | relation change, target state, semantic |
| `set_value` | entity | numeric value | forbidden | value state |
| `hover` | entity | empty | forbidden | target state, semantic |

“Permitted” is a verifier-routing bound, not proof that an observed change
satisfies an obligation. An exact obligation still has to be derived before
dispatch and closed by current evidence.

The initial operational meanings are also bounded:

- `read` invokes one read-only surface operation and incorporates its scoped
  result into the post-operation observation. It does not claim a world
  mutation; missing scoped evidence remains unknown.
- `focus` requests exact focus for one current entity and is mechanically
  confirmed only by a current `focused=true` fact for that entity.
- `hover` moves the private pointer over one current entity without activation.
  It is confirmed only by a declared target-state or semantic obligation; a
  successful pointer command alone is not effect truth.
- the initial `press_key` domain is exactly `Enter`, `Escape`, `Tab`,
  `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`, `Backspace`, `Delete`, and
  `Space`. Printable text uses `type_text`; modifiers/chords are deferred.
- `scroll.extent=small` means one adapter-defined bounded increment smaller
  than a viewport, while `page` means one adapter-defined increment no larger
  than a viewport. Both must be monotonic in the requested direction; public
  pixels are neither accepted nor promised.

### 5.2 Public parameter profiles

`ActionBinding.parameter_schema` originates the concrete current offer schema.
After task/currentness grouping, `ActionOption.parameter_schema` is the
authoritative current admission schema; model views and tools conserve it
exactly as disposable projections. The registry stores only the schema family
that validates these schemas. This permits current domains such as a select's
option enum or a slider's min/max without duplicating those values statically.

Initial public shapes are:

| Contract | Required public fields | Runtime-private fields |
|---|---|---|
| `EMPTY` | none | all route details |
| `TEXT` | `text: string` | keyboard backend, selector, clipboard mechanics |
| `OPTION_VALUE` | `value: string`, optionally current enum | native option value/handle |
| `SCROLL` | `direction: up\|down\|left\|right`, `extent: small\|page` | pixel delta, viewport geometry |
| `KEY` | one bounded named `key` enum for the admitted context | scan code, backend command |
| `NUMERIC_VALUE` | `value: number` with current min/max when known | drag point, step implementation |

The existing finite public JSON-schema validator remains the syntax gate.
Each parameter-contract validator adds semantic requirements. Reserved
selector/transport names (`choice`, `grounding_ref`, `source_grounding_ref`,
`destination_grounding_ref`, `grounding_pair`, `target`, `source`, and
`destination`) and private execution names remain forbidden inside business
parameters. A selector name derived from one semantic facet path is compiler-
owned and collision-checked; adapters cannot introduce it as a business field.

Action vocabulary is canonical:

```text
fill/select                old BrowserGym-local words; migrate out
type_text/select_option    canonical semantic actions
fill/select_option         may remain private backend primitives
```

Provider tool names may use short presentation labels, but their private
binding always names the canonical semantic action and the model response
resolves to the current canonical `ActionOption`.

The migration is replacement, not registration beside the old maps:

| Current duplicated expression | Final owner | Migration/deletion rule |
|---|---|---|
| `world/action_vocabulary.py` primitive-to-semantic map and verb-shaped schemas | registry definition + adapter profile + current binding schema | move semantic meaning/schema-family validation to the registry; move primitive mapping to the adapter profile; delete the shared map after every target adapter composes through the new owners |
| `model_boundary/action_candidate_projection.py` `click/fill/select` compatibility canonicalizer | registry-validated canonical `ActionOption.semantic_action` | a temporary alias may exist only at an explicit migration ingress inside the same slice; delete it when target producers switch, and never let ContextBuilder rename an already canonical action |
| BrowserGym `BrowserGymRoleSpec.semantic_action/primitive` singleton fields | `RoleCapabilityOffer[]` validated against profile/composer | replace one-role/one-action fields; do not retain a parallel lookup when multi-offer projection is active |
| BrowserGym binding schema `if semantic == ...` branches | current offer/binding schema builder validated by the registry parameter family | current enum/min/max values remain observation-owned; generic tool projection copies them and never reconstructs by verb |
| adapter execution `if primitive == ...` | adapter-local `PrimitiveTranslator` table | a finite local dispatcher may remain as implementation syntax, but the table/composer is the sole proof that a declared primitive is executable |
| model tool catalog entries | current compiled catalog | never copied into the static registry; they expire with context/ActionSpace identity |

The static registry therefore centralizes meaning, not every changing value.
Current option enums, slider bounds, targets, destinations, risk, currentness,
and private routes remain observation/binding data. Centralizing those in the
registry would create stale global state and is explicitly forbidden.

### 5.2.1 Atomic owner cutover and deletion rule

An owner migration is incomplete until the displaced owner and every semantic
compatibility path around it are deleted in the same coherent migration slice.
The repository may use multiple reviewable commits on a working branch, but it
must not attest, merge, or admit the new owner while any of these remain live:

- old and new registries both answering the same semantic question;
- dual writes to canonical and compatibility state;
- read-new/fallback-old behavior when the owners disagree;
- a second tool projection, resolver, schema builder, or evaluator branch for
  the same supported action family;
- adapter-local semantic aliases surviving the target producer cutover or
  leaking beyond the temporary migration ingress;
- tests or benchmark composition that can choose the superseded path.

A temporary shadow is permitted only inside that same migration slice when it
is read-only, authority-free, excluded from Actor requests and dispatch, emits
comparison telemetry, and has an explicit deletion change in the slice. A
shadow mismatch blocks cutover; it never selects the favorable result. Once
equivalence is demonstrated, the shadow and old owner are deleted before the
slice is marked implemented.

Permanent provider tolerance is not a compatibility owner. Wire aliases such
as `name/op` and `arguments/args`, and catalog reconciliation proven by the
current `authority_equivalence_digest`, terminate at
`ProviderCallNormalizer` and produce one canonical exact call. Likewise,
backend primitive names such as BrowserGym `fill` may remain private translator
values; they cannot re-enter the semantic vocabulary, model schema, admission,
or evaluation path.

Every migration change must include a deletion inventory:

```text
new sole owner
+ producers switched
+ consumers switched
+ old owner deleted
+ compatibility branches deleted
+ tests asserting old path is unreachable
= migration complete
```

If deletion cannot occur in the same slice, the status remains
`IMPLEMENTATION_PARTIAL / DUAL_PATH_NOT_ADMITTED`, dependent capability work is
not added on top of it, and the exact blocker is recorded. Compatibility has no
open-ended grace period. A separately frozen legacy product may retain its own
isolated contract until product cutover, but the target chain cannot import,
fallback to, or share that compatibility owner.

### 5.3 Current subject model

All semantic actions retain a non-empty `target_id`. Targetless actions are not
introduced.

This is an internal authority invariant, not a requirement that every model
tool contain a `target` parameter. When a compiled tool group has exactly one
current target, that target is a private tool constant and the Actor supplies
no selector. When several targets differ by verified public semantics, the
Actor supplies only those semantic differences. An observation-local E-ref is
accepted only by the explicit grounding fallback described in Section 8.

- element actions target the canonical element entity;
- viewport scroll targets a current synthetic semantic entity with role
  `viewport`;
- focus-aware keypress targets a current synthetic entity with role
  `focused_context`, related to the exact focused entity when known;
- drag targets the source entity and selects a separate current destination;
- global keyboard or viewport actions are offered only when the adapter can
  identify and revalidate their current semantic context.

Synthetic semantic subjects are ordinary observation-bound targets. They do
not expose a window handle, page object, coordinate, or backend session ID.

`press_key` always has a semantic subject. An entity-subject binding means the
backend can target that exact current entity; a focused-context binding means
the current observation identifies the exact focused entity. The first
BrowserGym breadth slice may implement only the offers supported by its pinned
backend, but it cannot fall back to an implicit global keypress.

## 6. Adapter interaction profile

### 6.1 Contract

Observation capability and interaction capability remain separate.

```python
@dataclass(frozen=True)
class AdapterCapabilitySupport:
    semantic_action: str
    primitive_actions: tuple[str, ...]
    subject_kinds: tuple[InteractionSubjectKind, ...]


@dataclass(frozen=True)
class AdapterInteractionProfile:
    profile_id: str
    surface: str
    executor_id: str
    capabilities: tuple[AdapterCapabilitySupport, ...]


class SurfaceAdapter(Protocol):
    surface: str

    @property
    def interaction_profile(self) -> AdapterInteractionProfile: ...

    # existing reset/observe/is_current/execute methods remain
```

The profile states only that the backend and its translator can implement a
semantic family. It does not contain current target IDs, schemas, destination
domains, risk, task effects, or binding payloads.

Currentness and dispatch reporting are not optional booleans on individual
capabilities. Every executable adapter profile must satisfy the shared
`SurfaceAdapter` contract: exact binding/currentness validation and trinary
`NOT_SENT/SENT/SENT_UNKNOWN` reporting. A backend that cannot satisfy those
guarantees does not advertise an executable capability.

At Runtime composition, `CapabilityComposer` validates:

1. every supported semantic action exists in the registry;
2. every named primitive has exactly one adapter translator;
3. subject kinds are a subset of the semantic definition;
4. the environment has a valid post-action observation route;
5. duplicate profile entries are identical or rejected;
6. unsupported/unknown combinations fail closed before a run.

Its immutable result is the only usable static backend-support view:

```python
@dataclass(frozen=True)
class ComposedAdapterCapability:
    semantic_definition: SemanticActionDefinition
    support: AdapterCapabilitySupport
    translators: Mapping[str, PrimitiveTranslator]


@dataclass(frozen=True)
class ComposedInteractionCapabilities:
    registry_id: str
    adapter_profile_id: str
    capabilities: tuple[ComposedAdapterCapability, ...]
```

Binding construction consumes this composed result, never a bare profile claim
or translator map. The profile owns declaration, the translator owns backend
implementation, and `CapabilityComposer` owns proof that they match. None owns
current legality.

`WorldEnvironment.interaction_capabilities` may expose the validated aggregate
for negotiation and diagnostics. It is never consulted as current action
membership; only observed bindings feed `ActionSpaceBuilder`.

### 6.2 Role to capability offers

A surface role profile produces zero to many current binding offers:

```python
@dataclass(frozen=True)
class RoleCapabilityOffer:
    semantic_action: str
    primitive_action: str
    availability_requirements: tuple[str, ...]
    currentness_fields: tuple[str, ...]


@dataclass(frozen=True)
class BrowserGymRoleSpec:
    role: str
    observable: bool
    offers: tuple[RoleCapabilityOffer, ...]
```

Examples:

```text
textbox  -> type_text/fill + focus/click + press_key/press
button   -> activate/click + focus/click + hover/hover
slider   -> set_value/... + press_key/press
item     -> activate/click + drag_to/drag_and_drop + hover/hover
```

An offer is still conditional. Disabled, hidden, stale, read-only, unfocused,
or otherwise ineligible entities produce no executable binding for that
action. Observable entities remain in the world even when they have no offer.

### 6.3 Adapter translator boundary

Primitive translation is adapter-local and selected from the validated
profile, for example:

```python
PrimitiveTranslator = Callable[[BoundActionRequest, PrivateBinding], BackendCommand]

browsergym_translators = {
    "click": translate_click,
    "fill": translate_fill,
    "select_option": translate_select_option,
    "scroll": translate_scroll,
    "press": translate_press,
    "drag_and_drop": translate_drag,
}
```

Adding an existing semantic shape to another surface requires only that
surface's offer/binding builder, primitive translator, and conformance tests.
It must not modify the AgentLoop, grounded-tool compiler, response parser,
admission, Binder, or generic evaluator routing.

If a profile claims a primitive but translation is absent, composition fails.
If an invariant escapes composition, execution returns
`NOT_SENT + UNSUPPORTED_ACTION`; it cannot silently drop parameters, switch
primitives, or execute a fallback.

## 7. Current binding and ActionSpace chain

### 7.1 Binding construction

An adapter may emit an `ActionBinding` only after registry validation. Its
existing fields remain the current private authority:

```text
world/source observation identity
target/source-target identity
semantic action + primitive action
concrete public parameter schema
effect/risk/barrier classification
eligible current destination IDs
private payload and executor route
currentness fingerprint/expiry
```

No action definition or adapter profile contains these observation-local
values.

Destination mode is conserved explicitly. During compatibility with the
current `destination_required + eligible_destination_ids` fields, exactly two
encodings are valid:

```text
required=true  + non-empty eligible destinations -> REQUIRED
required=false + empty eligible destinations     -> FORBIDDEN
```

`required=true` with an empty domain is `DESTINATION_UNAVAILABLE`;
`required=false` with a non-empty domain is an unsupported OPTIONAL contract,
not FORBIDDEN. It is rejected before model projection until OPTIONAL receives
an explicit no-destination row, verification meaning, and risk semantics. No
projection may derive `FORBIDDEN` from the boolean alone and silently discard
eligible destinations.

Each binding also carries one observation-local `VerificationContract`. It does
not assert that an effect happened; it contains sealed templates stating which
concrete postcondition shapes this current offer can support:

```python
class StatePredicate(StrEnum):
    VALUE = "value"
    FOCUSED = "focused"
    CHECKED = "checked"
    SELECTED = "selected"
    EXPANDED = "expanded"
    SCROLL_X = "scroll_x"
    SCROLL_Y = "scroll_y"
    NAVIGATION_CONTEXT = "navigation_context"


@dataclass(frozen=True)
class ParameterExpected:
    parameter_name: str


@dataclass(frozen=True)
class ConstantExpected:
    value: object  # None is a valid explicit expected value


@dataclass(frozen=True)
class ToggleBeforeExpected:
    predicate: StatePredicate


ExpectedValueTemplate = ParameterExpected | ConstantExpected | ToggleBeforeExpected


@dataclass(frozen=True)
class FactTransitionTemplate:
    predicate: StatePredicate
    expected: ExpectedValueTemplate
    required_assurance: ObservationAssurance


@dataclass(frozen=True)
class RelationTransitionTemplate:
    change: Literal["added", "removed"]
    relation_kind: RelationKind
    object_from: Literal["destination"]
    required_assurance: ObservationAssurance


@dataclass(frozen=True)
class FocusTransitionTemplate:
    required_assurance: ObservationAssurance


@dataclass(frozen=True)
class ScrollTransitionTemplate:
    direction_parameter: Literal["direction"]
    required_assurance: ObservationAssurance


@dataclass(frozen=True)
class NavigationTransitionTemplate:
    required_assurance: ObservationAssurance


class SemanticObligationKind(StrEnum):
    TARGET_RESPONSE = "target_response"
    HOVER_STATE = "hover_state"
    READ_RESULT = "read_result"


@dataclass(frozen=True)
class SemanticFallbackTemplate:
    kind: SemanticObligationKind


VerificationContractTemplate = (
    FactTransitionTemplate
    | RelationTransitionTemplate
    | FocusTransitionTemplate
    | ScrollTransitionTemplate
    | NavigationTransitionTemplate
    | SemanticFallbackTemplate
)


class VerificationSatisfaction(StrEnum):
    ANY_OF = "any_of"


@dataclass(frozen=True)
class VerificationContract:
    templates: tuple[VerificationContractTemplate, ...]
    satisfaction: VerificationSatisfaction = VerificationSatisfaction.ANY_OF
    contract_digest: str = field(init=False)
```

Examples are `value := parameters.text`, `focused := true`,
`member_of := destination`, and `navigation_context changed`. The registry
maps each sealed template class to one permitted verification family and
validates the whole template: referenced parameter existence and scalar type,
destination mode, state/relation vocabulary, assurance enum, and expected-value
type. `VerificationContract` requires one to eight unique templates and the
initial algebra permits only explicit `ANY_OF` satisfaction. Its digest is
SHA-256 over canonical typed JSON containing the union discriminator, every
field in stable template order, and the satisfaction mode. No adapter-authored
predicate, relation name, parameter path, rubric string, or assurance string
survives validation.

Bindings may be grouped into one `ActionOption` only when their public schema,
destination contract, effect classification, and verification contract are
equivalent. The option conserves the contract/digest for pre-dispatch plan
derivation; `AdmittedActionSelection` conserves the same immutable contract and
digest, and `BoundActionRequest` checks equality with the selected binding.
This is lifecycle conservation, not a second writer. Model tools do not expose
the contract as an execution argument.

World fusion rewrites source-local target and destination IDs into canonical
world IDs. It preserves binding provenance and does not merge non-equivalent
parameter schemas, effect classifications, or destination domains.

### 7.2 ActionSpace authority

`ActionSpaceBuilder` remains the only owner of legal current actions. Before
grouping bindings, it validates each binding against the registry, adapter
profile, current target class, and destination mode. It then applies existing
currentness, conflict, task-effect, risk, and schema-equivalence rules.

The build result has one authority and optional typed diagnostics:

```python
@dataclass(frozen=True)
class ActionSpaceBuildResult:
    action_space: ActionSpace
    issues: tuple[ActionOfferIssue, ...] = ()
```

An `ActionOfferIssue` identifies its owning stage, source, semantic action,
optional canonical subject/destination, and typed code. Observation-local
issues such as disabled or destination-unavailable originate beside the
surface binding offers and are identity-rewritten by fusion. Builder-owned
issues describe only bindings that the builder itself excluded. The builder
must not reconstruct missing role offers from target labels or roles.

`issues` can therefore explain why recognized offers were excluded, for example
`CAPABILITY_UNSUPPORTED`, `CURRENT_SUBJECT_UNAVAILABLE`,
`SCHEMA_CONTRACT_MISMATCH`, or `DESTINATION_UNAVAILABLE`. It cannot add an
option, be admitted, or be projected as a callable tool. Normal policy context
does not receive an exhaustive missing-capability list; bounded typed control
feedback may report a relevant issue after Runtime attribution.

The following remain distinct:

```text
registry contains scroll
!= adapter supports scroll
!= current observation has a scroll binding
!= task allows the binding's effects
!= ActionSpace offers scroll now
!= model selected scroll
!= scroll was dispatched
!= scrolling had the intended effect
```

## 8. Flat semantic tool compilation

### 8.0 Normative Actor-visible envelope

For `ACTION_SELECTION`, the Actor receives exactly these model-visible
channels, subject to existing budgets:

```text
task + progress
bounded last_transition + older verified history
one canonical, source-lineage-preserving ActorWorldSnapshot with current public facts
current screenshot(s), optionally with call-local grounding marks
flat public ToolSpec objects: name + description + input schema
bounded Runtime control feedback
```

Shared target semantics, selector meaning, business parameters, and bounded
risk/effect/consequence cues live inside each public `ToolSpec` description and
input schema. There is no second action presentation metadata channel. Complete
candidate records, `actions.entities`, `actions.groups`, action IDs, canonical
target IDs, BIDs, backend/CSS selectors, coordinates, bindings, destination
tables, and resolver entries are never transmitted.

Screenshot marks may remain visible because they bind visual evidence to the
current observation. Visibility does not make a mark callable: the Actor may
return an E-ref only when that exact value occurs in an emitted
`grounding_ref` schema. Actionable facts remain in the disposable Actor world
rendering even when a tool contains the minimum overlapping cue needed to be
self-contained. The compiler removes repeated candidate structure from the
tool catalog; it does not prune observed world truth. There is no objective
proposal model phase in target product or benchmark composition.

### 8.1 Closed candidates stay internal

`ContextBuilder` closes every current `ActionOption` exactly once. The
resulting `AgentActionOptionView` carries everything required to compile a
tool without another world join:

```text
canonical operation
private current action lookup key
complete bounded public target semantics
observation-local target grounding ref
exact public business-parameter schema + digest
destination mode + complete eligible destination semantics/grounding refs
public risk/effect/consequence summary
verification-contract digest
```

The existing label-only `AgentDestinationView` is insufficient for this
contract. Migration extends or replaces it with one closed destination
candidate carrying the private destination lookup ID, complete bounded public
destination semantics, and its observation-local grounding ref. The compiler
must not rejoin a destination ID through `AgentContext.world` to obtain those
fields.

This is internal compiler input, not the final prompt format. The catalog may
not look up `target_id` through a second entity table, reclassify the action
vocabulary, or infer target semantics from a screenshot mark. Full candidates
remain available for exact private resolution but are never copied into a
provider response or requested back from the Actor.

The grounding ref and semantic selector have different jobs:

```text
grounding ref       binds pixels/DOM/AX evidence to this observation
semantic selector   expresses the meaningful difference the Actor must choose
private action key  restores the exact current Runtime candidate
```

They must not be overloaded into one public identity. A semantic selector is
preferred whenever verified public facets uniquely distinguish the candidates.
An E-ref is a call-local grounding fallback, not the default action handle.

This assigns one projection responsibility to each boundary:

```text
ContextBuilder          closes complete public semantics for each legal candidate
GroundedToolCompiler    factors a candidate set into constants + minimal choices
provider binder         serializes public ToolSpec objects without regrouping
resolver                applies the compiler's private exact lookup table
```

The current `selection_key` / `selection_fields` compatibility path may be used
to migrate existing behavior, but it cannot remain an independently computed
model contract. Once the compiler owns semantic factoring, `ContextBuilder`
must not precompute a competing final selector and the provider binder must not
reconstruct groups from candidate records.

### 8.2 Mechanical grouping and semantic factoring

Factoring operates on exact concrete selection rows, not directly on a
destination-bearing option aggregate:

```python
@dataclass(frozen=True)
class ConcreteActionCandidateRow:
    option: AgentActionOptionView
    destination: AgentDestinationCandidateView | None
```

Row expansion is closed:

- `FORBIDDEN`: exactly one `(option, None)` row;
- `REQUIRED`: one `(option, destination)` row for every admitted current
  destination; an empty domain produces no tool and a typed
  `DESTINATION_UNAVAILABLE` issue;
- `OPTIONAL`: unsupported in the initial algebra and fails catalog construction
  with `UNSUPPORTED_DESTINATION_MODE` until an explicit no-destination row and
  its verification/risk meaning are designed.

The compiler removes source and destination constants before generating
selectors. One source/one destination therefore emits neither selector; one
source/many destinations emits only a destination difference; many sources/one
destination emits only a source difference. This row set is also the sole input
to Cartesian-product checks and private resolution-table construction.

The compiler first partitions candidates by exact non-negotiable contract
shape:

```text
canonical operation
business-parameter-schema digest
subject kind and destination mode
effect/risk/consequence contract
verification-contract digest
```

Within that technical partition it forms stable target-skeleton groups by the
bounded public fields `(target.role, target.label)`, treating an absent label
as an explicit value. This is mechanical domain logic: no task noun, page copy,
site name, benchmark ID, selector, or hand-authored role branch participates.
Additional fields common to every member, such as `within.role`, are then
hoisted into the group's constant target skeleton.

For each group the compiler:

1. computes the recursive intersection of every complete public target record;
2. removes those common fields from candidate selection;
3. enumerates varying paths from the bounded public facet algebra;
4. finds the smallest deterministic facet-path set that uniquely identifies
   every actual candidate;
5. emits only those values as semantic selector parameters;
6. retains a private table from the selector tuple to the exact action and
   destination identities.

The public facet algebra remains bounded to role, label, short scalar/list
state, one verified public scope, and typed public relations admitted by the
world projection. The compiler cannot invent a domain parameter such as
`product`. For the generic path `target.within.label`, it may mechanically emit
the collision-checked parameter `within_label`, with the original semantic path
retained in that input field's description and the private resolver.

A facet is eligible for selection only when it is present in the closed public
candidate, bound to the current observation, non-conflicted, identity-rewritten
where applicable, and admitted by the bounded scalar/list/relation projection.
Unknown, conflicted, truncated, private, model-proposed-but-unaccepted, or
unbounded values may be displayed as uncertainty when otherwise useful, but
cannot distinguish an executable candidate.

The canonical public target record is immutable typed JSON over `role`,
optional `label`, bounded `state`, optional `within`, and bounded typed
relations. `within` is a disposable projection of one accepted public scope
relation; it is not a second relation owner. Mapping keys use canonical path
order. Absent and explicit null are different. Ordered lists preserve order;
only vocabulary-declared set-valued collections are canonical-sorted. Typed
relations are ordered by their canonical relation tuple. Recursive intersection
keeps a field only when its canonical typed JSON value is equal in every row.

“Smallest” is reproducible: compare candidate facet sets first by path count,
then by total canonical encoded size, then by the canonical path-priority tuple
`state.semantic_grid_coordinate`, `label`, `within.label`, `role`, `within.role`,
sorted state paths, and sorted relation paths. The first set whose value tuples
are injective over the concrete rows wins. Minimality is scoped to one stable
target-skeleton group, not claimed across technically or semantically separate
tool groups.

For paths `p1..pn`, Cartesian completeness means that the set of observed
canonical value tuples is exactly `domain(p1) × ... × domain(pn)`, where each
domain is the distinct current value set for that path. Any missing tuple makes
the set non-Cartesian.

Selector construction follows these rules:

- one candidate: emit no target selector;
- one distinguishing path: emit one enum over that path's actual values;
- several paths whose observed candidate set is the complete Cartesian
  product: emit the independent path parameters;
- several paths with a sparse/non-Cartesian candidate set: emit one atomic
  `choice` enum containing only deterministic, meaningful labels for actual
  tuples;
- no supported public facet set distinguishes the candidates: emit the
  target-only, endpoint-qualified, or atomic-pair grounding selector defined
  below as the last resort.

The atomic label is canonical compact JSON over qualified semantic paths and
values, for example
`{"within.label":"MacBook Air","state.size":"large"}`. Canonical JSON
escaping prevents delimiter collisions. It never uses action ID, target ID,
BID, backend selector, coordinate, list position, or task-specific aliases. If
two actual tuples still render identically, the compiler does not append an
E-ref to pretend the choice is semantic; it switches the whole selector to the
explicit grounding fallback or fails catalog construction typed.

`GROUNDING_FALLBACK` is valid only when every concrete row has one non-empty,
current E-ref for every non-constant source/destination endpoint from the same
grounding index, and every emitted ref is rendered in at least one Actor-visible
current-observation channel (marked screenshot or bounded world grounding
text). Constants are omitted. For a complete Cartesian row set the compiler
may expose independent `source_grounding_ref` and
`destination_grounding_ref` enums. For a sparse row set it exposes one atomic
`grounding_pair` enum whose values are canonical JSON such as
`{"source":"E12","destination":"E20"}`. A target-only fallback uses
`grounding_ref`.

The mapping from the complete emitted grounding tuple to a concrete row must
be complete and injective. Missing, duplicate, stale, cross-context, or
unrenderable endpoint refs fail catalog construction with
`GROUNDING_FALLBACK_UNAVAILABLE` and produce zero dispatch. A visible mark that
is absent from the relevant emitted grounding enum/tuple is evidence only and
is rejected as a tool argument.

Destination-bearing actions apply the same algorithm to the actual admitted
source/destination pairs. Independent `source` and `destination` selectors are
permitted only when the admitted pair set is their complete Cartesian product.
Otherwise one atomic semantic `choice` represents an actual pair. The compiler
therefore cannot create an invalid source × destination combination.

### 8.3 Direct model-facing tools

The provider sees flat callable tools, not the normalized candidate graph.
Shared semantic structure appears once in the `ToolSpec` description; only
candidate differences and business values are arguments.

For two equal controls under different products, the input candidates may be:

```text
activate button "加入购物车" within product "MacBook Air"  -> A17 / E31
activate button "加入购物车" within product "MacBook Pro"  -> A18 / E47
```

The provider tool is:

```json
{
  "name": "activate",
  "description": "Activate the button '加入购物车' within a product.",
  "input_schema": {
    "type": "object",
    "properties": {
      "within_label": {
        "type": "string",
        "description": "target.within.label",
        "enum": ["MacBook Air", "MacBook Pro"]
      }
    },
    "required": ["within_label"],
    "additionalProperties": false
  }
}
```

The Actor returns only:

```json
{"within_label": "MacBook Pro"}
```

Runtime privately resolves that value to `A18`, its canonical target, current
grounding evidence, and exact binding. The Actor never copies the button record
or emits `E47`.

The same generic rule handles a verified grid:

```json
{
  "name": "activate",
  "description": "Activate a cell in the current semantic grid.",
  "input_schema": {
    "type": "object",
    "properties": {
      "semantic_grid_coordinate": {
        "type": "string",
        "enum": ["(-1,1)", "(0,1)", "(1,1)", "(1,-2)"]
      }
    },
    "required": ["semantic_grid_coordinate"],
    "additionalProperties": false
  }
}
```

The selected coordinate maps privately to the exact current E-ref/action. The
model is not required to derive `(1,-2) -> E38` from a separate candidate list.

When only one Search textbox supports text entry, its identity is a tool
constant and the tool contains only the business value:

```json
{
  "name": "type_text",
  "description": "Replace the value of the textbox 'Search'.",
  "input_schema": {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": false
  }
}
```

If the same target supports `type_text`, `focus`, and `press_key`, the compiler
emits direct tools for those canonical operations. It does not publish a
capability graph that the Actor must traverse. A semantically redundant action
is not emitted merely because the backend has a primitive: for example,
`press_key` on an entity may already include exact focus-before-key semantics,
while a separate `focus` offer exists only when changing focus itself is a
legal useful effect.

Canonical operation names are retained whenever all current candidates for
that operation fit one bounded schema without admitting a false candidate
combination. When one operation requires several incompatible public schemas
or independently described target-skeleton groups, provider-call-local names
use a deterministic digest suffix while each description carries the group's
shared semantic skeleton. Semantic page text is not inserted into tool names
because provider naming alphabets and length limits differ.

Digest material is canonical typed JSON over the canonical operation, common
target skeleton, selector shape, exact business schema, destination mode/pair
shape, effect/risk/consequence contract, and verification-contract digest. The
compiler begins with eight SHA-256 hexadecimal characters and lengthens every
colliding prefix deterministically until unique; different full digests that
still produce one name fail catalog construction. The suffix is transport
identity, not Actor-selected target identity.

Candidate/action pagination also bounds provider tool count. The compiler does
not merge semantically or technically incompatible groups merely to meet a
provider limit; it exposes the existing typed next-page control instead. A
provider transport may safely pack logical groups into one canonical-operation
tool only when its schema preserves exactly the same actual choices and private
resolution relation.

### 8.4 Generic schema compilation and resolution

After semantic factoring, tool compilation is shape-generic:

1. add the derived semantic selector fields, if any;
2. add an atomic pair/tuple `choice` when independent fields would admit an
   invalid Cartesian product;
3. add target-only, endpoint-qualified, or atomic-pair grounding selectors only
   for the explicit semantic-indistinguishability fallback;
4. copy business parameter properties and the required set exactly, without
   renaming or verb-specific branches;
5. reject selector/business-name collisions and schemas outside the finite
   public subset;
6. retain one private resolver entry for every actual admitted candidate or
   source/destination pair.

The compiler output keeps public presentation and private resolution adjacent
without conflating them:

```python
class SelectorMode(StrEnum):
    CONSTANT_TARGET = "constant_target"
    SEMANTIC_FIELDS = "semantic_fields"
    ATOMIC_SEMANTIC_CHOICE = "atomic_semantic_choice"
    GROUNDING_FALLBACK = "grounding_fallback"


@dataclass(frozen=True)
class CompiledSelectorField:
    public_name: str
    semantic_paths: tuple[str, ...]
    input_schema: Mapping[str, object]


@dataclass(frozen=True)
class PrivateResolutionEntry:
    selector_values: Mapping[str, object]
    action_id: str
    destination_id: str | None
    reconciliation_values: Mapping[str, object]


@dataclass(frozen=True)
class CompiledGroundedTool:
    canonical_operation: str
    public_spec: ToolSpec
    selector_mode: SelectorMode
    selector_fields: tuple[CompiledSelectorField, ...]
    private_resolutions: tuple[PrivateResolutionEntry, ...]
    authority_equivalence_digest: str
```

`public_spec` is the only model-facing member. Selector metadata is not emitted
as a second structure, although its bounded path description may be compiled
into `public_spec`. Action IDs, destination IDs, grounding bindings, and
resolution entries remain Runtime-private. `CompiledGroundedTool` is disposable
and bound to the same context / ActionSpace identity as its source candidates;
it is not a registry entry, ActionSpace copy, or durable tool installation.

`reconciliation_values` contains only complete call-local public identities
that the compiler already possessed, such as a rendered grounding ref omitted
from a singleton tool or the explicit selector tuple for one current row. It
does not contain a new selector, world data, or authorization. The exact
resolver continues to use `selector_values`; reconciliation metadata is read
only by the bounded pre-resolver normalizer.

After provider-call reconciliation has returned one exact call, the resolver
validates it against that exact emitted schema and performs only these
transformations:

```text
tool name + semantic/atomic/grounding selector tuple
                                    -> exact current ActionOption.action_id
optional destination/pair selector -> exact current semantic destination_id
business fields                    -> parameters unchanged
```

It returns the existing typed `SelectAction`. It never defaults a required
destination to `""`, renames `text` to `value`, normalizes or repairs the call,
performs an E-ref/world join, or searches for a similar action.

Admission then repeats authoritative membership, schema, and destination
checks against the still-current internal `ActionSpace`. Tool validation and
private resolution are early format/identity gates, not authorization.

Provider transports may serialize the same compiled catalog differently, but
they cannot change canonical operation meaning, selector candidates, business
parameter contracts, or private resolution. Raw normalized candidate tables
remain compiler diagnostics only and are excluded from every Actor request.

### 8.5 Provider-call normalization and model repair

Models should not have to reproduce inconsequential transport distinctions
perfectly. Conversely, Runtime must not silently turn a contradictory call
into a different risk, effect, destination, verification obligation, or
business operation. One pre-resolver `ProviderCallNormalizer` owns that
boundary.

It consumes only the raw call and the same immutable compiled catalog. It does
not read `WorldObservation`, `ActorWorldSnapshot`, `ActionSpace`, a binding, or
an executor. Its closed outcome algebra is:

```python
class ToolCallReconciliationStatus(StrEnum):
    EXACT = "exact"
    NORMALIZED_EQUIVALENT = "normalized_equivalent"
    REPAIR_REQUIRED = "repair_required"
    REJECTED = "rejected"


class ToolCallIssueCode(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT = "invalid_argument"
    TOOL_ARGUMENT_OWNER_MISMATCH = "tool_argument_owner_mismatch"
    AMBIGUOUS_TOOL_INTENT = "ambiguous_tool_intent"
    NON_EQUIVALENT_TOOL_INTENT = "non_equivalent_tool_intent"
    STALE_CATALOG = "stale_catalog"


@dataclass(frozen=True)
class ToolCallRepairHint:
    tool_name: str
    public_arguments: Mapping[str, object]
    reason_code: ToolCallIssueCode


@dataclass(frozen=True)
class ToolCallReconciliationResult:
    status: ToolCallReconciliationStatus
    exact_call: ToolCall | None
    issue_code: ToolCallIssueCode | None
    field_paths: tuple[str, ...]
    hints: tuple[ToolCallRepairHint, ...]
```

The normalizer applies four ordered rules.

1. **Wire normalization** is silent: exact aliases such as `op -> name`,
   `args -> arguments`, or an admitted flat envelope may be rewritten while
   preserving every argument value.
2. **Representation-equivalent catalog normalization** is silent only when an
   explicit public selector or redundant current grounding value identifies
   exactly one real compiled row and the source and destination tools have the
   same `authority_equivalence_digest`. This covers a model mixing two
   compiler-generated same-operation shape names, or echoing the current E-ref
   of a singleton whose tool made that target a constant.
3. **Semantic repair** never dispatches. When one non-equivalent alternative
   is strongly indicated, the same bounded model-repair path receives
   `TOOL_ARGUMENT_OWNER_MISMATCH` or `NON_EQUIVALENT_TOOL_INTENT`, the exact
   public field paths, the selected tool's schema, and at most a small set of
   `did_you_mean` calls. The model must emit a new call.
4. **Unknown or ambiguous intent** fails closed. Unknown names receive
   `UNKNOWN_TOOL` plus the bounded current tool names; ambiguous selectors
   receive `AMBIGUOUS_TOOL_INTENT` plus only actual public alternatives. No
   fuzzy candidate is executed.

The authority-equivalence digest is compiler-owned canonical typed JSON over:

```text
context/catalog identity
canonical semantic action
business-parameter schema digest
subject kind + destination mode
effect category + semantic effects
risk + consequence + reversibility + observation barrier
verification-contract digest
```

Tool name, description wording, digest suffix length, selector presentation,
and a redundant singleton grounding field are not authority-bearing. Target or
destination identity may differ between rows inside an otherwise equivalent
partition because the Actor's explicit public selector is precisely the
semantic choice being reconciled. A target inferred only from fuzzy label
similarity, prose, screenshot position, or an unenumerated E-ref is never
equivalent.

Business arguments remain byte-for-byte/typed-JSON equal during silent
normalization. The normalizer cannot rename `text` to `value`, synthesize a
missing destination, alter a selector value, cross catalog/context identity,
or downgrade risk. High-risk confirmation remains downstream and is evaluated
against the newly emitted exact call; reconciliation itself is not user
confirmation.

`REPAIR_REQUIRED` uses the existing single bounded response-repair budget. It
is not a second planner or agent turn and it does not refresh the world. The
repair prompt contains public schema/enum information and value-free actual
type/shape diagnostics; credentials, private bindings, raw payloads, and
canonical IDs remain absent. If repair changes a semantic selector, target,
destination, or tool, it is treated as a newly emitted decision and must pass
exact resolution, admission, risk, confirmation, and currentness from the
beginning. Until then dispatch is zero.

## 9. Canonical state and relation model

### 9.0 Multi-source observed-world information graph

`WorldObservation` is the sole current observed-world owner. “Graph” describes
its typed organization and identity links; it does not introduce another
storage system. The existing chain remains:

```text
BrowserGym / Playwright / DOM / AX / UIA / device API / WoT / HTTP
                  optional OCR / OmniParser-compatible provider
                                  |
                         thin SurfaceAdapter
                                  |
                immutable source-local SurfaceObservation(s)
                                  |
                    existing WorldFusion boundary
                                  |
              one canonical current WorldObservation graph
                         /                    \
          ActorWorldSnapshot             ActionSpace
       bounded epistemic view       independent legal actions
```

#### 9.0.1 Conserved layers

The graph retains five different kinds of information without confusing their
authority:

| Layer | Runtime representation | What is conserved | Model exposure |
|---|---|---|---|
| source envelope | `SurfaceObservation` | source profile, revision, acquisition root, coverage, raw artifacts/media refs | one compact source manifest |
| source structure lens | `ObservationStructureNode` forest or native typed relations | native parent/child order and source-local context | one bounded primary lens plus novel complementary context |
| canonical semantics | `SemanticTarget`, canonical `StateFact`, typed `RelationFact` | one current entity identity and accepted public claims | each canonical entity at most once |
| alignment/evidence | fusion-accepted `EntitySourceLink`, fact/relation evidence and canonical media links | source-local entity/region to canonical entity lineage | aggregated `source_refs`/evidence summaries; conflicts when material |
| current action authority | `ActionBinding` and `ActionSpace` | private route, legality, schema, currentness | separate minimal `ToolSpec`; never graph edges granting permission |

DOM, AX, UIA, visual parsing and WoT can describe different structures over
the same current entities. They are retained as **source lenses**, not forced
into one fictitious universal tree. The canonical graph contains accepted
typed relations such as `CHILD_OF`, `LABELLED_BY`, `MEMBER_OF`, `ROW_OF`,
`CELL_OF`, `HEADER_FOR` and `PRECEDES`; the original source forest remains
available for lineage and bounded contextual rendering.

No source modality is globally authoritative for every predicate. Authority is
predicate- and source-profile-specific. For example, a native AX/UIA checked
state can outrank a visual classifier for `checked`, while the screenshot can
be the only source for rendered colour or canvas content. This policy is a
closed table owned by fusion vocabulary/assurance contracts, not a series of
surface-name branches.

`ObservationPredicateRegistry` is that sole immutable policy owner for target
role/label and public state predicates:

```python
class ConflictDisposition(StrEnum):
    CONSENSUS_ONLY = "consensus_only"
    PREFER_DECLARED_ASSURANCE = "prefer_declared_assurance"
    MULTI_VALUE_UNION = "multi_value_union"


@dataclass(frozen=True)
class PredicateFusionDefinition:
    predicate: str
    value_schema: JsonSchema
    admissible_source_profiles: tuple[str, ...]
    admissible_provenance: tuple[Literal["native", "derived", "model"], ...]
    assurance_order: tuple[str, ...]
    conflict_disposition: ConflictDisposition
```

The default for a known scalar predicate is `CONSENSUS_ONLY`; disagreement
makes the canonical value unknown/conflicted. A predicate may prefer declared
assurance only when its registry definition explicitly supplies that ordering.
Stable source order is used solely to serialize equal evidence and never to
settle a value. `MULTI_VALUE_UNION` is legal only for predicates whose schema
and vocabulary define set semantics. Unknown predicates or source profiles fail
typed at normalization rather than being resolved by first-source wins.

`WorldFusion` applies this registry symmetrically to the complete claim set.
It may retain a selected value plus contrary evidence only when the definition
permits `PREFER_DECLARED_ASSURANCE`; otherwise no disputed value appears as an
ordinary `SemanticTarget.state` or accepted `StateFact`. Conflict alternatives
and their evidence remain available to evaluation and the bounded Actor view.

Identity domains are closed. Everything inside a `SurfaceObservation` uses
source-local IDs, including targets, facts, bindings, structure semantic links
and media grounding regions. Everything at the canonical level of
`WorldObservation` uses canonical IDs. The only bridge is an immutable link set
produced by `WorldFusion`:

```python
@dataclass(frozen=True)
class SourceEntityEndpoint:
    source_observation_id: str
    source_target_id: str


@dataclass(frozen=True)
class EntityAlignmentProposal:
    proposal_id: str
    source: SourceEntityEndpoint
    candidate: SourceEntityEndpoint
    basis: Literal["explicit_provider_correspondence"]
    evidence_refs: tuple[str, ...]
    confidence: float


class EntityAlignmentDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"


class EntityAlignmentBasis(StrEnum):
    EXPLICIT_PROVIDER_CORRESPONDENCE = "explicit_provider_correspondence"


@dataclass(frozen=True)
class EntityAlignmentDecision:
    proposal_id: str
    disposition: EntityAlignmentDisposition
    basis: EntityAlignmentBasis
    evidence_refs: tuple[str, ...]
    confidence: float
    reason_code: str


class EntityAllocation(StrEnum):
    EQUIVALENT = "equivalent"
    INDEPENDENT = "independent"


@dataclass(frozen=True)
class EntitySourceLink:
    source_observation_id: str
    source_target_id: str
    canonical_target_id: str
    acquisition_root_id: str
    allocation: EntityAllocation
```

Proposals name two source-local endpoints because a canonical endpoint does not
exist until fusion accepts equivalence. A `SurfaceObservation` may carry a
bounded tuple of proposals; the same source endpoint may have several candidate
proposals, but duplicate endpoint pairs/proposal IDs are invalid. Candidate
endpoints must exist in the selected source set. This replaces the current
input shape that lets an adapter write a value named `canonical_target_id`
before canonical acceptance.

Fusion validates every proposal and emits exactly one
`EntityAlignmentDecision` before forming equivalence components. A valid
component may contain at most one endpoint from each source observation and
must satisfy acquisition-root, role/profile and evidence requirements. Only
`ACCEPTED` decisions contribute edges, evidence or confidence to an
equivalence component. `REJECTED` and `CONFLICTED` decisions remain auditable
proposal outcomes but never support a final equivalence link. Endpoints not in
an accepted component are allocated independently. Canonical IDs are allocated
from the sorted complete endpoint component, so proposal/source input order
cannot change them.

There is exactly one link for every retained source target. The
`(source_observation_id, source_target_id)` endpoint is unique and resolves to
exactly one current canonical entity. Within one source observation, at most
one local target may link to a given canonical entity; multiple different
source observations may contribute to the same canonical entity. This
collection records only final `EQUIVALENT` or `INDEPENDENT` allocation;
consumers never recompute proposal outcomes, accepted components, unmatched
allocation, rejection/conflict isolation, or collision-renamed IDs.
Adapter-supplied correspondence values are fusion proposals, not the accepted
map.

Every proposal receives one typed decision. `ACCEPTED` requires
both endpoints to exist, compatible source profiles and roles, the same
non-empty acquisition root, explicit evidence refs, a supported basis, valid
confidence and the scoped one-to-one rule above. Invalid proposals become
`REJECTED`; mutually incompatible valid proposals become `CONFLICTED`.
Endpoints without an accepted decision are retained by `INDEPENDENT` links;
they are never dropped or guessed equal. Unknown bases fail typed before
fusion. Rejected/conflicted evidence belongs only to its decision and cannot be
unioned into accepted-component evidence. `EntitySourceLink` does not copy
proposal evidence or confidence; accepted lineage is derived through the
component's accepted decision IDs when diagnostics require it.

`WorldObservation.entity_alignment_decisions` is the complete proposal outcome
set. `WorldObservation.entity_source_links` is the accepted current allocation
mapping and the
sole input for source membership, structure projection and media alignment.
The current `WorldFusionResult.entity_provenance` sidecar must either move into
that field or become a pure derived view of it; it cannot remain a parallel
authority. Likewise, `WorldObservation.sources` must not be partly rewritten:
its source-local media regions remain local, while a canonical media-grounding
view is derived once from `entity_source_links` for Actor/evaluator consumers.

`surface` is a capability/adapter class, not a source-instance key. Fusion maps,
coverage, source manifests and stable ordering are keyed by
`source_observation_id`; surface, modality and profile are attributes. A world
may contain multiple DOM/AX/visual lenses from the same surface and acquisition
root without overwriting maps or coverage. Duplicate source observation IDs
fail construction. World identity and projection order are computed from the
sorted complete source-instance tuples, never from input order or a
`dict[surface, ...]`.

Accordingly, the current `WorldObservation.coverage: dict[surface, ...]`
migrates to a typed source-instance manifest containing
`source_observation_id`, surface, modality, profile, acquisition root and
coverage. Adapter-class summaries, when useful, are derived aggregations and
cannot replace per-instance coverage.

Construction of `WorldObservation` validates the accepted-world boundary, not
merely dataclass shape. Link endpoints exactly cover all retained source
targets; links name only existing canonical targets; every canonical target has
link coverage; endpoint allocation is functional and within-source injective;
equivalent groups have one non-empty acquisition root; and equivalent versus
independent allocation is consistent with the accepted decision components.
Forged, phantom, incomplete, wrong-root, non-injective, or decision-inconsistent
link collections fail construction.

The A.1 relation boundary is deliberately narrow. Existing identity-bearing
`parent_id`, `child_ids`, and `label_for_id` values must reference declared
source-local endpoints and are rewritten through `entity_source_links`.
Unknown endpoints return typed `FusionStatus.INCONCLUSIVE` with reason
`unresolved_source_relation`; they do not escape as a bare exception. Step 15,
not A.1 repair, introduces the general typed/provenance-bearing relation
vocabulary.

#### 9.0.2 Fusion algebra

Within one acquisition epoch, fusion follows these deterministic rules:

1. A source-local target, structure semantic link, relation endpoint, fact
   subject, binding endpoint and media region is rewritten through the same
   accepted `WorldObservation.entity_source_links` mapping. Fusion computes it
   once; no downstream consumer rebuilds explicit/collision fallback logic.
2. Equal claims about the same canonical subject/predicate/value are coalesced
   into one canonical fact or relation. All distinct source/evidence refs are
   retained on that one claim; duplicate facts are not emitted as separate
   Actor content.
3. Materially different claims remain typed alternatives in one conflict. They
   are not winner-overwritten, concatenated into prose, or duplicated as two
   apparent entities. Only the declared predicate authority policy may settle
   a conflict; otherwise the canonical value is unknown/conflicted.
4. A derived/model assertion cannot overwrite conflicting native evidence.
   Confidence ranks evidence within the same admissible authority class; it
   never creates identity, an action, or permission.
5. A visual-only entity remains explicit until a trusted correspondence is
   accepted. Matching by label, ordinal, coordinate overlap, or nearest node is
   evidence for a replaceable alignment provider, not deterministic identity
   authority.
6. Media is deduplicated by current acquisition lineage and content digest.
   Its regions point to canonical entities after correspondence rewrite. A
   screenshot, clean screenshot and SoM overlay are alternative renderings of
   one capture, not three independent worlds.
7. Adding a source is monotonic for retained assertions and evidence: it may
   add evidence, alternatives, conflicts or previously unseen entities, but it
   cannot silently erase a higher-authority accepted claim.

Media alignment uses upstream capture metadata instead of pixel heuristics.
`ObservationMedia` gains a stable current `capture_group_id`, `variant`
(`raw`, `annotated`, or `crop`), dimensions and `coordinate_space_id`;
grounding regions name that same coordinate space. BrowserGym bbox/screenshot
identity populates these fields directly. An annotated SoM image inherits the
base capture group and coordinate space. Sources with different acquisition
roots or coordinate spaces are not overlaid or treated as aligned unless an
explicit typed transform provider supplies a current transform. The Actor
provider mode selects one primary full-frame variant; identical content hashes
coalesce, while other variants remain Runtime evidence or are obtained by
explicit widening.

The target canonical fact shape is one accepted value with aggregated lineage,
not one repeated row per agreeing source:

```python
@dataclass(frozen=True)
class FactEvidence:
    source_observation_id: str
    source_subject_id: str
    evidence_ref: str
    provenance: Literal["native", "derived", "model"]
    confidence: float


@dataclass(frozen=True)
class StateFact:
    fact_id: str
    subject_id: str
    predicate: str
    value: JsonValue
    evidence: tuple[FactEvidence, ...]
```

A `SurfaceObservation` fact starts with source-local identity and one evidence
record. `WorldFusion` rewrites it and produces the canonical coalesced fact.
This replaces the current single `source_id` plus repeated agreeing fact rows;
it does not create a second fact owner. `RelationFact.evidence` follows the
same algebra.

#### 9.0.3 Bounded Actor graph view

Runtime conservation and model exposure are intentionally different. The
Actor receives a deterministic, bounded rendering with these rules:

- emit one node per retained canonical entity, even when DOM, AX, UIA, OCR and
  visual sources all observed it;
- inline its accepted role, label, state, facts, non-tree relations and
  aggregated `source_refs` once;
- select one primary structural occurrence mechanically from declared native
  structure assurance and stable source ordering; retain its ancestors,
  ordered children and the smallest neighbourhood needed to explain retained
  candidates;
- render complementary source structure only when it contributes a novel
  relation/context node, a conflict, uncertainty, or an unmatched entity;
  otherwise keep its lineage only in `source_refs`;
- attach each distinct screenshot once. SoM labels, when used by the selected
  provider mode, reuse the same current E-refs and replace rather than
  accompany a redundant second annotated element list;
- suppress OCR/icon captions that exactly repeat an accepted native label.
  Preserve them when they add visual-only content or disagree, with model/
  derived provenance visible;
- render facet collections only when an index is smaller than repeating the
  same field on many nodes. Collections contain refs, never copied entities,
  and do not remove inline facts required to understand an individual node;
- keep tools separate. A flat tool repeats only the minimum cue/difference
  needed for semantic choice and never becomes the entity description;
- render `last_transition` as a delta only. It does not repeat the current
  snapshot or the newest history row.

`StructuralLensSelectionPolicy`, owned by the Actor-world projector, closes
“primary” and “novel” without task/site branches. Each lens declares typed
structure provenance (`native`, `derived`, or `model`), assurance, source
coverage and its source-instance key. Primary selection uses, in order:

1. registry-declared structural provenance/assurance precedence;
2. complete before partial coverage;
3. greater retained ancestor closure for the already pinned canonical nodes;
4. the stable `source_observation_id` tie-break.

The tie-break affects rendering only and never canonical fact acceptance. A
complementary contribution is novel exactly when it contains: a canonical
typed edge absent from the primary lens; a typed conflict/uncertainty; an
unmatched canonical entity; or the ancestor closure required to explain such
an item. Equal canonical nodes, equal edges, repeated labels and alternate
source-only context are not novel. Source-only context from a non-primary lens
is available through explicit bounded lens widening, unless it is required as
the ancestor of an unmatched emitted entity. This prevents ungrounded DOM/AX
containers with similar prose from being guessed equal or dumped twice.

The policy input is the canonical graph plus immutable source lenses. It does
not read ToolSpecs, private bindings, benchmark IDs or expected task output,
and provider binders cannot override its selection.

Bounding is graph-aware rather than flat top-N truncation. Current legal action
targets and destinations are pinned together with their explanatory ancestors;
then current focus/viewport context, conflicts and relevant neighbours are
retained; remaining context is paged in stable source order. Every document
reports retained/total counts, coverage and truncation. Paging or an explicit
observation widening request retrieves omitted context; missing context is not
invented by the Actor.

This projection is disposable. It cannot be read by fusion, admission,
currentness, execution, evaluation or continuity. Different provider adapters
may serialize the same snapshot to text/image message formats, but may not
re-filter entities, recompute correspondences, repeat full source dumps, or
construct an alternative world graph.

#### 9.0.4 Reuse boundary

The implementation preference is direct open-source reuse behind existing
ports:

| Need | Reuse first | Repository-owned code |
|---|---|---|
| browser DOM/AX, iframe linkage, bbox, screenshot and primitives | pinned BrowserGym + Playwright | thin BrowserGym adapter/profile/translator |
| desktop native control tree and interaction | pywinauto/UIA or the platform accessibility API when that surface is admitted | thin desktop adapter and canonical normalization |
| mobile native hierarchy and device actions | the selected platform driver/API (for example ADB plus an established accessibility driver) | thin mobile adapter; no device automation framework |
| OCR, icon/control detection and visual region captions | replaceable established provider such as OmniParser-compatible output and a maintained OCR library | provider port, result validation, provenance and fusion only |
| graph traversal/ordering | ordinary immutable Python collections; an established graph library only if measured algorithms require it | bounded domain algebra and projection rules |

No new DOM parser, AX merger, layout engine, OCR engine, SoM renderer, screen
detector, mouse/keyboard driver, graph database, or generic ETL framework is
in scope without a demonstrated gap in the reused implementation. Copying an
upstream algorithm into this repository is less preferred than pinning and
wrapping the maintained library. Version constraints and adapter conformance
tests isolate upstream changes.

#### 9.0.5 Current implementation gap

The repository already retains `WorldObservation.sources`, BrowserGym
`ObservationStructureNode`s, aligned media, correspondences and a non-flat
`ActorWorldSnapshot`; these are reused. The immediate defect is narrower:
`_source_memberships()` applies source correspondence before looking up a
canonical entity, while `_structure_documents()` currently looks up
`ObservationStructureNode.semantic_target_id` as though it were already
canonical. With multiple aligned sources, the hierarchy can therefore survive
while its semantic node loses the canonical E-ref/state/facts and falls back to
an N-ref. Both functions are reconstructing only part of fusion identity
because the accepted `_canonical_maps()` result is not retained in
`WorldObservation`; explicit correspondences and collision-renamed identities
can therefore diverge again downstream. Fused source media is additionally
rewritten to canonical IDs while the source targets/structure remain local,
creating a mixed-domain source envelope.

The first implementation slice must materialize the accepted map once as
`WorldObservation.entity_source_links`, keep every `SurfaceObservation`
consistently source-local, and make all source membership/structure/media
consumers use those links. It must delete downstream correspondence
reconstruction rather than introduce a second map in `ActorWorldSnapshot`.
Later typed fact/relation coalescing completes the graph algebra in Step 15.

### 9.1 StateFact is the state truth

`WorldObservation.facts` becomes the sole writable canonical state. During
migration, `SemanticTarget.state` may remain as a compatibility field only if
it is produced by one deterministic function:

```python
project_target_state(
    target_id: str,
    facts: tuple[StateFact, ...],
    conflicts: tuple[ObservationConflict, ...],
) -> Mapping[str, object]
```

Construction validates exact equality between that projection and
`SemanticTarget.state`. Adapters and fusion may not write both independently.
After all consumers use the fact index, the compatibility field is deleted.

Focus, selected/checked state, value, scroll position/extent, min/max/step,
ordinal index, and current URL/page-context fields follow this rule. A state
value that lacks current source identity or is conflicted remains unknown; a
projection cannot settle it.

The rule also governs model convenience indexes. `ActorWorldSnapshot` may
inline fact-derived state beside a node, and a bounded `facet_collections`
index may group repeated public values for model cognition, but both are
disposable projections of the same fact index. A facet collection:

- carries truthful complete/partial/unknown coverage;
- excludes conflicted or unavailable predicates from definite partitions;
- cannot create a target, relation, binding, action, verification fact, or
  task-progress fact;
- is never read by admission, resolver, evaluator, or execution; and
- is rebuilt from the current snapshot rather than persisted across turns.

Structure-only AX/document node state may remain source-preserving contextual
evidence when no canonical semantic target exists. It is explicitly
non-authoritative and cannot be promoted into a canonical target fact without
the ordinary source-normalization and fusion path.

### 9.2 Typed relation facts

Identity-bearing relations move from `SemanticTarget.relations: dict` to a
typed edge collection:

```python
class RelationKind(StrEnum):
    CHILD_OF = "child_of"
    LABELLED_BY = "labelled_by"
    MEMBER_OF = "member_of"
    ROW_OF = "row_of"
    CELL_OF = "cell_of"
    HEADER_FOR = "header_for"
    PRECEDES = "precedes"


class RelationProvenance(StrEnum):
    NATIVE = "native"
    DERIVED = "derived"


@dataclass(frozen=True)
class RelationEvidence:
    source_id: str
    provenance: RelationProvenance
    confidence: float = 1.0


@dataclass(frozen=True)
class RelationFact:
    relation_id: str
    subject_id: str
    kind: RelationKind
    object_id: str
    evidence: tuple[RelationEvidence, ...]
```

`SurfaceObservation.relations` and `WorldObservation.relations` are the sole
typed edge collections. A surface relation starts with exactly one evidence
record. Fusion computes canonical edge identity from `(subject, kind, object)`,
deduplicates that edge, and conserves all distinct source evidence records.
Contradictory exclusive edges produce typed conflicts rather than winner-only
deduplication.

Only one canonical direction is stored for each relation; inverse views are
derived. Scalar attributes such as `ordinal_index` remain state facts rather
than becoming pseudo-relations.

Because every identity endpoint is typed, fusion rewrites `subject_id` and
`object_id` generically. It no longer needs key lists such as `parent_id`,
`label_for_id`, and `child_ids`. Unknown relation kinds fail contract
validation instead of surviving as partially rewritten dictionaries.

Native and derived edges remain distinguishable. Fusion may deduplicate the
same canonical edge while preserving its source records; a derived relation
cannot overwrite a conflicting native relation. Confidence ranks evidence
only and never grants action authority.

Relation meaning and conflict rules are owned by one immutable
`RelationVocabulary`, not by fusion branches:

| Kind | Objects per subject | Subjects per object | Additional invariant |
|---|---:|---:|---|
| `CHILD_OF` | at most one | many | acyclic |
| `LABELLED_BY` | many | many | none |
| `MEMBER_OF` | many | many | none |
| `ROW_OF` | at most one | many | acyclic |
| `CELL_OF` | at most one | many | acyclic |
| `HEADER_FOR` | many | many | none |
| `PRECEDES` | many | many | acyclic, irreflexive |

Two current authoritative native assertions that exceed an at-most-one rule or
create a prohibited cycle produce typed relation conflicts. Derived evidence
cannot resolve that conflict. Unknown relation kinds fail closed before
fusion. Extending relation vocabulary requires adding its cardinality,
cycle/inverse behavior, fusion properties, and delta properties together.

### 9.3 Cross-observation identity continuity

Adapters own source-local identity evidence; they do not directly declare
cross-observation canonical identity. They may emit a typed proposal:

```python
class ContinuityBasis(StrEnum):
    BACKEND_STABLE_ID = "backend_stable_id"
    EXPLICIT_PROVIDER_CORRESPONDENCE = "explicit_provider_correspondence"


@dataclass(frozen=True)
class SourceEntityContinuityProposal:
    before_source_observation_id: str
    after_source_observation_id: str
    before_source_target_id: str
    after_source_target_id: str
    basis: ContinuityBasis
    basis_digest: str


@dataclass(frozen=True)
class AcceptedEntityContinuity:
    before_observation_id: str
    after_observation_id: str
    before_canonical_target_id: str
    after_canonical_target_id: str
    source_proposals: tuple[SourceEntityContinuityProposal, ...]
```

`WorldIdentityResolver` is the sole owner that accepts canonical continuity.
It validates exact before/after lineage, source-profile compatibility, basis
digest format, endpoint existence, one-to-one mapping, role compatibility, and
absence of current identity conflicts. Backend-stable evidence must come from
the same adapter identity domain; provider correspondence must be an explicit
typed provider result, never a label/ordinal/coordinate heuristic.

Rejected, missing, one-to-many, many-to-one, cross-domain, or conflicting
proposals produce typed unknown continuity. `SemanticDiffer` consumes only the
accepted map. Fusion owns canonical identity within one observation;
`WorldIdentityResolver` owns continuity between two observations. Neither
adapter proposals nor model E-refs are identity authority.

## 10. SemanticDelta without a second state owner

### 10.1 Contract

`SemanticDiffer` is a pure Runtime-owned comparison over two immutable worlds:

```python
class DeltaComparability(StrEnum):
    COMPARABLE = "comparable"
    PARTIAL = "partial"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True)
class SemanticDelta:
    before_observation_id: str
    after_observation_id: str
    comparability: DeltaComparability
    compared_source_scopes: tuple[str, ...]
    appeared_entity_ids: tuple[str, ...]
    disappeared_entity_ids: tuple[str, ...]
    changed_facts: tuple[FactChange, ...]
    added_relations: tuple[RelationFact, ...]
    removed_relations: tuple[RelationFact, ...]
    unknown_scopes: tuple[DeltaScopeIssue, ...]
```

The differ applies these laws:

- source/acquisition coverage must be comparable before absence becomes
  disappearance or removal;
- stable canonical entity identity is required across observations;
- conflicts and partial/truncated coverage produce typed unknown scopes;
- fact changes retain before and current after evidence refs;
- relation changes compare typed canonical edges;
- screenshot digest changes are artifact changes, not entity/fact changes;
- the value states only temporal difference, never causal attribution.

Comparable source scope is an exact tuple of surface, source-profile contract,
page/incarnation epoch, and declared inventory/coverage domain. Entity IDs are
comparable only when `WorldIdentityResolver` accepts their typed continuity.
An epoch change without accepted cross-epoch continuity makes entity absence
unknown rather than disappearance.

An optional `ActionSpaceDelta` compares stable semantic option keys rather than
observation-scoped action IDs. Its base key is exactly:

```text
(semantic_action, canonical_target_id, effect_category, semantic_effects,
 parameter_schema_digest, verification_contract_digest,
 destination_mode, sorted_canonical_destination_ids, risk, barrier)
```

It reports availability change for context and liveness; the after
`ActionSpace` remains the sole current selection authority. If target or
destination identity is not comparable, the option enters an unknown scope
rather than an added/removed set.

### 10.2 Lifetime

The delta is computed once after fresh acquisition and before action
evaluation. If retained, it is an immutable child of the same root
`ControlTransition`. It is not independently updated, indexed as a ledger, or
used to reconstruct either observation.

The bounded model projection may include only verified, comparable changes
needed for the latest transition. Older history keeps verified semantic
anchors, not raw deltas or old screenshots indefinitely.

## 11. Action-specific effect verification

### 11.1 Verification is planned before dispatch

After action admission and construction of the final current
`BoundActionRequest`, but before dispatch, Runtime derives one immutable
`ActionVerificationPlan` from:

```text
admitted ActionOption + current target/facts/relations
+ selected parameters/destination + semantic action definition
```

The plan is bound to request ID and before observation ID. It cannot authorize
execution and is not sent to the adapter.

```python
@dataclass(frozen=True)
class ActionVerificationPlan:
    request_id: str
    before_observation_id: str
    obligations: tuple[RuntimeVerificationObligation, ...]
    semantic_fallback_allowed: bool
```

The plan builder instantiates only the option's validated
`VerificationContract`. It does not
choose a postcondition from an action name, role, label, or benchmark task.
When no concrete mechanical template applies, it can produce only an explicit
semantic fallback obligation permitted by the registry.

Task success criteria, requested outputs, and incidental task progress never
become action-effect obligations. `CRITERION_PROGRESS` and task-derived
`ARTIFACT_CREATED` are removed from this action-evaluation path and remain
exclusively under `TaskEvaluator`. A future action-specific artifact effect
requires a new sealed registry-permitted template bound to the current action;
it cannot be inferred from an output request.

The current obligation algebra is extended, not replaced. Concrete families
include:

```text
FACT_TRANSITION_TO(subject, predicate, expected)
RELATION_ADDED/REMOVED(subject, kind, object)
FOCUS_TRANSITION_TO(entity)
SCROLL_STATE_CHANGED(viewport, direction)
NAVIGATION_CONTEXT_CHANGED(context)
```

An unscoped `STRUCTURAL_WORLD_CHANGE` is not sufficient proof of an action
effect. It may remain an observation signal that triggers semantic validation,
but it cannot produce `EFFECT_CONFIRMED` by itself.

### 11.2 Evaluator input

The action evaluator receives one closed input only when post-action acquisition
succeeded:

```python
@dataclass(frozen=True)
class ActionEvaluationInput:
    request: BoundActionRequest
    result: ActionResult
    before: WorldObservation
    after: WorldObservation
    delta: SemanticDelta
    verification: ActionVerificationPlan
```

Preparation is typed:

```python
ActionEvaluationPreparation = (
    ActionEvaluationReady(input=ActionEvaluationInput(...))
    | ActionEvaluationUnavailable(execution_outcome, reason_code)
)
```

`CAPABILITY_UNAVAILABLE` or `FAILED` post-action acquisition therefore creates
no fabricated after observation, delta, evidence index, `ActionEvaluation`, or
`TaskEvaluation`. The root `ControlTransition` retains the original dispatch
truth and typed acquisition failure, and control treats the effect as
unresolved without replay. `ActionEvaluation.UNKNOWN` is used only when a
fresh after observation exists but cannot settle the obligation.

Mechanical evaluation considers only comparable delta entries and evidence
that satisfy a declared obligation. Examples:

- `type_text` confirms the target value transitioned to the admitted text;
- `select_option` confirms the target value/selection transitioned to the
  admitted option;
- `scroll` confirms scroll state changed in the admitted direction, or remains
  `UNKNOWN` when the adapter cannot expose a mechanically checkable state;
- `press_key` confirms only a key-specific state/navigation obligation, not
  any page change;
- `drag_to` confirms the declared relation/state change involving the source
  and admitted destination;
- `set_value` confirms the target value transitioned to the admitted number;
- `activate` confirms a target-state or navigation-context obligation;
  unrelated world or task-progress change does not qualify.

Screenshot or layout change is weak evidence that may justify a model-backed
semantic verifier. The semantic verifier must bind its proposal to the current
request, before/after observations, applicable obligation, and current public
evidence. Runtime validation still owns the accepted `ActionEvaluation`.

`ActionResult` remains transport truth only. `SENT_UNKNOWN` is never retried,
and a fresh observation failure cannot rewrite dispatch truth.

### 11.3 Exact temporal order

The effectful path has one order:

```text
current context/action selection
-> membership and public-parameter admission
-> risk classification and semantic confirmation
-> if confirmation/delay requires refresh:
     fresh observation -> rebuild ActionSpace -> compare the complete confirmed
     option digest
     -> if identical: re-admit the exact subject/parameters/destination
     -> if changed: repeat risk/barrier classification and obtain any newly
        required confirmation, or return a new policy turn
-> bind one exact current option/route
-> final non-mutating currentness probe
-> construct BoundActionRequest against that authoritative before observation
-> instantiate ActionVerificationPlan from its conserved template
-> dispatch once
-> ExecutionOutcome(result + typed post-action acquisition)
-> if acquired: SemanticDelta -> ActionEvaluation -> TaskEvaluation
-> close exactly one root ControlTransition
```

Nothing that can refresh, substitute, or mutate the before world occurs between
final currentness, plan instantiation, and dispatch. If final currentness or
plan instantiation fails, the call is `NOT_SENT`; Runtime reobserves or returns
control and never silently rebinds after the verification plan is frozen.

The complete confirmed-option digest covers semantic action, canonical target,
public parameter values, canonical destination, effect category/effects, risk,
consequence/reversibility, barrier, parameter-schema digest, and verification-
contract digest. Matching only target and parameters is insufficient.

## 12. Failure and unavailability algebra

Failures are attributed at the boundary that owns them:

| Boundary | Typed outcome | Dispatch |
|---|---|---:|
| unknown semantic action in registry | `UNSUPPORTED_SEMANTIC_ACTION` composition/contract error | none |
| adapter does not support a known action | `CAPABILITY_UNSUPPORTED` capability resolution | none |
| recognized action lacks a current subject/destination | `CURRENT_SUBJECT_UNAVAILABLE` / `DESTINATION_UNAVAILABLE` offer issue | none |
| optional destination mode reaches the initial compiler | `UNSUPPORTED_DESTINATION_MODE` catalog error | none |
| semantic candidates need E-ref fallback but refs are incomplete, ambiguous, stale, or unrendered | `GROUNDING_FALLBACK_UNAVAILABLE` catalog error | none |
| model names no current tool | `UNKNOWN_TOOL` reconciliation issue and bounded current-name repair context | none |
| tool exists but a public argument violates its exact schema | `INVALID_ARGUMENT` with public field path/code and bounded same-tool repair | none |
| tool name and explicit selector belong to one authority-equivalent row | `NORMALIZED_EQUIVALENT` with telemetry, then exact resolution | none at reconciliation |
| tool name and selector imply a non-equivalent or ambiguous choice | `TOOL_ARGUMENT_OWNER_MISMATCH` / `AMBIGUOUS_TOOL_INTENT`; bounded `did_you_mean`, model must re-emit | none |
| model selects no current ActionSpace member | `ACTION_OUTSIDE_ACTION_SPACE` admission issue | none |
| public parameters/destination violate current option | `INVALID_ACTION_PARAMETERS` admission issue | none |
| binding is stale | existing `STALE_BINDING` | `NOT_SENT` |
| currentness cannot be checked | existing `CURRENTNESS_UNAVAILABLE` | `NOT_SENT` |
| claimed primitive has no translator | composition failure; escaped invariant maps to `UNSUPPORTED_ACTION` | `NOT_SENT` |
| backend call fails before send | typed adapter error | `NOT_SENT` |
| backend accepted/completed call | existing result | `SENT` |
| send may have happened but receipt is uncertain | existing result | `SENT_UNKNOWN` |
| post-action acquisition is unavailable/failed | typed `ExecutionOutcome`; evaluation unavailable | unchanged |
| acquired fresh evidence cannot settle obligation | `ActionEvaluation.UNKNOWN` | unchanged |

Capability-unavailable is not overloaded onto `ActionResult` when no execution
request exists. Conversely, an executor cannot use capability diagnostics to
pretend a dispatched call was not sent.

## 13. Capability examples through the same chain

### 13.1 Viewport scroll

```text
registry: scroll(VIEWPORT, SCROLL, no destination, SCROLL_STATE)
adapter profile: BrowserGym scroll primitive supported
observation: viewport target + scroll facts + current scroll binding
ActionSpace: task-legal scroll option
tool: scroll(direction, extent) when one viewport is current; otherwise add
      only the minimal semantic container selector
translator: public direction/extent -> private backend deltas
verification: comparable viewport scroll/content-window obligation
```

No pixel delta or viewport geometry crosses the model boundary.

### 13.2 Focus-aware keypress

```text
registry: press_key(FOCUSED_CONTEXT, KEY, no destination, typed families)
observation: focused_context target related to exact focused entity
binding: exists only for admitted named keys and current focus
tool: press_key(key); focused target is a private constant
translator: named key -> backend press command
verification: focus/value/navigation action obligation or UNKNOWN
```

A stale or unknown focus context creates no binding. The model cannot send a
keypress to an implicit global target.

At a scroll boundary, a current `can_scroll_<direction>=false` fact prevents
that directional binding. If the binding was valid before dispatch but complete
post-state proves no directional movement, evaluation is
`NO_EFFECT_CONFIRMED`; incomplete/non-comparable post-state is `UNKNOWN`.

### 13.3 Drag and drop

```text
registry: drag_to(ENTITY, EMPTY, destination REQUIRED, RELATION_CHANGE)
observation: source entity + eligible canonical destinations
binding: private source/destination handles + complete public semantics
tool: drag_to(source semantic selector, destination semantic selector) only
      for a complete admitted Cartesian product; otherwise one atomic pair choice
resolver: semantic selector/pair round-trips to the exact admitted option
verification: source/destination relation or target-state obligation
```

Destination identity follows the same currentness and grounding rules as the
source. Coordinates remain private.

### 13.4 Slider or spinbutton value set

```text
registry: set_value(ENTITY, NUMERIC_VALUE, no destination, VALUE_STATE)
observation: value/min/max/step StateFacts + current binding schema
tool: set_value(value) for one target; otherwise minimal semantic target choice
translator: adapter chooses native set, key sequence, or drag privately
verification: exact value transition with current structural evidence
```

Different private techniques remain equivalent only when they implement the
same current semantic contract and verification obligation.

## 14. Migration plan

The numbered work items motivating this design are a coverage checklist, not a
mandatory implementation DAG. The architectural requirement is to settle the
shared owners and extension seam before adding backend-specific behavior.

### 14.1 Gap coverage matrix

| Required gap | Covered by this design | Resulting shared owner |
|---|---|---|
| activate false-positive | action-specific sealed verification contract and evaluator input | validated `ActionEvaluation` |
| canonical action vocabulary | finite semantic definitions and schema families | `InteractionCapabilityRegistry` |
| generic grounded parameters and destination | semantic-facet compiler, generic business schema, non-Cartesian-safe destination factoring, exact private resolver | `ContextBuilder` candidate closure + `GroundedToolCompiler`/resolver |
| minimal capability descriptor | profile + translator + composition validation | `AdapterInteractionProfile` / `CapabilityComposer` |
| StateFact single truth | strict fact-derived target-state migration | `WorldObservation.facts` |
| one role to multiple actions | `RoleCapabilityOffer` tuple | current adapter binding offers |
| scroll and focus-aware press | viewport/focused subjects, bounded schemas, translators and obligations | ordinary ActionSpace/execution/evaluation chain |
| multi-source observed-world graph | source-local lenses, one correspondence rewrite, evidence coalescing, conflict preservation and one bounded Actor node per canonical entity | existing `SurfaceObservation` / `WorldFusion` / `WorldObservation` / `ActorWorldSnapshot` chain |
| typed relations and semantic delta | typed edge vocabulary, continuity acceptance and comparable diff | `WorldObservation.relations` / pure `SemanticDiffer` |
| drag/slider/OCR/tiling/CLI breadth | adapter, provider, strategy and product-entrypoint boundaries | existing owner for each layer; no new kernel |

Coverage in this table means the target interface and authority boundary are
defined. It does not mean every implementation is complete or that one row must
be committed before the next row's code can be drafted.

### 14.2 Wave A — land the shared onboarding spine

Land the smallest coherent contract foundation with no new GUI behavior:

- canonical `SemanticActionDefinition` vocabulary and sealed verification
  contract;
- minimal `AdapterInteractionProfile` plus translator/composition validation;
- one `ProviderCallNormalizer` contract that preserves existing harmless wire
  tolerance, proves authority-equivalent catalog normalization, and returns
  typed `did_you_mean` repair instead of silently changing non-equivalent
  intent;
- exact generic parameter/destination conservation from `ActionBinding` through
  `ActionOption`, public candidate, tool schema, resolver and admission;
- flat semantic-tool compilation that hoists shared target structure, exposes
  only minimal public differences, and uses E-ref solely as an explicit
  indistinguishability fallback;
- migrate the current ContextBuilder `selection_key`/provider `actions.groups`
  compatibility path into that single compiler and delete the parallel
  regrouping path after shadow equivalence passes; shadow tables are telemetry-
  only and are never included in an Actor request;
- `StateFact` as the sole state write path with strict target-state derivation;
- current binding/ActionSpace remaining distinct from static support;
- typed unavailable/invalid/stale boundaries and property tests.

For each migrated concern, Wave A must switch all producers and consumers and
delete the displaced map, compatibility canonicalizer, schema branch, and test
fixture in the same coherent slice. Shadow comparison may exist only during
the slice under Section 5.2.1 and is deleted before the concern is admitted.

These contracts should be designed and reviewed together because they form one
extension seam. Their internal implementation commits may be split in whatever
order keeps the branch reviewable; the design does not prescribe a vocabulary-
versus-tool-versus-profile micro-sequence.

Exit: the new contracts can represent every existing activate/text/select/read
binding and tool shape, all migrated producer/consumer paths resolve through
the new sole owners, and the displaced compatibility/shadow paths have been
deleted. Offered actions, dispatch and evaluator results do not yet change.

### 14.2.1 Wave A.1 — close the observed-world graph owner spine

This is a separate architecture slice, not a retroactive claim that the
implemented interaction-registry slice already met multi-source exit criteria.
The owner spine is implemented, but closure is reopened because the original
gate did not prove proposal-level decision conservation, accepted-link lineage,
accepted-world construction invariants, typed unresolved-relation failure, or
the structure-free multi-source Actor fallback:

- key every fusion map, coverage record and source manifest by source instance,
  not adapter/surface name;
- materialize exactly one decision per proposal and the one final
  source-to-canonical allocation map as
  `WorldObservation.entity_alignment_decisions` and
  `WorldObservation.entity_source_links`; proposal rejection/conflict evidence
  never becomes accepted-link evidence;
- replace the current trusted `EntityCorrespondence` input with a typed
  proposal carrying basis/evidence/confidence; validate acquisition lineage,
  endpoint existence, role/profile compatibility and scoped one-to-one rules;
- apply it to targets, facts, bindings, destinations, media regions and
  structure semantic links, then delete downstream correspondence
  reconstruction and fusion-result-sidecar authority;
- keep all identities within `SurfaceObservation` source-local and all
  top-level `WorldObservation` identities canonical;
- preserve upstream capture-group/coordinate-space identity so raw screenshot,
  SoM variant and grounding regions align without pixel matching or duplicate
  full-frame attachment;
- introduce the immutable predicate/source-profile fusion policy and remove
  first-source-wins behavior;
- migrate the Actor document/lens representation from per-source repeated trees
  to one canonical node plus source refs and mechanically novel complementary
  context;
- preserve source-local structure/media in Runtime with truthful per-instance
  coverage, while emitting each canonical entity once in the bounded snapshot.

Exit: source/proposal permutation does not change decisions, accepted links,
the canonical graph, conflicts or Actor payload; mixed valid/invalid proposals
cannot contaminate accepted evidence or confidence; same-surface multiple
source instances do not overwrite maps or coverage; forged or inconsistent
link sets cannot construct accepted world truth; unresolved supported relation
endpoints fail typed; structure-free multi-source input projects correctly; a
corresponded structure node retains the canonical E-ref/state/facts of its
entity; agreeing sources produce one Actor entity node with aggregated source
refs; and rejected/conflicted alignment proposals retain independent entities
with their typed decision. No binder/provider reconstructs identity or lens
selection.

A.1 does not claim canonical fact/relation evidence coalescing. Until Step 15,
the one entity node may still contain the existing repeated agreeing fact rows;
it must not invent a projection-only canonical claim to hide that migration.
Step 15 replaces those rows with one canonical fact/relation claim carrying
aggregated evidence and activates the corresponding no-duplicate-claim exit
properties.

### 14.2.2 Wave A.2 — select sources before fusion

A.2 begins only after the A.1 repair gate. It retains the current
`ObservationOrchestrator` as the one selection owner and converges the existing
request/offer/structure-first/vision-escalation code. Physical multi-channel
capture, semantic source activation, selected-set fusion and Actor delivery are
separate layers. Normal structurally sufficient turns activate one semantic
source; at most one targeted complementary source is selected for a typed
residual coverage, ambiguity, visual-property or verification need.

The slice deletes observe-all compatibility and adapter-local plan mutation;
`WorldFusion` never selects a source, adapters never add one after selection,
and the Actor never receives parallel raw DOM/AX/SoM/visual dumps. The complete
selection matrix, model-lens contract, upstream reuse boundary and exit
properties are in the
[adaptive observation policy design](plans/2026-08-15-adaptive-observation-policy-a2.md).

### 14.3 Wave B — migrate existing actions and correct effect authority

Make existing behavior the first consumer of the spine before adding a new
capability:

- normalize public semantic names while retaining backend primitive names;
- emit sealed verification contracts for existing value, checked, selected,
  expanded and navigation-context effects;
- conserve their contract/schema digests through binding, ActionSpace,
  projection, resolver, admission and bound request;
- run compatibility/shadow assertions before switching authority;
- replace activate evaluation that accepts unrelated structural, layout or
  screenshot change with exact contract obligations;
- return `UNKNOWN` when no current contract/evidence can settle the effect, and
  retain regressions for unrelated changes;
- delete action-name postcondition guessing only after all current producers
  supply the shared contract.

Exit: existing actions traverse the new spine, current supported activation
families do not lose their ordinary control flow, and arbitrary temporal change
can no longer confirm effect truth.

### 14.4 Wave C — Step 14 vertical capability slice

Use BrowserGym scroll and keypress as the first proof that the spine works:

- change a role from one action to multiple current `RoleCapabilityOffer`s;
- normalize native scroll/active-element/AX state into current viewport,
  entity/focused-context `StateFact`s;
- reuse existing BrowserGym/session/Playwright primitives through thin
  translators;
- offer bounded `scroll`/`press_key` only when the current subject and backend
  support are valid;
- preserve ordinary admission, risk, currentness, dispatch receipt,
  post-action acquisition and action-specific verification;
- run targeted properties, adapter integrations and the selected capability
  cohort before broader gestures.

Exit: scroll and keypress add no BrowserGym branch to the Runtime kernel and do
not require a second action/tool/evaluator pipeline.

### 14.5 Wave D — Step 15 relational and changing-world slice

Implement the already-designed relation/delta interfaces when Step 15 needs
them:

- introduce `RelationFact`, `RelationVocabulary`, cardinality/cycle rules and
  Runtime-owned cross-observation continuity acceptance;
- replace repeated agreeing per-source fact/relation rows with one canonical
  claim carrying all source evidence, while retaining typed conflicting
  alternatives;
- normalize native DOM/AX/device table, row, cell, header, list, label,
  parent/child and ordering semantics first;
- use bounded deterministic geometry/parentage/regular-layout inference only
  when native semantics are absent, retaining `DERIVED` provenance/confidence;
- compute comparable `SemanticDelta` over canonical entities/facts/relations;
- share that one delta with verification, liveness, dynamic-target lifecycle
  and bounded latest-transition projection.

Exit: no consumer owns a private before/after differ, and the project still
does not rebuild HTML layout or ask a screenshot model for native structure by
default.

### 14.6 Wave E — evidence-driven breadth and cutover

Implement `drag_to`, `set_value`, hover, OCR/tiling, and bounded traversal as
separate adapter/provider/strategy slices over the same contracts:

- drag/hover/value actions reuse BrowserGym, Playwright, AX/UIA, OS pointer or
  device primitives through thin translators;
- slider/spinbutton prefer native value setters or bounded key primitives over
  visual coordinate drag;
- OCR and visual-only grounding use replaceable typed provider ports;
- screenshot tiling reuses capture backends while Runtime owns tile epoch,
  offset, overlap, budget and fusion admissibility;
- automatic scroll coverage is an explicit bounded strategy that proposes
  ordinary canonical scroll actions; adapters may not scroll invisibly;
- default CLI cutover remains a product-entrypoint migration, not an
  interaction capability.

A genuinely new semantic shape extends the finite registry and its properties.
A new primitive implementation of an existing shape changes only its adapter
profile and translator. New physical execution or perception machinery is
written only after existing backends/providers are shown insufficient.

### 14.7 Capability implementation review gate

Every capability change must answer these questions in its implementation
record or pull-request description:

1. Which existing backend primitives and source-state APIs were inspected?
2. Why is this change a Runtime contract, thin adapter, provider port, or
   optional strategy rather than another category?
3. Does any adapter mutate the environment during observation, normalization,
   tiling, OCR, or coverage traversal? If yes, the change is rejected until the
   mutation becomes an ordinary admitted action.
4. Can any backend/provider output create canonical identity, current binding,
   ActionSpace membership, dispatch truth, effect truth, or task completion
   without Runtime validation? If yes, the change is rejected.
5. Does an existing semantic shape require changes to AgentLoop, grounded-tool
   parsing, admission, or generic evaluator routing? If yes, either the shared
   contract is still incomplete or the change is not actually the same shape.
6. Is new low-level mechanics being added? If yes, the record must contain a
   concrete unsupported-capability witness for the existing backend/provider
   set and explain why a replaceable adapter/provider cannot close it.
7. Is exploration bounded, observable, interruptible and benchmarkable? Hidden
   adapter-side scrolling, OCR loops, or tiling loops are rejected.
8. Which old owner, alias, branch, fixture and composition path does this slice
   delete? If the answer is “later,” the slice remains partial and cannot admit
   dependent capabilities.

These are architecture and code-review gates. They do not require every
surface to support the same capability and do not turn missing support into an
exception; unsupported remains typed and fail-closed.

## 15. Verification strategy

Example tests remain useful witnesses, but closure depends on properties across
the whole onboarding chain.

### 15.1 Registry and composition properties

- every profile action resolves to exactly one semantic definition;
- every profile primitive resolves to exactly one translator;
- unknown action, primitive, subject kind, or schema family fails closed;
- adapter support never creates current ActionSpace membership;
- the same semantic definition validates equivalent DOM, Visual, WoT, Device,
  or BrowserGym bindings without surface branches in core code.

### 15.2 Projection and round-trip properties

- each current `ActionOption` has at most one closed public candidate;
- catalog compilation consumes only the candidate view;
- catalog construction is deterministic for the same context;
- forbidden/required destination modes expand to the exact declared concrete
  rows, while initial optional destination mode fails typed and emits no tool;
- business parameter schema and required fields are conserved exactly;
- no private field appears in a schema, provider message, or resolver result;
- every group constant equals the recursive intersection of its complete
  candidate semantics;
- every non-singleton semantic selector is the smallest supported facet set
  under the canonical tie-break and uniquely distinguishes the group's actual
  concrete rows;
- a singleton candidate emits no target selector, and a semantically unique
  candidate set never asks the Actor to choose an E-ref;
- every emitted semantic or grounding-fallback selector resolves to exactly
  one current admitted action/destination identity;
- every grounding fallback has a complete injective same-context rendered
  endpoint-ref tuple mapping; sparse source/destination pairs are atomic and
  missing/duplicate/stale/unrendered refs fail with zero dispatch;
- independent selector fields are emitted only for a complete actual Cartesian
  product; sparse target/destination or multi-facet sets admit only real atomic
  choices;
- complete candidate records and normalized entity/group tables are absent
  from every Actor request;
- shape-tool names remain unique under generated digest-prefix collisions and
  every selector tuple inside one tool maps to exactly one option;
- exact valid calls are unchanged by reconciliation;
- wire aliases preserve every argument value;
- silent cross-tool normalization occurs only for one complete real row with
  the same authority-equivalence digest and unchanged business arguments;
- non-equivalent, ambiguous, unknown, stale, or unenumerated choices produce
  zero dispatch and bounded typed repair/rejection rather than candidate
  substitution;
- a model-repaired semantic choice is resolved and admitted as a new exact
  decision rather than mutating the earlier call in place;
- a stale catalog/context/action produces zero bind/probe/execute calls;
- the latest transition occurs once per provider request, and each candidate
  group's common semantics occur once in its compiled tool surface.

### 15.3 State, relation, and delta properties

- every alignment proposal has exactly one typed decision, and only accepted
  decisions contribute equivalence edges, evidence or confidence;
- every source-local identity-bearing reference is rewritten by the same
  accepted correspondence map or is explicitly retained as unmatched;
- every retained source target has exactly one `EntitySourceLink`; source
  order, explicit correspondence and canonical-ID collision cases produce the
  same links for every consumer;
- link endpoints exactly cover retained source targets; canonical coverage,
  within-source injectivity, acquisition-root consistency and accepted-decision
  lineage are construction invariants of `WorldObservation`;
- `SurfaceObservation` identities remain source-local and
  `WorldObservation` top-level identities remain canonical; mixed-domain source
  envelopes are rejected;
- every retained canonical entity has at most one Actor node/E-ref even when
  observed by multiple sources;
- after Step 15, agreeing source claims render once with the complete set of
  evidence refs and no projection-only dedup path;
  conflicting claims render once as bounded alternatives and never as
  duplicated entities;
- primary structure rendering retains ancestor closure and child order;
  complementary lenses add only novel context/conflict/unmatched content;
- media captured from the same acquisition root and content renders once, and
  every emitted mark/region resolves to its current Actor entity or remains
  explicitly ungrounded;
- media/region overlay requires the same declared coordinate space or an
  accepted explicit transform; raw/annotated variants share one capture group
  and the selected provider mode attaches only its primary full-frame variant;
- adding an agreeing source cannot remove accepted evidence or increase the
  number of Actor entity copies;
- permuting source instances leaves entity links, accepted role/label/state,
  conflicts, primary lens and serialized Actor payload semantically equal;
- same-surface source instances retain distinct coverage/lenses and never
  overwrite one another;
- non-primary context satisfies the closed novelty rule or is omitted with
  truthful lens-widening availability;
- projection bounds are deterministic and report truthful retained/total,
  coverage and truncation values;
- provider serialization cannot independently filter, fuse, align or regroup
  the Actor graph;
- target-state compatibility projection equals the fact-index projection;
- two independent writers cannot construct a valid observation;
- every relation endpoint exists in the same canonical world or is rejected;
- fusion rewrites every typed endpoint and preserves provenance;
- relation cardinality/cycle conflicts are deterministic and cannot be settled
  by derived evidence;
- relation order or source order does not change the fused canonical graph;
- only `WorldIdentityResolver`-accepted one-to-one continuity makes entities
  comparable across observations;
- incomplete/non-comparable coverage never produces disappearance/removal;
- delta is deterministic, antisymmetric where scopes are comparable, and empty
  for semantically equal worlds despite new observation IDs;
- no current world or ActionSpace is reconstructed from a delta.

### 15.4 Execution and evaluation properties

- one admitted action produces at most one effectful dispatch;
- `SENT`/`SENT_UNKNOWN` never execute an alternate route;
- required destination and public parameters survive selection through bound
  request without mutation;
- every admitted verification contract is a sealed, registry-permitted
  template whose parameter/destination references match the exact option;
- a refreshed option with a changed confirmation digest cannot reuse earlier
  risk/barrier confirmation;
- `EFFECT_CONFIRMED` evidence satisfies at least one pre-dispatch obligation;
- unrelated entity, fact, relation, layout, or screenshot change cannot confirm
  an action effect;
- no-effect requires complete comparable evidence for every mechanically
  checkable obligation;
- unknown evidence remains `UNKNOWN`, not failure, success, or replay;
- action and task evaluation remain independent.

### 15.5 Integration and benchmark evidence

Each capability slice runs:

1. contract/property tests;
2. one adapter integration witness for success;
3. unavailable, invalid-parameter, stale, `NOT_SENT`, `SENT_UNKNOWN`, and
   post-observation-failure witnesses where applicable;
4. a small previously supported no-regression cohort;
5. its targeted live benchmark cohort;
6. later, the frozen breadth benchmark with capability coverage and aggregate
   success reported separately.

No production branch may inspect benchmark case IDs, expected answers, reward,
or known page text.

## 16. Falsifiable exit criteria

This design is ready for implementation only when repository review confirms:

1. every owner in the sole-owner table maps to one intended module and no
   competing owner is introduced;
2. `ActionSpace` remains the only current legal-action authority;
3. the registry/profile/binding distinction is preserved in interfaces and
   names;
4. flat model tools can be generated and resolved generically from complete
   closed candidates by hoisting shared semantics, exposing only minimal
   semantic differences/business values, preserving actual destination pairs,
   and using E-ref only as an explicit grounding fallback;
5. provider-call tolerance has one owner and a closed distinction between
   syntax normalization, proven authority-equivalent normalization,
   model-required semantic repair, and deterministic rejection;
6. state and relation migrations have one canonical write path and a deletion
   gate for compatibility fields;
7. delta comparability and non-causality are explicit;
8. effect confirmation requires an action-specific pre-dispatch obligation;
9. unsupported, unavailable, invalid, stale, sent, uncertain, and unknown
   outcomes remain typed and temporally consistent;
10. adding a second adapter for an existing semantic shape requires no
   AgentLoop/catalog/parser/evaluator branch;
11. the migration order respects the current Step 13/14 evidence gate and does
    not claim unimplemented behavior.

Implementation is complete only when the corresponding code, properties,
adapter integrations, docs/status, and fresh benchmark evidence agree. The
design document itself is not implementation or closure evidence.

## 17. Rejected alternatives

### Register provider tools directly

Rejected because provider tools would become a second action vocabulary and
could outlive current ActionSpace legality. Tools must be compiled from current
authority.

### Let each adapter name its own semantic actions

Rejected because `fill`, `type`, `write`, and `press` would leak backend
differences into policy, evaluator, memory, and benchmark semantics.

### Put all capability behavior in one generic action payload

Rejected because `parameters: any` destroys schema validation, risk clarity,
verification routing, and model decision quality.

### Expose the normalized entity/capability graph to the Actor

Rejected as an action-selection surface because it makes the Actor join entity
records to operation groups before acting. Such a graph may remain internal
compiler diagnostics, but it is excluded from every Actor request; the provider
receives direct flat tools.

### Make E-ref the default target selector

Rejected because it forces the Actor to map task semantics to an observation-
local mark even when the Runtime already has a unique verified semantic facet.
E-ref remains screenshot grounding evidence and the explicit fallback for
semantically indistinguishable visual candidates.

### Generate domain-specific parameter or tool names from page text

Rejected because fields such as `product` or Unicode page labels in tool names
would create task/site vocabulary and provider portability problems. Selector
fields are derived mechanically from bounded semantic paths; provider-local
tool variants use canonical operations plus deterministic transport suffixes.

### Make the adapter profile the ActionSpace

Rejected because static backend support does not include current target,
destination, task effects, risk, conflict, schema domain, or currentness.

### Persist SemanticDelta as a world ledger

Rejected because observations and current AgentLoopState already own truth.
A durable delta store would introduce reconstruction and consistency burdens
without evidence that the short GUI loop needs event sourcing.

### Accept any before/after change as activation success

Rejected because temporal correlation is not action-specific effect evidence.
Broad change may trigger semantic inspection but cannot settle the effect.

### Add BrowserGym branches for scroll, press, and drag

Rejected because it repeats the same missing shared contracts for every
interaction family and prevents cross-surface capability conformance.
