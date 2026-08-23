# Run21 C8/C10 authority-cutover recovery

Goal: recover the Run21 C8/C10 migration through serial owner cutovers. Preserve `output/`; keep status `reopened / non-closed`; do not run providers or live benchmark. Commit each verified cutover independently.

## Serial cutover constraints

- Gate 0, World, and Delivery are complete. The Envelope correction after `7844b7f1` is provider-free verified but awaits exit review; Gate 4 is not admitted.
- Preserve `output/` and all unrelated user files; each cutover receives one independent commit.
- A failing test or auditor counterexample is design evidence only. It does not authorize a local production patch.
- Run30 predates current production changes and is stale for current-tree verification.

| Step | Status | Evidence / modified files |
| --- | --- | --- |
| 1. Freeze production changes and invalidate stale current-tree evidence claims | completed | `.codex-plans/c10-joint-delivery-packing.md`; `docs/architecture.md`; `docs/benchmark.md` |
| 2. Design `CanonicalPublicWorldProjection` owner cutover | completed | `docs/architecture.md` typed input/output/invariants, producer/consumer/deletion map, permutation/remount production gate |
| 3. Design `ObservationDeliveryStore` delivery-state owner cutover | completed | `docs/architecture.md` cursor/capability algebra, Plan/Catalog cutover, zero-prefix committed sequence gate |
| 4. Design `CanonicalProviderEnvelope` owner cutover | completed | `docs/architecture.md` binder/admission/adapter ownership, typed provenance, exact Recording Provider gate |
| 5. Review the three designs together for authority uniqueness and establish non-circular serial migration | completed | one normative chain and responsibility table in `docs/architecture.md`; Gate 0 → World → Delivery → Envelope → vertical conservation in both current authority docs |
| 6. Build test-only Recording Provider Gate 0 through the actual policy/CoreLoop/provider boundary | completed | `tests/support/model/recording_pydantic_model.py`; `tests/integration/model/test_recording_provider_gate.py`; actual TargetRuntime/CoreLoop path: 6 passed; focused 78 passed/3 skipped; full 1558 passed/24 skipped/2 known non-Gate failures; no `src/` diff |
| 7. Implement World cutover and pass its owner-local production-path gate | completed | sole immutable `CanonicalPublicWorldProjection`; all E/N/F/R consumers migrated; old production allocators/fallbacks deleted; permutation/remount/effect/ambiguity/identity/Gate-0 production-path properties pass; focused `175 passed, 2 skipped`; full `1568 passed, 24 skipped`; Ruff/compileall/diff/negative searches pass; no Delivery/Envelope semantic migration |
| 8. Implement Delivery cutover and pass its two-turn production-path gate | completed | Store-owned immutable inventories/capabilities; pure Plan and bounded Packer; atomic Manifest resolver rows; capability-only dynamic Catalog; fanout/state/exact/privacy properties; real two-request FunctionModel gate; focused `231 passed`; full `1594 passed, 24 skipped`; Ruff/compileall/diff/negative searches pass |
| 9. Implement Envelope cutover and pass Recording Provider identity/cost gate | correction implemented and provider-free verified; exit review pending | preserved `7844b7f1`; reserve algebra and one-instruction/no-independent-history algebra corrected; default-profile, soft-target, exact-boundary, full, and static rerun pass (`587 passed, 3 skipped` focused; `1598 passed, 24 skipped` full) |
| 10. Run final vertical conservation plus focused/relevant/full static and provider-free verification | blocked / not admitted | Gate 3 exit review must explicitly admit Gate 4; Run30 cannot be reused |
| 11. Run one fresh-context read-only audit and report non-closed status honestly | pending | no closure without fresh evidence and separately authorized live benchmark |

## Known design evidence to absorb, not patch locally

- Public E/F refs and page membership use multiple order/ref allocators; target/binding enumeration changes current findings.
- `WorldDeliveryIndex._document_lineage` includes private viewport target identity, so identity remount can incorrectly become `new_document`.
- Store/Plan/Catalog split continuation meaning; a zero-admitted suffix can be permanently unreachable.
- RequestAdmission validates sidecar components rather than the exact physical messages/tools later reconstructed by the PydanticAI bridge; string blacklists violate public lexical neutrality.
- Run30 transition/recovery probes did not prove the production `ModelBackedAgentPolicy -> CoreLoop -> Store.reduce -> RunState.apply` chain, and Run30 is older than the current tree.

Each pending production cutover follows the normative six-step protocol in `architecture.md`: freeze its complete
producer/consumer/deletion scope; implement the positive typed owner; migrate every consumer; delete the displaced
path in the same stage; pass owner + CoreLoop production gates; stop before the next owner. No fallback keeps old and
new authorities simultaneously reachable.

Constraints: no provider calls, live benchmark, Task7/Go/OSM/page-specific production branches, fixed selectors/action IDs, second Loop/World/ActionSpace authority, generic optimizer, event sourcing, or closure claim.
