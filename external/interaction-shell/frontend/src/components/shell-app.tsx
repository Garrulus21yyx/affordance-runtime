"use client";

import {
  AppWindow,
  CircleOff,
  FlaskConical,
  MoreHorizontal,
  Plus,
  Settings,
  X,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import type { BenchmarkLabRunSpec, BenchmarkLabRunSummary, CompletedRunSummary } from "@/generated/types.gen";
import { useBenchmarkLabs, type LabEvent } from "@/hooks/use-benchmark-labs";
import { useShellSession } from "@/hooks/use-shell-session";
import type { ShellViewModel } from "@/session/view-model";
import {
  ConversationFeed,
  ControlBar,
  SurfaceViewer,
  UnifiedComposer,
} from "./collaboration-workspace";

type LabsTab = "experiment" | "bad-cases" | "evidence";

function statusLabel(status: string) {
  return ({
    idle: "等待任务",
    running: "任务运行中",
    waiting_user: "等待你的回答",
    waiting_confirmation: "等待操作确认",
    paused: "任务已暂停",
    done: "任务已完成",
    failed: "任务运行失败",
    blocked: "需要处理后才能继续",
    cancelled: "已取消",
    completed: "已完成",
  } as Record<string, string>)[status] ?? status;
}

function humanize(value: string) {
  const label = value.replace(/^browsergym\/miniwob\./, "").replaceAll("-", " ");
  return label ? label.charAt(0).toUpperCase() + label.slice(1) : "未命名任务";
}

const badCaseLabels: Record<string, string> = {
  structured_output_invalid: "Invalid JSON / Schema",
  provider_failure: "Provider failure",
  control_stall: "撞墙 · Control stalled",
  no_progress: "重复无进展",
  budget_exhausted: "步数 / 等待预算耗尽",
  harness_timeout: "Watchdog 超时",
  external_interruption: "外部终止",
  acquisition_failure: "页面观测失败",
  execution_failure: "动作执行失败",
  evaluation_failure: "评估失败",
  native_task_failure: "Native verifier 判定失败",
  runtime_rejected: "Runtime 拒绝",
  waiting_user: "等待用户输入",
  waiting_confirmation: "等待风险确认",
  cancelled: "任务已取消",
  cleanup_failure: "清理失败",
  environment_failure: "环境启动失败",
  evidence_failure: "证据完整性失败",
  unclassified_typed_failure: "其他 typed failure",
  not_assessed: "原因尚未分析",
};

export function CompletedBadCase({ run }: { run: CompletedRunSummary }) {
  const label = badCaseLabels[run.bad_case_category ?? "not_assessed"] ?? run.bad_case_category;
  const facts = [run.termination_source, run.failure_stage, run.failure_origin, run.failure_code].filter(Boolean);
  return (
    <article className="bad-case bad-case-detailed" data-testid="completed-bad-case">
      <div className="bad-case-heading">
        <span className="bad-case-copy"><b>{humanize(run.case_id)}</b><small>{run.run_attempt_id}</small></span>
        <span className="bad-case-category">{label}</span>
      </div>
      <p>{run.failure_summary || "该历史证据没有可用的 typed failure projection。"}</p>
      {facts.length > 0 && <div className="bad-case-facts" aria-label="失败事实">{facts.map((fact, index) => <code key={`${index}:${fact}`}>{fact}</code>)}</div>}
      <div className="bad-case-metrics">
        <span>Turns <b>{run.turns ?? 0}</b></span>
        <span>Stalls <b>{run.control_stalls ?? 0}</b></span>
        <span>Cycles <b>{run.state_oscillations ?? 0}</b></span>
      </div>
      {(run.langfuse_url || run.local_evidence_url) && <nav className="bad-case-links" aria-label="失败证据链接">{run.langfuse_url && <a href={run.langfuse_url} target="_blank" rel="noreferrer">Open in Langfuse ↗</a>}{run.local_evidence_url && <a href={run.local_evidence_url} target="_blank" rel="noreferrer">本地证据 ↗</a>}</nav>}
    </article>
  );
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
    <SurfaceViewer view={view} activeLabel={labRun ? "Agent 控制 · benchmark" : undefined}>
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
            <h3>{labRun ? "正在等待第一张画面" : "Live surface 尚未连接"}</h3>
            <p>{labRun ? "Runtime 记录 observation 后会显示在这里。" : surface.reasonCode}</p>
          </div>
        )}
        {(labRun || surface.status !== "unavailable") && <div className="viewer-note"><i /><span>{surface.status === "interactive" && !labRun ? "用户控制模式" : "只读模式 · Agent 操作期间无法手动点击"}</span></div>}
      </div>
    </SurfaceViewer>
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

function LabExperiment({ labs, showRun }: {
  labs: ReturnType<typeof useBenchmarkLabs>;
  showRun: (run: BenchmarkLabRunSummary) => void;
}) {
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
    try {
      const run = await labs.start(spec);
      showRun(run);
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "无法启动任务");
    }
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

function LabsDrawer({ open, tab, setTab, close, labs, showRun }: {
  open: boolean;
  tab: LabsTab;
  setTab: (tab: LabsTab) => void;
  close: () => void;
  labs: ReturnType<typeof useBenchmarkLabs>;
  showRun: (run: BenchmarkLabRunSummary) => void;
}) {
  const failed = labs.runs.filter((run) => run.status === "failed");
  const completedBadCases = labs.completedRuns.filter((run) => run.status !== "done");
  const badCaseCount = failed.length + completedBadCases.length;
  const [selectedRaw, setSelectedRaw] = useState<LabEvent | null>(null);
  return (
    <>
      {open && <button className="drawer-backdrop" aria-label="关闭 Labs 遮罩" onClick={close} />}
      <aside className={`labs-drawer ${open ? "open" : ""}`} aria-labelledby="labsTitle" aria-hidden={!open}>
        <header className="labs-header"><div><span>DEVELOPER WORKSPACE</span><h2 id="labsTitle">Labs</h2></div><button className="icon-button" type="button" aria-label="关闭 Labs" onClick={close}><X size={18} /></button></header>
        <div className="labs-tabs" role="tablist"><button className={tab === "experiment" ? "active" : ""} onClick={() => setTab("experiment")}>实验</button><button className={tab === "bad-cases" ? "active" : ""} onClick={() => setTab("bad-cases")}>Bad cases <span>{badCaseCount}</span></button><button className={tab === "evidence" ? "active" : ""} onClick={() => setTab("evidence")}>证据</button></div>
        <div className="labs-content">
          <section className="labs-view active">
            {tab === "experiment" && <LabExperiment labs={labs} showRun={showRun} />}
            {tab === "bad-cases" && <><div className="labs-intro"><h3>Bad cases</h3><p>失败类型来自 benchmark 持久化的 typed facts；点击链接可继续查看完整证据。</p></div><div className="bad-case-list">{failed.map((run) => <button className="bad-case" type="button" key={run.run_id} onClick={() => { labs.selectRun(run); setTab("evidence"); }}><span className="bad-case-copy"><b>{humanize(run.spec.case_id)}</b><small>{run.run_id}</small></span><span>等待持久分析</span></button>)}{completedBadCases.map((run) => <CompletedBadCase run={run} key={run.locator_id} />)}{!badCaseCount && <div className="bad-case-empty"><b>暂时没有 Bad case</b><span>失败运行会自动进入这里，不需要手动标记。</span></div>}</div></>}
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
  const statusTone = activeLab?.status ?? view.status.tone;
  const statusText = activeLab ? statusLabel(activeLab.status) : view.status.label;
  const recent = useMemo(() => labs.runs.slice(0, 8), [labs.runs]);
  const openLabs = (tab: LabsTab) => { setLabsTab(tab); setLabsOpen(true); };
  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand"><span className="brand-mark" aria-hidden="true" /><strong>Affordance</strong></div>
        <button className="new-task" type="button" onClick={() => { setShowLabRun(false); void shell.newSession(); }}><span>新建任务</span><Plus size={19} /></button>
        <p className="nav-label">Sessions · 会话</p>
        <nav className="session-list" aria-label="最近运行">
          {view.snapshot?.task_text && <button className={`session ${!showLabRun ? "active" : ""}`} type="button" onClick={() => setShowLabRun(false)}><b>{view.taskText}</b><small><i className={`session-status ${view.status.tone}`} />{view.status.label}</small></button>}
          {recent.map((run) => <button className={`session ${showLabRun && labs.selectedRun?.run_id === run.run_id ? "active" : ""}`} type="button" key={run.run_id} onClick={() => { labs.selectRun(run); setShowLabRun(true); }}><b>{humanize(run.spec.case_id)}</b><small><i className={`session-status ${run.status}`} />{statusLabel(run.status)}</small></button>)}
          {!view.snapshot?.task_text && !recent.length && <div className="session-placeholder">启动一个任务后，会话会出现在这里。</div>}
        </nav>
        <div className="sidebar-bottom"><button className="utility-link" type="button" aria-label="Labs" onClick={() => openLabs("experiment")}><FlaskConical size={17} /><span aria-hidden="true">Labs</span></button><button className="utility-link" type="button" disabled><Settings size={17} /><span>设置</span></button></div>
      </aside>
      <section className="conversation" aria-labelledby="taskTitle">
        <header className="conversation-header"><div className="title-block"><small>{activeLab ? activeLab.spec.case_id : "COLLABORATION FEED"}</small><h1 id="taskTitle">{title}</h1></div><div className="header-actions">
          {!activeLab && <ControlBar view={view} returnControl={shell.returnControl} takeOver={shell.takeOver} resume={shell.resume} pause={shell.pause} cancel={shell.cancel} />}
          <span className={`status-pill ${statusTone}`}><i /><span>{statusText}</span></span><button className="icon-button" type="button" aria-label="打开运行详情" onClick={() => openLabs("evidence")}><MoreHorizontal size={17} /></button>
        </div></header>
        <div className="thread" aria-live="polite">{activeLab ? <LabThread run={activeLab} activity={labs.activity} /> : <ConversationFeed view={view} respond={shell.respondInteraction} confirm={shell.confirm} />}</div>
        {activeLab ? <div className="composer-wrap"><div className="composer-hint">正式 benchmark 由 Labs 管理；普通用户会话仍保留在左侧。</div><div className="composer disabled"><FlaskConical className="composer-tool" size={18} /><textarea rows={1} readOnly value="" placeholder="Labs 运行中…" /><button className="send" type="button" onClick={() => openLabs("evidence")}><FlaskConical size={16} /></button></div></div> : <UnifiedComposer view={view} submitMessage={shell.submitMessage} revise={shell.revise} />}
      </section>
      <LiveView view={view} labFrameUrl={labs.frameUrl} labRun={activeLab} />
      <LabsDrawer
        open={labsOpen}
        tab={labsTab}
        setTab={setLabsTab}
        close={() => setLabsOpen(false)}
        labs={labs}
        showRun={() => { setLabsOpen(false); setShowLabRun(true); }}
      />
      {shell.notice && <div className="toast" role="status">{shell.notice}</div>}
    </main>
  );
}
