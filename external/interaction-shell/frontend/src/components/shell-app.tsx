"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import {
  Bot,
  AppWindow,
  CircleOff,
  FlaskConical,
  Hand,
  Maximize2,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Send,
  Settings,
  ShieldCheck,
  Square,
  X,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import type { BenchmarkLabRunSpec, BenchmarkLabRunSummary } from "@/generated/types.gen";
import { useBenchmarkLabs, type LabEvent } from "@/hooks/use-benchmark-labs";
import { useShellSession } from "@/hooks/use-shell-session";
import type { ShellViewModel } from "@/session/view-model";

type LabsTab = "experiment" | "bad-cases" | "evidence";

function statusLabel(status: string) {
  return ({
    idle: "空闲",
    running: "执行中",
    waiting_user: "等待确认",
    paused: "已暂停",
    done: "已完成",
    failed: "未完成",
    cancelled: "已取消",
    completed: "已完成",
  } as Record<string, string>)[status] ?? status;
}

function humanize(value: string) {
  const label = value.replace(/^browsergym\/miniwob\./, "").replaceAll("-", " ");
  return label ? label.charAt(0).toUpperCase() + label.slice(1) : "未命名任务";
}

function eventText(event: LabEvent, key: string) {
  return typeof event[key] === "string" ? event[key] : "";
}

function eventNumber(event: LabEvent, key: string) {
  return typeof event[key] === "number" ? event[key] : 0;
}

function labActivityLabel(event: LabEvent) {
  const kind = eventText(event, "event");
  if (kind === "run_started") return ["任务已交给 Agent", `最多 ${eventNumber(event, "max_steps") || "—"} 个决策步骤`];
  if (kind === "goal_compiler_completed") return ["目标已整理", `${eventNumber(event, "provider_attempt_count")} 次模型调用`];
  if (kind === "model_turn") return ["Agent 已完成一次决策", `${eventNumber(event, "attempt_count")} 次尝试`];
  if (kind === "step_completed") return ["已执行页面操作", eventText(event, "feedback") || `步骤 ${eventNumber(event, "step")}`];
  if (kind === "run_finished") return ["正式评估已结束", statusLabel(eventText(event, "status"))];
  if (kind === "run_error") return ["运行遇到错误", "Runtime 已保留完整错误证据"];
  return ["Runtime 已更新", kind || "trace event"];
}

export function EffectReconciliationNotice({ view }: { view: ShellViewModel }) {
  const reconciliation = view.effectReconciliation;
  if (!reconciliation) return null;
  return (
    <div className="activity-card warning" data-testid="effect-reconciliation">
      <b>正在核对页面效果</b>
      <span>{reconciliation.original_action} · {reconciliation.resource_ref}</span>
      <small>{reconciliation.code} · {reconciliation.reversibility}</small>
    </div>
  );
}

export function Progress({ view }: { view: ShellViewModel }) {
  return (
    <div className="activity-stack" aria-label="Runtime progress updates">
      {view.steps.map((step) => (
        <div className="activity done" key={step.step}>
          <span className="activity-copy"><b>{step.label}</b><small>{statusLabel(step.status)}</small></span>
        </div>
      ))}
      {!view.steps.length && <div className="activity current"><span className="activity-copy"><b>等待第一步</b><small>Runtime 进展会显示在这里</small></span></div>}
    </div>
  );
}

export function LiveView({ view, labFrameUrl = "", labRun = null }: {
  view: ShellViewModel;
  labFrameUrl?: string;
  labRun?: BenchmarkLabRunSummary | null;
}) {
  const [frameLoading, setFrameLoading] = useState(true);
  const surface = view.surface;
  return (
    <section className="browser-panel" aria-labelledby="browserTitle">
      <header className="browser-header">
        <div className="title-block"><small>LIVE SURFACE</small><h2 id="browserTitle">实时浏览器</h2></div>
        <div className="header-actions">
          <span className="control-badge" data-testid="surface-control-state"><AppWindow size={14} /><span>{labRun ? "Agent 控制中" : surface.status === "unavailable" ? "等待浏览器" : surface.interactive ? "用户控制中" : "Agent 控制中 · 只读"}</span></span>
          <button className="icon-button" type="button" aria-label="全屏浏览器" onClick={() => document.querySelector<HTMLElement>(".browser-stage")?.requestFullscreen()}><Maximize2 size={16} /></button>
        </div>
      </header>
      <div className="browser-stage">
        {labRun && labFrameUrl ? (
          <figure className="browser-frame">
            <div className="browser-chrome" aria-hidden="true"><span className="window-dots"><i /><i /><i /></span><span className="address"><i /><span>{humanize(labRun.spec.case_id)}</span></span><span className="chrome-more">···</span></div>
            <div className="frame-viewport">
              {/* eslint-disable-next-line @next/next/no-img-element -- ephemeral Runtime blob URL */}
              <img src={labFrameUrl} alt="Runtime 当前浏览器画面" onLoad={() => setFrameLoading(false)} />
              {frameLoading && <div className="frame-loading"><i /><span>正在等待当前画面</span></div>}
            </div>
          </figure>
        ) : !labRun && surface.status !== "unavailable" ? (
          <iframe key={surface.frameKey} title={surface.interactive ? "Interactive live surface" : "Read-only live surface"} src={surface.protectedPath} sandbox="allow-scripts allow-same-origin" />
        ) : (
          <div className="browser-empty" data-testid="surface-unavailable">
            <span className="browser-empty-icon">{labRun ? <AppWindow size={24} /> : <CircleOff size={24} />}</span>
            <h3>{labRun ? "正在等待第一张画面" : "浏览器尚未打开"}</h3>
            <p>{labRun ? "Runtime 记录 observation 后会显示在这里。" : surface.reasonCode}</p>
          </div>
        )}
        {(labRun || surface.status !== "unavailable") && <div className="viewer-note"><i /><span>{surface.status === "interactive" && !labRun ? "用户控制模式" : "只读模式 · Agent 操作期间无法手动点击"}</span></div>}
      </div>
    </section>
  );
}

function RuntimeThread({ view }: { view: ShellViewModel }) {
  const hasTask = Boolean(view.snapshot?.task_text);
  if (!hasTask) {
    return (
      <div className="welcome">
        <span className="welcome-orbit" aria-hidden="true"><i /></span>
        <p className="welcome-kicker">GUI AGENT</p>
        <h2>说出目标，观察每一步。</h2>
        <p>Agent 会在真实浏览器中执行任务。需要确认时，它会回到这里问你。</p>
      </div>
    );
  }
  return (
    <div className="thread-content">
      <div className="message user"><div className="bubble">{view.taskText}</div></div>
      <div className="message agent"><span className="avatar">A</span><div className="bubble">收到。我会根据当前页面逐步执行，并把重要状态同步在这里。</div></div>
      <p className="activity-lead">当前进展</p>
      <Progress view={view} />
      {view.question && <div className="message agent" data-testid="pending-question"><span className="avatar">?</span><div className="bubble"><b>需要你的补充</b><br />{view.question.prompt}</div></div>}
      <EffectReconciliationNotice view={view} />
      {view.completion && <div className="message agent final-message" data-testid="completion"><span className="avatar"><ShieldCheck size={15} /></span><div className="bubble"><b>{view.completion.outcome}</b><br />{view.completion.message}</div></div>}
    </div>
  );
}

function LabThread({ run, activity }: { run: BenchmarkLabRunSummary; activity: LabEvent[] }) {
  return (
    <div className="thread-content">
      <div className="message user"><div className="bubble">{humanize(run.spec.case_id)}</div></div>
      <div className="message agent"><span className="avatar">L</span><div className="bubble">正式 benchmark 已由 Labs 启动。这里仅展示 Runtime 已记录的公开进展。</div></div>
      <p className="activity-lead">当前进展</p>
      <div className="activity-stack">
        {activity.filter((event) => eventText(event, "event") !== "observation").map((event, index) => {
          const [title, detail] = labActivityLabel(event);
          return <div className={`activity ${eventText(event, "event") === "run_error" ? "failed" : "done"}`} key={`${eventNumber(event, "sequence")}-${index}`}><span className="activity-copy"><b>{title}</b><small>{detail}</small></span></div>;
        })}
        {run.status === "running" && <div className="activity current"><span className="activity-copy"><b>正在读取当前页面并决定下一步</b><small>右侧会同步 Runtime 最新画面</small></span></div>}
      </div>
      {run.status !== "running" && <div className="message agent final-message"><span className="avatar">A</span><div className="bubble">{run.status === "completed" ? "任务运行已经结束。正式结果与完整证据保存在 Labs 中。" : "任务没有完成；失败阶段和完整证据已保留在 Labs。"}</div></div>}
    </div>
  );
}

function Composer({ view, submitMessage, revise }: {
  view: ShellViewModel;
  submitMessage: (message: string) => Promise<void>;
  revise: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(false);
  const enabled = revision ? view.actions.revise : view.composer.enabled;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = message.trim();
    if (!value || !enabled) return;
    if (revision) await revise(value); else await submitMessage(value);
    setMessage("");
    setRevision(false);
  };
  return (
    <div className="composer-wrap">
      <div className="composer-hint">{revision ? "新目标会通过现有 TaskRevisionCompiler 校验。" : view.question ? "回答 Runtime 的问题后，任务会继续。" : view.composer.enabled ? "直接描述你希望 Agent 完成的任务。" : view.actions.revise ? "任务执行中；需要时可以修改目标。" : "当前任务暂时不接受新的输入。"}</div>
      <form className="composer" onSubmit={submit}>
        <Bot className="composer-tool" size={18} />
        <textarea aria-label="Task command" rows={1} value={message} onChange={(event) => setMessage(event.target.value)} readOnly={!enabled} placeholder={revision ? "输入修订后的目标…" : view.question ? "输入回答…" : view.composer.enabled ? "描述一个任务…" : "Agent 正在执行…"} />
        {view.actions.revise && <button className={`revision-toggle ${revision ? "active" : ""}`} type="button" onClick={() => setRevision((value) => !value)}>修改目标</button>}
        <button className="send" type="submit" aria-label="Send" disabled={!enabled || !message.trim()}><Send size={16} /></button>
      </form>
    </div>
  );
}

function LabExperiment({ labs, close }: { labs: ReturnType<typeof useBenchmarkLabs>; close: () => void }) {
  const config = labs.configuration;
  const [goalMode, setGoalMode] = useState<"model" | "disabled">("model");
  const [formError, setFormError] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!config) return;
    const data = new FormData(event.currentTarget);
    const spec: BenchmarkLabRunSpec = {
      case_id: String(data.get("case_id") || ""),
      action_model: String(data.get("action_model") || ""),
      action_wire_capability: String(data.get("action_wire_capability") || "native_single_tool"),
      goal_compiler_mode: goalMode,
      goal_compiler_model: goalMode === "model" ? String(data.get("goal_compiler_model") || "") : "",
      perception_profile: String(data.get("perception_profile") || "structure-first.v1"),
      profile: String(data.get("profile") || "CONSOLE_EXPERIMENT"),
    };
    try { await labs.start(spec); close(); } catch (reason) { setFormError(reason instanceof Error ? reason.message : "无法启动任务"); }
  };
  if (labs.state === "loading") return <div className="evidence-empty">正在读取 frozen manifest…</div>;
  if (!config) return <div className="evidence-empty">Labs 当前不可用。{labs.error}</div>;
  return (
    <form onSubmit={submit}>
      <div className="labs-intro"><h3>启动正式验证任务</h3><p>这些设置只影响 benchmark runner；不会改变 Runtime 的事实和控制权。</p></div>
      <label className="field"><span>MiniWoB task</span><select name="case_id">{config.cases.map((item) => <option key={item.case_id} value={item.case_id}>{humanize(item.task_id)}</option>)}</select><small>{config.manifest}</small></label>
      <div className="form-grid">
        <label className="field"><span>Action policy</span><select name="action_model">{config.action_models.map((item) => <option key={item.id}>{item.id}</option>)}</select></label>
        <label className="field"><span>Wire capability</span><select name="action_wire_capability">{config.action_wire_capabilities.map((item) => <option key={item}>{item}</option>)}</select></label>
      </div>
      <div className="role-card">
        <div className="role-card-title"><span>G</span><div><b>Goal compiler</b><small>为任务提供静态目标指导</small></div></div>
        <div className="segmented"><button type="button" className={goalMode === "model" ? "active" : ""} onClick={() => setGoalMode("model")}>Model</button><button type="button" className={goalMode === "disabled" ? "active" : ""} onClick={() => setGoalMode("disabled")}>Disabled</button></div>
        {goalMode === "model" && <label className="field"><span>Model</span><select name="goal_compiler_model">{config.goal_models.map((item) => <option key={item}>{item}</option>)}</select></label>}
      </div>
      <div className="form-grid">
        <label className="field"><span>Perception</span><select name="perception_profile">{config.perception_profiles.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="field"><span>Evidence profile</span><input name="profile" defaultValue="CONSOLE_EXPERIMENT" /></label>
      </div>
      {!config.provider_ready && <p className="form-error">模型服务尚未就绪；请先加载项目配置。</p>}
      {(formError || labs.error) && <p className="form-error">{formError || labs.error}</p>}
      <div className="launch-row"><button className="launch" type="submit" disabled={!config.provider_ready}><span>启动任务</span><i>↗</i></button>{labs.selectedRun?.status === "running" && <button className="stop" type="button" onClick={labs.stop}>停止</button>}</div>
    </form>
  );
}

function LabsDrawer({ open, tab, setTab, close, labs }: {
  open: boolean;
  tab: LabsTab;
  setTab: (tab: LabsTab) => void;
  close: () => void;
  labs: ReturnType<typeof useBenchmarkLabs>;
}) {
  const failed = labs.runs.filter((run) => run.status === "failed");
  const [selectedRaw, setSelectedRaw] = useState<LabEvent | null>(null);
  return (
    <>
      {open && <button className="drawer-backdrop" aria-label="关闭 Labs 遮罩" onClick={close} />}
      <aside className={`labs-drawer ${open ? "open" : ""}`} aria-labelledby="labsTitle" aria-hidden={!open}>
        <header className="labs-header"><div><span>DEVELOPER WORKSPACE</span><h2 id="labsTitle">Labs</h2></div><button className="icon-button" type="button" aria-label="关闭 Labs" onClick={close}><X size={18} /></button></header>
        <div className="labs-tabs" role="tablist"><button className={tab === "experiment" ? "active" : ""} onClick={() => setTab("experiment")}>实验</button><button className={tab === "bad-cases" ? "active" : ""} onClick={() => setTab("bad-cases")}>Bad cases <span>{failed.length}</span></button><button className={tab === "evidence" ? "active" : ""} onClick={() => setTab("evidence")}>证据</button></div>
        <div className="labs-content">
          <section className="labs-view active">
            {tab === "experiment" && <LabExperiment labs={labs} close={close} />}
            {tab === "bad-cases" && <><div className="labs-intro"><h3>Bad cases</h3><p>失败状态只来自正式 runner 或已完成 benchmark 的权威结果。</p></div><div className="bad-case-list">{failed.map((run) => <button className="bad-case" type="button" key={run.run_id} onClick={() => { labs.selectRun(run); setTab("evidence"); }}><span className="bad-case-copy"><b>{humanize(run.spec.case_id)}</b><small>{run.run_id}</small></span><span>failed</span></button>)}{labs.completedRuns.filter((run) => run.status !== "done").map((run) => <div className="bad-case" key={run.locator_id}><span className="bad-case-copy"><b>{run.case_id}</b><small>{run.run_attempt_id}</small></span><span>{run.status}</span></div>)}{!failed.length && !labs.completedRuns.some((run) => run.status !== "done") && <div className="bad-case-empty"><b>暂时没有 Bad case</b><span>失败运行会自动进入这里，不需要手动标记。</span></div>}</div></>}
            {tab === "evidence" && <><div className="evidence-head"><div><span>当前运行</span><b>{labs.selectedRun?.run_id ?? "尚未选择"}</b></div><button type="button" disabled={!selectedRaw} onClick={() => selectedRaw && navigator.clipboard.writeText(JSON.stringify(selectedRaw, null, 2))}>复制 JSON</button></div><div className="metric-strip"><div><span>Events</span><b>{labs.rawEvents.length}</b></div><div><span>Policy</span><b>{labs.rawEvents.filter((item) => eventText(item, "event") === "model_turn").length}</b></div><div><span>Actions</span><b>{labs.rawEvents.filter((item) => eventText(item, "event") === "step_completed").length}</b></div><div><span>Status</span><b>{statusLabel(labs.selectedRun?.status ?? "idle")}</b></div></div><div className="trace-list">{labs.rawEvents.map((event, index) => <button className={`trace-event ${selectedRaw === event ? "selected" : ""}`} type="button" key={`${eventNumber(event, "sequence")}-${index}`} onClick={() => setSelectedRaw(event)}><span>{String(eventNumber(event, "sequence") || index + 1).padStart(3, "0")}</span><span><b>{eventText(event, "event") || "Trace event"}</b><small>{eventText(event, "observation_id") || eventText(event, "outcome") || "recorded"}</small></span><em>TRACE</em></button>)}{!labs.rawEvents.length && <div className="evidence-empty">选择或启动一次运行后，原始事件会出现在这里。</div>}</div><div className="trace-inspector"><div className="trace-summary"><b>{selectedRaw ? eventText(selectedRaw, "event") : "选择一个事件"}</b><span>查看原始本地证据</span></div><pre id="jsonInspector" tabIndex={0}>{JSON.stringify(selectedRaw ?? {}, null, 2)}</pre></div><details className="stdout-drawer"><summary>Runner output</summary><pre id="stdoutOutput">{labs.selectedRun?.stdout_tail?.join("\n") || "No runner output yet."}</pre></details><p className="evidence-path">{labs.selectedRun?.evidence_dir ?? "No evidence directory"}</p></>}
          </section>
        </div>
      </aside>
    </>
  );
}

export function ShellApp() {
  const shell = useShellSession();
  const view = shell.viewModel;
  const [labsOpen, setLabsOpen] = useState(false);
  const [labsTab, setLabsTab] = useState<LabsTab>("experiment");
  const [showLabRun, setShowLabRun] = useState(false);
  const labs = useBenchmarkLabs(labsOpen || showLabRun);
  const activeLab = showLabRun ? labs.selectedRun : null;
  const title = activeLab ? humanize(activeLab.spec.case_id) : view.snapshot?.task_text || "从一句话开始";
  const status = activeLab?.status ?? view.runStatus;
  const recent = useMemo(() => labs.runs.slice(0, 8), [labs.runs]);
  const openLabs = (tab: LabsTab) => { setLabsTab(tab); setLabsOpen(true); };
  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand"><span className="brand-mark" aria-hidden="true" /><strong>Affordance</strong></div>
        <button className="new-task" type="button" onClick={() => { setShowLabRun(false); void shell.newSession(); }}><span>新建任务</span><Plus size={19} /></button>
        <p className="nav-label">最近</p>
        <nav className="session-list" aria-label="最近运行">
          {view.snapshot?.task_text && <button className={`session ${!showLabRun ? "active" : ""}`} type="button" onClick={() => setShowLabRun(false)}><b>{view.taskText}</b><small><i className={`session-status ${view.runStatus}`} />{statusLabel(view.runStatus)}</small></button>}
          {recent.map((run) => <button className={`session ${showLabRun && labs.selectedRun?.run_id === run.run_id ? "active" : ""}`} type="button" key={run.run_id} onClick={() => { labs.selectRun(run); setShowLabRun(true); }}><b>{humanize(run.spec.case_id)}</b><small><i className={`session-status ${run.status}`} />{statusLabel(run.status)}</small></button>)}
          {!view.snapshot?.task_text && !recent.length && <div className="session-placeholder">启动一个任务后，会话会出现在这里。</div>}
        </nav>
        <div className="sidebar-bottom"><button className="utility-link" type="button" aria-label="Labs" onClick={() => openLabs("experiment")}><FlaskConical size={17} /><span aria-hidden="true">Labs</span></button><button className="utility-link" type="button" disabled><Settings size={17} /><span>设置</span></button></div>
      </aside>
      <section className="conversation" aria-labelledby="taskTitle">
        <header className="conversation-header"><div className="title-block"><small>{activeLab ? activeLab.spec.case_id : "CURRENT TASK"}</small><h1 id="taskTitle">{title}</h1></div><div className="header-actions">
          {!activeLab && view.actions.returnControl && <button className="header-control" type="button" onClick={shell.returnControl}><RotateCcw size={13} />交还 Agent</button>}
          {!activeLab && view.actions.takeOver && <button className="header-control" type="button" onClick={shell.takeOver}><Hand size={13} />接管</button>}
          {!activeLab && view.actions.resume && <button className="header-control" type="button" onClick={shell.resume}><Play size={13} />继续</button>}
          {!activeLab && view.actions.pause && <button className="header-control" type="button" onClick={shell.pause}><Pause size={13} />暂停</button>}
          {!activeLab && view.actions.cancel && <button className="header-control danger" type="button" onClick={shell.cancel}><Square size={13} />停止</button>}
          <span className={`status-pill ${status}`}><i /><span>{statusLabel(status)}</span></span><button className="icon-button" type="button" aria-label="打开运行详情" onClick={() => openLabs("evidence")}><MoreHorizontal size={17} /></button>
        </div></header>
        <div className="thread" aria-live="polite">{activeLab ? <LabThread run={activeLab} activity={labs.activity} /> : <RuntimeThread view={view} />}</div>
        {activeLab ? <div className="composer-wrap"><div className="composer-hint">正式 benchmark 由 Labs 管理；普通用户会话仍保留在左侧。</div><div className="composer disabled"><FlaskConical className="composer-tool" size={18} /><textarea rows={1} readOnly value="" placeholder="Labs 运行中…" /><button className="send" type="button" onClick={() => openLabs("evidence")}><FlaskConical size={16} /></button></div></div> : <Composer view={view} submitMessage={shell.submitMessage} revise={shell.revise} />}
      </section>
      <LiveView view={view} labFrameUrl={labs.frameUrl} labRun={activeLab} />
      <LabsDrawer open={labsOpen} tab={labsTab} setTab={setLabsTab} close={() => { setLabsOpen(false); if (labs.selectedRun) setShowLabRun(true); }} labs={labs} />
      {shell.notice && <div className="toast" role="status">{shell.notice}</div>}
      <AlertDialog.Root open={Boolean(view.confirmation)}><AlertDialog.Portal><AlertDialog.Overlay className="dialog-overlay" /><AlertDialog.Content className="dialog-content" data-testid="confirmation-dialog"><AlertDialog.Title>Runtime 请求确认</AlertDialog.Title><AlertDialog.Description>{view.confirmation?.summary}<br />风险：{view.confirmation?.risk}</AlertDialog.Description><div className="dialog-actions"><AlertDialog.Cancel asChild><button type="button" onClick={() => shell.confirm(false)}>拒绝操作</button></AlertDialog.Cancel><AlertDialog.Action asChild><button className="approve" type="button" onClick={() => shell.confirm(true)}>批准操作</button></AlertDialog.Action></div></AlertDialog.Content></AlertDialog.Portal></AlertDialog.Root>
    </main>
  );
}
