# Interaction Shell frontend contract governance document plan

Goal: produce a standalone detailed design and governance document for the external interaction shell. The design must eliminate handwritten transport contracts while preserving authored UI/presentation code and one tightly bounded typed command builder, keep Runtime/checkpoint authority behind public Runtime ports, exclude the legacy main-worktree benchmark Console, and define an atomic, testable migration.

Target document: `docs/interaction-shell-frontend-contract-governance.md`

| Step | Status | Evidence / output |
| --- | --- | --- |
| 1. Confirm worktree, scope, dirty-tree constraints, and existing Shell authority | done | `codex/external-interaction-shell@7af330c7`; `docs/interaction-shell.md`; existing dirty files preserved |
| 2. Trace backend contract → OpenAPI → generated types → API/SSE controller → React presentation | done | `contracts.py`, `api.py`, `core_runtime_port.py`, `manager.py`, generated API, hook, components |
| 3. Define the positive owner model and the handwritten/generated boundary | done | Contract authority, generated client/validators, authored controller/view-model/components |
| 4. Specify target command, event, command-offer, surface-view, diagnostics, and recovery contracts | done | Closed typed algebras and temporal invariants in sections 6–13 |
| 5. Define migration batches, compatibility/versioning, CI gates, forbidden patterns, and exit criteria | done | Initial v3 migration, gates, tests, non-goals, exit criteria; phase ordering subsequently tightened by Step 8 |
| 6. Write and validate the standalone detailed design | done | `docs/interaction-shell-frontend-contract-governance.md` |
| 7. Validate the current v2 baseline without treating it as v3 closure | done | Baseline validation passed: 17 repository references resolve; Markdown fences/diff check clean; frontend typecheck + 13 tests pass; 16 backend isolation/contract tests pass. This remains baseline evidence; the later v3 design approval is recorded separately in Step 9. |
| 8. Close CommandOffer, recovery, SurfaceView, generation-boundary, and atomic-migration ownership in the design | done | Runtime owner/change surface added; checkpoint inspection remains Runtime-owned; SurfaceView is a closed display-only union; bounded typed builder and fixed operation IDs defined; phases reduced to atomic 0–4 and second-platform composition removed. |
| 9. Re-run architecture review and close review findings | done | Independent gates returned `APPROVE Phase 0–3 design` and, after the owner clarification, `APPROVE owner-clarity revision`. The final contract separates manager access, the Port's closed pre-Runtime deployment gate/wire conversion, Runtime semantic admission, single SurfaceAvailability→SurfaceView composition, live vs durable recovery owners, and manager installation. This is design approval, not implementation evidence. |

Constraints:

- Do not modify the main worktree or its legacy benchmark Console.
- Do not overwrite unrelated dirty changes in this worktree.
- Do not implement the governance migration in this task.
- Backend Pydantic contracts are the sole public schema authority.
- Frontend product code must not handwrite DTOs, endpoints, command envelopes, event payload casts, or Runtime state/admission algebra.
- Authored React presentation, accessibility, styling, controller behavior, and pure view-model logic remain legitimate handwritten code.
- The Shell remains outside Core and consumes only the versioned public Runtime session boundary.

Initial self-review checklist (superseded as closure evidence by the independent review):

- Can a reader tell exactly what “no handwritten frontend contract” means? Yes: sections 1 and 4 distinguish generated protocol artifacts from authored UI/controller/view-model code.
- Can a reader locate the authoritative producer for status, commands, events, viewer state, and diagnostics? Yes: section 3 owner matrix.
- Is the replacement for raw paths, weak command bodies, `data.snapshot`, and status inference concrete? Yes: sections 6–7 and 10.
- Is the display contract platform-neutral without expanding this plan into Android/desktop composition? Yes: the closed `SurfaceView` union is neutral, while real second-platform composition is explicitly deferred.
- Are transport reconnect and Runtime recovery separated? Yes: section 11 defines a typed resync/recovery sequence.
- Are versioning, security, tests, migration, non-goals, and deletion conditions explicit? Yes: sections 12–22.
- At design-approval time, could the document be mistaken for completed implementation? No: the then-current header separated approval from implementation. The implementation table below now supersedes that historical answer with actual evidence, while current Shell status remains in `docs/interaction-shell.md`.

First-review findings received:

- Runtime must own state-correct semantic capabilities and public refs before the Port projects `CommandOffer`; the Port may only intersect deployment/viewer availability.
- Recovery inspection must come from the Runtime checkpoint owner; Shell registry remains authentication/TTL/conversation-only.
- Session snapshot remains the sole control owner/lease authority; SurfaceView contains display capability only and uses a closed union.
- Generated protocol artifacts need stable FastAPI operation IDs, while a minimal authored typed command builder may express offer-to-command semantics without JSON/path access.
- The v3 schema, generated artifacts, controller, and view-model must switch atomically; Android/OSWorld composition is out of this governance scope until a real second platform exists.

Revision disposition (independently confirmed):

- `CommandOffer`: Runtime now owns state-correct semantic capability and refs; Port is limited to deployment-availability intersection and pure projection. `offer_revision` and ghost `start_new_task` are removed from the v3 target.
- Recovery: `RuntimeCheckpointStore` owns records/consumption while `TargetRuntimeSessionFactory` is the sole read-only inspection conversion owner; Shell registry remains auth/TTL/conversation-only. Authentication, Runtime inspection, and authenticated lookup are separate closed algebras; undefined `recovery_epoch` is removed.
- Surface: product snapshot is the sole owner of control owner/lease; display is `UnavailableSurface | ReadOnlySurface | InteractiveSurface` with a cross-model invariant.
- Generation: explicit FastAPI `operation_id` values stabilize the named SDK. DTO/client/validators/events are generated; a minimal exhaustive typed builder owns only offer + typed user input → command intent conversion. Fixtures are not required to be generated.
- Migration: Phase 0 validates the generator, Phase 1 repairs Runtime owners without breaking v2, Phase 2 atomically switches v3 schema/generated/controller/view-model, and Phase 3 removes v2 immediately after E2E. Diagnostics Phase 4 is dependency-blocked; Android/OSWorld composition is deferred.

Second-review disposition (independently confirmed):

- Offer algebra now has explicit soundness and completeness under an unchanged snapshot/actor/deployment boundary, at most one offer per kind, and a fixed UI rule separating Answer from Revise. Question/confirmation refs live only in interaction offers; checkpoint/lease remain only in the snapshot.
- Session lookup is live-first: a live handle authenticates against its in-memory session credential without requiring a recovery registry; only a missing handle enters registry auth and Runtime inspection. Store failures become typed `RecoveryInspectionFailed` outcomes.
- Only transport disconnect/cursor gap/epoch mismatch permit bounded resync. Unsupported version, unknown event type, and strict schema violations terminate as `protocol_mismatch` with no resync/recover/reconnect.
- Diagnostics Phase 4 is explicitly blocked until the benchmark owner publishes a versioned summary schema, stable read boundary, outcome algebra, and producer witness; this does not block Phase 0–3.
- Legal Revise commands now separate admission from business result: `needs_input/no_change/new_task_suggested/unsupported/failed/effect_reconciliation_required` return Accepted with `last_control_outcome`; Conflict is reserved for currentness/identity/ref/session-state conflicts, and undurable infrastructure failures are typed Rejected.
- The actual recover call now returns `Recovered | RecoveryConflict | RecoveryUnavailable | RecoveryFailed` after authentication. Supported races and store/runtime/reconnector/restore failures never become exception-detail strings; only Recovered installs a snapshot, and non-Recovered variants stop automatic recovery.

Final-review repair disposition (independently confirmed):

- `CommandOffer` now promises legality soundness rather than infrastructure infallibility: an unchanged valid offer cannot fail as Conflict/Unsupported for an already-published precondition; successful durable handling is Accepted, while only closed infrastructure failures may be Rejected.
- v3 closes `ConflictCode | UnsupportedCode | RejectedCode` across every command. Runtime owns normalization, unknown internal codes fail closed as `Rejected(internal_contract_failure)`, and the Shell Port loses its `runtime_conflict` fallback.
- Phase 1 now creates and verifies unpublished Runtime capability/ref, admission-conversion, and recovery-inspection owner ports behind the v2 compatibility adapter. All Shell offer projection, lookup/HTTP mapping, generated public results, and frontend changes occur atomically in Phase 2.
- The file-level migration surface now names the concrete BrowserGym factory/runtime composition, Steel viewer producer, Runtime owner tests, Shell contract/deployment tests, and frontend generator/ESLint gates; the deployment factory delegates checkpoint inspection and never becomes a second checkpoint authority.

Post-approval owner-clarity revision (independently confirmed):

- Command processing is split into non-overlapping owners: manager access/serialization, RuntimeSessionPort pre-Runtime deployment gate plus wire projection, and Runtime semantic admission/currentness/idempotency. Port may reject unavailable deployment capability only before any Runtime call and may not recalculate Runtime legality/business outcomes.
- Deployment viewer adapters now produce only ephemeral provider-neutral `SurfaceAvailability`; `CoreRuntimeSessionPort` is the sole `SurfaceView` composition owner and Pydantic only validates.
- Recovery facts and transitions are split explicitly: live TargetRuntimeSession owns live exact-ref admission; checkpoint store owns durable records/consumption; deployment owns reconnector injection; Target factory owns absent-handle inspection/recover currentness; manager owns authenticated pure lookup mapping, conversation projection, and handle installation.

## Phase 0–3 implementation plan

Goal: implement and verify the approved Interaction Shell frontend contract governance Phase 0–3 in this worktree without disturbing pre-existing unrelated changes. This section is the persistent execution plan and must be updated as evidence changes.

| Step | Status | Evidence / files |
| --- | --- | --- |
| I0. Read all authorities, record dirty-tree baseline, and trace the complete producer/consumer/code migration surface | completed | Authorities read in full before edits; initial dirty/untracked baseline captured; Runtime, manager, Port, viewer, recovery, API/OpenAPI, generated SDK/validator, controller/view-model/React and tests traced end to end. |
| I1. Phase 0: freeze v2 behavior, fix operation IDs, select/lock and prove the OpenAPI client/runtime-validator/event witness, and add regenerate/static debt gates | completed | v2 baseline: Runtime/Shell backend 72 tests and frontend 13 tests plus typecheck/lint/build passed before the switch. Fixed operation IDs and deterministic `generate_openapi.py`; pinned `@hey-api/openapi-ts@0.99.0` plus `valibot@1.4.2`. Named `CommandOffer` produces a generated discriminated DTO and recursive strict `v.variant`; `check:generated` and architecture negative gates are present. |
| I2. Phase 1: implement unpublished Runtime v3 capability/ref projection, closed admission conversion, exact live recovery admission, and factory-owned recovery inspection/delegation while preserving v2 public behavior | completed | `public_session.py` owns state-correct capabilities/refs, command admission/idempotency/currentness, legal revision normalization, live exact-checkpoint admission, typed inspection/recovery and factory transitions. Runtime owner suite: 50 passed. |
| I3. Phase 2 backend atomic switch: publish v3 Pydantic/FastAPI contracts, offers/events/surface/recovery, unified commands, and owner-correct manager/Port/deployment composition | completed | Public `interaction-shell.v3`, closed offers/surface/events/admissions/recovery, one `/commands`, manager-only lock/auth/projection/install, Port-only fresh TakeOver gate/wire projection, viewer-only `SurfaceAvailability`, and factory-delegated recovery are implemented as one undeployed worktree unit. |
| I4. Phase 2 generated/frontend atomic switch: regenerate OpenAPI/DTO/validators/named SDK/event decoder; migrate the bounded builder, controller, view-model, and React; remove authored transport/domain mirrors | completed | Checked-in OpenAPI plus generated DTOs, strict Valibot validators, named HTTP/SSE SDK and event decoder replace `generated/api.ts`, `lib/api.ts`, and `lib/types.ts`; authored frontend uses one exhaustive builder, controller, pure view-model and offer-driven React. |
| I5. Phase 2 verification: owner/property/generative tests, API/SSE integration, codegen diff, frontend gates, and architecture negative gates | completed | Shell backend/architecture: 81 passed, 1 optional harness skip; frontend: 27 passed; typecheck/lint/build pass. Owner/race/recovery/offer/all-command×closed-outcome/registry/OpenAPI/static-debt and adversarial nested-event causality properties are covered. Deterministic generation produces no second-run artifact delta; the HEAD-relative diff gate is rerun after the coherent commit. |
| I6. Phase 3: after provider-free API/SSE and synthetic Playwright pass, delete all v2 routes/models/generated/compatibility paths and prove one Shell contract remains | completed | Provider-free API/SSE synthetic Playwright passed after exercising start→answer→confirm, causal duplicate event handling and one unified command route. v2 routes/models/generated/manual transport compatibility paths are deleted; negative searches find no v2/runtime_conflict route algebra. |
| I7. Run complete relevant provider-free suites, Ruff, Pyright/Mypy according to existing gates, build, E2E, and `git diff --check`; repair root owners for any failures | completed | Runtime 50 passed; Shell backend/architecture 81 passed + 1 optional harness skip; frontend 27 passed, typecheck/lint/build and Playwright 1 passed. Ruff, backend Pyright and scoped Mypy pass; deterministic regeneration and `git diff --check` pass. Full import-following root Mypy exposes 219 unrelated existing errors in prohibited/unrelated modules and is recorded honestly rather than repaired here. |
| I8. Update all three authority/status documents with exact implementation and verification evidence | completed | Plan, governance contract, Shell status, README and external contract documentation now describe the sole v3 contract, final owner chain, verified gates, transitional Phase10 diagnostics boundary and Phase4 block. |
| I9. Independent fresh-context architecture review; resolve findings at the owning boundary and rerun affected gates | completed | Independent review returned APPROVE after three owner-level repairs: manager semantic reads removed and viewer-input admission moved to Runtime/Port; terminal exactly-once cleanup moved to TargetRuntimeSession; nested event/snapshot causal mismatch now terminates as protocol_mismatch. Review verified single authority/projection/checkpoint truth/call chain and Phase4 block. |
| I10. Final repository/branch/origin/HEAD audit and commit coherent Phase 0–3 implementation without including unrelated pre-existing changes | in_progress | Branch/origin began at `7af330c7` with 0/0 divergence. Final coherent staging, commit, post-commit regenerate-and-diff and remaining dirty-tree audit are pending. |

Implementation constraints:

- Phase 2 may use local intermediate edits, but it is one indivisible public deployment unit; no intermediate state is implementation evidence.
- Phase 3 deletion starts only after the v3 provider-free API/SSE and synthetic Playwright witness pass.
- No live provider or benchmark run is authorized.
- Existing dirty and untracked files are preserved; overlapping files are edited only where required by this governance migration.
