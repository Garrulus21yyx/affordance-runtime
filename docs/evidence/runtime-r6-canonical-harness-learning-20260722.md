# Runtime R6 Canonical Harness Learning Evidence

Date: 2026-07-22

Status: Runtime-first R6 exit complete. This evidence exercises the generic
Runtime with local non-BrowserGym profile fixtures. It makes no public
benchmark score claim.

## Boundary and learning invariant

Cross-run activation is permitted only through this chain:

~~~text
complete persisted Runtime JSONL
  -> causal/schema/terminal validation
  -> strong independent postcondition evidence
  -> backend-neutral semantic step extraction
  -> independent cross-variant clustering
  -> parameter/applicability/negative-example mining
  -> digest-bound quarantined TaskSkill
  -> fresh mandatory replay
  -> accepted persisted registry
  -> explicit normal-entrypoint loading
  -> one fresh observed/routed/contracted/verified step at a time
~~~

No selector, DOM index, backend handle, mark id, URL, coordinate, approval
token, BrowserGym action, or benchmark reward is learned. Concrete grounding
still belongs to the current Unified Route Planner, and accepted skills cannot
extend task capabilities, approval, or risk authority.

## Canonical trace validation and extraction

`CanonicalTraceValidator` reads the actual JSONL bytes and binds their SHA-256
digest. It rejects:

- empty or invalid JSONL;
- mixed run/runtime/contract schema identities;
- gaps, reordering, duplicate event ids, or forward/missing parents;
- a non-`TaskCreated` beginning, failed/aborted terminal, or multiple successful
  terminals;
- duplicate semantic contract ids;
- semantic contracts without passed verifier evidence and a trainable verified
  route outcome;
- weak, self-reported, planner-reported, or receipt-only evidence;
- a lifecycle that does not causally descend from contract to postcondition to
  route outcome.

Coordinator trace payloads now persist only the semantic learning material:
role, label, action kind, semantic parameters, verifier plan, capabilities, and
risk. Backend bindings remain in normal execution evidence but are not copied
into `VerifiedSemanticStep`. Postcondition events now carry the contract id and
typed verifier evidence needed to prove the extraction.

The extraction report has its own deterministic digest bound to the source
trace digest, runtime/schema versions, event count, terminal result, and
verified contract ids.

## Cross-run mining and quarantine

The generic integration test runs a System 2 profile-update planner three times
through the real Coordinator, DOM adapter, ContractBuilder, executor, verifier,
RouteOutcome, trace writer, and artifact-independent JSONL reader:

| Run | DOM variant | Bound value |
| --- | --- | --- |
| 1 | original layout | Margaret |
| 2 | fieldset/family layout | Grace |
| 3 | reordered held-out layout | Lin |

The semantic cluster key includes task family, ordered action kinds, target and
destination roles, parameter names, postcondition shape, and evidence shape;
it excludes backend identity and variable labels/values. The miner extracts
typed target-label and text slots, records task-family/semantic-shape/minimum-
variant applicability, and stores canonical report digests for negative
examples.

The resulting `TaskSkillPayload` uses schema 1.1. Every source trace has both a
source-file digest and canonical mining-report digest. The pipeline immediately
creates an `EvolutionArtifact` with `quarantined` status; mining alone cannot
activate it.

## Fresh replay and acceptance

Replay evidence is accepted only when each row binds:

- the actual replay trace SHA-256;
- a deterministically recomputed replay-report SHA-256;
- the exact TaskSkill payload SHA-256.

Duplicate report digests, malformed trace digests, payload mismatches, missing
categories, unsafe effects, verifier false accepts, duplicate-effect risks,
incorrect activation, loss of success, or absent efficiency improvement keep
the artifact quarantined.

The automatically mined candidate passed fresh `original`, `task_family`,
`heldout`, `global_smoke`, and `safety_smoke` runs. It retained task success,
zero policy/verifier/duplicate-effect violations, activation precision 1.0,
and reduced mean System 2 model calls below the one-call baseline. Only then did
the registry mark it accepted.

The accepted registry was persisted and loaded into a new Runtime profile. A
new held-out value (`Ken`) completed with fresh observation, semantic rebinding,
contract construction, preflight, execution, and independent verification,
while the System 2 planner received zero calls.

## Profile loading, fallthrough, and rollback

`AcceptedProfileLoader` hashes the complete registry file, ignores quarantined,
rejected, and rolled-back artifacts, and revalidates every accepted payload
digest before constructing Runtime components. It supplies:

- accepted `TaskSkillPayload` objects to `AcceptedTaskSkillRuntime`;
- accepted `RecoverySkillPayload` and `RecoveryPolicyPatchPayload` objects to
  the bounded recovery policy;
- accepted Runtime feature patches;
- profile digest and loaded artifact ids for `TaskCreated` trace provenance.

The normal CLI `run --accepted-profile ...` path is covered with a real Chromium
pricing run and an accepted RecoverySkill registry. TaskSkill selection emits
`TaskSkillSelectionEvaluated`; activation, step exposure/completion, completion,
and fallthrough retain their explicit trace events. Existing failure tests
prove that a failed later skill step preserves earlier verified checkpoints and
falls through before System 2/clarification. A rolled-back registry is absent
from a freshly loaded profile, and tampered payloads fail closed.

## Verification

Executed in the fixed Python 3.12 environment:

~~~text
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest -q
463 passed

python -m ruff check src tests
All checks passed!

python -m mypy --ignore-missing-imports src
Success: no issues found in 77 source files

git diff --check
passed
~~~

This closes R6 and the remaining Runtime-first M8.5 gate. R7 reproducible
clean-revision public evaluation remains separate: benchmark success may
confirm the architecture but is not used to define or activate learned core
behavior.
