# World-interaction capability migration

Source baseline: `A-Modular-Action-System-Architecture`, branch
`origin/feature/C-009-unify-runtime-architecture`, commit `c3d85f5`.

## Boundary

The migration reuses the old repository's tested hands, eyes, environments,
and evaluation fixtures. It does not make the old controller or mutable world
state authoritative in the current Runtime.

| Capability | Current owner |
|---|---|
| DOM transduction | Existing `adapters/dom.py` and `BrowserSession` |
| WoT TD/security/rate/events | `adapters/wot.py`, `adapters/wot_security.py` |
| Visual SoM/overlay | `adapters/som.py` |
| Fresh environment boundary | `environment_port.py` |
| Deterministic fixture | `testing/static_environment.py` |
| Failure catalogue | `testing/failure_injection.py` |
| Smart-room and mock web | `environments/` |
| External MiniWoB/WebArena glue | Existing BrowserGym benchmark modules |
| Viable-route ranking | `routing_policy.py` behind `UnifiedRoutePlanner` hard gates |
| Fast-path hints | `memory/binding_cache.py` |
| Short control loop | `agent/` |
| Low-risk batches | `execution/batch.py` |

## Preserved invariants

- A route policy ranks only candidates that already passed currentness,
  executor, action-support, evidence, and verifier gates.
- A cached hint can resolve only to a freshly grounded candidate with the same
  source, executor, and target fingerprint.
- WoT credentials are resolved at the transport boundary and redacted from
  receipts and errors.
- Every single action is followed by a fresh observation before evaluation.
- `SENT_UNKNOWN` never causes an implicit retry.
- Batches contain at most three low-risk actions on one backend and stop on
  the first failure or uncertain transport result.
- Telemetry and compatibility runtime state cannot authorize execution or mark
  a task complete in the new loop.

The older state-kernel/coordinator implementation remains temporarily available
for compatibility and its existing benchmark evidence. The migrated AgentLoop
does not import it; boundary tests enforce that separation.
