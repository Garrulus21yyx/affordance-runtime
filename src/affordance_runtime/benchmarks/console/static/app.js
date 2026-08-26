const state = {
  config: null,
  run: null,
  runs: [],
  activity: [],
  rawEvents: [],
  activityCursor: 0,
  rawCursor: 0,
  selectedRaw: null,
  goalMode: "model",
  activeLabsTab: "experiment",
  poller: null,
  pollingRunId: null,
  rawLoadingRunId: null,
  timer: null,
  toastTimer: null,
  frameRevision: 0,
};

const $ = (id) => document.getElementById(id);
const refs = Object.fromEntries([
  "newTaskButton", "labsButton", "settingsButton", "sessionList", "taskEyebrow", "taskTitle",
  "runStatus", "conversationMenu", "welcomeState", "welcomeStartButton", "threadContent", "threadTime",
  "taskInstruction", "agentIntro", "activityStack", "finalMessage", "finalMessageText", "composerHint",
  "composerLabsButton", "composerInput", "composerSend", "browserControl", "fullscreenButton", "browserStage",
  "browserEmpty", "browserFrame", "browserAddress", "browserImage", "frameLoading", "viewerNote",
  "drawerBackdrop", "labsDrawer", "closeLabsButton", "badCaseCount", "runForm", "caseSelect", "caseMeta",
  "actionModel", "actionWireCapability", "goalModelField", "goalModel", "perceptionSelect", "profileInput",
  "thinkingReadout", "formError", "launchButton", "stopButton", "badCaseList", "evidenceRunName",
  "copyButton", "eventCount", "turnCount", "executionCount", "runClock", "traceList", "inspectorSummary",
  "jsonInspector", "stdoutOutput", "evidencePath", "toast",
].map((id) => [id, $(id)]));

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

function option(value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  return item;
}

function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

async function initialize() {
  try {
    const [config, runsPayload, current] = await Promise.all([
      api("/api/config"),
      api("/api/runs"),
      api("/api/runs/current"),
    ]);
    state.config = config;
    populateConfiguration(config);
    state.runs = runsPayload.runs || [];
    renderRunCollections();
    if (current) attachRun(current);
    if (!config.provider_ready) {
      refs.formError.textContent = "模型服务尚未就绪；可以浏览界面，但正式任务需要先加载项目配置。";
    }
  } catch (error) {
    showToast(`Console 无法连接：${error.message}`);
  }
}

function populateConfiguration(config) {
  refs.caseSelect.replaceChildren();
  refs.actionModel.replaceChildren();
  refs.actionWireCapability.replaceChildren();
  refs.goalModel.replaceChildren();
  refs.perceptionSelect.replaceChildren();
  config.cases.forEach((item) => refs.caseSelect.append(option(item.case_id, humanizeTask(item.task_id))));
  config.action_models.forEach((item) => refs.actionModel.append(option(item.id, item.id)));
  config.action_wire_capabilities.forEach((item) => refs.actionWireCapability.append(option(item, item)));
  config.goal_models.forEach((item) => refs.goalModel.append(option(item, item)));
  config.perception_profiles.forEach((item) => refs.perceptionSelect.append(option(item, item)));
  refs.perceptionSelect.value = "structure-first.v1";
  updateCaseMeta();
  updateModelReadout();
}

function humanizeTask(value) {
  const label = String(value || "Untitled task").replace(/^browsergym\/miniwob\./, "").replaceAll("-", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function updateCaseMeta() {
  const item = state.config?.cases.find((entry) => entry.case_id === refs.caseSelect.value);
  refs.caseMeta.textContent = item
    ? `seed ${item.seed} · ${item.max_turns} steps · ${item.timeout_s}s watchdog`
    : "Frozen manifest";
}

function updateModelReadout() {
  refs.thinkingReadout.textContent = refs.actionWireCapability.value === "native_single_tool"
    ? "disabled · 512"
    : "provider profile";
}

function openLabs(tab = "experiment") {
  switchLabsTab(tab);
  refs.drawerBackdrop.hidden = false;
  refs.labsDrawer.inert = false;
  refs.labsDrawer.classList.add("open");
  refs.labsDrawer.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => refs.closeLabsButton.focus());
}

function closeLabs() {
  refs.labsDrawer.classList.remove("open");
  refs.labsDrawer.setAttribute("aria-hidden", "true");
  refs.labsDrawer.inert = true;
  setTimeout(() => { refs.drawerBackdrop.hidden = true; }, 240);
}

function switchLabsTab(name) {
  state.activeLabsTab = name;
  document.querySelectorAll("[data-labs-tab]").forEach((button) => {
    const active = button.dataset.labsTab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-labs-view]").forEach((view) => {
    const active = view.dataset.labsView === name;
    view.classList.toggle("active", active);
    view.hidden = !active;
  });
  if (name === "evidence" && state.run) loadRawEvents();
}

function showToast(message) {
  clearTimeout(state.toastTimer);
  refs.toast.textContent = message;
  refs.toast.hidden = false;
  state.toastTimer = setTimeout(() => { refs.toast.hidden = true; }, 2600);
}

function renderRunCollections() {
  renderSessions();
  renderBadCases();
}

function renderSessions() {
  refs.sessionList.replaceChildren();
  if (!state.runs.length) {
    refs.sessionList.append(make("div", "session-placeholder", "启动一个任务后，会话会出现在这里。"));
    return;
  }
  state.runs.forEach((run) => {
    const button = make("button", `session ${run.run_id === state.run?.run_id ? "active" : ""}`);
    button.type = "button";
    const title = make("b", "", taskTitleForRun(run));
    const detail = make("small");
    const dot = make("i", `session-status ${run.status}`);
    detail.append(dot, document.createTextNode(`${runStatusLabel(run.status)} · ${formatRelativeTime(run.started_at)}`));
    button.append(title, detail);
    button.addEventListener("click", () => attachRun(run));
    refs.sessionList.append(button);
  });
}

function renderBadCases() {
  const failed = state.runs.filter((run) => run.status === "failed");
  refs.badCaseCount.textContent = String(failed.length);
  refs.badCaseList.replaceChildren();
  if (!failed.length) {
    const empty = make("div", "bad-case-empty");
    empty.append(make("b", "", "暂时没有 Bad case"), make("span", "", "失败运行会自动进入这里，不需要手动标记。"));
    refs.badCaseList.append(empty);
    return;
  }
  failed.forEach((run) => {
    const button = make("button", "bad-case");
    button.type = "button";
    const copy = make("div", "bad-case-copy");
    copy.append(make("b", "", taskTitleForRun(run)), make("small", "", `${run.spec.case_id} · ${formatRelativeTime(run.started_at)}`));
    button.append(copy, make("span", "", "failed"));
    button.addEventListener("click", () => {
      attachRun(run);
      switchLabsTab("evidence");
    });
    refs.badCaseList.append(button);
  });
}

function taskTitleForRun(run) {
  const item = state.config?.cases.find((entry) => entry.case_id === run.spec?.case_id);
  return humanizeTask(item?.task_id || run.spec?.case_id || "Task");
}

function runStatusLabel(status) {
  return ({ running: "执行中", completed: "已完成", failed: "未完成" })[status] || "未知";
}

function formatRelativeTime(value) {
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return "刚刚";
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000));
  if (seconds < 60) return "刚刚";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

async function loadRuns() {
  try {
    const payload = await api("/api/runs");
    state.runs = payload.runs || [];
    renderRunCollections();
  } catch (error) {
    showToast(error.message);
  }
}

function resetRunView() {
  state.activity = [];
  state.rawEvents = [];
  state.activityCursor = 0;
  state.rawCursor = 0;
  state.selectedRaw = null;
  state.frameRevision = 0;
  refs.activityStack.replaceChildren();
  refs.traceList.replaceChildren(make("div", "evidence-empty", "运行事件会按 Runtime 顺序出现在这里。"));
  refs.jsonInspector.textContent = "{}";
  refs.copyButton.disabled = true;
  refs.finalMessage.hidden = true;
  refs.browserImage.removeAttribute("src");
  refs.browserFrame.hidden = true;
  refs.browserEmpty.hidden = false;
  refs.viewerNote.hidden = true;
  refs.frameLoading.hidden = false;
}

function attachRun(run) {
  if (!run) return;
  const changed = state.run?.run_id !== run.run_id;
  if (changed) resetRunView();
  state.run = run;
  refs.welcomeState.hidden = true;
  refs.threadContent.hidden = false;
  refs.taskEyebrow.textContent = run.spec?.case_id || "TASK";
  refs.taskTitle.textContent = taskTitleForRun(run);
  refs.threadTime.textContent = new Date(run.started_at).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  refs.taskInstruction.textContent = taskTitleForRun(run);
  refs.evidenceRunName.textContent = taskTitleForRun(run);
  refs.evidencePath.textContent = run.evidence_dir || "No evidence directory";
  refs.stdoutOutput.textContent = run.stdout_tail?.join("\n") || "No runner output yet.";
  refs.browserAddress.textContent = taskTitleForRun(run);
  refs.launchButton.disabled = run.status === "running";
  refs.stopButton.disabled = run.status !== "running";
  updateRunChrome();
  renderRunCollections();
  startClock();
  clearInterval(state.poller);
  pollActivity();
  if (run.status === "running") state.poller = setInterval(pollActivity, 700);
}

async function pollActivity() {
  if (!state.run) return;
  const runId = state.run.run_id;
  if (state.pollingRunId === runId) return;
  state.pollingRunId = runId;
  try {
    const payload = await api(`/api/runs/${encodeURIComponent(runId)}/activity?after=${state.activityCursor}`);
    if (state.run?.run_id !== runId) return;
    state.run = payload.run;
    state.activityCursor = payload.next_cursor;
    payload.events.forEach(addActivityEvent);
    refs.stdoutOutput.textContent = state.run.stdout_tail?.join("\n") || "No runner output yet.";
    refs.evidencePath.textContent = state.run.evidence_dir || "No evidence directory";
    updateRunChrome();
    updateMetrics();
    syncWorkingIndicator();
    if (state.activeLabsTab === "evidence") await loadRawEvents();
    if (state.run.status !== "running") {
      clearInterval(state.poller);
      clearInterval(state.timer);
      renderFinalMessage();
      await loadRuns();
    }
  } catch (error) {
    showToast(error.message);
  } finally {
    if (state.pollingRunId === runId) state.pollingRunId = null;
  }
}

function addActivityEvent(event) {
  state.activity.push(event);
  if (event.event === "run_started") {
    if (event.instruction) refs.taskInstruction.textContent = event.instruction;
    addActivityRow("任务已交给 Agent", `最多 ${event.max_steps || "—"} 个决策步骤`, "done", event.sequence);
  } else if (event.event === "goal_compiler_completed") {
    const ready = event.disposition === "ready" || event.disposition === "not_required";
    addActivityRow(ready ? "目标已整理" : "目标指导不可用，继续直接执行", `${event.provider_attempt_count || 0} 次模型调用`, ready ? "done" : "failed", event.sequence);
  } else if (event.event === "model_turn") {
    addActivityRow(decisionLabel(event.outcome), `${event.attempt_count} 次尝试 · ${(Number(event.latency_ms || 0) / 1000).toFixed(1)} 秒`, "done", event.sequence);
  } else if (event.event === "step_completed") {
    const failed = ["failed", "blocked", "cancelled"].includes(event.status_after);
    addActivityRow(actionLabel(event), feedbackLabel(event.feedback, event.evaluation_status), failed ? "failed" : "done", event.sequence);
  } else if (event.event === "observation" && event.browser_frame_available) {
    refreshBrowserFrame(event.sequence);
  } else if (event.event === "run_error") {
    addActivityRow("运行遇到错误", "Runtime 已保留完整错误证据", "failed", event.sequence);
  }
}

function addActivityRow(title, detail, status, sequence) {
  if (refs.activityStack.querySelector(`[data-sequence="${sequence}"]`)) return;
  const row = make("div", `activity ${status}`);
  row.dataset.sequence = String(sequence);
  const copy = make("span", "activity-copy");
  copy.append(make("b", "", title), make("small", "", detail));
  row.append(copy);
  refs.activityStack.append(row);
}

function syncWorkingIndicator() {
  refs.activityStack.querySelector("[data-working]")?.remove();
  if (state.run?.status !== "running") return;
  const row = make("div", "activity current");
  row.dataset.working = "true";
  const icon = make("span", "activity-icon");
  icon.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 12 4-4 4 4 4-4 6 6"/><path d="M3 18h18"/></svg>';
  const copy = make("span", "activity-copy");
  copy.append(make("b", "", "正在读取当前页面并决定下一步"), make("small", "", "右侧浏览器会同步 Runtime 最新画面"));
  row.append(icon, copy);
  refs.activityStack.append(row);
}

function decisionLabel(outcome) {
  return ({
    SelectAction: "已选择一个页面操作",
    RequestObservation: "正在获取更多页面信息",
    RequestActionPage: "正在查找可用控件",
    AskUser: "需要你的补充信息",
    FinalResponse: "正在核对最终结果",
    Abort: "Agent 已停止任务",
  })[outcome] || "已完成一次决策";
}

function actionLabel(event) {
  const action = ({
    activate: "已操作页面控件",
    set_value: "已填写页面内容",
    select: "已选择页面选项",
    read: "已读取页面信息",
    navigate: "已打开新页面",
  })[event.semantic_action];
  if (action) return action;
  if (event.execution_completed) return "已执行页面操作";
  return `已完成步骤 ${event.step}`;
}

function feedbackLabel(feedback, evaluationStatus) {
  const friendly = ({
    action_postcondition_satisfied: "页面变化已由当前 World 验证",
    action_postcondition_unsatisfied_change_strategy: "页面变化不符合预期，Agent 将调整策略",
    action_unchanged_change_strategy: "页面没有变化，Agent 将调整策略",
    local_tool_result: "已获得本地工具结果",
    user_input_required: "等待用户输入",
    final_response_evaluated: "最终结果已经正式评估",
  })[feedback];
  return friendly || (evaluationStatus ? `任务状态：${evaluationStatus}` : feedback || "Runtime 已记录结果");
}

function updateRunChrome() {
  if (!state.run) return;
  const status = state.run.status;
  refs.runStatus.className = `status-pill ${status}`;
  refs.runStatus.querySelector("span").textContent = runStatusLabel(status);
  refs.browserControl.querySelector("span").textContent = status === "running" ? "Agent 控制中" : status === "completed" ? "任务已结束" : "浏览器已停止";
  refs.launchButton.disabled = status === "running";
  refs.stopButton.disabled = status !== "running";
  refs.composerHint.textContent = status === "running"
    ? "当前 Runtime 不支持运行中修改；需要结束后再启动新任务。"
    : "当前验证任务已结束；可以在 Labs 中启动另一项任务。";
}

function renderFinalMessage() {
  if (!state.run) return;
  refs.activityStack.querySelector("[data-working]")?.remove();
  refs.finalMessage.hidden = false;
  refs.finalMessageText.textContent = state.run.status === "completed"
    ? "任务运行已经结束。正式结果与完整证据保存在 Labs 中。"
    : "任务没有完成，Runtime 已保留失败阶段和完整证据。可以在 Labs → Bad cases 中检查。";
}

function refreshBrowserFrame(sequence = Date.now()) {
  if (!state.run) return;
  state.frameRevision = Math.max(state.frameRevision, Number(sequence) || 0);
  refs.browserEmpty.hidden = true;
  refs.browserFrame.hidden = false;
  refs.frameLoading.hidden = false;
  refs.viewerNote.hidden = false;
  refs.browserImage.src = `/api/runs/${encodeURIComponent(state.run.run_id)}/browser-frame?revision=${state.frameRevision}`;
}

refs.browserImage.addEventListener("load", () => {
  refs.frameLoading.hidden = true;
});

refs.browserImage.addEventListener("error", () => {
  refs.frameLoading.hidden = false;
  if (state.run?.status !== "running") {
    refs.browserFrame.hidden = true;
    refs.browserEmpty.hidden = false;
    refs.viewerNote.hidden = true;
  }
});

async function loadRawEvents() {
  if (!state.run) return;
  const runId = state.run.run_id;
  if (state.rawLoadingRunId === runId) return;
  state.rawLoadingRunId = runId;
  try {
    const payload = await api(`/api/runs/${encodeURIComponent(runId)}/events?after=${state.rawCursor}`);
    if (state.run?.run_id !== runId) return;
    state.rawCursor = payload.next_cursor;
    payload.events.forEach(addRawEvent);
    updateMetrics();
  } catch (error) {
    showToast(error.message);
  } finally {
    if (state.rawLoadingRunId === runId) state.rawLoadingRunId = null;
  }
}

function addRawEvent(event) {
  if (!state.rawEvents.length) refs.traceList.replaceChildren();
  state.rawEvents.push(event);
  const summary = summarizeRawEvent(event);
  const button = make("button", "trace-event");
  button.type = "button";
  button.append(
    make("span", "", String(event.sequence || state.rawEvents.length).padStart(3, "0")),
    traceEventCopy(summary.title, summary.detail),
    make("em", "", summary.badge),
  );
  button.addEventListener("click", () => selectRawEvent(event, button, summary));
  refs.traceList.append(button);
  if (state.rawEvents.length === 1) selectRawEvent(event, button, summary);
}

function traceEventCopy(title, detail) {
  const copy = make("span");
  copy.append(make("b", "", title), make("small", "", detail));
  return copy;
}

function summarizeRawEvent(event) {
  if (event.event === "goal_compiler_completed") {
    const diagnostic = event.diagnostic || {};
    return { title: "Goal compiler", detail: `${diagnostic.final_disposition || "unknown"} · ${diagnostic.provider_attempt_count || 0} attempts`, badge: "GOAL" };
  }
  if (event.event === "model_turn") {
    const attempts = event.generation_attempts || [];
    const latency = attempts.reduce((sum, item) => sum + Number(item.latency_ms || 0), 0);
    return { title: `Policy · ${event.outcome || "unknown"}`, detail: `${attempts.length} attempts · ${(latency / 1000).toFixed(2)}s`, badge: "MODEL" };
  }
  if (event.event === "step_completed") {
    return { title: `Step ${event.step}`, detail: event.result?.feedback || event.result?.status_after || "completed", badge: event.result?.execution ? "EXEC" : "STEP" };
  }
  if (event.event === "run_finished") return { title: "Run finished", detail: `${event.status} · ${event.execution_count || 0} executions`, badge: "FINAL" };
  if (event.event === "run_error") return { title: "Run error", detail: event.exception_class || event.error || "error", badge: "ERROR" };
  return { title: event.event || "Trace event", detail: event.observation_id || event.run_id || "recorded", badge: "TRACE" };
}

function selectRawEvent(event, button, summary) {
  state.selectedRaw = event;
  document.querySelectorAll(".trace-event").forEach((item) => item.classList.toggle("selected", item === button));
  refs.inspectorSummary.replaceChildren(make("b", "", summary.title), make("span", "", summary.detail));
  refs.jsonInspector.textContent = JSON.stringify(event, null, 2);
  refs.copyButton.disabled = false;
}

function updateMetrics() {
  const source = state.rawEvents.length ? state.rawEvents : state.activity;
  refs.eventCount.textContent = String(source.length);
  refs.turnCount.textContent = String(source.filter((item) => item.event === "model_turn").length);
  refs.executionCount.textContent = String(source.filter((item) => item.event === "step_completed" && (item.result?.execution || item.execution_completed)).length);
}

function startClock() {
  clearInterval(state.timer);
  if (state.run?.status !== "running") {
    refs.runClock.textContent = "—";
    return;
  }
  const tick = () => {
    if (!state.run || state.run.status !== "running") return;
    const elapsed = Math.max(0, Date.now() - Date.parse(state.run.started_at));
    const seconds = Math.floor(elapsed / 1000);
    refs.runClock.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  };
  tick();
  state.timer = setInterval(tick, 1000);
}

refs.runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  refs.formError.textContent = "";
  const payload = {
    case_id: refs.caseSelect.value,
    action_model: refs.actionModel.value,
    action_wire_capability: refs.actionWireCapability.value,
    goal_compiler_mode: state.goalMode,
    goal_compiler_model: state.goalMode === "model" ? refs.goalModel.value : "",
    perception_profile: refs.perceptionSelect.value,
    profile: refs.profileInput.value.trim(),
  };
  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    closeLabs();
    await loadRuns();
    attachRun(run);
  } catch (error) {
    refs.formError.textContent = error.message;
  }
});

refs.stopButton.addEventListener("click", async () => {
  if (!state.run) return;
  try {
    state.run = await api(`/api/runs/${encodeURIComponent(state.run.run_id)}/stop`, { method: "POST", body: "{}" });
    await pollActivity();
  } catch (error) {
    refs.formError.textContent = error.message;
  }
});

refs.copyButton.addEventListener("click", async () => {
  if (!state.selectedRaw) return;
  await navigator.clipboard.writeText(JSON.stringify(state.selectedRaw, null, 2));
  refs.copyButton.textContent = "已复制";
  setTimeout(() => { refs.copyButton.textContent = "复制 JSON"; }, 900);
});

document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
  state.goalMode = button.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("active", item === button));
  refs.goalModelField.hidden = state.goalMode === "disabled";
}));

document.querySelectorAll("[data-labs-tab]").forEach((button) => button.addEventListener("click", () => {
  switchLabsTab(button.dataset.labsTab);
}));

refs.caseSelect.addEventListener("change", updateCaseMeta);
refs.actionModel.addEventListener("change", updateModelReadout);
refs.actionWireCapability.addEventListener("change", updateModelReadout);
refs.newTaskButton.addEventListener("click", () => openLabs("experiment"));
refs.welcomeStartButton.addEventListener("click", () => openLabs("experiment"));
refs.composerLabsButton.addEventListener("click", () => openLabs("experiment"));
refs.composerSend.addEventListener("click", () => openLabs("experiment"));
refs.composerInput.addEventListener("click", () => openLabs("experiment"));
refs.labsButton.addEventListener("click", () => openLabs("experiment"));
refs.conversationMenu.addEventListener("click", () => openLabs("evidence"));
refs.closeLabsButton.addEventListener("click", closeLabs);
refs.drawerBackdrop.addEventListener("click", closeLabs);
refs.settingsButton.addEventListener("click", () => showToast("设置会在独立产品配置页开放。"));
refs.fullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await refs.browserStage.requestFullscreen();
  } catch (error) {
    showToast(`无法进入全屏：${error.message}`);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && refs.labsDrawer.classList.contains("open") && !document.fullscreenElement) closeLabs();
});

initialize();
