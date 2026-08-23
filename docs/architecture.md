# Architecture

## Status

Current status: **Gate 0 complete / Gate 1 World complete / Gate 2 Delivery complete /
Gate 3 Envelope correction implemented and provider-free verified / Gate 3 exit review pending /
Gate 4 not admitted / Overall reopened / non-closed / no live run
authorized**. Causal post-action transition, TaskGoal public-input projection, and benchmark finalization remain
separate reopened gates. The mandatory
Planner/Milestone/Evidence/Auditor production path remains removed. Prior G0–G6 and C8–C9 artifacts are historical
scoped evidence for the implementations they exercised; they are not whole-runtime closure and do not authorize
another live run.

This file and [`benchmark.md`](benchmark.md) are the only current design, status, and acceptance authorities.
[`single-action-policy-convergence.md`](single-action-policy-convergence.md) is retained as migration rationale for the
removed mission path, not as a second current status document. Milestone-path sections below are historical analysis,
not a selectable production path.
Chronological run evidence, superseded designs, and prior reopenings are preserved in
[`history/architecture-pre-milestone-convergence-2026-08-22.md`](history/architecture-pre-milestone-convergence-2026-08-22.md).
They do not override this document.

The target runtime remains a small, continuous GUI runtime with one execution authority: one start/revision-only
GoalCompiler call, an optional static advisory GoalPlan, and one ActionPolicy loop. Long-horizon behavior in the baseline comes from
a bounded `AgentWorkspace` and optional exact working notes, not mandatory roadmap, milestone, Auditor, or MissionState
transitions. Change-first delivery, bounded workspace, one request-admission owner, strict binding/currentness, and the
information-increment Monitor remain accepted directions. Run20 proved that the model-facing action projection and
the harness finalization path do not yet preserve their owners' facts end to end.

Run20 remains the action-conservation witness: the fresh World and complete ActionSpace contained executable `Go`, but
delivery/search omitted it; the Monitor then correctly stalled while a separate report projection failure prevented
durable reporting and cleanup entry. Run21 remains the delivery-boundedness witness: recall relevance was promoted to
an unbounded mandatory prompt set, producing local `context_capacity` before any provider call. Detailed witness facts
and acceptance consequences live in `benchmark.md`; neither run is a production special case.

Implementation checkpoint (2026-08-23): useful owner-level foundations exist, including complete ActionSpace conflict
handling, functional context, public-ref syntax, typed termination, TaskGoal conservation, and durable finalization.
They do not form one accepted production chain while duplicate public ordering, continuation meaning, and provider
request construction remain reachable.

Run21 exposed the shared delivery root cause: recall membership, next-view priority, and protection of an already
admitted record had collapsed into one `protected` Boolean. The normative design keeps them separate: recall remains
complete in Runtime, Plan expresses priority, and only records frozen by `TurnPacker` are protected in the current
request. Exact counts and request breakdowns remain benchmark evidence, not architecture.

Pre-Run21 tests and artifacts remain revision-scoped evidence for the narrower owners they exercised. They do not
prove cardinality-independent delivery, final physical-request identity, or current-tree closure. Current finalization
and WebArena codec work remains in scope but is orthogonal to the frozen World/Delivery/Envelope cutover. Exact evidence
counts, artifacts, and active gates are maintained once in `benchmark.md` rather than repeated here.

Frozen Run21-repair checkpoint (2026-08-23): the attempted replacement implementation is not a converged authority
cutover. It added effect reconciliation, delivery obligations, private cursors, depth-round packing, exact route
manifests, and request privacy checks while older public-ordering, continuation, and provider-envelope owners remained
active. Fresh-context audit found that public target/fact ordering is still allocated by multiple projections, a
zero-admitted obligation suffix can be hidden by the Catalog, and RequestAdmission does not validate the same typed
physical envelope later consumed by the PydanticAI adapter. PublicEffect document lineage also still admits private
viewport identity. Production code and tests are therefore frozen while the World projection, delivery state, and
provider envelope receive explicit owner cutover designs and deletion maps.

The previously reported 1,551/full, 136/focused, and 240/expanded passing-test checkpoints describe an earlier tree.
The pre-Gate-1 tree was red on the inventory-enumeration permutation property; the current World checkpoint replaces
that witness with the owner-level properties recorded below. Likewise,
`evidence/w1b-world-c8-c10-provider-free-20260823-run30/` was written before later Store, Grounding, RequestAdmission,
diagnostic, and test changes and has no source-revision binding. Its six internally consistent provider-free case
records remain historical scoped evidence only; Run30 cannot verify the current tree or any production-chain
conservation claim. No model provider, live ActionPolicy, or live benchmark was run. The user-authorized pre-Gate
baseline commit is `0717f8e5`; it does not change the reopened/non-closed status.

Gate 0 implementation checkpoint (2026-08-23): the test-only Recording PydanticAI model is implemented through the
actual `TargetRuntime/CoreAgentLoop → ModelBackedAgentPolicy → PydanticAIGroundedDecisionPort → PydanticAI Agent →
FunctionModel` path. It snapshots the ordered typed `ModelMessage`/parts and the `AgentInfo` values PydanticAI 2.21.0
actually supplies: instructions/instruction parts, complete function/output tool definitions and parameter schemas,
strictness, model settings, and the public `ModelRequestParameters` output contract. It also observes real
`BinaryContent` MIME and bytes without rebuilding, sorting, filtering, or interpreting the request. The callback API
does not expose the Agent name or Runtime phase, so call ordinal is observed and phase is explicitly a scripted test
label rather than a claimed provider-boundary field. The recorder calls no network/provider and owns no production
state or semantics. No `src/` file was modified for Gate 0. This is acceptance instrumentation only.

World Gate 1 implementation checkpoint (2026-08-23): `CanonicalPublicWorldProjection` is now the sole production
allocator and ordering owner for public `E/N/F/R` records. It consumes one fresh `WorldObservation`, the unnumbered
`WorldDeliveryIndex`, and the complete current `ActionSpace`; retains private resolution lineage; and exposes immutable
ordered target/fact/region records, stable public structural slots and provenance, public document signature, and
private resolver maps. `ContextBuilder` installs the same value in `AgentContext`, and World projection, grounding,
actor rendering, observation paging/delivery, effects, action candidates, discovery, evaluator views, Manifest/Catalog
type flow, workspace and benchmark diagnostics consume supplied refs. The former `WorldDeliveryIndex` R allocator,
Grounding E/N allocator, `ContextBuilder._public_fact_refs`, and consumer-side public fact/ref fallbacks are physically
removed. Provider-free properties cover private ID value/length, target/fact/binding/structure/source enumeration,
hash seed, multiplicity, identity-only remount, precise semantic add/remove/modify effects, typed ambiguous grounding,
shared projection identity, and the real Gate 0 recorder path. Delivery and Envelope cutovers remain pending; overall
status remains reopened/non-closed, and no live evidence is claimed for this tree.

Delivery Gate 2 implementation checkpoint (2026-08-23): `ObservationDeliveryStore` now owns immutable current
effect/page-directory/base/query/interaction/destination/issue inventories, exact private offsets, requested foreground,
currentness, and typed continuation capabilities. `ActionDeliveryPlan` consumes those snapshots as a pure per-turn
priority value; `TurnPacker` requires only the foreground zero/one minimum, performs deterministic depth-round greedy
admission with bounded backoff, and freezes the exact admitted prefixes. `ModelTurnDelivery` freezes Store capabilities
with its text/media/Manifest, including zero-admitted suffixes. `PerTurnToolCatalog` consumes those capabilities and
Manifest-owned exact resolver rows; it no longer derives cursor inequalities or scans complete ActionSpace to infer a
route. Text action refs, route deltas, Manifest rows, and private resolver lineage commit atomically, while issue-only
fragments cannot publish an unrouted executable ref. Public history no longer carries observation IDs, World digests,
or raw delta records. Provider-free verification covers fanout `1/2/16/84/167/500`, added/removed/modified effects,
multi-scope finite recovery and staleness, exact short/Unicode/punctuation/boundary labels, zero-prefix continuation,
and a two-request real `TargetRuntime/CoreLoop → PydanticAI FunctionModel` sequence. Full pytest is `1594 passed, 24
skipped`; Ruff, compileall, diff check, and Delivery negative searches pass. Gate 4 vertical conservation remains
pending; this is not C10, benchmark, provider, or live closure.

Envelope Gate 3 correction checkpoint (2026-08-23): `CanonicalProviderEnvelopeBinder` is the sole producer of the
immutable PydanticAI model-boundary request. The current ActionPolicy algebra closes exactly one instruction and one
current user request; bounded history/tool-result context is embedded in canonical `user_text`, and independent
history messages are rejected at the Envelope owner. It also closes exact media bytes and MIME,
Catalog-derived ordered strict tool definitions and schemas, model identity/settings, parallel-call policy, output
contract, output reserve, deterministic counting method, and attempt lineage before admission. The stable
`envelope_id` hashes only physical model-visible content and selected provider/model profile; Runtime-only Catalog
resolver identity and trace/delivery lineage are excluded. `RequestAdmission` accepts only that complete envelope,
counts every physical component with a deterministic conservative local fallback, and returns the same immutable
value on admission. `TurnPacker` reuses its final admitted envelope. The PydanticAI bridge is a mechanical typed codec
to ordered `ModelMessages + ModelRequestParameters`; it no longer rebuilds prompt, tools, media, settings, or output
contract after admission. Every physical initial or repair call records its envelope projection at attempt start.
Provider-free exact-boundary, identity/cost, media/tool, pre-provider totality, repair, and two-turn production-path
properties pass. Full pytest is `1598 passed, 24 skipped`; Ruff, compileall, diff check, and production negative
searches pass. No real provider, live benchmark, Task-7 replay, external token-count request, or raw HTTP payload
builder was used. Gate 4 vertical conservation is not admitted and remains pending; overall status is reopened/non-closed.

## Normative single production chain

This section is the sole normative production data flow. Later sections may explain an owner or preserve failure
evidence, but they may not define another ordering, ref allocator, cursor transition, delivery path, ToolCatalog source,
provider request, or acceptance sequence. If a later diagram disagrees with this section, this section wins and the
later diagram must be corrected or moved to history.

The pre-cutover implementation was frozen because it layered new projections over old owners instead of cutting the
old owners over. Gates 1–3 have now cut over World, Delivery, and Envelope; Gate 4 remains an explicitly non-admitted
vertical conservation target, not another Agent framework:

```text
BrowserGym observation
→ SurfaceAdapter
→ fresh WorldObservation                                      # current GUI truth
   ├→ WorldDeliveryIndex                                      # unnumbered public structure
   ├→ complete ActionSpace                                    # current legal routes
   └→ WorldTransitionProjector(before, current)               # lossless raw delta
→ CanonicalPublicWorldProjection(World, index, ActionSpace)    # sole public refs/order
→ PublicEffectInventory(previous projection, current projection, raw delta)
→ ObservationDeliveryStore                                    # sole temporal inventory/cursor state
→ ActionRecallSet                                              # complete ordered recall, no delivery veto
→ ActionDeliveryPlan                                           # immutable per-turn priorities/obligations
→ TurnPacker                                                   # bounded selection under one request profile
→ ModelTurnDelivery + DeliveryManifest                         # exact visible facts/routes/media
→ PerTurnToolCatalog                                           # Manifest routes + Store capabilities only
→ ProviderEnvelopeBinder
→ CanonicalProviderEnvelope                                    # exact messages/tools/media/settings/output
→ RequestAdmission                                             # validates/prices that same envelope
→ PydanticAI wire codec                                        # mechanical transport only
→ provider
```

The return path is equally direct:

```text
provider tool call
→ one PerTurnToolCatalog resolver row
→ SelectAction
→ Binder
→ Executor
→ dispatch receipt
→ causal stable fresh WorldObservation
```

Only `WorldObservation`, complete `ActionSpace`, `ObservationDeliveryStore`, and the existing episode `RunState` are
authoritative or stateful within their declared responsibilities. `CanonicalPublicWorldProjection`,
`PublicEffectInventory`, `ActionRecallSet`, `ActionDeliveryPlan`, `ModelTurnDelivery`, `DeliveryManifest`,
`PerTurnToolCatalog`, and `CanonicalProviderEnvelope` are immutable values or read models. They do not add a second
World, loop, planner, workflow graph, memory system, or state machine.

### Responsibilities and compression boundary

| Owner/value | One responsibility | Explicitly does not own |
|---|---|---|
| `SurfaceAdapter` → `WorldObservation` | acquire and normalize current external GUI facts with coverage/provenance | model priority, prompt compression, task semantics, action legality |
| `WorldDeliveryIndex` | derive one unnumbered structural/container/region index from that World | model refs, presentation order, continuation state, prompt selection |
| complete `ActionSpace` | enumerate current legal semantic action routes and private bindings | model visibility, ranking, pagination, execution |
| `CanonicalPublicWorldProjection` | allocate public `E/N/F/R` refs and one stable public order exactly once | legality, temporal state, prompt capacity |
| `ObservationDeliveryStore` | own current effect/local inventories, private cursors, requested scope, staleness, and cursor transitions | ranking, rendering, token fitting, tool schemas |
| `ActionRecallSet` + `ActionDeliveryPlan` | preserve complete recall and express one immutable per-turn priority/obligation plan | deleting legal routes, mutating cursors, declaring prompt admission |
| `TurnPacker` | choose bounded World/action/media records and freeze their exact route deltas under the supplied request profile | full-World truth, cross-turn state, semantic action legality, provider transport |
| `DeliveryManifest` | record the exact operand roles and routes actually delivered in text or attached media | inferring routes from refs after rendering |
| `PerTurnToolCatalog` | compile model-callable operations from the frozen Manifest and Store continuation capabilities | independent search/ranking, complete-ActionSpace scanning, cursor interpretation |
| `ProviderEnvelopeBinder` | assemble one typed physical request from admitted public parts | compression policy, action selection, provider retry |
| `RequestAdmission` | validate and price that exact envelope once | rebuilding messages/tools or applying another component cap |
| PydanticAI adapter | encode the admitted envelope and transport it | adding, filtering, reprioritizing, or reparsing semantic content |

Compression is therefore lossless with respect to Runtime reachability, not lossless in a single prompt. Complete
World facts and legal routes remain in Runtime. The model receives one bounded foreground page plus budget-fit records;
every supported omission remains behind a Store-owned continuation capability. `focus`, `viewport`, `delta`, exact
query, and same-container membership are priority signals. They never make every matching record simultaneously
mandatory. If a selected foreground inventory has a representable record, exactly one first record is required; other
records are optional current-page additions. If that one atomic foreground record plus its exact route/schema cannot
fit, the typed result is `context_capacity` with zero provider attempts.

During fitting, `TurnPacker` may call the pure Manifest/Catalog/envelope-cost projections repeatedly to price a
tentative page. Those tentative values have no identity, cursor transition, or provider visibility; only the final
frozen page enters the linear chain above. This is a bounded construction loop, not another Runtime state machine.

### Serial cutover and non-circular gates

Migration is strictly `Gate 0 → World → Delivery → Envelope → vertical conservation`. A later owner is never a
prerequisite for an earlier cutover gate:

1. **Gate 0 — test-only recorder (implemented; not closure).** A local Recording Provider/harness observes the actual current
   `ModelBackedAgentPolicy → CoreAgentLoop → provider adapter` boundary. It records but does not reinterpret the current
   physical request. It is acceptance instrumentation, not a production owner.
2. **World cutover (implemented and provider-free verified; not closure).** One canonical public projection is supplied
   to every public-ref/order consumer; displaced allocators are physically removed; canonical records, refs, public
   signature and page membership are invariant under supported private identity/enumeration changes.
3. **Delivery cutover (implemented and provider-free verified; not closure).** Store capabilities are the only cursor/continuation meaning, Plan/Packer are pure consumers,
   make Manifest/Catalog consume the same frozen page, and prove a committed two-turn zero-prefix continuation through
   the real CoreLoop.
4. **Envelope cutover.** Bind messages/tools/media/settings/output once, admit and price that object, and make the
   PydanticAI adapter consume it unchanged.
5. **Vertical conservation gate.** Only after all three cutovers, prove private-identity permutations leave the final
   recorded envelope digest/cost unchanged and every visible/callable route remains closed from World to Binder.

No failing example authorizes a local production patch. A stage may begin only after the previous stage's owner-local
production-path gate is green; closure still requires the final vertical gate and fresh held-out review.

### Per-stage cutover protocol

Every production stage above is one complete owner cutover, not a sequence of symptom patches. It uses the same six
steps:

1. **Freeze the stage surface.** Before editing production code, record the one authoritative producer, its typed input
   and output, every direct consumer, exceptional path, persistence/trace projection, old path to delete, and the
   owner-local production gate. Newly discovered consumers expand this stage's migration map; they do not receive a
   caller-side compatibility patch.
2. **Introduce the positive owner contract.** Implement the typed value/transition defined in this document. The owner
   must support the declared normal, capacity, stale, ambiguous, and unsupported outcomes before downstream migration.
   It does not special-case Run20, Run21, Task 7, `Go`, a selector, task text, or a known page shape.
3. **Migrate all consumers mechanically.** Consumers may select, render, serialize, validate, or execute only the
   supplied owner value. They cannot reconstruct its facts, keep their old fallback, or compare old/new results and
   choose whichever passes.
4. **Delete the displaced path in the same stage.** Remove the former producer, allocator, cursor inequality,
   reconstruction, sidecar, compatibility alias, and its tests/fixtures once its consumers have moved. A cutover with
   both authorities still reachable is incomplete even if tests pass.
5. **Prove the owner invariant through production orchestration.** Run generative/sequence/fault properties at the
   owner boundary and at least one Gate-0/CoreLoop production path. Negative source searches prove the old path is
   absent. Example regressions remain witnesses only.
6. **Stop at the gate.** Record the exact source revision/digest and results. Do not edit the next owner until this
   stage is green. A failure is first classified against the current stage invariant; if it exposes an unmigrated
   producer/consumer, reopen this stage instead of compensating in the caller or changing a threshold.

Cross-stage edits are limited to Gate-0 test instrumentation and mechanical import/type fallout required to compile
the active cutover. They may not change the later owner's semantics. No stage may be declared implemented while an old
authority remains reachable; no set of owner-local green gates may be called closure before vertical conservation,
held-out provider-free evidence, and fresh review agree.

### Cutover A: canonical public World projection

`WorldObservation` remains the sole current-GUI truth and complete `ActionSpace` remains the sole legality authority.
The existing `WorldDeliveryIndex` remains the structural owner, but after cutover it supplies unnumbered public
structural slots, functional containers, region membership, and stable public document/region signatures. It no longer
allocates model refs or presentation order. One observation-delivery-boundary conversion creates exactly one immutable
derivative value per fresh World:

```text
fresh WorldObservation
+ current WorldDeliveryIndex unnumbered public structure
+ complete current ActionSpace
→ CanonicalPublicWorldProjection
   projection_lineage                 # Runtime-private currentness identity
   public_document_signature          # public semantics only
   ordered_target_records             # one total public-semantic order
   ordered_fact_records               # same order algebra, multiplicity preserved
   ordered_region_records
   target_refs / fact_refs / region_refs
   target_structural_slots
   typed_public_provenance
   private target/fact/ref resolver maps
```

The total-order key may use only source-declared stable public structure: page route/title/root semantics, public
functional path and slot, source structural order when that order is itself a declared stable slot, role, normalized
label, public state, public geometry, predicate/value, modality/surface/coverage, and current legal operation/schema
shape from `ActionSpace`. It cannot use observation/source/target/fact/action/binding IDs, capture epoch, source input
enumeration, Python insertion order, or the length/value of a private identifier. Public-semantic duplicates retain
multiplicity. Equal readonly/fact records may receive occurrence refs within their equal public multiset because a
private permutation leaves the public sequence byte-identical. Two executable records that lack any stable public slot
but bind to different physical targets are not silently ordered by private identity; the projection returns typed
`public_grounding_ambiguous` before provider admission until the SurfaceAdapter supplies a supported public structural
distinction.

The projection has these invariants:

- the same public semantics and stable public slots produce byte-identical ordered records, refs, page membership,
  Manifest, Catalog, and request cost under private-ID value changes and source/target/fact/binding enumeration
  permutations;
- `E/N/F/R` allocation occurs exactly once and every consumer uses the supplied refs;
- `public_document_signature` is invariant under identity-only remount, including viewport targets; identity churn can
  leave the lossless raw delta non-empty while producing zero effect atoms and no `new_document` transition;
- `PublicEffectProjector` reconciles prior/current `CanonicalPublicWorldProjection` semantic multisets and raw-delta
  lineage; it never rebuilds its own semantic atoms or ordering from `WorldObservation`;
- the projection is a non-authoritative immutable derivative. It cannot create legality, bindings, task meaning, or a
  second World/index.

Current producers and consumers cut over as follows:

| Displaced path | Implemented cutover |
|---|---|
| `ContextBuilder` independently calls `project_model_world`, `GroundingProjection`, `_public_fact_refs`, and evidence projection | one projection-owner call; store the returned value in `AgentContext`; all later builders receive it |
| `GroundingProjection` sorts targets and allocates E/N refs | consume ordered targets and refs; retain only media mark construction against admitted refs |
| `ObservationPager` traverses `observation.targets` ordinal and fingerprints observation/target IDs | page canonical public records; bind private cursor currentness to projection lineage and order digest; expose no hashed observation ID |
| `world_projection` orders state/public-text facts by input ordinal and creates canonical private evidence refs | consume ordered public target/fact records; private `WorldEvidenceIndex` remains resolver lineage only |
| `ContextBuilder._public_fact_refs` mixes evaluator priority, World fact order, and evidence-index order | delete; evaluator priority may select or rank supplied F refs but cannot allocate or reorder them |
| `WorldDeliveryIndex._assign_public_refs` and `_document_lineage` allocate R refs and include viewport target IDs | retain unnumbered structural regions; move R allocation to the canonical projection; build document signature only from stable public page/root/source semantics |
| `PublicEffectProjector` builds its own before/after semantic atoms | consume prior/current canonical records and preserve raw delta only as private lineage |
| Actor snapshot, task projection, action paging/recall, findings, compact renderer, Manifest, Catalog, Workspace, Monitor, evaluator views | consume the same projection identity and supplied refs; none may call a ref allocator or sort raw World inventories |

Deletion is part of this cutover, not follow-up cleanup: remove production ref allocation from
`GroundingProjection.project`, `_public_fact_refs`, ordinal priority from `_public_text_fact_candidates` and state-fact
projection, raw-inventory traversal/fingerprinting from `ObservationPager`, model-facing R-ref allocation from
`WorldDeliveryIndex`, viewport/private identity from `_document_lineage`, and renderer/evaluator fallbacks that call
`canonical_fact_ref` or reconstruct public refs. `PublicRefCodec` remains a syntax codec only; private canonical
evidence refs remain internal resolver lineage and never become a presentation-order owner.

The World migration gate runs the real CoreLoop context build under (a) private-ID value permutation, (b)
source/target/fact/binding enumeration permutation, and (c) full viewport/button identity remount. The first two require
byte-identical canonical public records, refs, public order, and downstream page-membership inputs. Repository-negative
and construction-path checks prove that every old public ref/order allocator has been removed and every downstream
consumer receives the same projection value. The remount requires a lossless raw identity delta, zero public-effect
atoms, unchanged public document signature, and no `new_document` upgrade. Final Manifest/Catalog/envelope digest and
cost invariance belongs to the vertical conservation gate after Delivery and Envelope cutover; it is not a prerequisite
for starting them.

### Cutover B: delivery state

`ObservationDeliveryStore` is the sole temporal and continuation-state owner. It owns the active external-effect and
local-result inventory identities plus every private cursor transition:

```text
DeliveryInventoryKey =
  World/ActionSpace/effect-or-local-result lineage
  + obligation kind
  + deterministic order digest

DeliveryCursorState = DeliveryInventoryKey + offset

ObservationDeliveryStore =
  latest_effect
  local result inventories / active_read
  cursor states by bounded public scope
  requested_foreground_scope | None
  currentness/staleness rules
```

`ActionDeliveryPlan` becomes a pure immutable projection of current authorities plus a Store snapshot. It may contain
the current deterministic obligation records and derive one foreground, but it cannot own a cursor transition or
reinterpret continuation availability. After `TurnPacker` freezes admitted prefixes, the Store owner projects typed
`DeliveryContinuationCapability` values. Each capability carries a public `scope` and `continuation_available`, plus a
Runtime-private exact cursor transition binding used only by the resolver. `ModelTurnDelivery` freezes these
capabilities with the admitted counts. Catalog construction merely factorizes the frozen capabilities into the fixed
`read_next_page` scopes (`effect | page_directory | active_read`) and the currently present bounded action-result
scopes; it does not inspect offsets or invent its own inequality.

For every obligation the owner computes mechanically:

```text
next_offset = cursor.offset + admitted_count
suffix_exists = next_offset < inventory_size
```

If `suffix_exists`, the capability is present even when `admitted_count == 0`. Resolving a zero-prefix continuation
keeps the offset unchanged, records that scope as `requested_foreground_scope`, and returns an immutable next Store.
Only the committed local `StepResult` may install it through `Store.reduce` and `RunState.apply`. On the next turn that
eligible scope is the derived foreground and its first atomic record is required; failure to fit it returns typed
`context_capacity`. A positive admitted count advances by exactly that count. Fresh World/ActionSpace/effect/local
lineage makes all prior capabilities and cursors typed stale. Local read/search replaces only `active_read`; it cannot
clear effect or page-directory continuations.

| Current path | Cutover |
|---|---|
| Store exposes generic `cursor_offset`/`with_advanced_cursor` while Plan reconstructs cursor meaning | Store exposes typed inventory/cursor snapshot and validates/produces the only transition |
| Plan copies `requested_continuation_scope` and separately derives foreground | pure Store-backed projection; foreground rule consumes the typed requested scope without persisting plan state |
| Catalog checks `0 < admitted < len(remaining)` and resolver repeats the check | delete both interpretations; Catalog consumes frozen capabilities and resolver applies their Store-owned transition |
| separate world/action continuation bindings derive offsets | both bind the same `DeliveryContinuationCapability` algebra; only public tool vocabulary differs |
| policy/bridge carries an untyped `next_delivery_store`; non-local decisions can currently attach one | `ResolvedModelDecision` and `StepResult` admit a next Store only for the closed local continuation/read/search result algebra |

The Delivery migration gate uses the real canonical projection → Store → Plan → renderer → Packer → Manifest → Catalog
path for every obligation kind. It covers zero-prefix, exact fit, one-unit-under, and an oversized optional head followed
by a smaller group. A two-turn production sequence must show: suffix capability emitted at zero admitted; the Gate-0
Recording Provider selects it through the actual current adapter; prior Store unchanged before commit;
`CoreLoop -> Store.reduce -> RunState.apply` installs exactly one next Store; the same scope becomes foreground; one
record is delivered; concatenating all delivered prefixes and the final suffix is exactly the authority inventory in
order, without cycles or omission. Exact physical-envelope identity and complete wire cost remain Envelope/vertical
gate responsibilities.

### Cutover C: canonical physical provider envelope

One `ProviderEnvelopeBinder` owns the complete provider-bound value:

```text
ModelTurnDelivery + frozen PerTurnToolCatalog
+ public TaskGoal/GoalPlan/Workspace/history projections
+ provider profile and output contract
→ CanonicalProviderEnvelope
   instructions and ordered prompt parts
   exact tool definitions
   exact admitted media
   output contract
   provider settings
   typed public provenance per part
   canonical serialization, digest, and cost input
```

The binder accepts only typed public projections or explicitly public user/page text. Arbitrary public text is
lexically neutral and may contain strings such as `private_cursor`, `observation_id`, or `raw_delta_lineage` without
being reinterpreted. Runtime-private types and provenance—private cursors, observation/source/capture IDs, raw delta
records/lineage, binding/selector/BID/coordinate identity, and non-admitted media/routes—cannot be inserted into an
envelope part. Privacy validation checks typed visibility/provenance and structural ownership before canonical
serialization; it never substring-scans public values.

`RequestAdmission` accepts and returns this same envelope value. It verifies typed provenance, provider protocol
representability, canonical digest integrity, and complete input cost including tools, media, settings, and output
contract. Output reserve remains a separate context-window allocation: `effective_input_limit =
min(configured_input_limit, model_context_window - envelope_reserve)`, and admission requires both `input_total <=
effective_input_limit` and `input_total + envelope_reserve <= model_context_window`. The 8k soft target is likewise an
input target and never subtracts reserve again. If workspace fitting changes a public input, the sole binder creates a new envelope and Admission validates
that replacement; sidecar `component_payloads` cannot stand in for physical messages/tools. `AdmittedModelRequest` is
replaced or narrowed to an admitted wrapper around the exact `CanonicalProviderEnvelope`. The PydanticAI adapter may
construct SDK objects as a mechanical wire codec, but it must pass the envelope-owned instructions, prompt parts,
tool definitions, media, output contract, and settings without rebuilding, filtering, or adding semantic content. The
object/digest recorded at the provider boundary must be the object/digest admitted and priced.

| Current path | Cutover |
|---|---|
| `GroundedPolicyContextBinder._PolicyRequestCandidate` carries physical messages plus diagnostic `component_payloads` | replace with the canonical envelope; diagnostics are derived from it |
| `validate_provider_request_privacy` scans sidecar components, keywords, regexes, and private values | delete lexical/dynamic scanning; validate typed provenance and envelope integrity |
| RequestAdmission returns only messages/tools while media/settings/output contract remain elsewhere | return the admitted complete envelope |
| PydanticAI bridge runs `_pydantic_prompt`, creates `ExternalToolset`, appends `delivery.media`, selects output/settings after admission | move those choices into `ProviderEnvelopeBinder`; adapter is a lossless wire codec over the admitted envelope |
| transcript/diagnostic reconstructs `instructions/user_prompt` separately | record the admitted envelope canonical serialization/digest directly at the provider boundary |

The Envelope migration gate uses a local Recording Provider, never a model provider. Through
`ModelBackedAgentPolicy -> CoreAgentLoop`, it records the exact provider-bound envelope and asserts identity/digest and
cost equality with the admitted envelope. It also proves that arbitrary public TaskGoal and World text survives
byte-for-byte, that typed private provenance fails before capacity/provider, that media and tool definitions equal the
frozen Manifest/Catalog, and that neither the pre-provider capacity path nor transcript/history/Workspace/public trace
contains a private part. Only after this gate passes may a new six-page provider-free diagnostic be generated; Run30
cannot be reused.

## Target end-to-end data flow

The normative World-to-provider prefix is defined once above. The complete episode loop adds task input, execution,
evaluation, and durable finalization around that same prefix:

```text
User request
→ TaskGoal
→ GoalCompiler exactly once at start/revision → optional static advisory GoalPlan
→ one continuous CoreAgentLoop
    fresh WorldObservation
    → WorldDeliveryIndex + complete ActionSpace + lossless PublicWorldDelta
    → CanonicalPublicWorldProjection → PublicEffectInventory → ObservationDeliveryStore
    → ActionRecallSet → ActionDeliveryPlan → TurnPacker
    → ModelTurnDelivery + DeliveryManifest
    → PerTurnToolCatalog
    + TaskGoal + GoalPlan + bounded AgentWorkspace/history + provider/output profile
    → ProviderEnvelopeBinder → CanonicalProviderEnvelope
    → RequestAdmission → PydanticAI wire codec → provider
    → exactly one typed ActionPolicy decision
       - GUI decision: exactly one current action route → Resolver → Admission → Binder → BrowserGym Executor
                       → ExecutionReceiptBatch → causal stable fresh WorldObservation
                       → WorldTransitionProjector → StepResult
       - local observation: typed discovery/read result → ObservationDeliveryStore → StepResult, zero GUI routes
       - AskUser: typed waiting-user StepResult, zero GUI routes
       - final response: current-lineage admission → environment FinalResponseCodec
                         → canonical native content or typed final_response_invalid before STOP
    → RunState.apply + total WorkspaceReducer + fixed-size EpisodeMonitor update
    → TaskEvaluator + deterministic ordinary/recovery control
→ canonical admitted final response → one STOP → fresh acquire → native evaluator
→ immutable OfficialOutcomeCheckpoint when evaluated
→ typed CaseOutcomeRecord referencing that checkpoint → durable store
→ unconditional outer finally: clean an acquired environment once, or record NOT_ACQUIRED/NOT_APPLICABLE
→ fallible rich report projection, isolated from cleanup
→ monotonic FINAL record with report disposition
→ optional JSON/viewer materialization from the durable store
```

There is one BrowserGym session, one current World authority, one ActionSpace, one Binder, one executor, one
TaskEvaluator/native-verifier authority, and one mutable episode transition point. Projections are read models, not
alternative control paths.

## Causal post-action observation boundary

`WorldObservation` freshness has two independent dimensions: it must be newly acquired, and it must belong to the
stable causal post-state of the dispatched action. BrowserGym returning from a click and producing an observation does
not by itself establish the second fact. Playwright distinguishes navigation request/start, main-frame commit, and
DOMContentLoaded; actionability and action completion do not close an arbitrary delayed navigation.

The BrowserGym/Playwright owner thread therefore owns this closed state algebra; its current-tree acceptance gate
remains open:

```text
STABLE_NO_NAVIGATION
STABLE_NAVIGATION
NAVIGATION_PENDING
ACQUISITION_UNSTABLE
```

Before dispatch it installs main-frame navigation and document-mutation observers and records URL/document epoch.
Browser-native link and form-submit controls receive a bounded navigation-start lease. A mechanically non-navigation
control skips that lease. When navigation starts, the same step waits boundedly for main-frame commit,
DOMContentLoaded, and a short DOM-quiet predicate before a fresh `_get_obs` capture. No fixed long sleep is an
authority. `NAVIGATION_PENDING` and `ACQUISITION_UNSTABLE` carry no post observation, fail post-action acquisition, and
therefore cannot start another ActionPolicy turn.

The owner emits, and trace only forwards, `dispatch_started`, `dispatch_returned`, `navigation_started`,
`navigation_committed`, `post_capture_started`, `post_capture_completed`, before/after URL, before/after document
epoch, and stability status. Neither CoreLoop, Monitor, nor trace may reconstruct these facts from adjacent steps.

This contract follows the current Playwright navigation lifecycle and event-waiting model; Playwright explicitly
separates commit/load states and warns that time-based waits can observe stale state. BrowserGym's upstream fixed
`pre_observation_delay` remains a compatibility delay, not causal proof.

## Authority and owners

| Fact or transition | Sole owner | Non-owner rule |
|---|---|---|
| user intent | `TaskGoal` | plans may describe but never replace it; compiler/context projections cannot filter an admitted public fact by key spelling |
| current GUI truth | fresh `WorldObservation` | no downstream DOM/AX re-interpretation |
| source-inventory coverage | SurfaceAdapter `EntityInventorySummary`/coverage facts | World, discovery, and search may preserve or narrow coverage but never upgrade partial/truncated to complete |
| public transition between two Worlds | `WorldTransitionProjector` | ActionOutcome, Monitor, delivery, history, and trace consume one delta rather than rebuilding it |
| model-facing public effect inventory | deterministic `PublicEffectProjector` inside the observation-delivery boundary | it reconciles raw identity churn against before/after public semantic atoms; renderer, action recall, Workspace, and Monitor consume the result rather than interpreting raw target identity changes |
| currently legal semantic actions over the admitted World | complete `ActionSpace` | rendered text and model output cannot authorize actions; source-partial acquisition cannot imply page-wide absence |
| unnumbered public functional context | the existing `WorldDeliveryIndex` | region formation and container grouping consume the same fields; it does not allocate model refs/order or create another World |
| public records, `E/N/F/R` refs, and public order | one immutable `CanonicalPublicWorldProjection` | Grounding, findings, pager, effects, renderer, Manifest, Catalog, Workspace, and evaluator views consume it and never sort raw World inventories or allocate refs |
| current action recall inventories | `ActionRecallSet` over complete `ActionSpace` + canonical public projection + active Store effect | ranking may order but cannot delete exact/structural/base/effect members or claim that recall membership requires simultaneous delivery |
| per-turn delivery selection | stateless `ActionDeliveryPlan` | bounded obligations and cursors select candidates for packing; only records actually admitted by `TurnPacker` become protected |
| active latest external GUI effect and local-result delivery state | `ObservationDeliveryStore` | World rendering, action recall, Workspace, and Monitor consume the same effect identity; a local read/find/search cannot clear or fork it |
| final model-turn payload and delivered action-route relation | deterministic `TurnPacker` producing atomic `ModelTurnDelivery` | renderer fragments and actual image marks carry route deltas at creation; post-hoc ref scans, ToolCatalog, history, and trace cannot infer or add a route |
| model-facing current-run continuity | total `WorkspaceReducer` producing `AgentWorkspace` | raw history, provider messages, and trace cannot become a second workspace |
| whole-request capacity | `RequestAdmission` | `TurnPacker` consumes its profile/estimator to fit one candidate request; RunState, history projection, renderer, pager, catalog, and provider Binder cannot own independent caps |
| finite public JSON-Schema subset | existing `actions.schema_validation` contract validator | ToolSpec, capability schemas, catalog compiler, normalizer, value validator, and final-response admission consume the same supported AST; JSON-tree validity alone is not schema admission |
| model-visible action contract | `PerTurnToolCatalog` compiled from frozen Manifest routes + Store continuation capabilities | it cannot scan complete ActionSpace, rank controls, or derive cursor inequalities |
| physical provider request | `ProviderEnvelopeBinder` producing one `CanonicalProviderEnvelope` | RequestAdmission validates/prices it and the provider adapter transports it; neither reconstructs semantic content |
| private physical binding | Binder | model never submits selector, BID, or coordinates |
| physical dispatch truth | `ExecutionReceiptBatch` | projection cannot reconstruct or overwrite receipts |
| episode transition | validated `StepResult` through `RunState.apply` | history, monitor, trace, and benchmark only consume committed state |
| Runtime control termination | typed `ControlTermination` committed with `StepResult`/`RunState` | display feedback and benchmark classification cannot infer `control_stalled`, budget exhaustion, or abort reason |
| advisory goal decomposition | start/revision-only `GoalCompiler` | `GoalPlan` is static guidance and has no progress state |
| operational recovery | deterministic `EpisodeMonitor` + same `ActionPolicy` | monitor signals cannot claim task semantics |
| benchmark completion | native `TaskEvaluator` after one delivered STOP | policy and final response cannot self-certify |
| durable official evaluator outcome | immutable `OfficialOutcomeCheckpoint` written at the evaluator boundary | CaseOutcome/report records reference its id+digest and cannot duplicate or alter official status |
| case behavior outcome | typed `CaseOutcomeRecord` made from Runtime/harness owner facts and an optional official-checkpoint reference | rich report schemas, cleanup, export, and detached-status views cannot rewrite it |
| local trace | synchronous JSONL recorder with typed integrity disposition | write/seal failure invalidates benchmark evidence but cannot throw across Runtime/finalizer control or skip cleanup; remote viewers are lossy and fail-open |
| benchmark result | durable result store | cleanup/export cannot erase or revise it |

### Run20 causal model and convergence decision

The two Run20 failures share one mechanism: a projection that should only select, order, validate, or serialize owner
facts was allowed to veto them. In the action path, a lexical ranker decided whether a legal control existed in model
delivery. In the reporting path, a copied benchmark vocabulary decided whether an already committed Runtime terminal
fact was allowed to reach persistence and cleanup.

The repository review found a third reachable instance of the same older pattern: TaskIntake, GoalCompiler request
projection, and the downstream `AgentContext.task` projection remove otherwise public TaskGoal mappings whose keys
happen to be named `coordinates`, `selector`, `x`, or similar. Those privacy-by-name filters can erase legitimate
business inputs from planning or policy even though GoalPlan output is already non-authoritative. They are part of this
convergence scope, while the removed MilestonePlanner rejection remains historical only.

Two conservation invariants replace per-witness fixes:

```text
Legal-action conservation
complete admitted action-bearing source inventory (or typed no-World capacity failure)
→
current legal binding
→ complete ActionSpace option
→ finite discoverability route for its current public ref
→ exact model delivery + DeliveryManifest `(operation, ref[, destination])` admission
→ PerTurnToolCatalog schema admits exactly that route
→ Resolver/Binder can consume the same option

Terminal-outcome conservation
committed Runtime or harness terminal facts
→ typed CaseOutcomeRecord
→ durable store
→ rich case projection or typed HARNESS_PROJECTION
→ acquired cleanup attempted exactly once, or typed NOT_ACQUIRED/NOT_APPLICABLE
→ reconstructable case/run status
```

The repository-wide defect classes and owner changes are:

| Class | Current defect | Convergence change |
|---|---|---|
| architecture | recall and ranking are one function; report projection precedes mandatory cleanup | high-recall discovery precedes non-authoritative ranking; durable terminal record precedes rich projection; cleanup is structurally unconditional |
| open contract | exact label, short/Unicode labels, functional neighbors, false-positive queries, and search continuation have no reachability guarantee | bounded discoverability contract with exact-label inclusion, structural inclusion, additive search, and lossless inventory continuation |
| duplicated truth | form semantics are guessed separately from AX roles; Monitor diagnostics and control reasons become display strings while benchmark copies second vocabularies | one typed functional-context projection; typed Monitor diagnostics and `ControlTermination`; one exhaustive owner-to-report codec |
| over-strict semantic admission | TaskIntake, GoalCompiler, and TaskContext projections guess privacy from ordinary mapping key names | TaskGoal/TaskIntake owns typed visibility; both compiler and ActionPolicy context preserve every admitted public field, while the GoalPlan output schema remains the only plan boundary |
| projection integrity | renderer can add refs to `DeliveryManifest` before the corresponding text survives byte admission; screenshot marks are not reconciled with the manifest | text/image payload and manifest commit atomically from the final admitted fragments |
| verification | long-label examples and normal report construction pass while reachable short-label and projection-fault sequences are absent | generated conservation, state-sequence, and fault-injection properties across all owners and consumers |
| documentation/governance | historical pass counts and removed Planner wording can be read as current closure | current status lives only here and in `benchmark.md`; historical checkpoints remain explicitly scoped |
| environment/provider | neither caused Run20 | retain the separate causal-navigation gate and provider failure algebra; do not patch either for this witness |
| intentionally strict boundary | Binder currentness, Monitor stall termination, and closed report schemas correctly fail closed | preserve strictness, but source legal values from one owner and make unsupported projection total and typed |

This does not add a workflow graph, mission ledger, event-sourcing system, or another Agent loop. Discovery is a pure
per-World projection. Finalization is one linear `try/finally` protocol. The only persistent control state remains the
existing bounded Runtime state plus the small operational repetition Monitor; benchmark lifecycle phases are durable
diagnostics, not a second control machine.

## World delivery and discovery

The complete current World remains authoritative. Model delivery is a reversible, change-first projection, not
destructive memory. This replaces the prior design in which every turn rebuilt a page projection and ranked a global
pool of public scalar facts using task/plan lexical similarity.

This is the World/delivery slice of the normative chain; it introduces no alternative projection order:

```text
BrowserGym raw observation
→ SurfaceAdapter
→ fresh WorldObservation
   ├→ one WorldDeliveryIndex with unnumbered structure/containers/regions
   ├→ complete current ActionSpace
   └→ lossless PublicWorldDelta against the preceding fresh World
→ one CanonicalPublicWorldProjection with all public records/refs/order
→ one reconciled PublicEffectInventory
→ ObservationDeliveryStore inventories and private cursors
→ ActionRecallSet complete ordered recall
→ immutable ActionDeliveryPlan obligations and one foreground
→ TurnPacker
→ atomic ModelTurnDelivery + DeliveryManifest
→ PerTurnToolCatalog from admitted routes and Store continuation capabilities
```

### Run3 World-delivery inflation: causal model

Run3 did not show growth in the authoritative World or failure of structural deduplication. Comparing the earlier C8
W1b-World artifacts with `evidence/w1b-world-c10-c11-provider-free-20260823-run3/` shows that comparable pages retain
the same public facts, approximately the same World serialization, and the same ActorWorld node-collapse counts. The
growth occurs only in the final model-facing selection:

| task | World facts old → run3 | compact rendered bytes old → run3 | request `actor_world_tokens` old → run3 | delivered `E/N/F` old → run3 |
|---:|---:|---:|---:|---:|
| 0 | 825 → 825 | 10,076 → 16,247 | 3,574 → 5,744 | `16/52/116 → 24/69/176` |
| 7 | 438 → 438 | 9,566 → 20,335 | 3,371 → 7,194 | `12/6/54 → 30/86/251` |
| 21 | 1,059 → 1,059 | 10,232 → 29,724 | 3,563 → 10,415 | `6/17/33 → 25/125/340` |
| 27 | unchanged | 8,955 → 8,857 | 3,180 → 3,154 | effectively unchanged |
| 266 | unchanged | 11,820 → 11,712 | 4,200 → 4,164 | effectively unchanged |

Task 7 is the clearest cut: the internal World remains about 1.60 MiB, the supported-public ActorWorld snapshot remains
about 89 KiB, but final text grows from 9.6 KiB to 20.3 KiB. Internal indexes are not provider input; the regression is
therefore not “the World became larger.” Existing suppression of aligned duplicate targets, `InlineTextBox`, empty
generic wrappers, parent/child duplicate text, and repeated public refs still operates. The final view instead admits
many additional *distinct but irrelevant* siblings and facts.

The current causal chain is:

```text
same lossless World and structural deduplication
→ more accurate functional-region partition
→ objective rerank chooses one leading candidate
→ leading candidate implicitly selects its whole region
→ renderer expands every distinct sibling/fact in that region
→ old independent 10 KiB renderer guard is absent, but no joint packer has replaced it
→ ModelTurnDelivery, manifest refs, relational ToolCatalog, and request cost grow together
```

This failure is page-conditional: adding one small region may cost nothing material, while selecting one large
functional/generic region can double or triple delivery. It is not caused by DeepSeek tokenization, history growth, or
VLM media; the compared diagnostics use the same estimator and zero image tokens. JSON/provider-envelope accounting
adds a stable overhead after text rendering, but does not explain the old-to-new ratio.

### Bounded semantic delivery: authority, recall, page, and recovery

Compression is not deletion from Runtime truth or reachability. The complete supported `WorldObservation`, complete
legal `ActionSpace`, and lossless `PublicWorldDelta` remain owner facts within their declared acquisition bounds. The
existing `WorldDeliveryIndex` and `CanonicalPublicWorldProjection` remain Runtime-only derived indexes/values over
those facts. Model input is a bounded read model. Four collections must remain distinct:

1. **Authority inventory** — every current supported public fact, structure record, legal action route, route issue,
   and source-coverage disposition. Cardinality may be large; none is model input merely by existing.
2. **Recall inventory** — deterministic unions for exact query, current focus, functional-container neighbors,
   viewport, the reconciled latest public effect, changed values/actions, base inventory, and route issues. Recall is high-recall
   indexing, not a delivery promise and not a legality decision.
3. **Current delivery page** — the finite records selected under the actual complete-request budget for this model
   turn. Only records on this page become protected against later reranking, rendering, manifest, or catalog loss.
4. **Recovery surface** — generation-local private cursors plus model-visible bounded continuation scopes and local
   read/find tools that enumerate every omitted supported record in finite, non-cyclic pages without changing authority
   or erasing the base inventory.

Recovery reuses the existing stable local operations rather than registering one tool per record or obligation. The
Runtime-owned cursor is opaque, generation-local, bound to owner lineage/kind/order/offset, and never enters prompt or
tool arguments. The model sees only `continuation_available` and a bounded public scope:

- `read_next_page` continues `effect`, `page_directory`, or `active_read`. With one live scope it has no arguments;
  with two or three it exposes only the currently live values in a maximum three-value dynamic `scope` enum. `effect`
  resumes the active latest-effect evidence/tombstone page; `page_directory` enumerates the current World's bounded
  PageOutline/RecoveryDirectory so a region ref omitted from the first directory page can become known; `active_read`
  resumes the current `read_region`/`search_page_content` lens.
- `read_region(R*)` selects a current region and starts/replaces `active_read`; `search_page_content` does the same for
  its result inventory. Neither replaces `effect` nor `page_directory`, so either can resume after a local read.
- `action_results_next_page` continues one live action-obligation scope selected from a small dynamic enum such as
  `base | query | interaction | effect_actions | issues`.

These enums are bounded by obligation kinds, not inventory size. Catalog bindings map the public scope to the private
cursor, so the model never receives a private target/action/binding ID or cursor. A fresh World makes all prior cursors
stale; a foreign/mismatched internal cursor returns typed `stale_cursor`/`stale_catalog` before any provider or GUI
dispatch and cannot be normalized into the new lineage.

This yields the positive compression invariant:

```text
complete Runtime authorities
→ high-recall ordered inventories
→ bounded delivery obligations with cursor-backed remainders
→ TurnPacker selects atomic current-page records under the one request budget
→ selected records are frozen/protected
→ one ModelTurnDelivery + exact Manifest + exact ToolCatalog
```

`ActionDeliveryPlan` is a pure immutable projection for one fresh World and one local-view lineage. It does not persist
task progress or introduce another state machine. Instead of global `mandatory_fragments`, it contains a bounded fixed
shell and ordered `DeliveryObligation` groups. A delivery obligation has:

```text
kind
authority lineage (World / ActionSpace / latest-public-effect / local-result identity)
deterministic ordered atomic records
foreground priority
private current cursor + public continuation scope
source/result coverage and omission disposition
public provenance needed to interpret each record
```

Here “public provenance” is bounded semantic provenance only: surface kind, modality, declared source coverage, and
public structural context needed to interpret the record. Observation IDs, source-record IDs, UUIDs, capture epochs,
private target/action/binding identities, and their lengths are private lineage. They remain in Runtime/Trace and never
enter a model fragment, Workspace/history item, public result, Manifest, catalog schema, or capacity weight.

The complete ordered records may stay in Runtime behind a cursor; they are not copied into the plan's rendered text.
The plan stores one derived `foreground_scope | None`, not a mutable `minimum_progress` flag on every obligation.
Obligation kinds are a closed, bounded protocol family—current explicit query/continuation, active public effect,
current interaction neighborhood, base actions, region/evidence recovery, destination routes, and route issues. The
plan creates at most one group per kind/current explicit lens, never one group per changed target, fact, region, or
action. At most the current foreground obligation requires one record when matching records remain. Other groups
expose a bounded directory entry and continuation scope and may contribute as budget permits. Foreground is determined
mechanically, in this precedence order, not from task-specific text:

- the local operation that produced the current view: explicit `find_controls`/action continuation or explicit
  `read_region`/content-search continuation;
- otherwise the active external GUI effect's exact evidence page;
- otherwise the current interaction-neighborhood/base page on an initial or ordinary view.

Non-foreground groups are still ordered: current interaction-neighborhood actions precede base/semantic actions after
an external effect, so field-to-sibling routes are normally delivered without making the whole container compulsory.

There is no rule that every group must contribute one record simultaneously. The foreground is the highest-precedence
obligation that still has an undelivered supported record. Required progress is mechanically one record when that scope
exists and zero when every eligible inventory is empty. There are no kind-specific exceptions. Remaining groups stay reachable. If that
one required atomic record plus its route/schema cannot fit, the owner returns typed `context_capacity`. Large
collection cardinality alone is never an irreducible shell. A typed empty/miss result belongs to the bounded fixed
shell and does not fabricate a record merely to satisfy progress.

Protection is therefore post-selection. Once `TurnPacker` admits an atomic record to the current page, reranking,
rendering, Manifest construction, and ToolCatalog factorization must preserve it exactly. Before packing, `exact`,
`focus`, `same_container`, `viewport`, and `delta` are typed recall reasons and ordering signals; none converts every
matching member into an unbounded protected prompt fragment.

This retains useful semantic promotion without sacrificing reachability. Each inventory has a deterministic public
base order. Exact query hits and the active causal/focus neighborhood form its leading strata; source semantics,
TaskGoal/static GoalPlan relevance, recent public outcomes, and an optional stateless model/VLM-derived **World
evidence** score may reorder only the remaining tail. The ordered inventory is then paged, never truncated as truth.
If an optional reranker is unavailable, deterministic structure/order remains; if it succeeds, it can bring useful
records forward but cannot remove a record, change legality, invent a route, or bypass the cursor. No extra reranker
call is required by the baseline.

### Model-facing effect view versus diagnostic delta

`PublicWorldDelta` is the one lossless typed account of supported public additions, removals, and modifications with
before/after lineage. Navigation or framework remount may legitimately renew many target identities. Raw target/fact
added/removed counts, identity-renewal counts, digest churn, and region-member totals are useful to Runtime diagnostics,
packing telemetry, and private Trace. They have no task meaning by themselves and are not serialized into the model
prompt. In particular, diagnostic values such as `targets added=167/removed=139` or `facts added=496/removed=440`
must never appear merely because a delta is large. The same rule excludes full `LatestEffect count`, changed-region
`members=<total>`, RecoveryDirectory member totals, whole-inventory `omitted_count`, and repeated source-instance strings
such as `browsergym-observation:<uuid>:<n>` from the prompt. A bounded
directory row contains only public region identity/label/role, `continuation_available`, and its current scope. The
private Trace retains the full totals for diagnosis.

Hiding those counts is insufficient: identity renewal must not reappear as hundreds of apparently meaningful effect
records. The observation-delivery boundary owns one deterministic `PublicEffectProjector`:

```text
lossless identity-based PublicWorldDelta
+ before/after supported-public snapshots
+ prior/current existing WorldDeliveryIndex public structural slots/order
→ PublicEffectInventory
   - typed transition header
   - current added/modified target/fact semantic atoms
   - ref-free removed tombstones
   - current changed-target public structural-slot keys for an ActionSpace join
   - semantically changed public regions
```

The projector is a read-model conversion, not another World/change authority. It first serializes before/after public
semantic atoms without generation refs or private IDs. An atom contains its public kind, source-provided functional
container/path/role/label, predicate and canonical public value; duplicates retain multiplicity. It then:

1. cancels the exact multiset intersection, so byte-identical public content remounted under new identities is not a
   model-visible change;
2. pairs different values as `modified` only when the source supplies the same stable public structural slot and
   predicate;
3. emits residual after-atoms as `added` and residual before-atoms as ref-free `removed` tombstones;
4. preserves deterministic before/after public order and multiplicity; ambiguous atoms remain explicit add/remove
   records rather than being guessed as the same entity.

This reconciliation never changes canonical target identity, current refs, binding/currentness, `PublicWorldDelta`, or
ActionSpace. It is a small deterministic projection inside the existing observation-delivery owner, not a semantic
judge, learned deduplicator, second index, or new lifecycle state. `ObservationDeliveryStore.latest_effect` stores the
resulting `PublicEffectInventory` identity alongside the raw delta lineage. Model-facing effect pages and
effect-derived action recall consume this exact same inventory.
The projector does not infer action operations, schemas, bindings, or route legality. `ActionRecallSet` joins current
changed-target structural-slot keys to the complete current `ActionSpace` and may prioritize the matching legal routes;
it does not use raw `WorldDeliveryIndex.delta_membership` as a delivery reason and never makes a removed tombstone
executable. A route-contract change with no target/fact semantic change is still finitely reachable through the complete
base inventory; detecting it as effect-salient would require an ActionSpace-owned typed delta and is outside this
projection. Trace records both the lossless raw delta and the reconciled effect inventory so false cancellation or
residual noise is observable.

The model sees a deterministic bounded `EffectHeader` derived from existing typed public facts and the action receipt,
followed by a bounded exact evidence page. Header region labels are only those represented on the current admitted
effect/directory pages; the header never enumerates the full changed-region inventory:

```yaml
LatestEffect:
  action: press Enter in "Search"
  dispatch: sent
  transition: navigation_completed
  page: "OpenStreetMap"
  current_query: "international airport"
  current_scopes: ["Search Results", "Search Form"]
ChangedEvidencePage:
  continuation_available: true
  next_scope: "effect"
  items:
    - <exact current public result/value records>
```

The header is not a semantic judge and does not infer task completion, business entities, or whether a result is
correct. It uses only declared action kind, dispatch receipt, public page identity, source-provided region labels/roles,
and typed transition kind. When the Runtime can establish only a document replacement, it emits
`transition: new_document`; it does not narrate raw churn as meaning. `continuation_available` and `next_scope` define
recovery without repeating a page-item count the model can already observe. Full churn, inventory, and omitted totals
remain private unless a count is itself a public source-provided business fact, such as a user-visible result total.

Exact changed values are not summarized by another LLM. They are deterministic atomic records, ordered by public
structure and declared source semantics, then paged. Result/status/table cells, selected values, identifiers, amounts,
dates, and full address strings may receive higher delivery priority than decorative DOM facts, but Runtime does not
split an address into inferred fields or claim a task constraint is satisfied. Folded evidence remains finitely
recoverable through the `effect` continuation scope or a selected region's `active_read` scope.

Removal is first-class public effect semantics rather than an absent current node that downstream code silently loses.
The active effect inventory contains typed `added | modified | removed` records. Added/modified records may carry
current generation refs. A removed target/fact is a ref-free tombstone containing only its prior public
label/role/functional path or predicate/value, public provenance, `change=removed`, and `current=false`. Tombstones are
paged through the same `effect` scope and may be retained as bounded SemanticEvents, but they never enter current
ActionSpace, Manifest, ToolCatalog operands, Binder, `remember_fact` refs, or evaluator evidence refs. Thus the model
can observe that a dialog/result/value disappeared without receiving a stale executable/evidence ref.

`RegionVersion` remains part of the existing `WorldDeliveryIndex`, not a second region system. It supports unchanged
region reuse and changed-region rebuilding. The first changed-region page is bounded; a large region never becomes a
whole-prompt obligation. Page outline and recovery-directory views are themselves bounded and cursor-backed, so a page
with many regions cannot create another fixed-shell fan-out.

`ObservationDeliveryStore` is the single temporal owner of the active latest external GUI effect. Both the model-facing
World effect view and action recall consume that same stored effect. Local operations such as `read_region`,
`search_page_content`, and `find_controls` may produce their own typed local result but do not clear, reconstruct, or
fork the external effect. The next external GUI effect supersedes it. `last_step.public_world_delta` from a local
same-World operation is not allowed to erase delta-derived recall while `LatestEffect` still presents the prior GUI
change. Workspace and Monitor consume the Store's same `DeliveryTransition`/`InformationDelta`; neither recomputes it.

The default bounded view contains a compact page identity, one effect header when present, a bounded exact evidence
page, a bounded current-interaction action page, a bounded functional PageOutline/RecoveryDirectory page, and public
continuation scopes backed by private cursors for omitted material. Large repeated siblings, boilerplate, duplicate
parent/child text, decorative state, and inactive
content remain folded. The guarantee is recoverability and atomic public semantics—not simultaneous presentation of
every recalled or changed item.

### Functional context and action discoverability

Run20 proved that the same rule must apply to actions: a relevance score may order legal options but may not decide
whether an option remains discoverable. The fresh World contained `From`, `To`, `Go`, and `Reverse Directions` as
siblings. Their common AX node had role `Section` and public DOM tag `form`; the current RegionIndex recognizes only an
AX role literally equal to `form`, while `set_form_fields` repeats a separate role-only check. The form was therefore
folded into a 657-member generic region, its empty-label ancestor disappeared from functional paths, and the physical
and tree adjacency never reached action ranking.

This was not physical occlusion: `Go` already had current executable bindings in the fresh World. “Not delivered to
the model” is a discoverability/projection failure; Playwright visibility, stability, hit testing, and obstruction are
executor actionability checks that begin only after a current public ref is selected and bound. These failure classes
must remain separately observable.

The structural projection extends the existing immutable `WorldDeliveryIndex` for each fresh World; it does not create
a parallel `FunctionalContextIndex` or perform a second structure traversal. The index normalizes only source-provided
public structure, for example AX `form` or public `semantic.dom.tag=form`, into a typed bounded
`FunctionalContainerKind` such as `form | search | dialog | navigation | table | list | region | generic`. It also
retains public parent/child slots, nearest container, current focus, and viewport visibility. It owns no public ref,
presentation order, raw/effect delta membership, cursor, or prompt selection. `CanonicalPublicWorldProjection`
consumes these structural slots once; effect priority is joined later from `ObservationDeliveryStore.latest_effect`.
The index does not infer task completion, form purpose, or which button the user ought to press.

Fusion may align equivalent structural targets from multiple SurfaceObservations to one canonical target. The same
`WorldDeliveryIndex` assigns that canonical target to exactly one deterministic primary structural region and retains
secondary equivalent-source provenance as context; it never inserts the target into one region per source. Primary
selection uses declared source/public structural priority and stable public signatures, not source input order or
private IDs. Permuting equivalent sources therefore leaves region membership, functional path, presentation order,
and action routes unchanged while preserving their lineage.

The target discovery path is:

```text
complete current ActionSpace
+ current CanonicalPublicWorldProjection records/refs/structural slots
+ ObservationDeliveryStore.latest_effect       # the active reconciled public effect
+ ObservationDeliveryStore cursor snapshots
→ ActionRecallSet                               # complete high-recall inventories, Runtime-only
   - normalized exact accessible label/role/operation
   - current viewport controls
   - same-container and recent-focus neighborhood
   - current legal routes joined from active-effect changed-target slots into complete ActionSpace
   - lossless base-inventory cursor
→ ActionReranker                         # ordering only; cannot remove inventory members
   - TaskGoal/static GoalPlan
   - public label/path/container/state
   - recent public outcomes and repetition penalty
   - optional stateless model/embedding score over public World facts
→ immutable ActionDeliveryPlan
   - bounded fixed shell
   - ordered DeliveryObligation groups
   - independent base/query/effect/container/issue cursors
→ TurnPacker
   - greedily admits atomic current-page records under the complete request budget
   - freezes admitted records; leaves every remainder behind its cursor
→ atomic text/image ModelTurnDelivery + DeliveryManifest
→ PerTurnToolCatalog from Manifest routes + frozen Store continuation capabilities
```

`ActionRecallSet` is a union, not a classifier decision, delivery page, or capacity promise. Objective/semantic scoring
may reorder records within a declared inventory but cannot delete exact or structural members or alter the cursor's
finite enumeration. One declared public-label/query contract covers every label admitted by the SurfaceAdapter (the
current BrowserGym bound is 240 characters). Unicode NFKC/casefold normalization preserves each complete bounded
label, including one- and two-character labels and punctuation-only labels with an exact public string. Discovery
accepts at least that same bound and never silently slices a query to 120 characters; an over-bound label/query fails
typed before matching. When a bounded natural-language query contains a complete label span, extra intent words may
improve ordering but cannot cancel that exact-label recall. Lexical overlap, stemming, fuzzy matching,
four-character prefix/suffix fragments, task similarity, risk, and history are ordering signals only.

Base inventory, query results, and automatic candidates are not four competing projections. The discovery owner
creates one `ActionDeliveryPlan` over the complete ActionSpace. A query's complete ordered result remains internal and
recoverable by its cursor. Exact matches form the head of the query obligation and semantic false positives follow as
lower-priority records; neither collection is copied wholesale. `top_k=None` is not permission to put a whole query
page in the prompt. When an explicit query is the foreground obligation and matches exist, packing must deliver at
least its first exact/structural atomic record or return typed capacity; after admission, that current-page record is
protected. False positives cannot replace exact hits or remove the base-inventory continuation.

Here and below, a “finitely recoverable legal route” is a current legal route whose one atomic public route and
parameter-schema representation fits the declared active provider/RequestAdmission profile. A legal route that exceeds
that atomic representability bound remains in complete ActionSpace and, when it becomes the required foreground
record, returns deterministic typed `context_capacity` with the offending component. It is never reported absent or
silently dropped. Source/action-schema bounds should make this exceptional rather than creating another delivery cap.

The generic field-to-submit sequence is therefore bounded without losing `Go`-like controls:

```text
fresh World identifies focused field + typed functional container
→ complete same-container route inventory remains in Runtime
→ current-interaction obligation orders the focused field and sibling actions by public tree/operation order
→ TurnPacker delivers the budget-fit first page and a continuation
→ exact find_controls("Go directions route") builds a separate exact-first query obligation
→ normalized complete label span "Go" is first-page recall even though it has two characters
→ admitted E-ref/route enters Manifest and ToolCatalog, then Resolver/Binder owns execution
```

The literal label is a historical witness only. The contract is generated over short/Unicode/punctuation labels,
different containers, page-tail placement, and arbitrary sibling cardinality. It neither reserves a `Go` branch nor
requires every sibling to be present simultaneously.

Action recall is complete only relative to an admitted action inventory. The BrowserGym SurfaceAdapter must either
project every recognized supported control and its bindings into the internal World/ActionSpace inventory or return a
typed acquisition-capacity failure with no actionable World. It may not retain the first 512 controls and let
downstream search infer that omitted controls do not exist. Read-only facts/structure may remain explicitly partial,
but their existing `EntityInventorySummary`/coverage and omitted counts propagate unchanged into delivery and search;
an exact miss under partial source coverage is `source_partial/unknown`, never authoritative `no_matches` or
`source_coverage=complete`.

The same conservation rule applies inside one control. One shared option-domain bound is consumed by BrowserGym
projection, interaction capability/schema validation, ActionSpace, and ToolCatalog. A select whose complete public
domain is within that bound retains every option and a current `select_option` binding; a larger domain remains visible
with typed `option_domain_capacity/unsupported` and non-complete action coverage. The adapter may not accept 12 schema
items, attempt 16, retain 512 as state, or silently omit a binding for 17–512 options. Full admitted domains are folded
or paged only in model delivery; legality and resolver validation remain lossless internally.

Destination-required actions use the same route inventory rather than a second per-option truncation. Every legal
`(operation, source, destination)` tuple is one public route record in the complete ActionSpace, or source acquisition
fails typed before exposing an actionable partial World. Delivery pages those records with the same
RequestAdmission allocation and cursor. `max_destinations_per_option=16` cannot truncate/underestimate the page while
a later candidate or catalog path restores the full destination set; the pager estimate and final manifest/catalog
range over the same records.

`ActionSpace` also owns public-route uniqueness before delivery. Bindings from aligned sources with the same
`(operation, source, destination)` selector and byte-identical public parameter/effect/barrier/verifier contract merge
behind one route. If those contracts differ, the owner emits typed `action_route_conflict`, exposes the target and its
why-not fact, and publishes no ambiguous route; it never sends two apparently legal rows with the same public selector
to fail later as `catalog_invalid`. The baseline does not add a new public discriminator merely to preserve a
conflicting source projection.

The default page is ordered by public structure and target-group presentation, not opaque private target hashes.
Multiple legal action variants for one target are grouped into one public target record with its supported verbs; the
private action IDs remain available to Resolver. Score ties use public source/tree/viewport ordinal and a declared
action-variant ordinal. Because current action IDs include observation identity, they are identities only and cannot
influence presentation order across equivalent fresh Worlds. Search is additive: an active query may put its matches first, but it
does not replace the base inventory or remove the base/search continuations. Therefore every legal option has a finite
route into a current manifest through at least one of default delivery, exact-label lookup, structural-neighborhood
delivery, or lossless inventory paging. Empty accessible labels remain reachable through typed role/operation,
container context, or inventory browsing; the Runtime must not claim semantic completeness when none applies.

`ActionPager` does not own a shadow 24 KiB capacity decision. `RequestAdmission` supplies the action-delivery
allocation; paging measures the actual public target/verb/destination records that can enter `ModelTurnDelivery`, not
private action/target IDs, full internal schemas, or descriptions that are rendered elsewhere. A count limit may remain
as a protocol page bound, but private-ID, schema-size, or observation-identity changes cannot move a public route to a
different page. If one public route cannot fit its supplied allocation, the result is typed `context_capacity`, not an
empty or cycling page.

The current `action_results_next_page` cursor is not accepted as such a route: for a base page its empty query causes
ContextBuilder to rerank the complete ActionSpace again, so page two can reproduce the same automatic Top-5 instead of
delivering its own targets. The replacement contract binds each base or search cursor to its exact ordered result set,
and every continuation makes at least one previously undelivered target/verb visible until `has_more=false`. A cursor
cycle, skipped legal option, or page that changes only private action IDs is invalid.

A compact action candidate already carries its public ref, operation/verbs, label/role, functional path/container,
focus/viewport/delta reasons, and any parameters needed to understand its route. Candidate membership may raise the
priority of that compact fragment, but it does **not** select or expand the candidate's full region. Full region content
is admitted only by an explicit `read_region`/region cursor, by the separately bounded changed-region contract, or by a
declared current-dialog/focus fragment whose own cost is visible to the packer. This removes the current
`leading candidate → selected_region_keys → full ActiveView region` coupling without discarding functional context.

`TurnPacker` is a small deterministic fitter, not a general optimizer:

```text
RequestAdmission profile/estimator
+ fixed system/task/GoalPlan/workspace/history/output reserve
+ bounded current page/effect/recovery shell
+ ordered DeliveryObligation groups
→ choose the one foreground obligation for this turn
→ attempt only its declared minimum prefix (zero or one record) first
→ compile tentative fragment-route deltas, media, Manifest, and factorized ToolCatalog
→ price the complete provider-bound request after every tentative record
→ if that required record cannot fit, return typed context_capacity
→ otherwise visit every eligible obligation once in stable priority order, attempting its next record
→ repeat those depth rounds while any record is admitted and capacity remains
→ if an optional head record overflows, retain it plus its suffix behind that group's cursor and continue with later groups
→ freeze ModelTurnDelivery + PerTurnToolCatalog + component breakdown
→ RequestAdmission final verification, or typed context_capacity
```

`TurnPacker` compares tentative request input cost with the 8k input soft target. `RequestAdmission` separately records
`estimated_total_tokens` as complete input cost, `output_reserve_tokens` as the one reserve, and
`complete_request_tokens` as their sum. The default profile therefore admits up to 62,904 input tokens with a separate
4,096-token reserve inside the 67,000-token context window; it does not reduce either 62,904 or 8,000 by 4,096 again.

The algorithm is deterministic greedy plus bounded backoff. It has no learned objective, mutable episode state,
knapsack search, cross-turn cache authority, or independent byte limit. “Fixed cost” includes actual tool schema and
media envelope cost, not estimates of private ActionSpace IDs. The fixed shell is itself bounded: it cannot contain an
unbounded region directory, changed-value list, focus neighborhood, route-issue list, or raw delta inventory. A record
can be emitted in compact or expanded form, but each form has an exact public cost and recovery relation; the packer
cannot truncate the inside of a route, source/destination adjacency, image mark, tool schema branch,
tool-call/result pair, or scalar public value.

Depth-round packing is the bounded anti-starvation rule. A large effect/query inventory gets its foreground evidence
first but cannot consume a second record before the current interaction, base, directory, destination, and issue
groups have each had one fit attempt. The number of groups is bounded by protocol kind, so this does not reintroduce
fan-out. A too-large optional head blocks only its own consecutive cursor; it cannot stop a later small group. Adding
low-priority inventory cannot evict the already admitted foreground minimum, although it may replace deeper optional
records in the same finite request.

The packer may shorten each selected page prefix; it may never mutate or discard the complete authority/recall
inventories. `context_capacity` is valid only when the bounded fixed shell itself cannot fit, the foreground obligation
has remaining records but one minimal atomic record plus its required route/catalog representation cannot fit, or the
provider cannot represent the declared page/cursor protocol. It is not valid merely because 84, 840, or any other
number of records share `delta`, `focus`, `same_container`, `exact`, or `route_issue` provenance.

After freezing, every admitted text/media record is protected as one transaction: its public content, provenance,
route delta, Manifest row, ToolCatalog schema branch, delivery identity, and cost lineage either all exist or none do.
This is the only meaning of “protected” in model delivery. It does not describe the pre-packing recall inventory.

Packing observability distinguishes stages rather than reporting a failed tentative catalog as if it were delivered.
Private Trace records authority/recall cardinality, each obligation's admitted prefix and omitted cursor, every tentative
complete-request/component cost, the frozen delivery/catalog cost when one exists, and the typed capacity component
when none exists. A pre-provider capacity result still records the current ActionSpace identity/count and decision kind;
aggregate provider attempts remain separate from the zero attempts of that failed turn. Public case reports project only
declared safe aggregates and never reconstruct these facts from an absent final catalog.

An optional model-backed `ActionReranker` is a typed, stateless extension point, not a mandatory second Agent. It
receives only bounded public facts from the current fused World, returns ranked current public target refs or
`unknown|unsupported`, and cannot authorize, bind, dispatch, remember, or block an action. Any VLM/visual-grounding
provider belongs behind SurfaceAdapter/Fusion: it may enrich that same World with typed current evidence, but discovery
cannot call it as a second direct path or treat its score as legality. The AX ref path remains primary for web tasks.
An actually attached screenshot/SoM may complement the public World for the multimodal ActionPolicy, subject to the
atomic manifest rule below; a screenshot merely captured upstream or omitted from a text-only request is not model
evidence and cannot be used to claim discoverability.

`DeliveryManifest` must be the atomic sibling of what the model actually received. It carries exact delivered action
routes `(operation, source_ref[, destination_ref])`, with `executable_refs` derived from that relation. Each route is
represented by an admitted text fragment or an actually attached actionable image mark; a later model tool operand is
a consumer of this manifest, never a producer. Renderers build a fragment plus a temporary route/ref delta and commit
both only after byte admission. They may not mutate the final manifest and then discard the corresponding region text.
They also may not collect visible refs and later scan the complete ActionSpace to invent their Cartesian or relational
meaning. Each action fragment or actual image mark carries its exact route delta when created; the final manifest is
only the ordered union of deltas from fragments/media that survived packing.

`ModelTurnDelivery` owns exact attached-media records, not an `includes_images` boolean. Each record identifies the
content-addressed payload, actual MIME/digest, coordinate space, and actual marks. Its `delivery_id` covers final text,
ordered media MIME/digests/marks, and `DeliveryManifest.action_routes`; changing any one changes the identity. The
provider binder attaches only `ModelTurnDelivery.media` and cannot pass a separate `request.image_inputs` list around
this owner. Thus the delivery identity, manifest, trace metadata, and actual provider envelope describe the same bytes.

Image annotation is also transactional. The annotator validates observation/revision, coordinate space, media
dimensions, and in-frame bbox intersection and returns the exact marks actually drawn into the bytes that will be
attached plus the actual output MIME type/digest, or typed unavailable. If annotation converts JPEG input to PNG bytes,
the attached media declares PNG; MIME, magic bytes, digest, and payload cannot diverge. Missing annotation support may
attach an unmarked raw image, but contributes no marks or executable routes. Every `E` mark participates in at least
one current delivered action route with an explicit operand role: a source carries its operation/verb, while a
destination-only mark is labelled as that route's destination and does not invent a unary verb. Marks outside any
route are read-only. This closes both currently observed inconsistencies: byte-rejected regions can leave unseen refs
in the manifest, while a raw or out-of-frame screenshot can be labelled “marked” without a mark the model received.

Discovery has three distinct contracts:

| Public operation | Answers | Does not do |
|---|---|---|
| `find_controls` | exact-label, structural, and semantic matches over the complete current ActionSpace, plus a finite continuation route | search readable page facts, future controls, or redefine action legality |
| `search_page_content` | which current public text/value/fact matches a query | authorize or execute GUI actions |
| `read_region` | what content/status/table is inside a known region | serve as a low-precision action registry |

The old names `find_actions`, `find_content`, and `open_region` are removed at migration completion; they are not kept
as parallel compatibility tools. Results distinguish `source_scope`, `source_coverage`, `result_scope`, row-level
`match_kind`, `unmatched_terms`, and `continuation_available`; each target row carries its current verbs.
Exact-label, structural, and semantic matches are separate sections. `source_coverage=complete` means the source was
scanned and its upstream action inventory was complete; source-partial input is preserved and cannot claim absence. It
does not claim semantic recall. The ambiguous fields `exact=true`,
`coverage=complete_current_action_space`, and `authority_changed` are removed from action-search output. Empty or
semantic-only results retain exact-label and base-inventory continuations and give a mechanically correct next
operation.

The public `RequestActionPage` decision contains only the public query or bounded continuation scope plus its tool-call
identity. The corresponding opaque cursor remains private in the Store/catalog resolver. The unproduced `target_id`,
`relevance_role`, and `exact_target_ref` filters and their
payload/history/Monitor projections are deleted; structural inclusion comes from `WorldDeliveryIndex`, not a second
model-facing filter vocabulary.

Search results, recent history, `InformationDelta`, and public trace views contain public target refs, labels, roles,
verbs, match kinds, source/result coverage, and bounded continuation scopes only. Runtime inventory/result/action-
variant totals stay in private diagnostics; current verbs are explicit rather than summarized as a count. Private cursors,
`action:<hash>`, target IDs, binding IDs, selectors, and executor
routes never become result items or novelty evidence. A newly exposed private action ID is not operational progress;
discovery novelty is the first delivery of a public target/verb record in the current World generation.

Action candidates are generated automatically after every fresh World. A model should not have to read regions merely
to discover a currently executable control. `find_controls` remains an explicit full-inventory fallback whose
exact-label/inventory recall path is independent of the automatic reranker's semantic score.

### Open-source reuse boundary

The target adopts three public designs without importing their competing browser and Agent authorities:

| Reference implementation | Adopted contract or algorithm | Integration boundary |
|---|---|---|
| [Agent-E Change Observation](https://github.com/EmergenceAI/Agent-E/blob/master/ae/utils/dom_mutation_observer.py) | every external action returns a first-class account of newly appearing/changing page content | its MutationObserver may be an optional non-authoritative BrowserGym settle hint; the authoritative delta is still the full before/after World diff because Agent-E's observer does not cover every style/class/visibility transition |
| [WebChallenger PageMem](https://github.com/jayoohwang1/webchallenger) | stable page sections, unchanged-section reuse, changed-section refresh, and selective exact expansion | implement on the existing `WorldDeliveryIndex`; do not import its Playwright session, Agent loop, LLM section summarizer, offline site memory, or compound-action authority |
| [agent-browser snapshot diff](https://github.com/vercel-labs/agent-browser/blob/main/cli/src/native/diff.rs) | independent added/removed/changed snapshot comparison | use as a diagnostic/conformance oracle over serialized public snapshots; its line-level diff is not the production typed World authority and its browser session is never composed |

BrowserGym remains the only capture/execution dependency. No second DOM walker, selector map, browser session, ref
registry, action registry, or Agent loop is introduced. If external source code is copied rather than reimplemented
against typed World objects, its MIT/Apache attribution and exact pinned revision must be recorded; the initial baseline
requires no vendored external runtime code.

## AgentWorkspace and request capacity

The repeated history-capacity and post-result wandering failures shared one cause: model continuity was an
append-oriented rendering of `recent_steps`, while result salience, repetition folding, request fitting, and provider
serialization were split across different owners. The production state now uses the reducer below; whole-request
fitting is owned by `RequestAdmission`, while provider binders only serialize an already fitted/admitted candidate.

Each committed `StepResult` therefore has three independent consumers:

```text
StepResult
├── Full Trace: complete and lossless
├── WorkspaceReducer: total update of bounded model workspace
└── EpisodeMonitor: fixed-size operational-stall state
```

The model-facing contract is:

```text
fresh public World + PublicEffectInventory derived from the lossless PublicWorldDelta
→ CurrentFindings
→ WorkspaceReducer(previous workspace, committed StepResult)
→ AgentWorkspace within the allocation supplied by RequestAdmission
```

```python
@dataclass(frozen=True)
class CurrentFinding:
    evidence_ref: str
    predicate: str
    exact_value: PublicScalar
    public_provenance: PublicProvenance  # surface kind/modality/coverage/public structure only
    coverage: CoverageState

@dataclass(frozen=True)
class SemanticEvent:
    step_index: int
    kind: Literal[
        "gui_effect", "public_result", "working_fact", "typed_failure", "recovery"
    ]
    summary: str
    exact_public_values: tuple[PublicValue, ...]

@dataclass(frozen=True)
class ActivitySummary:
    family: Literal[
        "read_region", "search_page_content", "find_controls", "wait", "no_effect"
    ]
    world_digest: str
    attempt_count: int
    new_finding_count: int
    last_outcome: str

@dataclass(frozen=True)
class AgentWorkspace:
    recent_steps: tuple[DetailedStep, ...]       # at most four
    semantic_events: tuple[SemanticEvent, ...]  # fitted within allocation
    activities: tuple[ActivitySummary, ...]     # aggregated
    working_facts: tuple[WorkingFact, ...]
```

`CurrentFinding` accepts only values explicitly present in the public World or current public delta. A whole address
remains a whole address unless the page separately exposes structured state/postcode values. Runtime never parses or
guesses new business facts from a string. `SemanticEvent.summary` is a deterministic template over the committed
operation/effect/failure; no per-step LLM summarizer is introduced.

`WorkspaceReducer.reduce(previous, step, detailed_step, step_index, current_findings)` is a total deterministic function for every
ordinary supported step. Its rules are:

- keep the latest four steps in detailed form;
- retain an exact bounded `SemanticEvent` subset selected by `WorkspaceReducer` for a real GUI effect, newly exposed public result, working-note change,
  typed failure, or recovery transition;
- aggregate ordinary reads/searches/waits with no new finding into `ActivitySummary` instead of appending history;
- deterministically deduplicate repeated exact public values and fold older low-priority events within the supplied
  fixed workspace bounds;
- write every original step to Full Trace regardless of workspace retention.

An effect may exceed the Workspace allocation. The reducer retains only its deterministic bounded exact subset;
current facts remain available through the current World/effect/region continuations, and private Trace retains the
full raw delta plus reconciled effect inventory. A `SemanticEvent` is not a second complete effect store.

Forty searches with no information gain therefore occupy one activity record, not forty model-history entries.
`WorkspaceReducer` does not throw an episode-history-capacity exception for ordinary growth. Allocation-aware
`WorkspaceReducer.fit()` and conversion of irreducible overflow to `context_capacity` with `provider_attempts=0` remain
owned by the next `RequestAdmission` stage.

`RequestAdmission` is the sole capacity authority:

```text
model/provider window and configured request target
→ allocate task/plan, current delivery, tools, images, recent detail, workspace
→ WorkspaceReducer.fit(workspace allocation)
→ estimate the complete request
→ admit or typed context_capacity
→ Provider Binder serializes the admitted request unchanged
```

The old independent model-history byte cap, RunState pre-validation cap, `EpisodeHistoryCapacityError`, and any provider
Binder pruning/capacity decision are removed. The provider Binder does not summarize, trim, reinterpret, or retry a
locally rejected request.

The same rule covers current action and tool delivery. `ActionPager.max_projected_bytes`,
`DEFAULT_MODEL_DELIVERY_MAX_RENDERED_BYTES`, and `MAX_GROUNDED_WORKSPACE_BYTES` are removed as independent vetoes.
`TurnPacker` consumes the profile/estimator supplied for the prospective request and fits atomic obligation records by
the derived foreground-minimum plus depth-round contract;
RequestAdmission verifies the final text, images, workspace, output reserve, and exact relational ToolCatalog together.
A large but legal catalog/request can
only be admitted or return typed `context_capacity` with `provider_attempts=0`; it cannot become
`grounded_tool_catalog_invalid`/`invalid_tool_arguments` because an earlier component used a different byte estimate.
A stable tool-count limit may remain as protocol shape, not a token-capacity owner.

`EpisodeMonitor` holds fixed-size digests and counters rather than reading retained model history:

```text
world digest
current-findings digest
working-facts digest
observation-only stall family/count
recovery count
latest public attempt signature / same-attempt streak / cumulative no-progress count
```

Different read/search queries or regions are still one stall family when there is no World, finding, working-fact, or
GUI-dispatch delta. The configured profile determines when feedback becomes RECOVERY and when recurrence becomes
`CONTROL_STALLED`. Monitor terminates a control loop; it does not change `TaskEvaluation` to `BLOCKED` or claim that the
user task is impossible. A recovery call receives current findings, the aggregated activity, fresh delivery, and the
same `submit_final_response` option through the same ActionPolicy.

Budget values are carried by one generic profile:

```python
@dataclass(frozen=True)
class AgentLoopProfile:
    max_policy_decisions: int
    max_consecutive_observation_only: int
    max_recoveries_per_stall: int
```

Values such as `30/8/1` are experiment-profile defaults. A larger number such as 100 may remain an abnormal global
safety ceiling, but cannot authorize dozens of zero-information reads/searches. Profile values are not site/task
branches and do not change the fixed contracts above.

## Tool and action path

Tools express stable operations; current refs express operands. Executable targets use `E*`, public scalar evidence
uses `F*`, read-only structural nodes use `N*`, and expandable regions use `R*`. Generation-local refs are valid only
for the current context and are removed before any StepResult is retained in AgentWorkspace.

```text
Semantic Capability Registry
→ BrowserGym InteractionProfile with complete translator/executor support
→ complete current ActionSpace
→ CanonicalPublicWorldProjection refs + WorldDeliveryIndex functional context
→ high-recall ActionRecallSet over complete ActionSpace
→ non-authoritative ActionReranker over complete ordered recall inventories
→ one immutable ActionDeliveryPlan over Store-backed bounded obligations
→ TurnPacker commits route-bearing text/media fragments
→ atomic ModelTurnDelivery + exact DeliveryManifest action-route relation
→ factorized PerTurnToolCatalog compiled only from delivered routes
   + Store-owned continuation capabilities
→ ProviderEnvelopeBinder → CanonicalProviderEnvelope → RequestAdmission
→ PydanticAI wire codec
→ provider-native tool call
→ catalog-aware representation normalization
→ Resolver / Admission / Binder / Executor
```

One shared `PublicRefCodec` owns generation-local `E/N/F/R` syntax and the declared per-kind cardinality bound.
Grounding, candidates, manifest, decisions, ToolCatalog schemas, resolver, history, and renderer consume it rather than
copying two-, three-, or four-digit regexes. Crossing the bound is typed capacity before a ref is published. Migration
tests straddle the existing `E999/E1000` disagreement; either side of the chosen bound must be accepted or rejected
identically by every producer and consumer.

The existing `actions.schema_validation` module becomes the sole structural and value-semantic owner for the finite
JSON-Schema subset used by ActionSpace, ToolSpec, PerTurnToolCatalog, provider-call normalization, and final-response
admission. `ToolSpec` construction calls that contract validator; a recursively valid JSON tree is not sufficient.
The subset explicitly bounds objects, arrays/items, scalars, enum/const/ranges, and discriminated `oneOf`/`anyOf`.
Catalog-generated `oneOf` branches use a unique finite target/route discriminant, so overlap is rejected mechanically
without a general theorem prover. Unknown keywords, ill-typed bounds, malformed combinations, and ambiguous unions
become typed catalog/schema failures before a provider attempt. The runtime value validator interprets exactly this
same subset and cannot silently ignore a schema keyword.

ActionDiscoverability/Pager, not CoreLoop, constructs a typed `ActionDiscoveryResult` containing public match records,
source/result coverage, query/continuation-scope lineage, and continuations. The private
cursor remains in the Store/catalog resolver. CoreLoop only attaches that result to the
committed `StepResult`. The current `_action_page_result_payload` dict and its private IDs/ghost filters are removed so
orchestration cannot become a second public search-contract owner.

For every current tool, the public JSON Schema and private resolver denote the same finite relation. A schema-admitted
call must select exactly one current resolution row, and every resolution row must be schema-admitted. Operation tools
therefore use bounded singleton-enum/`oneOf` branches for the delivered target/destination and that row's parameter
schema; they do not publish a regex for all `E*` refs and then reject most of the manifest at resolve time. If the exact
relation exceeds the catalog allocation it is paged or returns typed capacity; it is never widened. Representation
normalization cannot guess a different tuple to repair a schema/resolver mismatch.

Catalog compression is relational factorization, not semantic approximation. Rows may share one enum branch only when
their operation, operand role, destination relation, and business parameter schema are identical. A sparse
source/destination graph is grouped by an actually identical adjacency set or kept as exact discriminated branches;
independent source and destination enums must never create nonexistent Cartesian pairs. The generated finite schema is
accepted only when property checking proves `schema accepts call ⇔ Resolver matches exactly one current row`. The
packer prices the factorized schema actually bound to the provider, not a pre-factorization row count.

The provider layer may normalize wire representation and validate Pydantic models. It cannot repair an invalid target
by choosing a different semantic target or operation. A representation violation receives at most one same-turn,
schema-only repair; a repeated violation becomes a typed policy failure and never creates a GUI step.

The optional `set_form_fields` compound path is removed from the target baseline. It adds no grounding capability that
the existing `type_text`/`select_option` routes lack, but creates a second form-key registry, a cross-item uniqueness
constraint that bounded JSON Schema cannot express without combinatorial branches, and a second partial-dispatch
algebra. The single ActionPolicy instead selects one current route, receives one fresh post-action World, and then
selects the next field or submit control. Typed form/container context remains a recall and presentation signal; it is
not an execution namespace or mini-workflow. The dead `ActionOption.batchable`, `ActionBatch`/`execute_action_batch`,
`from_form_fields`, and partial-form receipt branches are deleted with it. `ExecutionReceiptBatch.from_atomic` remains:
one semantic route may still need to conserve multiple physical attempt/uncertainty receipts, which is not compound
model control.

The executor port is total for ordinary failures. `execute` returns a typed outcome containing `DispatchStatus`,
`ActionError`, bounded `ExecutionDiagnostic`, and receipt truth; adapters catch implementation exceptions at the point
where they know whether dispatch was crossed. An exception after the call may have crossed the physical boundary is
conservatively `SENT_UNKNOWN` and is never replayed. CoreLoop must not catch a generic executor exception and collapse
it to the display string `execution_failed` with no receipt/`RuntimeFailure`. Cancellation remains its existing typed
path.

## TaskGoal and GoalCompiler public-input boundary

`TaskGoal` is the sole user-intent authority, and `TaskBoundary.inputs`, `TaskGoal.inputs`, and `success_criteria` are
admitted public task facts. `ThinTaskIntake`, the GoalCompiler request projection, and every `AgentContext.task`
projection preserve them losslessly within the one declared intake bound; a mapping key's English spelling has no
privacy or execution meaning. The compiler and ActionPolicy therefore receive the same admitted facts. Inputs beyond
the bound fail typed at intake/admission before a partial TaskGoal is created; fixed item/depth/string slicing or a
`[TRUNCATED]` sentinel without a recovery handle is not accepted. Both the intake
`_PRIVATE_INPUT_KEYS` rejection and compiler `_PRIVATE_TASK_KEYS` filtering/deletion are removed because they reject or silently
drop legitimate business data named `coordinates`, `selector`, `x`, `y`, `dom_id`, or `target_id`. If a future task
intake supports model-private material, it must mark that field with a typed visibility contract or place it outside
public `TaskBoundary.inputs`. The TaskGoal→AgentContext path likewise stops importing `_model_private_key` or
`_route_key` as a name-based filter. Those predicates may still protect genuinely private World/execution projections;
renaming a public task key can never change visibility.

This does not expose execution authority. GoalCompiler still outputs only the five bounded advisory fields
`id | objective | done_when | depends_on | final`; GoalPlan cannot contain a binding, authorize an action, or bypass
the PerTurnToolCatalog/Binder. Private selectors, BIDs, coordinates used as physical routes, and credentials remain in
their existing typed private owners rather than being guessed from user vocabulary.

GoalCompiler runs once at task start and once after an explicit user revision, never after navigation, layout change,
stall, or failed action. A `Ready` plan contains 1–8 bounded items, unique IDs, existing acyclic dependencies, and at
most one final item. `NotRequired` supplies no plan. `Unsupported|Failed` records advisory guidance as unavailable and
continues the ordinary GUI loop. Only `NeedsInput` backed by a genuinely missing user-owned fact enters the existing
`AskUser/waiting_user` path; provider, schema, or semantic uncertainty cannot masquerade as missing user input.

The provider envelope ignores unknown bounded descriptive fields but closes missing/type/bound/DAG/final-count errors
through at most one schema repair and one boundary-contract repair, with every initial/repair transcript recorded at
the provider boundary. A Ready GoalPlan is projected unchanged and directly into `AgentContext`; Runtime stores no item
status, frontier, achievement record, or auto-recompile trigger and does not remove ActionSpace routes based on plan
text. Each ordinary ActionPolicy turn sees TaskGoal, the static plan when available, fresh World, bounded workspace,
and current tools, reconstructs which objectives are visibly satisfied, and selects exactly one typed decision. A GUI
decision names exactly one current action route; local observation, `AskUser`, and final-response decisions name none.
It preserves an already satisfied objective, does not repeat an active toggle unless TaskGoal requests reversal,
prioritizes an unsatisfied item whose dependencies are visibly satisfied, and attempts a final item only when every
dependency is clearly satisfied in the fresh World. These are ActionPolicy reasoning obligations, not a Runtime plan
state machine or permission filter; only TaskEvaluator/native verification can complete the task.

The unused `GoalSemanticContract`/`is_private_goal_semantic_name` SurfaceAdapter chain is removed from the active
single-policy path: current World and ActionSpace types already own public surface roles, facts, relations, and legal
operations, and no production consumer uses that goal-specific copy. Historical adapters/codecs may read archived
evidence but cannot restore it as a second vocabulary.

## Removed mission path (historical)

MilestonePlanner, Supervisor, Auditor, MissionState, milestone yield, and their episode state path are removed from the
target runtime. Their detailed design and reopening history live only in
[`history/architecture-pre-milestone-convergence-2026-08-22.md`](history/architecture-pre-milestone-convergence-2026-08-22.md)
and [`single-action-policy-convergence.md`](single-action-policy-convergence.md). They are not current owners,
fallbacks, acceptance gates, or alternative modes. The only retained lesson is already applied above: free-text or key
vocabulary cannot become a mechanical admission boundary, and projections cannot veto their owner facts.

## Progress, recovery, and budgets

`EpisodeMonitor` is deterministic and owns a current-run route trail independent of model-facing history. Every
committed GUI or local-tool step contributes a sample; provider representation failures remain at the provider
boundary and do not become monitor-visible GUI steps.

When Monitor recommends `BLOCK`, CoreLoop commits a typed `ControlTermination(CONTROL_STALLED)` with the terminal
`StepResult`; `feedback="episode_monitor_blocked:..."` remains display-only. When `RunState` consumes the last allowed
policy decision, the same transition owner commits typed `TURN_BUDGET_EXHAUSTED` instead of silently changing only
`status`. Abort, cancellation, task-evaluator block, provider/runtime failure, and harness failure retain their own
typed kinds. Snapshot and benchmark project the committed termination directly. They never recover a reason from
feedback text or fabricate it from a terminal status.

Monitor may expose one small internal typed diagnostic algebra, for example
`state_changed | new_local_information | exact_local_replay | no_operational_progress`, rather than the current
`last_progress_event_type: str` mixture of `EpisodeMonitorEvent`, `InformationDeltaKind`, and historical feedback
literals. `InformationDeltaKind` remains owned by `ObservationDeliveryStore` and is exhaustively consumed at the
Monitor boundary. Because no current acceptance/classification consumer needs the last diagnostic label, the complete
`last_progress_event_type` Snapshot→benchmark→SQLite/JSON chain and its ghost metrics are removed. Private trace may
serialize the internal enum through its sole codec; the public snapshot keeps only declared counters and the typed
`ControlTermination`. A future public metric must name a live typed producer rather than restore the old string union.

Progress distinguishes authoritative/structural result change from focus, hover, cursor, appearance, or screenshot-only
change. Route regression compares page identity, current findings, newly visible public result evidence, and working
facts. The first repeated route without new evidence produces RECOVER; recurrence after recovery produces the typed
control termination `CONTROL_STALLED`. Task evaluation remains `INCOMPLETE|UNKNOWN`; Monitor does not claim that the
task is semantically blocked. A useful unremembered public result prevents a false no-progress decision.

Machine repeat prevention uses one shared typed `PublicAttemptSignature`; human recovery text is a separate field.
For a dispatched GUI action, Monitor derives that signature from the admitted receipt intent and the public pre-action
World. If World, CurrentFindings, WorkingFacts, and structured action outcome all show no increment, the first attempt
continues, the second emits RECOVER with the typed prohibited signature, and CoreLoop rejects a third identical
selection before Binder/executor dispatch. The monitor-owned signature digest and counters are projected read-only into
`EpisodeSnapshot`; benchmark projection does not recount trace events.

For local observations, a first delivery containing unseen public items is progress and its exact bounded items enter
one `PUBLIC_RESULT` SemanticEvent. The same World, public arguments, and public result digest is `exact_replay`: the
full payload is omitted from recent model history and Monitor immediately emits RECOVER. Repeating it after recovery
produces `CONTROL_STALLED`. Different observation operations without information increment retain the general profile
threshold. This prevents World stability from being mistaken for delivery novelty.

Repeated discovery has a typed public query-attempt signature. Recovery may prohibit the exact repeated query and
mechanically restore the base inventory/remaining continuation, but it does not choose a replacement control. A
non-empty semantic false positive is not `new_information` merely because it exposes previously unseen private action
IDs; novelty is measured over the public result contract and exact target matches. This keeps the existing bounded
Monitor useful without making it a semantic search planner.

Keyboard dispatch has one public route per intent. A focused concrete element with an executable BrowserGym `press`
binding exposes only element `press_key`, which resolves to `press(BID, key)`. The page-level focused-context fallback
is offered only when there is no concrete element press route; it resolves the actual focus at dispatch time through
`keyboard_press(key)` and does not invent BID currentness.

Runtime owns bounded execution budgets:

- one `AgentLoopProfile` with maximum policy decisions, maximum consecutive observation-only activity, and maximum
  recoveries per stall;
- one bounded hard ActionPolicy safety cap;
- recovery does not automatically expand the cap;
- model output cannot submit or rewrite the cap.

The hard cap is a safety boundary, not a second planning authority.

## Provider, schema, and reasoning boundary

PydanticAI owns supported provider message/tool transport and Pydantic validation. The current ToolCatalog closes the
available output schemas. One parseable invalid call admits at most one same-turn representation-pruning repair that
may delete invalid fields but cannot add or change any effect-bearing leaf. A multiple-call envelope may repair only
to one exactly unchanged parseable member of the rejected set. Zero-call and wholly unparseable envelopes fail typed without
repair because no semantic identity exists to preserve. Unsupported or still-invalid output becomes a typed policy
failure.

Role reasoning is explicit rather than globally disabled:

- ordinary ActionPolicy: low/off extended thinking with a small tool-call output budget;
- genuine ambiguity or typed recovery: one bounded deliberate policy call;
- representation repair: thinking off and narrow output;
- mechanical boundaries: no model call.

Provider transport retry remains separate from semantic policy calls and never replays GUI effects. Every physical
attempt records its actual reasoning mode, output limit, origin, duration, phase, and typed result. Exhausted repair
exposes bounded field-path/code diagnostics; raw rejected values are not copied into public diagnostics.

Exception classification is closed at the provider boundary:

| Owner failure | Public policy failure |
|---|---|
| `GroundedToolResolutionError` | `invalid_tool_arguments` |
| `ModelRequestCapacityError` / RequestAdmission rejection | `context_capacity` |
| provider transport failure | `provider_unavailable` |
| unexpected Runtime failure | `internal_error` |

A broad `except (ValueError, TypeError) -> invalid_tool_arguments` mapping is absent because it hides workspace,
serialization, and internal defects as model mistakes. Malformed provider arguments first close into a typed
`GroundedToolResolutionError`; an unexpected ValueError follows the `internal_error` path.

Model-turn construction is one typed pre-provider boundary in the existing ActionPolicy port:
`ActionDeliveryPlan/World fragments → TurnPacker tentative ModelTurnDelivery + PerTurnToolCatalog compile →
RequestAdmission final verification → provider bind`. Delivery and catalog compilation remain separately faulted
sub-stages inside the packer so diagnostics retain their owner. Each stage either
returns its value or a declared local failure with `provider_attempts=0`. Diagnostics consume only already constructed
optional values; an exception before `catalog` exists cannot read `catalog.specs` and raise a secondary
`UnboundLocalError`. This is staged totality inside the current port, not a new orchestration state machine.

### Current SOTA alignment (fresh-context review 2026-08-23)

The comparison separates mature interface practice from research signals. A mature tool contract can justify a
deterministic ref/currentness boundary but does not guarantee autonomous task success. Research results can motivate a
candidate architecture but do not justify importing a training stack or mandatory second Agent.

| Target design | Classification |
|---|---|
| complete World retained in Runtime; compact structured/visual view sent to the model | mature GUI-agent practice |
| high-recall inclusion separated from non-authoritative semantic/visual reranking | SOTA-aligned research/engineering pattern |
| candidate does not implicitly expand a whole region; explicit find/read/cursor restores detail | mature compact-interface practice and required local fix |
| VLM adds typed current evidence through SurfaceAdapter/Fusion while Runtime retains execution authority | conservative SOTA-aligned boundary |
| deterministic joint packing of World fragments, routes, media, and exact dynamic tool schema | project-required integration; no cited GUI library provides it as a drop-in |
| atomic route manifest and schema↔unique-resolver equivalence | project typed-runtime correctness contract, not an industry-standard GUI abstraction |
| per-step Manager/Worker, RAG, semantic judge, universal knapsack, or schema Boolean-minimization platform | unsupported/overweight for the current evidence |

- [Playwright navigation lifecycle](https://playwright.dev/python/docs/navigations) and
  [Page API](https://playwright.dev/python/docs/api/class-page) distinguish navigation start, commit,
  DOMContentLoaded, and later load states, and provide event/predicate waits around actions. This is the direct
  execution-boundary reference for causal post-action capture; Playwright actionability alone does not certify an
  arbitrary timer-delayed navigation.
- [Playwright library guidance](https://playwright.dev/python/docs/library) warns that time-based sleeps can leave code
  observing outdated state. The Runtime therefore uses bounded navigation events and DOM-quiet predicates rather than
  a fixed long sleep.
- [Playwright MCP v0.0.79](https://github.com/microsoft/playwright-mcp/blob/v0.0.79/README.md) is a mature interface
  reference: actions use exact refs from a structured accessibility snapshot, while `browser_find` scans that current
  snapshot by case-insensitive substring or regex and returns the matching node, root path, and context. This supports
  an exact full-inventory recall channel independent of semantic ranking. It is an interface practice, not an Agent
  success guarantee.
- [browser-use v0.13.8](https://github.com/browser-use/browser-use/releases/tag/0.13.8) presents current viewport
  interactive indexes, compact structure, and optional screenshots rather than a complete raw DOM/action inventory.
  It supports compact current delivery plus explicit recovery, but its indexes do not replace this Runtime's complete
  ActionSpace, currentness, or route manifest.
- [PydanticAI dynamic tools and preparation](https://ai.pydantic.dev/tools-advanced/#tool-prepare) and
  [toolsets](https://ai.pydantic.dev/toolsets/) are reused for model transport and per-run tool preparation. They do
  not provide a GUI ActionSpace, exact action-route manifest, joint World/tool budget fitter, or proof that schema
  admission denotes one resolver row; those bounded responsibilities remain local.
- [BrowserGym's current environment implementation](https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/core/src/browsergym/core/env.py)
  applies `pre_observation_delay` before extracting an observation. That is useful compatibility pacing but, by
  inference, cannot identify which dispatch owns a later navigation and is not accepted as causal proof here.
- [WorkArena / BrowserGym (ICML 2024)](https://proceedings.mlr.press/v235/drouin24a.html) evaluates realistic knowledge
  work through rich actions and multimodal observations, supporting validation on actual browser tasks rather than
  planner-shaped fixtures.
- [The BrowserGym Ecosystem (TMLR 2025)](https://openreview.net/forum?id=5298fKGmv3) exposes AX/DOM, screenshot,
  bounding boxes, visibility/clickability, focused element, and stable element identifiers in the same observation.
  The design signal is a structured-ref primary path with optional visual evidence, not a pixels-only route or a
  second browser authority. BrowserGym is explicitly a research framework, not a production assurance claim.
- [Mind2Web (NeurIPS 2023)](https://arxiv.org/abs/2306.06070) uses two-stage candidate generation and reports candidate
  Recall@50 below 90% on its cross-task/site/domain splits. That result makes candidate recall an independently measured
  bottleneck: a learned or lexical ranker cannot be the action-reachability authority.
- [SeeAct (ICML 2024)](https://proceedings.mlr.press/v235/zheng24e.html) separates action description from grounding and
  shows a large oracle-grounding gap. The target adopts the separation—high-recall current candidates followed by
  semantic/visual choice—without importing a mandatory cross-encoder call or a new control loop.
- [WebVoyager (ACL 2024)](https://arxiv.org/abs/2401.13919) combines DOM-derived interactive elements with screenshot
  marks and element text. Together with SeeAct, it supports SoM as complementary grounding evidence; it does not show
  that screenshots should replace AX refs on ordinary web forms.
- [GUI-Actor (NeurIPS 2025)](https://proceedings.neurips.cc/paper_files/paper/2025/hash/16130af940e9dabb43c726119bd3b42e-Abstract-Conference.html)
  proposes multiple visual candidates followed by verification. This is a future optional grounding-provider pattern,
  not evidence for a per-step verifier or workflow state machine in the baseline.
- [WebArena (ICLR 2024)](https://openreview.net/forum?id=Jjn5IFp3qP) evaluates functional correctness of resulting site
  state and permits multiple valid action paths. This supports keeping native evaluation authoritative and forbids
  Auditor/Planner claims or reference action sequences from becoming completion truth.
- [WebArena-Verified v1.2.3](https://github.com/ServiceNow/webarena-verified/releases/tag/v1.2.3) uses audited,
  type-aware deterministic evaluators and explicit status codes rather than an LLM judge or substring score. This
  supports separating task outcome, Runtime control outcome, and harness/report outcome in durable evidence.
- [Agent-E](https://arxiv.org/abs/2407.13032) makes action-caused DOM changes first-class model feedback. Its released
  observer is a useful change-notification reference but is not complete enough to replace typed before/after World
  comparison.
- [WebChallenger](https://arxiv.org/abs/2606.10423) uses stable page sections, cached summaries, and changed-section
  refresh. The target adopts this incremental-delivery shape on the existing `WorldDeliveryIndex` without its separate
  Playwright/Agent/memory stack or additional per-step summarizer calls.
- [agent-browser diffing](https://agent-browser.dev/diffing) provides compact structural snapshot comparisons. It is
  used as an independent diagnostic reference rather than a second browser or production World authority.
- [Python `asyncio` task documentation](https://docs.python.org/3/library/asyncio-task.html) defines
  `FIRST_COMPLETED`, cancellation, and bounded timeout behavior. The harness explicitly waits for the first terminal,
  interruption, or case-return signal and uses a separate cancellation grace because cancellation completion itself
  is not instantaneous.
- [OpenTelemetry SDK lifecycle requirements](https://opentelemetry.io/docs/specs/otel/trace/sdk/#shutdown) require
  shutdown/flush to honor a timeout and report failure. Langfuse export follows that mature observer pattern but stays
  weaker than the local result path: it is bounded, fail-open, and never awaited by the Runtime handoff.

## Results, persistence, cleanup, and observability

Task completion does not require an LLM Finalizer. `submit_final_response` may optionally cite current or explicitly
remembered public evidence refs; the mechanical final-response boundary validates lineage and output shape without
claiming semantic completeness. Public output schemas use one finite
closed subset (`type`, object properties/required/additionalProperties, arrays/items/bounds, scalar constraints, and
bounded `oneOf`/`anyOf`); unknown keywords or malformed combinations fail closed before value validation. Core sends
STOP once, acquires one post-STOP World, invokes the native evaluator once, and does not resume ActionPolicy afterward.
`SENT_UNKNOWN` is evaluated from the acquired post-state without replaying STOP. `NOT_SENT` admits neither a
post-STOP capture nor native evaluation, even if an inconsistent adapter returns an acquisition. Standalone atomic
tasks may still terminate directly from their native evaluator; the STOP gate is the mission benchmark protocol.

The native evaluator boundary returns exactly one of `Evaluated(TaskEvaluation)`, typed `Unavailable`, or typed
`InternalFailure`. Only `Evaluated` may populate native status or the official-outcome sink. Failure diagnostics are
bounded and synchronously appended to local trace at the evaluator owner boundary, including stage, exception type,
safe message, observation identity, native snapshot present-field names, and diagnostic/traceback references; Runtime
never fabricates `UNKNOWN` from an exception.

Run20 falsified the previous claim that a preliminary rich `BenchmarkCaseResult` is always durably committed before
cleanup. `project_case_result` was called before its commit `try` and before `CLEANUP_STARTED`; the constructor rejected
`exact_replay`, so cleanup, `CASE_FINISHED`, case export, run aggregation, and summary never ran. The replacement is a
small linear finalization protocol, not event sourcing:

```text
enter case finalizer before environment acquisition; cleanup_owned=false
→ acquire environment
   success → cleanup_owned=true immediately → case body terminal outcome, exception, or interruption
   failure → terminal acquisition failure + cleanup=NOT_ACQUIRED/NOT_APPLICABLE
→ construct typed minimal CaseOutcomeRecord from owner facts
→ insert CaseOutcomeRecord revision=BODY
→ finally
   cleanup_owned=true  → bounded cleanup attempted exactly once
   cleanup_owned=false → no fake cleanup call; retain NOT_ACQUIRED/NOT_APPLICABLE
   → monotonic cleanup disposition update revision=CLEANUP when the store is available
→ append FINAL_ATTEMPT to local trace, then bounded seal/flush
   failure → attach HARNESS_TRACE without changing Runtime/task outcome
→ attempt rich projection from durable owner records
   success     → attach public report disposition
   unsupported → attach HARNESS_PROJECTION without rewriting case status
→ atomically commit revision=FINAL and current_phase=CASE_FINISHED
→ derive run report, summary, and detached status from SQLite; JSON is a rebuildable view
```

`OfficialOutcomeCheckpoint` remains the immutable sole durable copy of an `Evaluated(TaskEvaluation)` result and is
written at that owner boundary. `CaseOutcomeRecord` contains only already owned bounded facts: case/run identity,
Runtime `RunStatus`, terminal reason, optional checkpoint id+digest (or a non-official evaluator-port disposition),
counters, safe snapshot identity, and orthogonal harness dispositions. It never copies official status/reward fields;
projection joins the referenced checkpoint and fails typed on a missing/digest-divergent pair. The record is not
reconstructed from trace and is not a generic event ledger. The rich `BenchmarkCaseResult` remains the public schema
and may evolve, but its codec cannot gate cleanup or erase the durable record. Case behavior and harness integrity
remain orthogonal: after the terminal-reason owner is repaired, the Run20 facts project as
`blocked/CONTROL_STALLED` while reporting is `failed/HARNESS_PROJECTION`; reporting failure makes benchmark acceptance
fail but does not rewrite the case as a GUI `failed` outcome. Until then, the observed display string is evidence of a
missing typed transition and must not be silently promoted to authoritative truth.

All public closed values have one typed owner. Domain algebras such as `RunStatus`, `DecisionKind`, evaluator outcomes,
Monitor diagnostics, cleanup disposition, report disposition, and lifecycle phase stay distinct; report codecs use
their enums or one exhaustive mapping rather than merging them into arbitrary strings. Unknown external/schema values
fail closed as a bounded typed projection result. Strict rejection is preserved, but it produces a durable integrity
fact and continues to cleanup. SQLite and JSON use one declared codec/version path; serialization itself is inside the
store's typed exception boundary.

Persistence failure becomes typed `HARNESS_PERSISTENCE`; projection/encoding incompatibility becomes typed
`HARNESS_PROJECTION`; local trace write/seal failure becomes typed `HARNESS_TRACE`; display text is not sufficient.
Environment cleanup has a deadline, and already-closed
conditions such as Playwright `TargetClosedError` are idempotent cleanup success. Other cleanup failures are secondary
harness facts and cannot replace a previously durable task outcome. Trace event/write/seal, snapshot, lifecycle
observation, body-record construction/commit, report projection/validation, final commit, case JSON export, run
aggregation, and summary export each have bounded containment; none can bypass the outer cleanup `finally`.

All SQLite writes cross one bounded store-owned boundary and carry a monotonic case revision,
`BODY < CLEANUP < FINAL`. `BODY` is insert-only; its sole idempotent retry must be byte-identical. The CLEANUP update
can only fill or advance cleanup fields and a same/equal/stale BODY retry cannot clear them. A timed-out or cancelled
caller cannot leave an unowned worker that later overwrites a newer revision: the store either proves cancellation or
rejects the late write with compare-and-swap. Cleanup disposition, official checkpoint, run commit, and export use the
same bounded boundary instead of mixing deadline-wrapped daemon-thread writes with unbounded synchronous writes. This
is monotonic persistence, not an event log: one current case row remains authoritative and older revisions can never
replace newer facts.

The final trace event is `FINAL_ATTEMPT` with the expected prior revision and intended report disposition. Trace is then
sealed before the fallible FINAL store write. If FINAL commit fails, no already sealed or failing sink is required to
self-report its own failure: durable BODY/CLEANUP plus a non-finished SQLite phase, and `FINAL_ATTEMPT` when trace sealing
succeeded, are the deterministic detached diagnosis. The runner never emits `CASE_FINISHED` or fabricates a FINAL row.

`run_finished` is a synchronous local handoff fact and never waits on viewer IPC. Once observed, the harness permits a
fixed two-second case-body return window; expiry is typed `case_return_timeout`, snapshots the terminal state when
possible, and continues through durable minimal outcome and cleanup even if snapshot or rich projection fails. The
overall watchdog waits for the first of case completion, external interruption, or this terminal handoff, not all
signals. `run_suite` contains each case finalization failure, reloads the durable case record when necessary, and still
attempts a run report/summary; one fallible case projection cannot abort the entire suite. A pre-case or mid-suite
external interruption yields a typed partial suite over the completed durable records; aggregation does not use a
strict zip that assumes every manifest case returned.

`failure_reason` is bounded display text only. It cannot determine `execution_completed`, acceptance, case status, or
round-trip truth and may be omitted from a public codec without changing any decision. Those values derive from typed
body/control/harness dispositions. Runtime and benchmark failure codes share one bounded identifier codec, and one
exhaustive table maps official evaluator outcome plus Runtime status into case disposition. `CASE_FINISHED` is emitted
only after body, cleanup, and report dispositions are known. The local trace may retain phase chronology, but SQLite
does not need a second append-only phase ledger in addition to one current phase and typed outcome columns.

Detached status reads `run-results.sqlite3` before optional JSON views. It distinguishes at least case-body not
returned, durable case without materialized JSON, projection/report failure, cleanup not started/running/completed,
and run-summary failure. `stopped_without_report` is reserved for absence of durable case/report facts, not for every
missing `summary.json`.

Langfuse is a viewer, not part of the control path. Local JSONL is the synchronous authoritative raw transcript for
what it actually recorded, but it is never case/control truth and is not replayed to reconstruct a missing owner fact.
Remote projection is bounded before `put_nowait` to an isolated child process. Queue full/closed/broken, child death/hang, network failure,
flush, close, and repeated close are total fail-open conditions. No Langfuse future, socket, or shutdown may block the
Runtime handoff, case finalizer, or result commit.

## Root-cause migration and deletion map

The implementation change is deliberately broader than changing one token threshold or adding `exact_replay` to one
set, but it stays within existing owners. The following old paths must be replaced and then physically removed rather
than retained as compatibility fallbacks:

| Remove or replace | Owner change | Consumers that must migrate |
|---|---|---|
| BrowserGym first-512 action-bearing target slice followed by a usable partial World | SurfaceAdapter either preserves every supported control/binding for ActionSpace or returns typed acquisition capacity; read-only partial coverage remains explicit | World/ActionSpace builders, discovery source coverage, diagnostics |
| conflicting select-domain limits (`_MAX_ENUM_ITEMS=12`, `MAX_SELECT_OPTIONS=16`, inventory options=512) and silent binding omission | one shared option-domain bound; within-bound domains conserve every option/binding, overflow emits typed non-complete eligibility/coverage | schema validation, BrowserGym projection, capability registry, ActionSpace, ToolCatalog |
| `ContextProjectionBudget.max_destinations_per_option=16` truncating/under-counting destination routes while candidate/catalog paths retain the full set | represent every legal source/destination pair as the existing public action-route record and page it under RequestAdmission; no second destination cap or partial-complete claim | context budget/projection, ActionPager weight/page, candidates, manifest, ToolCatalog, Resolver |
| one WorldDelivery region membership per structural source after Fusion aligns them to the same canonical target | WorldDeliveryIndex chooses one deterministic primary region per canonical target and retains secondary source provenance without duplicate membership | Fusion/index boundary, functional paths, region versions, action discovery |
| multiple ActionOptions with the same public `(operation,source,destination)` selector but incompatible schema/effect/barrier/verifier contracts, rejected only during catalog compilation | ActionSpace merges contract-identical private bindings and closes incompatible selectors as typed `action_route_conflict` with no public route | Fusion/binding projection, ActionSpace builder, why-not facts, catalog compiler, resolver |
| role-only form/container checks in RegionIndex | extend the existing `WorldDeliveryIndex` with one typed functional-context projection from public AX/DOM facts; do not add a parallel index | functional paths, container grouping, action discovery, renderer |
| optional `set_form_fields` decision/schema/form-key/resolver/Binder/executor path, `ActionOption.batchable`, unused `ActionBatch/execute_action_batch`, `form:<label-slug>-<hash(private-ref)>`, and partial-form receipt constructors | remove the compound path; ActionPolicy uses ordinary current `type_text`/`select_option` routes with a fresh World after each dispatch, while `WorldDeliveryIndex` container context remains discovery-only; retain only atomic receipt conservation | grounded tool catalog/compiler, decisions, CoreLoop, Binder/execution contracts, batch module, history/trace, tests |
| opaque target-id order as default model presentation | presentation order uses source/tree order, viewport, target grouping, and stable public tie-breaks | `ActionPager`, ActionCandidates, page cursors, diagnostics |
| `ActionPager.max_projected_bytes` as a shadow capacity owner weighted by private IDs/internal schemas | `RequestAdmission` supplies the delivery allocation; pager measures only the actual public route records and retains a count-only protocol bound | ContextBuilder, ActionPager, request estimates, cursor tests |
| fixed `DEFAULT_MODEL_DELIVERY_MAX_RENDERED_BYTES` and `MAX_GROUNDED_WORKSPACE_BYTES` vetoes before whole-request admission, followed by their removal without joint fitting | one deterministic `TurnPacker` consumes RequestAdmission's profile/estimator and fits the complete rendered World/routes/media/catalog candidate; RequestAdmission remains the sole final capacity authority | DeliveryPlanner/ModelTurnDelivery builder, grounded catalog construction, policy bridge, failure classification, cost trace |
| `ActionCandidateRanker(require_match=True)` and token/fuzzy logic as search admission | `ActionRecallSet` owns inclusion; `ActionReranker` only orders | automatic candidates, `find_controls`, action paging, tests |
| `ActionDeliveryFragment.mandatory`, `ActionDeliveryPlan.mandatory_fragments/optional_fragments`, and `TurnPacker(optional_count=...)` as the packing algebra | `ActionDeliveryPlan` exposes bounded obligation groups/cursors and one derived foreground scope; `TurnPacker` admits the required first record, then depth-round prefixes, and freezes one current page | action candidate contracts/projection, ModelTurnDelivery builder, packer metrics, diagnostics/tests |
| exact/structural recall re-sorted by objective relevance, then global `protected` promotion turns an arbitrarily large recall set into one unpageable shell | keep recall complete and cursor-addressable; create bounded delivery obligations; protect only records admitted to the frozen current page; return capacity only when the bounded shell or one atomic foreground record cannot fit | ActionRecallSet, candidate projection, ActionDeliveryPlan, TurnPacker, generated cardinality/state-sequence tests |
| leading automatic candidate inserted into `selected_region_keys` and expanded as a full `ActiveView` region | a candidate emits one compact route/context fragment; full region expansion requires explicit region/change/focus admission with its own visible cost | ModelTurnDelivery selection, compact renderer, PageMap/read-region cursors, W1b cost probes |
| query candidate projection with `top_k=None` copying a whole result page into the prompt | retain the complete exact/semantic result behind its cursor; the query obligation contributes only the budget-fit current prefix, with at least one exact/structural record when it is foreground and representable | query paging, candidate projection, delivery metrics |
| short-token deletion and four-character prefix/suffix pseudo-fuzzy matches as admission | exact normalized labels are independent of tokens; semantic fuzzy scoring is optional and non-vetoing | query matcher and candidate reason contract |
| BrowserGym admitting labels to 240 characters while RequestActionPage/pager limits or slices discovery queries at 120 | one declared public label/query bound covers every admitted label; over-bound input is typed and no query is silently truncated | SurfaceAdapter label contract, decisions, pager/matcher, tool schema, history/trace |
| target-state `newly_revealed` bonus disconnected from its producer | join current changed-target public slots from `ObservationDeliveryStore.latest_effect` to complete current ActionSpace routes; delete the synthetic flag and do not rank from raw identity-delta membership | PublicEffectProjector, ActionRecallSet/candidate projection, delivery metrics |
| `focused or delta_membership → protected=True` and focus-container/route-issue fan-out before packing | create cursor-backed delivery obligations from every recall source; select a budget-fit foreground page; apply protection only after records are admitted | candidate projection, ActionDeliveryPlan contracts, TurnPacker, renderer, diagnostics |
| action recall reads `last_step.public_world_delta` while World delivery retains an earlier external `LatestEffect` across local reads/searches | `ObservationDeliveryStore.latest_effect` is the single temporal source for both reconciled public-effect delivery and effect-derived action recall until the next external GUI effect | PublicEffectProjector, ObservationDeliveryStore, ContextBuilder, action discovery, Workspace, Monitor |
| unbounded `_latest_effect_values`, changed-region/recovery-directory rendering, and unconditional `route_issue_fragments` in the pre-pack shell | one bounded effect/evidence page, bounded region directory, and cursor-backed issue obligation, all priced through the same TurnPacker | ObservationDelivery, DeliveryPlanner/renderer, ActionDeliveryPlan, World/action continuation tools, trace |
| raw target/fact added/removed counts, identity churn, and whole-delta membership rendered as model meaning, or merely hidden while the same remount noise is emitted as hundreds of effect records | keep lossless `PublicWorldDelta` in Runtime/Trace; deterministically reconcile before/after public semantic multisets into one `PublicEffectInventory`; render only its typed header and bounded current/tombstone pages | WorldTransitionProjector, PublicEffectProjector, ObservationDeliveryStore, action recall, World renderer, ModelTurnDelivery, reconciliation/privacy tests |
| `record.source_id` / observation UUID copied into model-facing `source_context`, history, or cost | public provenance contains only bounded surface kind, modality, source coverage, and public structural context; instance identity stays in private lineage/Trace and is excluded from request cost | ObservationDelivery, fragment/result codecs, Workspace/history, ModelTurnDelivery, request estimator, public trace/report views |
| base page, query page, automatic candidates, and search candidates maintained as overlapping projections; a non-empty search can replace base inventory while a base next-page cursor is not fed into actual delivery | one immutable per-turn `ActionDeliveryPlan` over complete ActionSpace with bounded base/query/effect/container obligation groups and independent cursors; each continuation directly contributes a new budget-fit route page | `RunState`, ContextBuilder, paging/candidate projection, catalog continuation tools, recovery |
| unproduced `RequestActionPage.target_id/relevance_role/exact_target_ref` and their public result/history/Monitor fields | one query-or-continuation public decision; structural filters are internal fields of the canonical delivery index | decisions, CoreLoop payload, step projection, monitor, benchmark support |
| CoreLoop `_action_page_result_payload` ad-hoc public dictionary | discovery owner emits typed `ActionDiscoveryResult`; CoreLoop only commits it | paging/discovery, StepResult, renderer, Workspace, Monitor, trace |
| `exact=true`, `complete_current_action_space`, and `authority_changed` search fields | typed source/result/match coverage contract | CoreLoop payload, renderer, Monitor novelty, trace, tests |
| private action IDs in `matches`, recent history, and information-delta novelty | public target/verb match records; private IDs remain resolver-only | CoreLoop local result, step projection, ObservationDeliveryStore, Workspace |
| manifest mutation before fragment byte admission, post-hoc `_manifest_with_routes` ref scan over complete ActionSpace, image marks outside manifest, `ModelTurnDelivery.includes_images` without media identity, direct `request.image_inputs` provider attachment, “marked” raw/out-of-frame images, and annotated PNG bytes retaining an input JPEG MIME | every text/media fragment carries its exact route delta at creation; `TurnPacker` atomically commits final text/media MIME+digest/actual marks and unions only admitted route deltas; provider binding consumes delivery media only | renderer, annotation/grounding projection, catalog, provider media binding, resolver, delivery identity, trace |
| operation schemas using E-ref regexes and merged per-target business domains while resolver accepts only sparse tuples | PerTurnToolCatalog compiles a bounded relational schema whose admitted calls equal unique current resolver rows | grounded tool compiler/catalog, schema validator, normalizer, resolver tests |
| `ToolSpec` accepting any JSON tree while `validate_parameter_schema_contract` and `validate_value` recognize different schema keywords | extend the existing schema-validation owner to one finite structural/value subset and require every ToolSpec/catalog/final schema to pass it before provider admission | capability schemas, ToolSpec, catalog compiler, provider normalizer, ActionSpace/final-response value validation |
| pre-provider generic failure handler reading `catalog.specs` when delivery/catalog assembly failed before `catalog` assignment | one staged typed assembly outcome with optional constructed artifacts; every local failure returns before provider binding and diagnostics are total | PydanticAI ActionPolicy bridge, delivery/catalog builders, RequestAdmission, provider-attempt metrics |
| duplicated incompatible `E/N/F/R` regex/cardinality rules across grounding, decisions, context, manifest, and catalog | one shared generation-local `PublicRefCodec` and typed capacity boundary | all ref producers/consumers, public schemas, fixtures, archive adapters |
| CoreLoop broad catches that stringify executor/compound-action exceptions without receipt truth | executor owner returns total typed outcomes/diagnostics with conservative `SENT_UNKNOWN` after an uncertain boundary | environment ports/adapters, CoreLoop, receipt projection, RuntimeFailure, benchmark |
| raw `last_progress_event_type`, historical action-feedback literals, and external metrics that read removed `context.progress` | delete the public field/ghost metrics; keep any operational diagnostic as a Monitor-private enum and persist only typed `ControlTermination` plus declared counters | Monitor, snapshot, external breadth observers, case projection/schema, SQLite/JSON |
| terminal reasons encoded only in feedback or implied by budget reaching zero | typed `ControlTermination` committed by the transition owner | RunState, snapshot, terminal-reason projection, breadth classification |
| display-only `failure_reason` deciding `execution_completed`/acceptance and disappearing in public codec | derive execution and acceptance only from typed body/control/harness dispositions; text never affects truth | case projection, acceptance, codec round-trip |
| different identifier grammars for Runtime failure codes and benchmark failure facts | one shared bounded `FailureCode` codec or an exhaustive lossless mapping | RuntimeFailure, FailureFacts, external classification |
| duplicated/inconsistent task-outcome-to-run-status tables | one exhaustive owner-to-case disposition mapping, including post-STOP incomplete/failed combinations | official checkpoint, case projection, terminal reasons, acceptance |
| active `BenchmarkCaseResult` duplicate failure/cleanup/watchdog fields, fields with no producer, `legacy_case_projection.py`, and in-constructor v6–v11 conditions | one small current `CaseFacts`/report schema; historical readers move to a read-only archive adapter | case projection, public codec, acceptance, fixtures |
| SQLite `asdict + json.dumps` beside a different public `case_evidence_codec` | one declared current codec/privacy path inside the bounded store exception boundary | SQLite payloads, case JSON, reload, detached status |
| unguarded preliminary/final report construction around cleanup | monotonic `BODY/CLEANUP/FINAL` `CaseOutcomeRecord` plus one bounded linear case finalizer; rich projection occurs after cleanup | runner, result store, suite aggregation, CLI |
| timeout wrappers whose cancelled future leaves a daemon store write able to overwrite newer data, plus unbounded sibling writes | one store-owned bounded write boundary with monotonic revision/CAS | body/final commit, cleanup disposition, official checkpoint, run commit/export |
| CLI and test-only reporting entry points that separately commit/export run truth | runner owns case/run finalization and aggregates only durable revisions; adapters may request a view but cannot commit a second truth | `run_suite`, CLI, `target_loop/reporting.py`, exporters |
| lifecycle/status observer callbacks whose exception can abort the owner | bounded fail-open observation after the owner transition; callback failure becomes diagnostic only | instrumentation, heartbeat, viewer callbacks |
| `CASE_FINISHED` emitted before final report construction/commit and three competing lifecycle projections | emit finished only after body, cleanup, and report dispositions are known; keep one runner-owned current phase plus typed outcomes and delete the SQLite phase-event ledger if chronology is already in trace | runner, instrumentation, result store, detached status |
| JSON-only detached status | SQLite lifecycle/outcome/report read model with JSON as optional materialization | detached CLI and operational tests |
| ThinTaskIntake `_PRIVATE_INPUT_KEYS`, GoalCompiler `_PRIVATE_TASK_KEYS`, and TaskGoal→AgentContext use of `_model_private_key/_route_key`, plus fixed 12-item/depth-3/string-240 truncation over already admitted public task mappings | enforce one typed intake bound before TaskGoal creation, then preserve every admitted public fact exactly to both compiler and ActionPolicy context; any private field uses typed visibility, never a name blacklist | NaturalLanguageTaskRequest/TaskBoundary intake, compiler request projection, task context projection, RequestAdmission, privacy/capacity tests, prompt transcript |
| unused `GoalSemanticContract`/`is_private_goal_semantic_name` adapter vocabulary and ambiguous historical Planner wording | remove the dead goal-specific surface contract from the active path; current World/ActionSpace types own surface semantics | goal/world exports, SurfaceAdapter/WorldEnvironment ports, fixtures, `AGENTS.md` status wording |

Migration may add typed fields and a new public case schema version; old evidence remains readable through explicit
versioned codecs and is never silently reinterpreted. Search cursors and functional-context identities are
generation-local and are invalidated with the current World like existing refs. No selector, BID, coordinate, private
target ID, screenshot, prompt, or model reasoning enters public reports.

Rejected alternatives are: lowering the token cutoff from three to two; restoring a standalone 10 KiB renderer guard;
always dumping the whole ActionSpace or a candidate's whole region into every prompt; accepting arbitrary report
strings; reconstructing outcomes from trace; adding a vector database/training pipeline; building a generic knapsack
or schema Boolean-minimization platform; or routing each step through Planner, Manager, Grounder, and Verifier roles.
Threshold/cap patches either hide a legal route or move overflow to another component, while whole-region dumping
recreates the measured run3 inflation. The latter options add cost and state without evidence that they are needed. A
stateless optional reranker over public World facts is admitted only behind measured recall and latency gates and
cannot be a required reachability path; visual inference, if enabled, stays inside the existing SurfaceAdapter/Fusion
port.

## Superseded mission-path implementation inventory

The provider-free implementation of the mission path was completed before the single-ActionPolicy redesign reopened
the architecture. This map records the contracts C1–C6 removed or replaced; none is a current production owner:

| Superseded contract | Historical owner and contract |
|---|---|
| Manager page/control assignment | `MilestonePlanner` proposes one bounded `MilestoneRoadmap` |
| mutable subtask status | admitted `MissionState` outcomes; roadmap remains advisory |
| `entry_scope_key` execution authority | ref-free `FunctionalRegionSummary`, used only as Planner situation context |
| eight-turn page cutover | one continuous milestone episode with Runtime-owned hard cap 15 |
| `yield_subtask` | typed `yield_milestone(outcome_proposed|needs_replan)` |
| `find_actions` / `find_content` / `open_region` | `find_controls` / `search_page_content` / `read_region` |
| compact-JSON product bridge | provider-native `ToolCall` through the single catalog/resolver path |
| Planner/Manager state-change review | deterministic evidence admission, with Auditor only for `UNKNOWN` |
| LLM finalization review | mechanical response admission, one STOP, one post-world acquire, one native evaluation |

Side-effect-free role retry, automatic candidates, typed route recovery, and single-route receipt conservation remain on
their existing owners. Lifecycle isolation, durable-result ordering, and bounded cleanup remain target contracts but
are reopened by C11; they must not be described as implemented closure. No compatibility alias or fallback production
path is retained. Live capability evidence remains a separate, explicitly authorized benchmark stage and is not
implied by provider-free implementation completion.

## Non-goals

- no second GUI loop, Binder, browser session, evaluator, DOM walker, selector map, or action registry;
- no compound GUI action, form-key namespace, per-step workflow, or partial-batch dispatch algebra in the baseline;
- no mandatory per-step Manager, Auditor, summarizer, grounding/verifier Agent, vector database, or separately trained
  retrieval stack; an optional stateless reranker may only reorder an already sufficient recall set;
- no benchmark-case, site-label, fixed-ref, selector, or expected-answer specialization;
- no attempt to prove an open-world objective is reachable from a functional-region summary;
- no long-term cross-case recall during W1b/W2;
- no production-grade workflow platform, event-sourcing system, or generalized ledger.

## Superseded mission-path closure criteria (historical)

The milestone architecture is no longer a closure target. The following criteria are retained as historical evidence
and regression input; active closure is defined by C8–C12 in `benchmark.md`, including change-first delivery, bounded
workspace, action discoverability, and total benchmark finalization:

1. production search finds no old assignment contract or compatibility alias;
2. provider-free replay proves successful continuous routes are not split at ordinary page/state changes;
3. state-machine/property tests cover every decision, receipt, yield, cancellation, retry, partial, persistence, and
   projection boundary;
4. held-out route regression and form workflows pass without site-specific branches;
5. six real-page World/Action/Evidence recoverability gates pass;
6. full tests, lint, diff check, docs, and durable evidence agree;
7. an independent fresh-context architecture review passes;
8. a later explicit live W1b witness improves or preserves success and cost without reopening the same authority gap.

The reopened BrowserGym transition additionally requires a generic delayed-link witness, typed navigation timeout,
typed acquisition-instability witness, a non-navigation fast-path bound, trace-order assertions, and proof that no
next policy decision is admitted before stable capture. Task-7 replay is not closure evidence and remains blocked until
those properties, C8–C12, the full provider-free suite, docs, held-out evidence, and a fresh-context review agree.
