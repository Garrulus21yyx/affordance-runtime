# Gate 2 read-only visual mark recovery

Status: in_progress; gate_2_reopened; gate_3_admitted; gate_4_stopped_not_admitted;
overall_reopened_non_closed

## Goal

Separate visual evidence selection from action authorization so an actual in-frame public target mark may reference
either `E*` or `N*`, while operand roles, route deltas, Catalog rows, and Binder authority remain executable-only.

## Constraints

- Falsification checkpoint: `75d34443bff422b20bba608738e0c3e739801c75`.
- Preserve untracked `output/`; never modify, stage, or commit it.
- Gate 3 remains admitted and is out of modification scope.
- Gate 4 remains stopped/not admitted; do not resume its vertical assertions.
- No provider, live benchmark, Task7 replay, fixed ref/selector, or case-specific production branch.
- Use canonical public World ordering and a deterministic bounded visual candidate selection; ActionSpace controls only
  route/role attachment.

## Positive contract

```text
Canonical public in-frame target (E or N)
→ bounded VisualMarkCandidateSet
→ actual annotated mark
→ AgentImageMark / DeliveredMediaMark / CanonicalMediaRecord

actual E route operand + exact current route
→ typed source/destination role + route delta
→ Manifest/Catalog authorization
```

An `N*` mark has no operand roles, route deltas, or callable tool. Out-of-frame targets are absent from actual marks.
Selection order and bound depend only on canonical public facts, not private target IDs or source enumeration.

## Steps

1. [completed] Commit the Gate 4 attempt-2 falsification documentation checkpoint.
2. [completed] Map canonical target/region inputs and define the bounded visual mark candidate owner.
3. [completed] Implement E/N mark support and executable-only route binding at Grounding/Media ownership.
4. [completed] Add N-only, N+E, out-of-frame, bounded/permutation, and real Recording FunctionModel tests.
5. [completed] Run focused/full/static/negative verification and update Gate 2 evidence.
6. [in_progress] Commit the Gate 2 repair independently.
7. [pending] Perform a fresh read-only Gate 2 exit review; update admission status without starting Gate 4.

## Files modified

- `.codex-plans/gate2-readonly-visual-mark-recovery.md` — persistent recovery record.
- `src/affordance_runtime/agent/context/grounding_projection.py` — bounded canonical E/N visual candidates and
  action-independent annotation.
- `src/affordance_runtime/agent/context/context.py` — E/N image mark contract with executable-only route roles.
- `src/affordance_runtime/agent/context/model_turn_delivery.py` — preserves N marks as read-only Manifest evidence.
- `src/affordance_runtime/model/policy/canonical_provider_envelope.py` — independently validates E/N marks and E-only
  route operands.

## Evidence log

- Owner/BrowserGym/Recording/Delivery/architecture focused suite: `154 passed`.
- N-only real Runtime turn reaches Recording FunctionModel with exact admitted Envelope, one actual `N1` PNG mark,
  no roles/routes, no executable Manifest refs, and no action route.
- Mixed N1+E1 real Runtime turn records both marks; only E1 has `source` and `(activate,E1,"")`; N1 is read-only
  Manifest evidence and never an action operand.
- Out-of-frame N produces no candidate/actual mark. Forty read-only regions are bounded to seven in canonical public
  order, with identical marks and annotated digest under private identity and enumeration permutation.
- Full provider-free suite: `1612 passed, 24 skipped`; Ruff, compileall, `git diff --check`, and negative searches for
  ActionSpace-driven mark selection, production fixture labels, and non-E route operands pass. No provider, live
  benchmark, or Task7 replay ran.
- Fresh review found `VisualMarkCandidate` relied on the upstream region for bbox positivity instead of closing its
  own typed boundary. The candidate now independently rejects negative origins/non-positive dimensions. Recorder
  assertions also prove N-only publishes no interaction tool, while mixed N+E publishes only `activate` and its
  provider schema contains no N1. Exit review restarts from the correction commit.
- The restarted review found `AgentGroundingEntityView.marked` was derived from selected candidates before annotation,
  so annotation-unavailable could claim a mark absent from the delivered image. Grounding now derives this flag only
  from annotation-returned actual marks; a fault-injected unavailable annotation proves the candidate remains
  unmarked and carries no media mark.
