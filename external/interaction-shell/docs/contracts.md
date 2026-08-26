# Public shell contracts

Schema version: `interaction-shell.v1`.

The shell has exactly four public concepts:

- `RuntimeSessionPort` owns the only coarse shell-to-Runtime boundary.
- `ShellCommand` is a closed discriminated union.
- `RuntimeSessionSnapshot` is the current owner-projected public view.
- `ShellEvent` is an ordered, epoch-and-cursor-addressed public AG-UI event envelope.

Commands return `Accepted`, `Conflict`, `Unsupported`, or `Rejected`. An
accepted HTTP command is never interpreted as GUI task success. Only the
`completion` field copied from a Runtime-owned public snapshot/event can render
success.

The Runtime now publishes `affordance-runtime.session.v1`. When a deployment
composes `CoreRuntimeSessionPort` with a `TargetRuntimeSessionFactory`, the
supported commands are start, AskUser answer, confirmation approve/reject,
cooperative cancel, durable pause/resume, zero-prior-effect task revision, and
close. The opaque Core handle owns resumable `RunState`; the external manager
stores only that handle and drains owner-projected events by epoch/cursor without
retaining a second event list, timestamp, or envelope projection. Without a
configured Runtime/environment factory, the production-safe default remains
typed `Unsupported`. `INTERACTION_SHELL_DEMO=true` enables a contract-only
local/E2E port; it emits no GUI action, has no agent loop, and labels its
completion `demo_owner_completion`.

Task revision is one dedicated command/port call and always remains paused after
success. The Shell manager supplies an immutable language-only context of at
most six turns and 16 KiB, ending at exactly one identified latest user turn.
Runtime supplies the authoritative current goal and pending interruption facts,
and the complete command/context participates in Runtime idempotency digesting.
Conversation never authorizes actions or enters ActionPolicy model history. A
versioned Shell-private recovery projection retains at most six recent turns and
64 immutable revision contexts in the existing recovery credential row. The
Shell persists a new context before invoking `RuntimeSessionPort.revise`, restores
it before recovering the Runtime handle, and deletes it with the session. It is
not a command-result store or Runtime checkpoint. A
prior `SENT` or `SENT_UNKNOWN` receipt returns typed
`effect_reconciliation_required`; compensation, new-task replacement, takeover,
and return-control remain unavailable. Viewer interaction likewise remains
disabled without an exclusive typed control lease and return outcome.

Steel/Browserbase Live View is a deployment projection, not a media protocol:
`ViewerStateProjector` may publish only a read-only, secret-free same-origin
`/viewer/...` path. Unconfigured deployments publish typed unavailable. The
provider session and its cleanup stay in the Runtime environment lease.

## SOTA alignment

The boundary follows the mature thread/run/interrupt pattern rather than
exposing an internal checkpoint:

- one stable session identity can host a start and later resume runs;
- an interruption publishes a snapshot plus a stable interrupt identity before
  accepting a response;
- responses must address the exact open interrupt;
- snapshots hydrate current UI state and ordered events resume from a cursor;
- private resumable state remains an implementation detail of the Runtime owner.

This matches the public event/snapshot and interrupt guidance in
[AG-UI events](https://docs.ag-ui.com/concepts/events) and
[AG-UI interrupts](https://docs.ag-ui.com/concepts/interrupts), and the same
separation between durable private run state and public approval/rejection in
[OpenAI Agents SDK HITL](https://openai.github.io/openai-agents-python/human_in_the_loop/)
and [sessions](https://openai.github.io/openai-agents-python/sessions/).
