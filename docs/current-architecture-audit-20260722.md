# Current Architecture Audit - 2026-07-22

## 1. Scope and Reviewed Revision

This audit reviews remote branch agent/migrate-runtime-components at:

~~~text
0272765ae596902e71697e7ab6e4603230dd6d3a
Complete unified routing and BrowserGym reliability [skip ci]
~~~

The branch matched its remote and the worktree was clean during review. The
audit compares implementation with the project plan, current implementation
plan, implementation status, milestone evidence, and the normative
runtime-first architecture boundary.

## 2. Executive Assessment

The repository has progressed beyond an executable skeleton. Its ActionContract,
preflight, execution, post-observation verification, recovery, trace,
BrowserGym bridge, gesture binding, and declarative evolution components are
substantive.

The complete declared product loop is not yet closed on the generic Runtime main
path. The highest-risk gaps are semantic rather than provider-related:

~~~text
active subgoal or SkillStep
  -> required perception
  -> target-specific evidence
  -> route and ActionContract
  -> matching postcondition evidence
  -> verified progress
~~~

Several local components and controlled experiments exist, but their status was
promoted to milestone completion before normal-entrypoint wiring and
criteria-bound evidence were complete.

| Area | Assessment |
| --- | --- |
| Contract execution harness | strong |
| Policy, preflight, and uncertain-effect handling | strong |
| Recovery cascade and policy replay | strong |
| BrowserGym adapter and matrix machinery | medium to strong |
| Task-plan model and controlled sequencing | medium |
| Generic task-aware multimodal perception | partial |
| Target-specific adaptive route calibration | partial |
| Criteria-bound subgoal and SkillStep progress | incorrect |
| Automatic trace-to-TaskSkill learning | partial |
| Current-revision public evidence reproducibility | partial |
| Responsibility containment | weakening |

## 3. Verification Results

Executed in the provisioned BrowserGym Python 3.12 environment:

~~~text
pytest -q
401 passed

ruff check src tests scripts
All checks passed
~~~

Full mypy did not pass. Four optional-integration errors remain around WorkArena,
BrowserGym package typing, and LangGraph availability in that environment.

The latest commit includes [skip ci], so local verification is not equivalent to
a current GitHub Actions result.

## 4. Critical Findings

### F-01 - Subgoal verification is not bound to the subgoal

Severity: critical.

VerifierBackedSubgoalVerifier discards SubgoalSpec. Any passed evidence item can
complete the active subgoal. It does not match success criteria, evidence
requirements, expected effect, semantic target, or observation freshness. The
Coordinator then commits subgoal progress from that result.

Impact:

- an unrelated successful action can complete the wrong subgoal;
- task-level early completion may be falsely accepted;
- TaskPlan evidence is not trustworthy;
- TaskSkill checkpoints inherit the same semantic weakness.

Required repair:

Create one shared CriteriaEvidenceMatcher used by task subgoals, SkillSteps,
task completion, and benchmark-independent verifier assertions. It must return a
structured match report, not arbitrary evidence strings.

Exit evidence:

- unrelated passed evidence is rejected;
- partial criteria remain pending;
- stale evidence is rejected;
- all mandatory evidence must be present;
- one action satisfies multiple criteria only through explicit matches.

Resolution (2026-07-22): the shared matcher, typed identities, current-epoch
and strong-evidence gates, structured reports, and trace links close F-01/R1.
Generic negative controls cover unrelated, partial, stale, weak, unbound, and
explicitly multi-linked evidence. F-02/R2 is also closed by context-rich
planning evidence; Runtime-first R3 has since closed with generic and real
Chromium evidence, while R4-R5 remain open.

### F-02 - Task-level planning is a controlled component, not a real main path

Severity: high.

Resolution status: closed on 2026-07-22. See
`evidence/runtime-r2-task-planning-context-20260722.md`.

TaskPlannerPort receives only TaskSpec and state_version. Replanning does not
receive current observation summary, completed evidence, failure summary, active
subgoal, remaining budget, or prior plan lineage. Generated plan versions remain
fixed at version 1.

Task planning is wired mainly into tests and a controlled ablation. BrowserGym,
the primary CLI, and the natural-language local E2E path do not consistently use
the task-level planner.

Required repair:

Define TaskPlanningContext with:

~~~text
TaskSpec revision
current state and plan versions
current environment and affordance summary
active and completed subgoals
criteria evidence ledger
failure and recovery summary
disproved assumptions
remaining budgets
~~~

Wire the optional PlanningRouter into the normal reference application and one
non-BrowserGym real Chromium scenario. Increment plan_version and record
supersedes_plan_id.

### F-03 - Generic task-aware multimodal perception — resolved for R3

Severity: resolved Runtime gate; legacy adapter cleanup remains under R5.

Coordinator now derives requirements from TaskSpec and the complete active
SubgoalSpec, then passes them to BrowserSession. BrowserSession captures bounded
DOM/accessibility/SVG/screenshot evidence, calls the generic bounded visual
region port, emits current typed candidates and sourced assertions, and binds
semantic point activation through the trusted visual binder.

Required repair:

Completed. Ordinary BrowserGym point-region observation also reuses the generic
orchestrator. BrowserGym drag geometry normalization, backend action encoding,
and compatibility fallback helpers remain adapter-local and are audited again
in R5.

Exit evidence:

- a non-BrowserGym Chromium task requests visual and spatial evidence;
- DOM, SVG, and screenshot share one observation epoch;
- the generic visual grounder produces a typed candidate;
- RoutePlanner selects it;
- ContractBuilder creates a fresh contract;
- execution and independent verification succeed.

Evidence: `evidence/runtime-r3-generic-perception-20260722.md`.

### F-04 - Browser source assertion and active perception — resolved for R3

Severity: resolved for the generic browser observation path.

Generic BrowserSession now produces property-specific current assertions,
arbitrates them, and implements bounded `capture_targeted` by creating a fresh
coherent epoch with new leases, fingerprints, and screenshot references.
Persistent SVG/visual position disagreement remains unresolved and blocks route
selection rather than being averaged or silently accepted.

Required repair:

Completed for browser visibility, enabled state, semantic label, and spatial
location. Cross-surface device/postcondition calibration remains part of R4 and
does not weaken the R3 browser conflict boundary.

### F-05 - Route ranking is not verifier-calibrated as planned

Severity: high.

Current ranking uses static confidence, latency, cost, and source preference. It
does not use verifier-backed historical success scoped by environment family,
action kind, and source. A legacy backend tracker uses execution receipt success
and is not the required label.

Required repair:

Introduce RouteOutcome only after postcondition verification. Scope route
statistics by generic environment capability profile, action kind, source,
executor, and verifier plan. Official reward and receipt success cannot be
route-learning labels.

Evidence requirements must be candidate- and target-specific. Page-global
visual evidence must not make an unrelated DOM candidate satisfy a visual
requirement.

### F-06 - Semantic entity alignment is weaker than planned

Severity: medium to high.

Current fusion uses exact normalized role, label, action, and container context.
It does not yet apply the planned geometry evidence. Conservative duplicate
handling prevents unsafe fusion, but often also prevents corresponding
cross-source duplicates from becoming one semantic target.

Required repair:

Use staged alignment:

1. stable explicit identity when available;
2. role, name, action, and container compatibility;
3. geometry overlap within one observation epoch;
4. conflict when state assertions disagree;
5. separate entities when confidence is insufficient.

Do not force uncertain fusion to improve route count.

### F-07 - Benchmark semantics have leaked into shared modules

Severity: high governance risk.

No direct task-id, fixed-coordinate, or selector answer table was found in the
generalist planner. However, the planner contains many MiniWoB-shaped semantic
compilers for calendar, social collection controls, food ordering, trees, SVG
items, dates, sorting, and drag families. Shared DOM code also knows BrowserGym
set-of-marks and authored task-family semantics.

This is soft benchmark specialization. It can increase family scores without
proving an open-world Runtime architecture.

Required repair:

- keep BrowserGym attributes and episode semantics in BrowserGym adapters;
- move environment-independent behavior into a typed compiler registry;
- require applicability, evidence, negative examples, and non-BrowserGym tests;
- remove unconditional calendar, social, order, and tree family logic from
  shared DOM and generalist planner modules;
- run an ablation with benchmark profiles disabled.

### F-08 - TaskSkill mining is not an automatic trace-to-skill loop

Severity: high.

VerifiedSemanticTrace, SemanticTraceNormalizer, and TaskSkillMiner exist, but no
production extractor builds them from canonical JSONL Runtime traces. Current
tests construct semantic traces manually.

Skill activation matching and checkpoints are also weaker than the declared
typed trigger, postcondition, and evidence model.

Required repair:

~~~text
persisted accepted run traces
  -> trace validator
  -> semantic step extractor
  -> cross-variant alignment
  -> parameter and negative-example mining
  -> quarantined TaskSkill
  -> held-out fresh Runtime replay
  -> accepted registry artifact
  -> explicit Runtime profile loading
~~~

Replay evidence must bind trace digest, Runtime revision, environment identity,
and report digest. Caller-supplied booleans are insufficient.

### F-09 - Recovery Skill is executable but not a default knowledge path

Severity: medium.

CandidateRuntimeProfile can load a digest-validated RecoverySkill and apply
bounded steps by FailureSignature while preserving inspect-before-repeat. This
is a real executable component.

Normal CLI and Runtime entrypoints do not automatically load an accepted
registry profile. Current usage is concentrated in replay, benchmark, and tests.

Required repair:

Add an explicit runtime-profile reference-app configuration. Record loaded
artifact ids and digests in run metadata. Never silently activate new accepted
knowledge.

### F-10 - Public benchmark and Docker environments are split

Severity: high reproducibility risk.

The web extra pins Playwright 1.61 while BrowserGym 0.14.3 requires Playwright
1.44 in the provisioned environment. The Docker image installs the web profile,
not BrowserGym. Compose reproduces local fixture and WoT evidence but not the
official BrowserGym nightly/release path.

Required repair:

Use explicit compatible profiles:

~~~text
runtime-web
runtime-browsergym-0.14.3
~~~

Each profile records Python, Playwright, browser, BrowserGym, model, fixture,
manifest, and source digests. Add a BrowserGym container or documented isolated
environment that can execute smoke and a bounded matrix.

### F-11 - Evidence claims are not frozen at current HEAD

Severity: high governance risk.

The frozen 300/300 nightly belongs to v112 and temporary artifacts. The later
v155 repair evidence is targeted and breadth diagnostic evidence, not a new
immutable nightly or release. The latest commit skipped CI.

Required repair:

Claims must identify exact immutable commit, clean or dirty source state,
manifest and environment digest, retained raw artifacts, evidence level, and
acceptance failures. Historical results must not be presented as current-HEAD
verification.

### F-12 - Responsibility concentration is architectural debt

Severity: medium.

Approximate source sizes:

~~~text
coordinator.py          1817 lines
generalist_planner.py   2796 lines
browsergym.py           2307 lines
~~~

The Coordinator owns task-plan lifecycle, TaskSkill progress, contract execution,
policy, verification, recovery, active perception, and trace details. The
generalist planner combines provider context, schema binding, many rule
compilers, and benchmark-shaped semantics.

Extract internal collaborators without creating services:

~~~text
TaskPlanLifecycle
PerceptionSession
ContractExecutionLoop
RecoveryHandler
CriteriaEvidenceMatcher

GeneralistActionPlanner
SemanticCompilerRegistry
PlannerContextBuilder

BrowserGymObserver
BrowserGymActionEncoder
BrowserGymEpisodeRunner
BrowserGymReportAdapter
~~~

Coordinator remains the only authoritative state writer.

### F-13 - Core payload typing remains incomplete

Severity: medium.

Typed GroundingCandidate payloads exist, but core Affordance locator, state, and
payload fields still contain broad dictionaries, and selected candidates are
translated back through source affordances.

Introduce tagged source payloads at serialization boundaries and make
ActionContract carry the selected typed binding. Preserve compatibility
temporarily, but do not claim the current implementation never collapses into
opaque locators.

## 5. What Is Genuinely Complete

This audit does not invalidate:

- immutable ActionContract and canonical validity binding;
- one effectful action lane per run;
- capability, approval, preflight, and immediate re-observation;
- separate execution receipt and postcondition verification;
- core dual-target GestureBinding with epoch, revision, lease, source,
  destination, overlay, and fingerprint checks;
- backend-only BrowserGym gesture encoding;
- safe candidate exclusion and fresh-contract fallback lineage;
- uncertain-effect post-state inspection before repeat;
- RecoveryIncident, FailureSignature, no-progress and oscillation detection,
  bounded cascade, replayed RecoveryPolicyPatch, and rollback;
- JSONL trace and artifact-backed local scenario evidence;
- useful BrowserGym matrix, checkpoint, acceptance, and diagnostic machinery;
- 401 passing tests and clean Ruff results at the reviewed revision.

These form a strong base. The required next work is semantic integration and
claim correction, not a rewrite.

## 6. Corrected Milestone Status

| Milestone | Corrected status | Reason |
| --- | --- | --- |
| M0-M8.1 | done | existing scope remains supported |
| M8.2A | done | typed intake and action-level generalist boundary exist |
| M8.2B | in progress | residual release and external suites remain |
| M8.3 | done for RecoveryPolicyPatch | recovery cascade and controlled policy replay are real |
| M8.4 | done | criteria-bound planning, context-rich replanning, monotonic lineage, flat routing, and a real non-BrowserGym reference entrypoint are proven |
| M8.5 | in progress | route and gesture components exist; generic perception, calibrated routing, trace mining, and strict checkpoints remain |
| M9 | pending and conditional | no change |

## 7. Detailed Forward Plan

### Phase R0 - Claim and Boundary Correction

Deliverables:

- adopt runtime-first-boundary.md;
- correct README, project plan, current plan, and status matrix;
- mark M8.4 and M8.5 in progress;
- label benchmark evidence by immutable revision and evidence level;
- update test and type-check statements.

Exit:

- no current document claims generic completion from custom diagnostics or a
  targeted benchmark family;
- all status claims point to current or clearly historical evidence.

### Phase R1 - Criteria-Bound Progress

Status: complete on 2026-07-22. See
`evidence/runtime-r1-criteria-evidence-20260722.md`.

Deliverables:

- typed criteria and evidence identity where necessary;
- CriteriaEvidenceMatcher;
- SubgoalVerificationReport;
- SkillStepVerificationReport;
- task completion based on matched mandatory criteria;
- negative tests for unrelated, partial, stale, and weak evidence.

Exit:

- arbitrary passed evidence cannot advance subgoal or skill progress;
- TaskPlan and TaskSkill use one matcher;
- trace records criterion-to-evidence links.

### Phase R2 - Context-Rich Task Planning

Status: complete on 2026-07-22. See
`evidence/runtime-r2-task-planning-context-20260722.md`.

Deliverables:

- TaskPlanningContext;
- plan version and supersession lineage;
- failure, recovery, evidence, environment, and budget summaries;
- normal reference-app integration;
- one real non-BrowserGym multi-stage task;
- rerun Flat, Always-plan, and Adaptive with a semantic oracle.

Exit:

- replanning changes behavior from disproved assumptions or evidence;
- verified progress survives plan versions;
- simple tasks remain flat;
- no planner emits selectors, coordinates, backend strings, or authority.

### Phase R3 - Generic Perception Orchestration — Runtime exit complete

Deliverables:

- generic PerceptionOrchestratorPort;
- TaskSpec/SubgoalSpec to PerceptionRequirements derivation;
- generic DOM, accessibility, SVG, and screenshot observation bundle;
- generic visual region and grounding adapters;
- sourced assertions and active perception in BrowserSession;
- BrowserGym observer reduced to normalization.

Exit:

- one non-BrowserGym visual-primary task succeeds;
- one DOM-primary task escalates to visual after a generic failure;
- one source conflict triggers targeted perception or safe inconclusive;
- all routes use one coherent epoch and the same Coordinator.

All four exit cases are covered by generic unit/integration tests plus a public
`BrowserSession.launch` real-Chromium run; see
`evidence/runtime-r3-generic-perception-20260722.md`. Full legacy BrowserGym
observer removal remains an R5 de-specialization item rather than a reason to
keep the generic Runtime path open.

### Phase R4 - Target-Specific Unified Routing

Deliverables:

- geometry-aware conservative semantic entity resolver;
- target-specific evidence requirements;
- RouteOutcome emitted after verification;
- verifier-backed route calibration;
- environment, action, and source scoped statistics;
- no receipt- or reward-trained route policy.

Exit:

- one semantic target exposes multiple source candidates;
- unrelated global evidence cannot satisfy a candidate gate;
- routing improves cost or success on held-out non-BrowserGym variants;
- safety and false-accept rates do not regress.

### Phase R5 - De-Specialize Planner and DOM

Deliverables:

- BrowserGym marker handling moved to its observation adapter;
- generic authored-interactive extension mechanism where necessary;
- SemanticCompilerRegistry with typed applicability and evidence;
- benchmark-family logic removed from unconditional shared paths;
- non-BrowserGym conformance and negative-control corpus;
- benchmark-profile-disabled ablation.

Exit:

- core contains no BrowserGym task family or action syntax;
- generic rules have non-BrowserGym evidence;
- benchmark gains persist through the Runtime path;
- disabling benchmark profiles does not remove declared Runtime capabilities.

### Phase R6 - Complete Harness Learning

Deliverables:

- canonical trace validator and semantic step extractor;
- cross-run success clustering and parameter mining;
- applicability and negative-example mining;
- digest-bound replay evidence;
- accepted profile loader for TaskSkill and RecoverySkill;
- explicit System 1 activation and fallthrough trace.

Exit:

- at least three independent verified traces across two variants produce one
  quarantined TaskSkill automatically;
- held-out replay proves success and reduced model calls or latency;
- skill failure preserves progress and enters recovery or System 2;
- rollback removes the artifact from a fresh profile.

### Phase R7 - Reproducible Public Evaluation

Deliverables:

- compatible web and BrowserGym environment profiles;
- BrowserGym Docker or isolated environment manifest;
- full mypy policy for optional integrations;
- clean current-HEAD smoke, PR, nightly, and residual release runs;
- retained raw reports and summary artifacts.

Exit:

- current immutable revision has CI evidence;
- nightly and release claims are reproducible;
- acceptance failures remain visible;
- BrowserGym success is evaluation, not architecture completion.

### Phase R8 - Internal Module Containment

Deliverables:

- extract Coordinator internal collaborators;
- split generalist planner context, LM, and rule registry;
- split BrowserGym observer, encoder, runner, and reporting;
- migrate typed payloads with compatibility tests.

Exit:

- one authoritative Coordinator remains;
- no service, queue, or distributed state is introduced;
- module ownership matches runtime-first-boundary.md;
- behavior and trace schemas remain stable.

## 8. Required Evaluation Matrix

| Layer | Required evidence |
| --- | --- |
| Unit | contract or invariant without BrowserGym import |
| Generic integration | local Playwright, synthetic visual, WoT, or port fixture |
| Negative control | unrelated elements and actions remain unavailable |
| Safety | policy, uncertain effect, duplicate effect, and false accept |
| Adapter conformance | BrowserGym translation only |
| Targeted replay | original failure family |
| Breadth | PR or diagnostic breadth |
| Promotion | immutable nightly or release when applicable |

Benchmark task-family pass rate alone cannot close an architecture milestone.

## 9. Immediate Ordered Queue

1. **Complete:** implement CriteriaEvidenceMatcher and repair Subgoal and
   SkillStep progress.
2. **Complete:** define and wire TaskPlanningContext plus plan lineage.
3. **Next:** pass PerceptionRequirements through generic Coordinator and BrowserSession.
4. Create executable generic visual candidates outside BrowserGym.
5. Move benchmark semantics out of shared DOM and planner modules.
6. Add verifier-backed route outcomes and target-specific evidence gates.
7. Connect canonical traces to TaskSkill mining and explicit profile loading.
8. Resolve Playwright profile incompatibility and freeze current-HEAD evidence.
9. Split oversized modules after semantic behavior is protected by tests.

## 10. Final Governance Judgment

Continue the current repository; do not merge it back into the old action-system
architecture and do not rewrite the Runtime.

The next gains must strengthen the generic semantic path rather than add more
benchmark-family rules:

~~~text
one Runtime capability
  -> one generic invariant
  -> one non-benchmark proof
  -> one adapter conformance proof
  -> one external benchmark confirmation
~~~

BrowserGym remains important only as an external pressure test and conformance
consumer of the Runtime main path.
