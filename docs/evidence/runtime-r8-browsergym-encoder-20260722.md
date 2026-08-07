# Runtime R8 BrowserGym Encoder Containment Evidence

Date: 2026-07-22

Status: BrowserGym encoder slice complete; R8 remains in progress.

## Boundary

`benchmarks/browsergym_encoder.py` now owns BrowserGym-only translation:

- attachment of externally selected typed `BrowserGymAction` values to a Core
  `ActionContract`;
- translation of general semantic activate, point, type, select, press, and
  drag proposals after Core contract construction;
- `GestureBinding` encoding to `drag_and_drop` or bounded viewport
  `mouse_drag_and_drop`;
- point target encoding to current `bid` click or trusted viewport center;
- native date/time value normalization and eventful search typing choice;
- BrowserGym action-specific verifier mapping from the pre-action snapshot;
- validation of adapter-owned viewport boxes and fail-closed handling when no
  usable handle or geometry exists.

The responsibility boundary is unchanged and explicit:

```text
Core ContractBuilder / GestureContractBinder / preflight
  -> distinct semantic endpoints
  -> same observation epoch
  -> both leases and fingerprints current
  -> shared route, policy, capability, risk, approval
  -> immutable ActionContract + GestureBinding
BrowserGym encoder
  -> current bid or trusted viewport geometry
  -> BrowserGymAction schema
  -> adapter verifier plan
```

The encoder does not resolve semantic IDs, choose a route, grant authority,
weaken currentness, or accept model-authored selectors/coordinates. It imports
no benchmark task manifest and contains no task-id dispatch. The bridge facade
continues to export both contract builders, both encoders, and all prior helper
names used by conformance tests and callers.

## Adapter and Core evidence

Direct encoder tests prove facade identity, current-handle DOM drag, invalid
geometry rejection, point handle precedence, missing point/gesture binding
failure, generic native date/time conversion, eventful-typing requirements,
and pre-action scroll-state verifier binding. Existing adapter tests retain
sortable insertion geometry, visual drag, same-cell distinct calendar
boundaries, DOM option/click/fill/select/press translation, and visual point
contract behavior.

Independent Core tests—not BrowserGym encoder branches—continue to prove:

- gesture source and destination must differ;
- source supports drag and destination accepts drop;
- both endpoints share one route and coherent observation identity;
- both leases, page/snapshot revisions, target fingerprints, and blocking
  overlays are rechecked before execution;
- contract hash binds both endpoints.

The BrowserGym bridge fell from 1,890 to 1,537 lines. The extracted encoder is
382 lines. No executor, runner, scheduling, checkpoint, report, planner, Prompt,
schema, budget, Coordinator, or StateKernel behavior changed.

No real benchmark episode was run for this containment slice. Adapter
conformance plus generic Core gesture tests prove the claimed boundary;
benchmark reward would not prove it.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused encoder, adapter, visual-contract, BrowserGym-runtime, Core contract,
  and boundary tests: 88 passed;
- full repository tests: 512 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 86 source files: passed;
- `git diff --check`: passed.

## Remaining R8 work

- split single-episode execution/process isolation from suite
  scheduling/checkpointing;
- isolate report aggregation and improve trace-derived FailureEnvelope family
  attribution without task-id dispatch;
- migrate selected bindings toward tagged payloads and finish the ownership and
  trace-schema audit.
