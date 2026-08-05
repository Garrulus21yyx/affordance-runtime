# Documentation Governance

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** documentation authority, lifecycle, discovery, archival, and maintenance
> **Current architecture:** [Task Contract-centered authoritative architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Machine-readable index:** [documentation-manifest.yaml](documentation-manifest.yaml)

## 1. One discovery path

Humans and AI agents start at [Documentation Index](README.md), then use the
manifest to identify a document's role. Filename recency, file length, search
ranking, backlinks, and the word “architecture” do not establish authority.

Authority precedence is:

```text
authoritative target architecture
→ authoritative evolution plan
→ current implementation truth / active queue
→ normative subordinate policy or contract
→ maintained reference
→ immutable evidence or admission record
→ archived history
```

Target design and implementation truth are deliberately separate. A target
contract is not implemented merely because it is authoritative. A current code
fact does not redefine the target merely because compatibility still exists.

Within the authoritative architecture, readers use the fixed semantic layers:

```text
§0 architecture laws and current amendments
→ normative contracts and authority matrix
→ migration/deletion gates
→ acceptance invariants and source mappings
```

Schema examples, migration tables, tests, and historical mappings do not mean
every named logical owner requires a class, service, store, queue, or model
call. This internal layering avoids creating a third authority merely to make a
large specification easier to search.

## 2. Lifecycle classes

| Lifecycle | Use | May define current semantics? |
|---|---|---:|
| `current authoritative` | exactly one target architecture and one evolution plan | yes |
| `current status` | factual implementation state and active work | no target redefinition |
| `current normative` | one bounded subordinate responsibility | only within its scope |
| `current reference` | scenarios, integration guidance, threat models | no |
| `immutable record` | evidence and change-admission at a fixed revision | no |
| `archived` | superseded design, audit, plan, report, or log | no |
| `redirect` | stable legacy path pointing to archive and replacement | no |

## 3. Current terminology contract

Maintained documents use the following meanings:

- `SourceEnvelope` is the always-on lightweight source identity/version record.
- `SourceAnchor` selectively binds material fields to legal source spans.
- `SemanticAudit` is optional, risk-triggered, and pass/veto/clarify-only.
- `TaskSpecAuthority` is the only Task Meaning Write Barrier.
- `SourceContextView` is bounded, read-only, source-bound, and always `context_only`; visibility is not authority.
- `TaskRequirement` gives each material requirement one canonical typed identity.
- `TaskSpec` is the stable user authorization and completion contract; its objective is explanatory only.
- `TaskPlan<StepSpec>` is a replaceable, observation-grounded milestone graph.
- `Canonical UnifiedObservation` is the current observed semantic authority.
- `ActionChoiceCatalog` is Runtime-owned and complete before model presentation.
- `ActionContract` is one grounded, gated, expiring transaction.
- `LoopEvaluator` performs typed effect/step/task evaluation inside the loop.
- `TaskCompletionEvaluator` owns pure TaskSpec.success closure semantics.
- required OutputSpec materialization/source binding is part of task closure.
- `RuntimeCommitter` is the only writer of authoritative progress and terminal state.

Historical documents may contain superseded vocabulary. Their archive status is
the disambiguation mechanism; historical prose is not rewritten to look current.

## 4. Archival rule

Archive a document when its primary purpose is a completed plan, dated audit,
superseded design, frozen implementation-baseline report, or historical origin
comparison. Preserve the complete content and record:

- original path;
- archive date and reason;
- current replacement;
- whether a stable redirect remains.

Evidence and change-admission records are not “outdated documentation.” They
remain in their dedicated directories, immutable and non-authoritative.

## 5. Simple mechanical gate

The documentation test checks only:

1. manifest paths and lifecycle values;
2. exactly one authoritative architecture and one evolution plan;
3. current README authority links do not target archive;
4. archive collection and redirect targets exist;
5. relative links in maintained Markdown resolve.

It does not scan archive/evidence/admission prose for deprecated words, enforce
writing style, infer semantic equivalence, or block historical citations.

## 6. Update protocol

When architecture changes:

1. update the authoritative architecture and evolution plan together;
2. update implementation status only with factual evidence;
3. update the active queue with migration dependencies and exit gates;
4. update affected subordinate contract documents;
5. archive replaced plans/audits instead of layering another authority notice;
6. update README and the manifest in the same change;
7. run the simple documentation gate and architecture governance tests.
