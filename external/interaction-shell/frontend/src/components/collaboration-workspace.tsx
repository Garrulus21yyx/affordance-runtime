"use client";

import {
  AlertTriangle,
  ArrowDownToLine,
  Check,
  CheckCircle2,
  CircleHelp,
  Eye,
  FileCheck2,
  GitCompareArrows,
  Hand,
  ListChecks,
  Maximize2,
  MessageSquareText,
  Pause,
  Play,
  RotateCcw,
  Send,
  ShieldAlert,
  Square,
} from "lucide-react";
import { FormEvent, ReactNode, useState } from "react";
import { Streamdown } from "streamdown";
import type {
  FeedBlock,
  InteractionFieldValue,
  InteractionOption,
  InteractionRequest,
  InteractionResponse,
  PublicArtifact,
} from "@/generated/types.gen";
import type { ShellViewModel } from "@/session/view-model";

function assertNever(value: never): never {
  throw new Error(`Unhandled presentation variant: ${String(value)}`);
}

function readableTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function AssistantMessage({ children }: { children: string }) {
  return (
    <div className="assistant-prose">
      <Streamdown mode="static">
        {children}
      </Streamdown>
    </div>
  );
}

type GoalBlock = Extract<FeedBlock, { kind: "goal_accepted" }>;

export function ConstraintChips({ constraints }: { constraints: string[] }) {
  if (!constraints.length) return null;
  return (
    <ul className="constraint-chips" aria-label="目标约束">
      {constraints.map((constraint, index) => <li key={`${index}:${constraint}`}>{constraint}</li>)}
    </ul>
  );
}

export function GoalSummary({ goal }: { goal: GoalBlock }) {
  return (
    <article className="goal-summary" data-testid="goal-summary">
      <div className="feed-card-heading">
        <span className="feed-icon goal"><ListChecks size={15} /></span>
        <div><small>目标已确认 · revision {goal.task_revision}</small><h3>{goal.summary}</h3></div>
      </div>
      <ConstraintChips constraints={goal.constraints} />
    </article>
  );
}

const evidenceNames = {
  structural: "结构证据",
  visual: "视觉证据",
  frame_change: "画面变化",
  mixed: "结构 + 视觉证据",
  unknown: "证据状态",
} as const;

const evidenceStatus = {
  observed: "已确认",
  partial: "部分确认",
  unknown: "无法确认",
  failed: "检查失败",
  stale: "证据已过期，正在重新检查",
} as const;

export function EvidenceBadge({
  kind,
  status,
  confidence,
  count,
}: {
  kind: keyof typeof evidenceNames;
  status: keyof typeof evidenceStatus;
  confidence: number | null;
  count: number;
}) {
  return (
    <span className={`evidence-badge ${status}`} data-testid="evidence-badge">
      <Eye size={13} />
      <span>{evidenceNames[kind]} · {evidenceStatus[status]}</span>
      {confidence !== null && <b>{Math.round(confidence * 100)}%</b>}
      {count > 0 && <em>{count}</em>}
    </span>
  );
}

export function AttributeList({ attributes }: { attributes: InteractionOption["attributes"] }) {
  if (!attributes.length) return null;
  return (
    <dl className="attribute-list">
      {attributes.map((attribute, index) => (
        <div key={`${index}:${attribute.label}`}><dt>{attribute.label}</dt><dd>{attribute.value}</dd></div>
      ))}
    </dl>
  );
}

export function UncertaintyNotice({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="uncertainty-notice">
      <AlertTriangle size={14} />
      <div><b>{items.length} 项无法确认</b>{items.map((item, index) => <span key={`${index}:${item}`}>{item}</span>)}</div>
    </div>
  );
}

export function OptionCard({
  option,
  selected,
  interactive,
  selectionMode,
  onSelect,
}: {
  option: InteractionOption;
  selected: boolean;
  interactive: boolean;
  selectionMode: "single" | "multi";
  onSelect: () => void;
}) {
  return (
    <article className={`option-card ${selected ? "selected" : ""}`} data-testid="option-card">
      {option.media_ref && <div className="option-media"><Eye size={18} /><span>媒体证据可用</span></div>}
      <div className="option-card-copy">
        <div className="option-title-row"><h4>{option.title}</h4>{selected && <span><Check size={12} />已选择</span>}</div>
        {option.description && <p>{option.description}</p>}
        <AttributeList attributes={option.attributes} />
        <div className="option-evidence">结构/视觉证据 · {option.evidence_refs.length}</div>
        <UncertaintyNotice items={option.uncertainties} />
      </div>
      <button type="button" disabled={!interactive} aria-pressed={selected} onClick={onSelect}>
        {interactive ? selected && selectionMode === "multi" ? "取消选择" : "选择" : "已处理"}
      </button>
    </article>
  );
}

export function OptionSet({
  request,
  active,
  respond,
}: {
  request: InteractionRequest;
  active: boolean;
  respond: (response: InteractionResponse) => Promise<unknown>;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  if (request.response_kind !== "single_select" && request.response_kind !== "multi_select") return null;
  const choose = (optionId: string) => {
    if (!active) return;
    if (request.response_kind === "single_select") {
      setSelected([optionId]);
      void respond({ kind: "single_select", request_id: request.request_id, option_id: optionId });
      return;
    }
    setSelected((current) => current.includes(optionId)
      ? current.filter((item) => item !== optionId)
      : [...current, optionId]);
  };
  return (
    <div className="option-set" aria-label="可选实体">
      {request.options.map((option) => (
        <OptionCard
          key={option.option_id}
          option={option}
          selected={selected.includes(option.option_id)}
          interactive={active}
          selectionMode={request.response_kind === "single_select" ? "single" : "multi"}
          onSelect={() => choose(option.option_id)}
        />
      ))}
      {request.response_kind === "multi_select" && active && (
        <button
          className="option-set-submit"
          type="button"
          disabled={!selected.length}
          onClick={() => void respond({
            kind: "multi_select",
            request_id: request.request_id,
            option_ids: selected,
          })}
        >确认 {selected.length} 项选择</button>
      )}
    </div>
  );
}

function fieldValue(
  field: InteractionRequest["fields"][number],
  data: FormData,
): InteractionFieldValue | undefined {
  const raw = data.get(field.field_id);
  if (raw === null || raw === "") return undefined;
  switch (field.kind) {
    case "text":
      return { kind: "text", field_id: field.field_id, text: String(raw) };
    case "integer":
      return { kind: "integer", field_id: field.field_id, integer: Number(raw) };
    case "decimal":
      return { kind: "decimal", field_id: field.field_id, decimal_string: String(raw) };
    case "boolean":
      if (raw !== "true" && raw !== "false") return undefined;
      return { kind: "boolean", field_id: field.field_id, boolean: raw === "true" };
    case "date":
      return { kind: "date", field_id: field.field_id, iso_date: String(raw) };
    default:
      return assertNever(field.kind);
  }
}

function StructuredFields({
  request,
  active,
  respond,
}: {
  request: InteractionRequest;
  active: boolean;
  respond: (response: InteractionResponse) => Promise<unknown>;
}) {
  if (request.response_kind !== "structured_fields") return null;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void respond({
      kind: "structured_fields",
      request_id: request.request_id,
      values: request.fields.flatMap((field) => {
        const value = fieldValue(field, data);
        return value === undefined ? [] : [value];
      }),
    });
  };
  return (
    <form className="structured-fields" onSubmit={submit}>
      {request.fields.map((field) => (
        <label key={field.field_id}>
          <span>{field.label}{field.required && <b>必填</b>}</span>
          {field.description && <small>{field.description}</small>}
          {field.kind === "boolean"
            ? <select
                name={field.field_id}
                defaultValue=""
                required={field.required}
                disabled={!active}
              >
                <option value="">{field.required ? "请选择" : "未填写"}</option>
                <option value="true">是</option>
                <option value="false">否</option>
              </select>
            : <input
                name={field.field_id}
                type={field.kind === "date" ? "date" : field.kind === "text" ? "text" : "number"}
                step={field.kind === "decimal" ? "any" : undefined}
                required={field.required}
                disabled={!active}
              />}
        </label>
      ))}
      {active && <button type="submit">提交信息</button>}
    </form>
  );
}

export function InteractionRequestPanel({
  request,
  active,
  respond,
}: {
  request: InteractionRequest;
  active: boolean;
  respond: (response: InteractionResponse) => Promise<unknown>;
}) {
  return (
    <article className={`interaction-panel ${active ? "active" : "resolved"}`} data-testid="interaction-request">
      <div className="feed-card-heading">
        <span className="feed-icon question"><CircleHelp size={15} /></span>
        <div><small>{active ? "需要你的决定" : "已处理的决定"}</small><h3>{request.prompt}</h3></div>
      </div>
      {request.public_intent && <p className="public-intent">{request.public_intent}</p>}
      <OptionSet request={request} active={active} respond={respond} />
      <StructuredFields request={request} active={active} respond={respond} />
      {request.response_kind === "free_text" && <p className="interaction-guidance">{active ? "请在下方输入回答；也可以修改整个目标。" : "这项请求已经处理。"}</p>}
    </article>
  );
}

export function RevisionDiff({ block }: { block: Extract<FeedBlock, { kind: "revision_applied" }> }) {
  const rows = [
    ["移除", block.removed, "removed"],
    ["新增", block.added, "added"],
    ["保留", block.retained, "retained"],
  ] as const;
  return (
    <article className="revision-diff" data-testid="revision-diff">
      <div className="feed-card-heading">
        <span className="feed-icon revision"><GitCompareArrows size={15} /></span>
        <div><small>修订已应用</small><h3>目标已更新 · revision {block.task_revision}</h3></div>
      </div>
      <dl>{rows.map(([label, values, className]) => values.length > 0 && (
        <div className={className} key={label}><dt>{label}</dt><dd>{values.join(" · ")}</dd></div>
      ))}</dl>
      {block.goal_description_changed && !rows.some(([, values]) => values.length) && <p>目标说明已更新。</p>}
    </article>
  );
}

export function ArtifactPanel({ artifact }: { artifact: PublicArtifact }) {
  return (
    <section className="artifact-panel" data-testid="artifact-panel">
      <div className="artifact-title"><FileCheck2 size={18} /><div><small>结果产物</small><h4>{artifact.title}</h4></div></div>
      <p>{artifact.summary}</p>
      {artifact.items.length > 0 && <div className="artifact-items">{artifact.items.map((item) => (
        <article key={item.item_id}><h5>{item.title}</h5><p>{item.summary}</p><AttributeList attributes={item.attributes} /></article>
      ))}</div>}
      {artifact.links.length > 0 && <nav className="artifact-links" aria-label="结果链接">{artifact.links.map((link) => (
        <a key={link.artifact_ref} href={link.artifact_ref}><ArrowDownToLine size={13} />{link.title}</a>
      ))}</nav>}
      <span className="artifact-evidence">可核验依据 · {artifact.evidence_refs.length}</span>
    </section>
  );
}

export function ConfirmationPanel({
  summary,
  risk,
  active,
  confirm,
}: {
  summary: string;
  risk: string;
  active: boolean;
  confirm: (approved: boolean) => Promise<unknown>;
}) {
  return (
    <article className="confirmation-panel" data-testid="confirmation-panel">
      <div className="feed-card-heading">
        <span className="feed-icon confirmation"><ShieldAlert size={15} /></span>
        <div><small>操作确认</small><h3>{summary}</h3></div>
      </div>
      <p><b>风险说明</b>{risk}</p>
      {active
        ? <div className="confirmation-actions"><button type="button" onClick={() => void confirm(false)}>拒绝操作</button><button className="approve" type="button" onClick={() => void confirm(true)}>批准操作</button></div>
        : <span className="handled-label">该确认请求已处理</span>}
    </article>
  );
}

export function ActivityTimeline({ blocks }: { blocks: Extract<FeedBlock, { kind: "runtime_activity" }>[] }) {
  if (!blocks.length) return null;
  return (
    <ol className="typed-activity-timeline" aria-label="Runtime 活动">
      {blocks.map((block) => <li className={block.status} key={block.block_id}><i /><div><b>{block.label}</b><small>{readableTime(block.occurred_at)}</small></div></li>)}
    </ol>
  );
}

function FeedBlockView({
  block,
  view,
  respond,
  confirm,
}: {
  block: FeedBlock;
  view: ShellViewModel;
  respond: (response: InteractionResponse) => Promise<unknown>;
  confirm: (approved: boolean) => Promise<unknown>;
}) {
  switch (block.kind) {
    case "user_turn":
      return <article className="feed-turn user"><div><small>你 · {readableTime(block.occurred_at)}</small><p>{block.content}</p></div></article>;
    case "goal_accepted":
      return <GoalSummary goal={block} />;
    case "agent_intent":
      return <article className="feed-turn agent"><span className="agent-monogram">A</span><div><small>Assistant</small><p>{block.content}</p></div></article>;
    case "runtime_activity":
      return <ActivityTimeline blocks={[block]} />;
    case "evidence_summary":
      return <article className="evidence-summary"><EvidenceBadge kind={block.evidence_kind} status={block.status} confidence={block.confidence} count={block.evidence_refs.length} /><p>{block.message}</p></article>;
    case "interaction_request":
      return <InteractionRequestPanel request={block.request} active={view.interaction?.request_id === block.request.request_id} respond={respond} />;
    case "revision_applied":
      return <RevisionDiff block={block} />;
    case "confirmation_required":
      return <ConfirmationPanel summary={block.summary} risk={block.risk} active={view.confirmation?.request_id === block.request_id} confirm={confirm} />;
    case "completion":
      return <article className={`completion-panel ${block.completion.outcome}`} data-testid="completion"><div className="feed-card-heading"><span className="feed-icon completion"><CheckCircle2 size={15} /></span><div><small>Assistant</small><AssistantMessage>{block.completion.message}</AssistantMessage></div></div>{block.completion.artifact && <ArtifactPanel artifact={block.completion.artifact} />}</article>;
    case "failure":
      return <article className="failure-panel"><div className="feed-card-heading"><span className="feed-icon failure"><AlertTriangle size={15} /></span><div><small>任务运行失败 · {block.code}</small><h3>{block.message}</h3></div></div></article>;
    default:
      return assertNever(block);
  }
}

export function ConversationFeed({
  view,
  respond,
  confirm,
}: {
  view: ShellViewModel;
  respond: (response: InteractionResponse) => Promise<unknown>;
  confirm: (approved: boolean) => Promise<unknown>;
}) {
  if (!view.feed.length && !view.snapshot?.task_text) {
    return (
      <div className="collaboration-empty">
        <span><MessageSquareText size={21} /></span>
        <small>Affordance Assistant</small>
        <h2>直接说你想知道什么，或想让它完成什么。</h2>
        <p>普通问题会直接回答；确实需要操作界面时，浏览器会自动出现，并展示可核验的实时进展。</p>
      </div>
    );
  }
  const interactionInFeed = view.interaction && view.feed.some((block) => (
    block.kind === "interaction_request" && block.request.request_id === view.interaction?.request_id
  ));
  const confirmationInFeed = view.confirmation && view.feed.some((block) => (
    block.kind === "confirmation_required" && block.request_id === view.confirmation?.request_id
  ));
  const completionInFeed = view.completion && view.feed.some((block) => block.kind === "completion");
  return (
    <div className="conversation-feed" data-testid="conversation-feed">
      {!view.feed.length && view.snapshot?.task_text && <GoalSummary goal={{
        block_id: "current-goal",
        kind: "goal_accepted",
        occurred_at: "",
        summary: view.snapshot.task_text,
        constraints: [],
        task_revision: view.taskRevision,
      }} />}
      {view.feed.map((block) => <FeedBlockView key={block.block_id} block={block} view={view} respond={respond} confirm={confirm} />)}
      {view.interaction && !interactionInFeed && <InteractionRequestPanel request={view.interaction} active respond={respond} />}
      {view.question && !view.interaction && <article className="interaction-panel active"><div className="feed-card-heading"><span className="feed-icon question"><CircleHelp size={15} /></span><div><small>需要你的回答</small><h3>{view.question.prompt}</h3></div></div></article>}
      {view.confirmation && !confirmationInFeed && <ConfirmationPanel summary={view.confirmation.summary} risk={view.confirmation.risk} active confirm={confirm} />}
      {view.completion && !completionInFeed && <article className={`completion-panel ${view.completion.outcome}`} data-testid="completion"><div className="feed-card-heading"><span className="feed-icon completion"><CheckCircle2 size={15} /></span><div><small>Assistant</small><AssistantMessage>{view.completion.message}</AssistantMessage></div></div>{view.completion.artifact && <ArtifactPanel artifact={view.completion.artifact} />}</article>}
    </div>
  );
}

export function ControlBar({
  view,
  pause,
  resume,
  cancel,
  takeOver,
  returnControl,
}: {
  view: ShellViewModel;
  pause: () => Promise<unknown>;
  resume: () => Promise<unknown>;
  cancel: () => Promise<unknown>;
  takeOver: () => Promise<unknown>;
  returnControl: () => Promise<unknown>;
}) {
  return (
    <div className="control-bar" aria-label="任务控制">
      {view.actions.returnControl && <button type="button" onClick={() => void returnControl()}><RotateCcw size={13} />交还 Agent</button>}
      {view.actions.takeOver && <button type="button" onClick={() => void takeOver()}><Hand size={13} />接管</button>}
      {view.actions.resume && <button type="button" onClick={() => void resume()}><Play size={13} />继续</button>}
      {view.actions.pause && <button type="button" onClick={() => void pause()}><Pause size={13} />暂停</button>}
      {view.actions.cancel && <button className="danger" type="button" onClick={() => void cancel()}><Square size={13} />停止</button>}
    </div>
  );
}

export function UnifiedComposer({
  view,
  submitMessage,
  revise,
}: {
  view: ShellViewModel;
  submitMessage: (message: string) => Promise<void>;
  revise: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [revisionOverride, setRevisionOverride] = useState(false);
  const revision = revisionOverride || view.composer.mode === "revise";
  const enabled = revision ? view.actions.revise : view.composer.enabled;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = message.trim();
    if (!value || !enabled) return;
    if (revision) await revise(value); else await submitMessage(value);
    setMessage("");
    setRevisionOverride(false);
  };
  const placeholder = revision
    ? "说明要增加、移除或保留的条件…"
    : view.composer.mode === "answer"
      ? "回答当前问题…"
      : view.composer.mode === "start"
        ? "问任何问题，或描述需要完成的任务…"
        : view.composer.mode === "interaction"
          ? "请使用上方的选项或字段…"
          : "当前没有可用的文字操作";
  return (
    <div className="unified-composer-wrap">
      <div className="composer-context">
        <span>{revision ? "修改当前请求" : view.composer.mode === "answer" ? "回答问题" : view.composer.mode === "start" ? "发送消息" : view.composer.mode === "interaction" ? "等待你的选择" : "输入暂不可用"}</span>
        {view.actions.revise && view.composer.mode !== "revise" && <button type="button" aria-pressed={revisionOverride} onClick={() => setRevisionOverride((current) => !current)}>{revisionOverride ? "返回当前问题" : "修改整个目标"}</button>}
      </div>
      <form className="unified-composer" onSubmit={submit}>
        <textarea aria-label="Task command" rows={1} value={message} onChange={(event) => setMessage(event.target.value)} readOnly={!enabled} placeholder={placeholder} />
        <button type="submit" aria-label="发送" disabled={!enabled || !message.trim()}><Send size={16} /></button>
      </form>
    </div>
  );
}

export function SurfaceViewer({
  view,
  children,
  activeLabel,
}: {
  view: ShellViewModel;
  children: ReactNode;
  activeLabel?: string;
}) {
  const surfaceKind = view.surface.status === "unavailable" ? "界面" : ({
    web: "网页",
    mobile: "移动界面",
    desktop: "桌面",
    generic: "界面",
  } as const)[view.surface.surfaceKind];
  const controlLabel = activeLabel ?? (view.surface.status === "unavailable"
    ? "等待连接"
    : view.surface.interactive ? "你正在控制" : "Agent 控制 · 只读");
  return (
    <section className="browser-panel surface-viewer" aria-labelledby="surfaceTitle">
      <header className="browser-header">
        <div className="title-block"><small>LIVE SURFACE · {surfaceKind}</small><h2 id="surfaceTitle">当前界面</h2></div>
        <div className="header-actions">
          <span className="control-badge" data-testid="surface-control-state"><i /><span>{controlLabel}</span></span>
          <button className="icon-button" type="button" aria-label="全屏显示当前界面" onClick={() => document.querySelector<HTMLElement>(".browser-stage")?.requestFullscreen()}><Maximize2 size={16} /></button>
        </div>
      </header>
      {children}
    </section>
  );
}
