# Public shell contract

Schema version: `interaction-shell.v3`.

FastAPI/Pydantic is the only public schema and operation authority. The checked-in
OpenAPI document generates TypeScript DTOs, Valibot runtime validators, the named
HTTP/SSE SDK, and the event decoder with `@hey-api/openapi-ts@0.99.0`. Authored
frontend code contains no endpoint strings, raw fetches, request dictionaries, or
domain casts.

The causal path is fixed:

```text
manager credential/session lock
→ RuntimeSessionPort pre-Runtime deployment gate
→ Runtime semantic admission/transition
→ RuntimeSessionPort wire projection
→ generated validator/client
→ frontend controller/view-model
```

`RuntimeSessionSnapshot.command_offers` is the complete, state-correct public
command presentation. Every offer kind is unique; interaction offers carry the
exact Runtime-owned request ref. Offers are not permissions or cached admission.
All commands use the single `/sessions/{session_id}/commands` operation and the
closed `Accepted | Conflict | Unsupported | Rejected` result algebra. Business
revision outcomes remain `Accepted` and appear in `last_control_outcome`.

The Runtime owns command identity, idempotency, semantic currentness, refs,
session/control state, checkpoint currentness, and business results. The Port
only performs the closed pre-Runtime `take_over` deployment gate, then projects
typed Runtime outcomes. `return_control` is never blocked by media availability.

Surface adapters publish only ephemeral, provider-neutral
`SurfaceAvailability`. `CoreRuntimeSessionPort` alone combines that availability
with Runtime control facts to produce the closed public
`unavailable | read_only | interactive` `SurfaceView`. No provider identity,
control owner, or lease is duplicated inside Surface contracts.

`RuntimeCheckpointStore` owns durable checkpoint records and consumption.
`TargetRuntimeSession` owns exact live checkpoint currentness.
`TargetRuntimeSessionFactory` owns absent-handle inspection/recovery transitions.
The Shell registry stores only salted auth, TTL, and bounded conversation
projection; the manager maps typed recovery results and installs a handle only
for `Recovered`.

SSE sends the typed AG-UI custom envelope
`{type: "CUSTOM", name: "snapshot.updated", value: SnapshotUpdated}`. The
frontend applies only the next cursor in the same epoch, ignores duplicates,
performs one bounded snapshot resync on a gap, and fails closed on schema or
event-kind mismatch.
