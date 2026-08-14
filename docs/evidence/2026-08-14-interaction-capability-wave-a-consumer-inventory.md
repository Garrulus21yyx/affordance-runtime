# Interaction Capability Onboarding Wave A consumer inventory

Date: 2026-08-14

Status: `IMPLEMENTED_EXISTING_ACTION_SINGLE_PATH / STATEFACT_CUTOVER_PARTIAL / LIVE_NOT_RUN`

## Post-implementation outcome

All target-chain producers and consumers listed below now use the registry,
adapter profiles/composer, generic schema path, explicit normalizer, and exact
resolver. The following displaced owners are physically absent and asserted
unreachable by architecture/property tests:

- `world/action_vocabulary.py`;
- `_CANONICAL_COMPATIBILITY` and `canonical_action_operation`;
- BrowserGym role singleton `semantic_action`/`primitive` fields;
- `_normalize_catalog_call` and `_constant_grounding_owner`;
- grounded-path private-field filtering and verb-specific business schema
  reconstruction.

No shadow, read-old fallback, dual semantic map, or alternate composition
fixture remains. The only non-complete concern is the explicitly listed
StateFact producer cutover. Evaluator parameter lookup and permitted-family
routing now consume registry definitions; sealed per-binding postcondition
contracts remain a later verification-contract slice and do not admit a new
action family.

This record covers the target `WorldObservation -> ActionSpace -> AgentContext
-> grounded catalog -> exact resolver -> admission` chain and every production
surface that currently imports the shared action vocabulary. Historical
transaction-planner action aliases are a separate product contract; they do
not feed the target ActionSpace and are not a compatibility fallback for this
cutover.

## Semantic actions, aliases, and primitive mapping

Current semantic action fields are owned by `ActionBinding.semantic_action`,
then conserved by `ActionOption`, `AgentActionOptionView`, compiled tool private
rows, `SelectAction`, admission, `AdmittedActionSelection`, and
`BoundActionRequest`. The competing definition sites are:

| Current owner/producer | Consumers | Wave-A replacement/deletion |
|---|---|---|
| `world/action_vocabulary.py::_CANONICAL_BY_PRIMITIVE` and `_parameter_schema` | DOM, Visual, WoT, BrowserGym visual producers; one target-world test | replace with `InteractionCapabilityRegistry` plus adapter profile/composed translators; delete the module and its direct test |
| `model_boundary/action_candidate_projection.py::_CANONICAL_COMPATIBILITY` and `canonical_action_operation` | `close_action_candidates`; grounding projection verb summary; focused tests | all target producers emit canonical names before ActionSpace; delete compatibility renaming and make candidate closure reject unknown/noncanonical operations through the registry |
| BrowserGym `BrowserGymRoleSpec.semantic_action/primitive` | semantic analysis availability/options, lattice filtering, binding production, currentness compatibility | replace with `RoleCapabilityOffer[]`; each offer resolves through the composed BrowserGym profile; delete singleton fields and singleton equality path |
| adapter `if primitive == ...` dispatch syntax | DOM/Visual/WoT/BrowserGym executors | retain only as private backend mechanics; profile/composer translator tables prove the primitive is declared and unique; these strings never enter public vocabulary/admission/evaluation |

Canonical existing actions are `activate`, `type_text`, `select_option`, and
`read`. BrowserGym/DOM `click`, `fill`, `type`, `select`, Visual
`point_activate`, and WoT `invoke`/`read_property`/`write_property` are private
primitive names. The legacy workflow planner still recognizes aliases in
`action_choice_builder.py` and `generalist_planner.py`; those consumers do not
produce target `ActionBinding`s and are explicitly outside this target-chain
owner cutover.

## `world/action_vocabulary.py` producer/consumer closure

Production imports exist in:

- `surfaces/dom/adapter.py` for DOM binding semantics/schema;
- `surfaces/visual/adapter.py` for point-activation bindings;
- `surfaces/wot/contracts.py` for private WoT route metadata;
- `surfaces/wot/adapter.py` for current WoT bindings;
- `benchmarks/external_smoke/browsergym_visual_projection.py` for current
  BrowserGym visual bindings.

The only direct target test import is `tests/test_target_world_contracts.py`.
Every listed producer must switch before `world/action_vocabulary.py` is
deleted. No registry facade may delegate back to that map.

## Action-candidate compatibility canonicalizer

`close_action_candidates()` is called by `model_boundary/context_builder.py`
and directly by grounded-tool tests. Its `click/fill/select` compatibility map
currently rewrites `AgentActionOptionView.operation`. The related
`canonical_action_operation()` consumer in
`model_boundary/grounding_projection.py` renders verb summaries. Both must
resolve an already canonical `semantic_action` against the new registry. The
old map/function and tests that can feed old verbs into this target path must
be deleted or changed to assert typed fail-closed behavior.

## BrowserGym role-to-action path

Definition and consumers:

```text
browsergym_semantic_profile._ROLE_SPECS
  -> browsergym_semantics.browsergym_role_spec / CanonicalBrowserControl.role_spec
     -> executable/availability and select-option domain checks
  -> browsergym_projection lattice filter and _binding_pair
  -> browsergym_currentness primitive compatibility
  -> browsergym_execution private primitive dispatcher
```

The replacement is `BrowserGymRoleSpec.offers`, with zero-to-many
`RoleCapabilityOffer`s. Observation and inventory roles remain independent of
offers. Binding production selects the current eligible offer and resolves it
through the immutable BrowserGym composed capabilities. Wave A creates no new
offer for scroll, press, focus, drag, value setting, or hover.

## Schema conservation and destination path

The current business-schema path is:

```text
adapter current offer builder
  -> ActionBinding.parameter_schema (contract validation)
  -> ActionSpaceBuilder grouping + schema digest
  -> ActionOption.parameter_schema
  -> model_boundary.projection.project_parameter_schema_for_model
  -> AgentActionOptionView.parameter_schema
  -> GroundedToolCompiler._business_schema
  -> ToolSpec.input_schema (selectors added separately)
  -> exact resolver validate_value
  -> SelectAction.parameters unchanged
  -> ActionSpaceBuilder.try_admit[_selection]
  -> validate_value_issue against current ActionOption.parameter_schema
  -> AdmittedActionSelection / BoundActionRequest
```

`project_parameter_schema_for_model()` currently reconstructs the finite schema
node-by-node and may silently drop private-looking properties/required names.
Because `ActionBinding` already rejects private names, Wave A must turn this
into an exact validated copy. `GroundedToolCompiler._business_schema` is
generic and already copies properties/required without fill/select branches;
its selector fields remain compiler-owned and separate.

Destination producers are `ActionBinding.destination_required` and
`eligible_destination_ids`; fusion rewrites IDs; `ActionSpaceBuilder` groups
and copies them; paging and model projection bound the domain;
`close_action_candidates()` currently derives `required` versus `forbidden`
from the boolean alone; the compiler expands concrete rows; the resolver emits
one destination ID; admission, route selection, execution contracts,
confirmation and refresh equivalence re-check it. The invalid state
`required=false + nonempty domain` is presently accepted and downgraded to
`forbidden`; it must become typed unsupported before tool emission. Empty
required domains are currently rejected at binding/option construction rather
than represented as a typed catalog issue; Wave A will preserve a typed
`DESTINATION_UNAVAILABLE` boundary where an incomplete projected current
domain reaches compilation.

## Provider normalization, exact resolver, repair, and admission

Current call chain:

```text
provider native/compact response
  -> _GroundedCommandPayloadBase (name/op, arguments/args wire aliases)
  -> _GroundedAdapterBase._resolve_catalog
  -> embedded _normalize_catalog_call
  -> resolve_grounded_*_call
       context/catalog identity check
       exact tool-name lookup
       exact emitted-schema validation
       exact private selector-row lookup
  -> selected-tool schema repair only for non-selector business fields
  -> SelectAction
  -> AgentLoop try_admit_selection against current ActionSpace
```

The embedded normalizer reads only catalog specs/bindings, but currently proves
only canonical-operation equality plus a unique schema match. It and
`_constant_grounding_owner` will be deleted after an explicit
`ProviderCallNormalizer` owns wire/cross-tool reconciliation. The compiled row
must carry a catalog/context-bound authority-equivalence digest covering
canonical action, business schema, subject/destination mode, effect,
risk/consequence/reversibility/barrier, and verification contract digest.
Unknown, invalid, owner-mismatched, ambiguous, non-equivalent, and stale calls
must remain typed and zero-dispatch. The resolver remains unchanged in
responsibility: exact schema and private-table lookup only, with no world read,
repair, fuzzy search, or authorization.

Permanent `name/op` and `arguments/args` wire tolerance remains at the provider
envelope and terminates in one canonical `ToolCall`; it is not semantic
authority. Strict same-catalog representation equivalence may also remain in
the normalizer, because it produces one exact current call and still passes
resolver plus ActionSpace admission.

## Evaluator action-name branches

The current branches are:

- `evaluation/action_evaluator.py`: `activate` accepts target/world/screenshot
  differences; `type_text/select_option` guess the value parameter name;
- `evaluation/action_verification.py`: derives text/select value obligations by
  action name and also admits criterion/artifact/structural-world obligations;
- `evaluation/action_applicability.py`: special-cases activate visual diff;
- `agent/progress_control.py`: guesses text/select current value and parameter;
- `world/action_space.py`, `world/relevance.py`, and
  `world/action_classification.py`: bounded legality/relevance/effect
  classification branches, not postcondition proof.

Wave A makes verification families and parameter names registry-owned and
records the exact definition digest in binding, option, candidate, catalog,
selection, route, and currentness equivalence. The listed evaluator/progress
branches now route through registry parameter families/permitted verification
families instead of spelling `fill/select/activate` schema ownership. Sealed
per-binding postcondition values remain a later coherent verification-contract
cutover; until then, this boundary cannot be used to admit new interaction
families.

## Canonical state writers and projections

Production state writers currently construct both `SemanticTarget.state` and
matching `StateFact`s in DOM, Visual, WoT, HTTP JSON, BrowserGym structural,
BrowserGym visual, target-loop support, and canonical-observation builder
paths. `WorldFusion` independently merges `SemanticTarget.state`, detects
target-state conflicts, and separately fuses facts. Consumers of target state
include world/model projections, grounding, ActorWorldSnapshot/facet
collections, semantic digests, progress control, evaluator compatibility, and
fusion itself.

This is a genuine dual-write boundary. Wave A may add a single
`project_target_state(facts, conflicts)` function and construction-time
equality checks for migrated observations, and it must prove that
ActorWorldSnapshot/facet collections do not delete facts or grant authority.
It may not claim full StateFact cutover until every producer writes facts first,
fusion derives canonical target state from fused facts, and every listed
consumer stops treating target state as independently authored. If that cannot
be completed atomically here, status remains
`IMPLEMENTATION_PARTIAL / STATEFACT_DUAL_WRITE_NOT_ADMITTED` with these exact
producers/consumers listed.

## Synchronous deletion inventory

Required for an implemented target-chain concern:

- delete `world/action_vocabulary.py` and its imports;
- delete `_CANONICAL_COMPATIBILITY` and `canonical_action_operation`;
- delete BrowserGym singleton `semantic_action`/`primitive` role fields and
  primitive equality helper once all consumers use offers/composition;
- delete embedded `_normalize_catalog_call` and
  `_constant_grounding_owner` once the explicit normalizer is integrated;
- delete verb-specific schema reconstruction on the grounded path;
- delete fixtures/tests able to select the old vocabulary/composition path;
- retain no read-new/fallback-old or dual-write semantic owner.

The private adapter primitive dispatchers, provider wire aliases, exact current
catalog resolution, and final ActionSpace admission remain. They implement
backend mechanics, transport normalization, identity lookup, and legal
membership respectively; none is a second semantic-action authority.
