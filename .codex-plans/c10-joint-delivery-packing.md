# Run21 C8/C10 authority-cutover recovery

Goal: recover the Run21 C8/C10 migration from a non-convergent layered implementation. Production code and tests are frozen until three owner cutover designs are complete. Preserve the dirty worktree and `output/`; keep status `reopened / non-closed`; do not run providers, live benchmark, or commit.

## Freeze

- Frozen: `src/`, `tests/`, benchmark implementation, production diagnostics.
- Allowed before cutover approval: read-only inspection; this plan; `docs/architecture.md` owner/cutover design; `docs/benchmark.md` evidence-status correction.
- A failing test or auditor counterexample is design evidence only. It does not authorize a local production patch.
- Run30 predates current production changes and is stale for current-tree verification.

| Step | Status | Evidence / modified files |
| --- | --- | --- |
| 1. Freeze production changes and invalidate stale current-tree evidence claims | completed | `.codex-plans/c10-joint-delivery-packing.md`; `docs/architecture.md`; `docs/benchmark.md` |
| 2. Design `CanonicalPublicWorldProjection` owner cutover | completed | `docs/architecture.md` typed input/output/invariants, producer/consumer/deletion map, permutation/remount production gate |
| 3. Design `ObservationDeliveryStore` delivery-state owner cutover | completed | `docs/architecture.md` cursor/capability algebra, Plan/Catalog cutover, zero-prefix committed sequence gate |
| 4. Design `CanonicalProviderEnvelope` owner cutover | completed | `docs/architecture.md` binder/admission/adapter ownership, typed provenance, exact Recording Provider gate |
| 5. Review the three designs together for authority uniqueness and establish non-circular serial migration | completed | one normative chain and responsibility table in `docs/architecture.md`; Gate 0 → World → Delivery → Envelope → vertical conservation in both current authority docs |
| 6. Build test-only Recording Provider Gate 0 through the actual policy/CoreLoop/provider boundary | pending | instrumentation only; no production semantics, provider call, or second request builder |
| 7. Implement World cutover and pass its owner-local production-path gate | pending | no Delivery/Envelope migration; final envelope invariance is deferred to the vertical gate |
| 8. Implement Delivery cutover and pass its two-turn production-path gate | pending | no Envelope migration until complete |
| 9. Implement Envelope cutover and pass Recording Provider identity/cost gate | pending | exact admitted object must be the transported/recorded object |
| 10. Run final vertical conservation plus focused/relevant/full static and provider-free verification | pending | Run30 cannot be reused |
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

Constraints: no provider calls, live benchmark, Task7/Go/OSM/page-specific production branches, fixed selectors/action IDs, second Loop/World/ActionSpace authority, generic optimizer, event sourcing, commit, or closure claim.
