# Benchmark Governance and Anti-Specialization Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** benchmark use, repair admission, evidence claims, and specialization controls
> **Runtime boundary:** [Runtime-First Architecture Boundary](runtime-first-boundary.md)

## 1. Decision

Benchmarks audit Affordance Runtime; they do not own it. Every benchmark-driven
change must improve a generic Runtime contract, invariant, or capability and
must have at least one non-benchmark or metamorphic control.

Product safety profiles and benchmark ablations are physically separate.
Product composition cannot disable task authority, capability intersection,
required approval, freshness/preflight, uncertain-effect protection, or
completion gates. Ablation flags exist only in benchmark composition, are
included in the immutable profile digest, and cannot be selected as a product
fallback.

## 2. Prohibited production dependencies

Runtime core, shared planners, prompts, semantic owners, adapters, recovery,
and verification may not depend on:

- benchmark task ID, seed, family, site, expected answer, or authored solution;
- fixture selectors, coordinates, exact labels, URLs, or DOM layouts;
- task-template branches disguised as “generalist” helpers;
- benchmark reward as progress/completion authority;
- evaluation-only metadata in planner context;
- benchmark-only safety ablations in product composition;
- benchmark replay that falls back to live drivers, credentials, or network.

Moving a special case to a shared module does not make it general.

## 3. Admissible repair form

A benchmark failure may justify a change only when the repair packet contains:

1. typed generic failure cause;
2. owner and contract boundary;
3. non-benchmark reproduction or metamorphic negative control;
4. protected-family/breadth regression plan;
5. safety and uncertain-effect analysis;
6. immutable revision/profile identity;
7. explicit non-claims.

## 4. Evaluation separation

| Result | Meaning |
|---|---|
| Runtime `TaskCompleted` | TaskSpec.success closure committed by RuntimeCommitter |
| external reward/oracle | evaluator judgment for one episode |
| harness diagnostic | injected/internal path evidence |
| benchmark profile result | aggregate for one immutable revision and profile |

These values are reported separately. A passed evaluator cannot retroactively
make an unsafe or unverified Runtime transition valid.

## 5. Profiles and claims

At minimum, reports identify planner profile, provider/model, environment and
asset version, source revision, dirty state, seed set, budgets, missing/unrun
episodes, Runtime result, external result, and official-score claim flag.

Targeted smoke supports diagnosis. Breadth supports regression confidence.
Promotion additionally requires architecture admission, safety, cross-surface
or non-benchmark evidence, and all required checks at the same revision.

Provider/model/tool-schema capability descriptors and their versions/digests
are profile identity. An unknown action, missing required safety feature, or
schema drift is a typed failed run, not permission to downgrade validation or
switch to an unrecorded provider behavior.

A report is incomplete when a required variant is missing. Rates retain their
opportunity denominators, and an expected fail-closed variant must carry the
specified typed failure reason plus its trace signal; `0/0` and unrelated
crashes never count as a passing safety result.

## 6. Data and prompt isolation

Task instructions and page content remain untrusted inputs. Evaluation labels,
expected values, hidden state, and oracle code cannot enter Runtime planning or
verification context unless the public integration contract would provide the
same data in production.

Web pages, email, PDF, DOM, AX, OCR, screenshots, notifications, memory/skills,
and tool outputs cannot become user authority or grant capability, approval,
policy, TaskSpec revision, or control flow. Security fixtures may exercise these
flows, but injected instructions remain observation data throughout the run.

## 7. Optional offline SOTA security profiles

These profiles are required only for a release/paper claim that selects them.
They do not block P4/P5 mainline work.

| Suite | Required report | Governance boundary |
|---|---|---|
| AgentDojo | benign utility, utility-under-attack, targeted ASR | offline state-based injection gate; no online dependency or sole safety proof |
| WASP | benign utility, utility-under-attack, targeted ASR | isolated browser-agent security gate; malicious/evaluator metadata cannot enter product context |
| OSWorld-V2 | pinned manifest, functional checkpoints, applicable collateral-effect probes | reward, partial score, or model judge cannot commit Runtime completion |

These metrics are reported separately with denominators, missing/unrun cases,
attack configuration, and immutable suite/environment identity. A defense that
reduces targeted ASR by making the agent unusable is not promoted without its
benign and under-attack utility.

## 8. Replay and trace privacy

Benchmark replay is strict offline simulation. Missing artifacts fail the replay
instead of invoking a live tool. Simulated receipts are typed separately from
real receipts, and a fresh live rerun receives a new run identity.

Screenshots, prompts, tool output, environment state, evidence, and artifacts
follow explicit minimization, redaction, encryption, access, and retention
policy. A reproducibility claim does not justify copying credentials, private
content, or unrestricted raw observations into reports.

## 9. Selective adoption and complexity boundary

The project adopts benchmark ideas only as offline evaluators: state-based
utility/security functions, adaptive attacks, pinned manifests, functional
checkpoints, and risk-triggered collateral probes. It rejects benchmark reward
as Runtime authority, prompt-only defenses as enforcement, benchmark-specific
branches, and live fallback from replay.

This policy does not require a general taint engine, benchmark microservice,
second semantic graph, or theorem prover. Runtime enforcement remains narrow,
typed, and source-to-effect specific; benchmark harnesses remain outside the
product composition.

## 10. Historical evidence

Old reports remain valid only for their recorded revision/profile. They are not
rewritten when architecture changes and do not define current behavior.

The previous detailed policy is archived at
[maintained-pre-consolidation/benchmark-governance-boundary.md](archive/superseded-2026-08-05/maintained-pre-consolidation/benchmark-governance-boundary.md).
