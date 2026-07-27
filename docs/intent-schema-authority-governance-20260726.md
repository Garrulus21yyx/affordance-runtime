# Intent Schema and Obligation Authority Governance

Status: **normative remediation record**.

Audited revision: bba582c on agent/migrate-runtime-components. SG1 source-ledger
implementation is delivered at the succeeding revision; SG2-SG7 remain open.

This document governs the natural-language intake boundary. It is jointly
normative with:

- [Runtime-First Architecture Boundary](runtime-first-boundary.md);
- [Responsibility Containment Boundary](responsibility-containment-boundary.md);
- [Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md);
- [Task Intake and Generalist Planner](task-intake-and-planner.md).

It answers one specific question:

> Who owns the standard task schema and the sourced obligation graph when a
> provider model interprets a real user request?

The answer is:

> Code owns the vocabulary, canonical graph construction, validation, policy,
> and READY decision. A model may propose semantic interpretations, but it does
> not own the executable schema or authorize the resulting task.

## 1. Audit Verdict

The current implementation is safer than a raw
natural-language-to-model-JSON-to-execution pipeline, but it remains too
dependent on provider graph generation.

### 1.1 Implemented correctly

At the audited revision:

- TaskSpec, SourcedTaskClaim, and TaskObligationSpec are frozen Pydantic
  models owned by Runtime code;
- obligation kind, relation, value source, dependency, terminal, and evidence
  fields use a versioned typed vocabulary;
- IntentDraftValidator owns ambiguity, policy, provenance, and READY
  admission;
- _validate_task_obligation_graph() rejects duplicate ids, dangling
  references, cycles, uncovered required claims, invalid value-source
  combinations, non-sink terminals, and blocking nodes that cannot reach a
  terminal;
- raw-language intake requires a claim ledger and obligation graph before
  constructing TaskSpec;
- provider obligation nodes are decoded as untrusted inputs before they can
  cross the immutable TaskSpec boundary;
- missing or malformed graph output has one bounded repair attempt;
- draft, repair, and coverage share a three-call intake budget;
- repair uses a distinct immutable Prompt identity and is represented in trace;
- unsafe repair, ambiguity, policy conflict, malformed graph, and exhausted
  budget remain fail-closed;
- TaskObligationOutcomeCompiler preserves accepted obligation ids,
  dependencies, values, and evidence requirements into TaskPlan.

These are real protocol and local correctness improvements. They do not prove
that the graph instance is independent of the model.

### 1.2 Current authority gap

The default raw-language path is still:

~~~text
LLMIntentCompiler
  -> model supplies candidate_source_claims
  -> model supplies candidate_obligations
  -> deterministic structural validator
  -> model-backed coverage review
  -> TaskSpec READY
~~~

The same provider class is used for the original draft, bounded repair, and,
by default, the coverage review. Separate Prompt identities improve
traceability but do not create independent semantic authority.

The current deterministic compiler validates a proposed graph. It does not yet
construct a canonical graph from code-owned source units and generic templates.
The default coverage checker may reject a graph, but its COMPLETE result is
currently part of READY admission. A model is therefore still both a major
author of the graph and a semantic completeness judge.

Other concrete gaps:

- LLMIntentDraft requires objective, effects, and success criteria in its
  provider schema, while source claims and obligations remain optional and are
  recovered only after provider output;
- claim statements and evidence requirements remain free-form strings;
- source authorization proves that a source_ref is allowed, but a claim does
  not yet bind to an exact source span or caller-supplied typed fact;
- no generic, code-owned obligation-template registry exists;
- no construction provenance distinguishes rule/template/model/parent nodes in
  the final graph;
- no deterministic source-clause coverage gate can prove that every explicit
  imperative, value, constraint, dependency, and terminal outcome was
  considered before a model review;
- local protected-family evidence shows that valid sourced graph production is
  not reliable enough to be treated as a provider formatting detail.

The correct diagnosis is an intake-architecture gap. It must not be repaired
with benchmark task names, more retries, a larger context window, a larger
model-call budget, or a Prompt-only patch.

## 2. Authority Layers

Four layers must remain distinct.

| Layer | Owner | May use a model | Authority |
| --- | --- | --- | --- |
| Schema vocabulary | Runtime code | no | defines legal fields, enums, unions, versions, and invariants |
| Semantic proposal | reference LM or parent agent | yes | proposes intent, clause labels, claims, dependencies, and ambiguity |
| Canonical compilation | deterministic Runtime compiler | no for commit | creates ids, provenance, typed obligations, edges, evidence contracts, and terminal graph |
| Admission and policy | deterministic validators and policy | no | returns READY, clarification, conflict, or unsupported |

The optional model coverage reviewer has **negative authority only**:

~~~text
COMPLETE
  -> no authority increase; deterministic gates must already pass

NEEDS_CLARIFICATION / UNSUPPORTED
  -> may downgrade or block
~~~

It may never create a missing claim, repair an obligation in place, grant a
capability, or upgrade an otherwise invalid task to READY.

## 3. Target Intake Pipeline

~~~text
UserRequest / parent-supplied typed facts
  -> SourceLedgerBuilder
       exact source units and caller lineage
  -> HybridIntentInterpreter
       deterministic extraction for explicit facts
       plus LM semantic proposals for open language
  -> ClaimCanonicalizer
       canonical ids, source binding, duplicate merge
  -> CanonicalObligationCompiler
       generic templates and validated proposal edges
  -> DeterministicObligationCoverageValidator
       source-to-claim and claim-to-terminal coverage
  -> optional ModelCoverageAuditor
       veto/clarification only
  -> IntentDraftValidator / Policy
  -> immutable TaskSpec
  -> TaskObligationOutcomeCompiler
  -> TaskPlan
~~~

The Coordinator continues to receive only the accepted immutable TaskSpec.
This remediation does not move parsing or compilation logic into the
Coordinator, step planner, BrowserGym adapter, or recovery dispatcher.

## 4. Code-Owned Contracts

### 4.1 Source ledger

Add a bounded source ledger before semantic interpretation:

~~~text
SourceUnit
  source_unit_id
  source_ref
  source_kind
  exact_span_start / exact_span_end when available
  content_sha256
  required_candidate
  sensitivity
~~~

The full source text may remain in the bounded in-memory intake context.
Canonical trace stores hashes, lengths, ids, and redacted excerpts according
to sensitivity policy.

Source-unit identity is deterministic. The model may label or relate a source
unit, but it may not invent a source id. Caller-supplied structured facts use
the same ledger with their original reference.

The first implementation should use simple bounded sentence/list/clause
segmentation plus caller-provided references. It must not become a new
general-purpose NLP parser. When segmentation or conjunction scope is
ambiguous, the result is an explicit ambiguity or model proposal bound to exact
source spans.

**SG1 implementation status:** complete for source identity and bounded
lineage. `SourceLedgerBuilder` deterministically emits a whole-request unit,
at most 32 trimmed request clause units with exact offsets and content hashes,
and metadata-only units for supplied conversation, attachment, target, and
profile references. `LLMIntentCompiler` builds this ledger before any model
call, records only ids/spans/hashes/lengths in trace, exposes the same metadata
to the model, and maps the legacy `raw_text` alias to the canonical whole
request unit. An over-bound request rejects as `UNSUPPORTED` without a model
call. This does not yet make model claim or graph proposals canonical; exact
proposal-unit enforcement and canonical compilation are SG3 and SG2.

### 4.2 Semantic proposal

Replace model ownership of final graph nodes with an explicitly untrusted
proposal:

~~~text
IntentSemanticProposal
  objective proposal
  entity proposals
  effect proposals
  claim proposals[]
    source_unit_ids[]
    proposed kind and statement
  dependency proposals[]
    source_unit_ids[]
    producer / consumer semantic references
  ambiguity proposals[]
~~~

Provider fields are candidates. Provider-generated ids, evidence strings, and
terminal declarations are not canonical.

During migration, the existing LLMIntentDraft.candidate_obligations field may
remain as compatibility input, but it must be normalized through the canonical
compiler and tagged construction_source=model_proposal. Direct copy into
TaskSpec.obligations is the behavior to remove.

### 4.3 Canonical obligation compiler

Add one environment-independent CanonicalObligationCompiler. It owns:

- deterministic claim and obligation ids;
- normalized source provenance;
- generic observation, transformation, local state-change, external effect,
  and verification templates;
- dependency-edge construction;
- value flow from literal, observation, or obligation output;
- typed evidence requirements;
- terminal-node selection;
- construction provenance and compiler version.

The template vocabulary describes dataflow and effect semantics, not benchmark
families:

~~~text
observe resource/value
derive or transform a sourced value
make a local reversible state change
produce an external or irreversible effect
verify a predicate/effect
~~~

There must be no enter-date, text-transform, MiniWoB, calendar, shopping,
social, form-family, or seed-specific template.

For an open-world operation with no applicable generic template, the model or
parent may propose graph relations. The compiler canonicalizes only relations
that bind to known source units, legal typed predicates, legal value flow, and
available evidence classes. Unsupported semantics or unresolved dependency
direction returns clarification/unsupported instead of inventing a graph.

**SG2 foundation status:** `CanonicalObligationCompiler` now constructs stable
claim/obligation ids, canonical provenance, generic read/effect terminal
relations, and typed evidence only from source-ledger-bound inputs. Unknown
effect or evidence source units reject before graph construction. The flat raw
model-draft path is now migrated to this compiler; the remaining authority
replacement is limited to bounded multi-stage relation/value-flow templates.

**SG3/SG5 implementation status:** model and parent claim/obligation IDs are
proposal-local handles. Before either semantic proposal can cross the
`TaskSpec` boundary, Runtime validates every referenced source unit and
reconstructs canonical graph nodes, identities, claim edges, dependencies,
obligation-output references, and typed evidence. A proposal may contribute
only a validated legal relation/value-flow/edge; it never contributes a graph
node instance or free-form evidence contract. The model coverage reviewer
receives this canonical graph. `ParentSemanticProposalCompiler` is model-free
but applies the same ledger, deterministic validation, policy, and immutable
admission boundary; a complete typed TaskSpec remains a separate API. A legacy
reviewer-reference bridge is replay compatibility only and cannot place a
provider handle in `TaskSpec`. SG4 and SG5 are complete.

**SG4 implementation status:** `DeterministicTaskObligationCoverageValidator`
proves known SourceLedger source-unit lineage into required claims and a
structurally valid obligation graph with a reachable terminal. It runs before
any model audit. The model auditor may only veto, request clarification, or
report unsupported semantics; `COMPLETE` cannot upgrade a deterministically
invalid proposal, and temporary auditor unavailability cannot reject one that
the deterministic admission path has already accepted. SG5 remains responsible
for removing the remaining proposal-shape compatibility path in favor of
canonical graph construction.

**SG5 migration status:** `CanonicalObligationCompiler` constructs a generic
flat terminal graph directly from source-bound requested effects and
reconstructs multi-stage proposal relations into new canonical graph nodes.
The compiler derives stable ids, canonical provenance, dependency/value-flow
references, and typed independent evidence; it does not retain a proposal
node instance or its free-form evidence text. Both `ParentSemanticProposalCompiler`
and the model-draft entrypoint use this boundary. A coverage-auditor `COMPLETE`
is advisory only and does not provide graph admission authority, while typed
non-complete findings remain bounded vetoes.

**SG6 local status:** ordinary non-BrowserGym intake has a held-out sequential
value-flow conformance request using unrelated agreement/records vocabulary.
It traverses model intake, canonical multi-stage construction, deterministic
coverage, and the optional independent audit without benchmark-specific
vocabulary. Source-clause omission, unknown-source, stale-lineage, ambiguity,
and typed-auditor-veto controls remain negative evidence. This local gate does
not authorize benchmark, provider, PR-breadth, diagnostic, nightly, or release
evaluation.

### 4.4 Typed evidence requirements

Free-form evidence descriptions are useful for explanation but should not be
the only verifier contract. Introduce a typed requirement envelope:

~~~text
EvidenceRequirement
  kind: dom_state | accessibility_state | visual_state | api_state |
        file_receipt | download_receipt | device_state | human_confirmation
  subject
  relation
  value_ref
  minimum_strength
  source_constraints[]
~~~

Human-readable text may remain as a description. READY and terminal readiness
must depend on typed requirements that a verifier port can resolve.

## 5. Hybrid Interpretation Policy

The target is hybrid, not model-free and not model-owned.

### Rule-first path

Use deterministic normalization when authority is explicit:

- caller-supplied typed TaskSpec or facts;
- explicit literal values and quoted identifiers;
- explicit negative constraints and forbidden effects;
- explicit operation/effect class already present in a structured parent call;
- generic dataflow/effect templates with unambiguous source binding.

### Model-assisted path

Use a model for:

- paraphrase and open-language semantic classification;
- entity and reference proposals;
- genuinely ambiguous dependency interpretation;
- non-trivial task decomposition;
- open-world success-condition proposals.

Every model proposal must cite known source-unit ids. Low confidence,
conflicting proposals, missing source coverage, or safety-relevant ambiguity
must remain visible.

### Parent-agent path

A parent may submit a complete typed TaskSpec or semantic proposal. It does not
bypass schema validation, policy, capability intersection, terminal evidence,
or stale task revision checks.

### Benchmark path

Benchmark adapters should submit a canonical `TaskSpec` when evaluating the
Runtime itself. Raw-language intake is a separately identified intake
evaluation and may not be merged into a Runtime score. No protected family,
PR breadth, diagnostic, nightly, or release run is authorized until SG1-SG6
have passed their local and held-out gates.
