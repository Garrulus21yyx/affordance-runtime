# Integrations

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** parent-agent, API, CLI, and UI boundary

## 1. Request boundary

Canonical integrations submit a TaskGoal and may attach an optional
EvaluationSpec or explicit strict-ingestion profile. They do not submit raw
selectors, coordinates, backend bindings/endpoints, file paths, approval tokens,
milestone satisfaction, or completion facts.

During migration, legacy TaskSpec-based endpoints may project one-way into new
contracts. New core code never imports those legacy request types.

## 2. Runtime outcomes

Integrations handle:

```text
Done(result)
WaitingUser(question)
WaitingConfirmation(confirmation_subject_id, semantic_summary, consequences)
Failed(reason)
```

Confirmation UX must display the concrete semantic effect/consequences and
return a decision bound to confirmation-subject identity. Runtime reobserves and
rebinds before execution; binding-only changes do not require another prompt.

## 3. Observation and action privacy

External APIs may expose AgentWorldView and privacy-safe ControlTransition
summaries. They do not
expose credentials, selectors, backend handles, signed URLs, or unrestricted
screenshots/trace by default.

## 4. Cancellation and resume

Cancellation can stop before the next primitive action. A cancel racing with an
effectful dispatch cannot claim the action did not occur; the Runtime returns
SENT_UNKNOWN and requests typed fresh acquisition when supported. Acquisition
failure does not authorize replay. Current target does not promise process-
crash checkpoint/resume.

## 5. Benchmark integrations

Benchmark adapters translate environments into the same world/action/evaluation
contracts. They cannot pass hidden expected answers or fixture metadata into
the policy or Runtime.

## 6. Evidence-gated Vision providers

Vision is configured as independent provider roles, not one provider that
implicitly owns observation, identity and execution:

- open-world visual entity proposal: disabled by default. Set
  `VISUAL_REGION_PROVIDER=omniparser` and `OMNIPARSER_BASE_URL` to use the thin
  official `POST /parse/` adapter. `OMNIPARSER_API_KEY` and
  `OMNIPARSER_MODEL_ID` are optional. Setting `VISUAL_REGION_PROVIDER=vlm`
  explicitly enables the compatible VLM proposer instead.
- DOM-candidate visual disambiguation: when the main Agent consumes screenshot
  plus AX/DOM marks, it selects the semantic action and one offered `E*` ref in
  the same policy call. The environment does not make a redundant pre-policy
  disambiguation call. Policies without multimodal marked-choice support may
  use the bounded disambiguator port, which can return only an offered E-ref or
  `null`. Dense marks are numbered in stable visual reading order and their
  labels are rendered outside tiny targets. A singleton semantic operation
  carries its sole target in the ephemeral Runtime binding, so the model does
  not serialize a redundant E-ref or operation name.
- open-vocabulary set classification: a bounded classifier (GLM under the
  current Zhipu profile) receives one frozen marked screenshot plus the full
  supplied E-ref inventory and returns every ref exactly once as
  `true/false/unknown`. Missing, duplicate or invented refs invalidate the
  response. The classifier cannot declare scope completeness; BrowserGym's
  structured inventory owns viewport closure, while Runtime owns membership,
  item-effect obligations, stability and the completion certificate.
- point grounding: GLM/ShowUI/UI-TARS-style adapters remain explicit offline
  grounding or legacy-compatibility benchmark arms. They are not offered as a
  BrowserGym target-loop capability and cannot create an ActionBinding.

The target-loop BrowserGym path uses only explicitly configured region,
E-ref disambiguation, or predicate-classification providers. A legacy benchmark option may still build
a GLM point adapter for isolated comparison, but the target-loop environment
does not call or advertise it. The OmniParser
adapter consumes the current server schema documented by the
[official OmniParser repository](https://github.com/microsoft/OmniParser/tree/master/omnitool/omniparserserver).
It imports none of OmniTool's planner, memory or executor.

All provider outputs remain observations or proposals. Runtime's typed visual
gate decides whether a call occurs; `EntityCorrespondence`/`WorldFusion` own
identity; action-space admission and currentness own DOM execution authority.
Region-proposer action claims are discarded at all current adapter boundaries;
an unmatched V-ref remains observation-only.

The BrowserGym adapter may publish current visible computed-style color family
as `appearance.color_family` and current selected state. It does not promote a
repeated-leaf appearance heuristic into an exact count, and does not expose
fixture `data-*` answers, selectors, CSS classes, or new executable bindings.
The main Agent may explicitly establish a typed `FactEquals` objective from
bounded public facts. Catalog consumes only the Runtime control directive and
never branches on a color, task name or benchmark case. Runtime admission and
DOM identity remain authoritative.

Regular-lattice semantics follow the same rule. Current element bboxes and
visible numeric label bboxes may derive row/column membership and Cartesian
values. The main Agent can select one public coordinate value through the same
generic typed objective tool; the reducer then exposes only the admitted member
action and privately retains its DOM action ID. It emits no model coordinate
or point. Incomplete, irregular, duplicate, ambiguous or multiple-grid evidence
does not activate this closure.
