const state = {
  config: null,
  run: null,
  events: [],
  cursor: 0,
  selected: null,
  goalMode: "model",
  timer: null,
  poller: null,
};

const $ = (id) => document.getElementById(id);
const refs = Object.fromEntries([
  "systemSignal", "systemLabel", "systemDetail", "runForm", "caseSelect", "caseMeta",
  "actionModel", "actionWireCapability", "thinkingReadout", "goalModel", "goalModelField",
  "perceptionSelect", "profileInput", "launchButton", "stopButton", "formError", "runStatus",
  "runClock", "eventCount", "turnCount", "executionCount", "outcomeReadout", "eventRail",
  "emptyState", "inspectorSummary", "jsonInspector", "copyButton", "stdoutToggle", "stdoutOutput",
  "evidencePath",
].map((id) => [id, $(id)]));

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

function option(value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  return item;
}

async function initialize() {
  try {
    state.config = await api("/api/config");
    state.config.cases.forEach((item) => refs.caseSelect.append(option(item.case_id, `${item.case_id} · ${item.task_id}`)));
    state.config.action_models.forEach((item) => refs.actionModel.append(option(item.id, item.id)));
    state.config.action_wire_capabilities.forEach((item) => refs.actionWireCapability.append(option(item, item)));
    state.config.goal_models.forEach((item) => refs.goalModel.append(option(item, item)));
    state.config.perception_profiles.forEach((item) => refs.perceptionSelect.append(option(item, item)));
    refs.perceptionSelect.value = "structure-first.v1";
    updateModelReadout();
    updateCaseMeta();
    refs.systemSignal.className = `signal ${state.config.provider_ready ? "ready" : "error"}`;
    refs.systemLabel.textContent = state.config.provider_ready ? "Provider ready" : "Provider unavailable";
    refs.systemDetail.textContent = `${state.config.provider} · ${state.config.manifest}`;
    const current = await api("/api/runs/current");
    if (current) attachRun(current);
  } catch (error) {
    refs.systemSignal.className = "signal error";
    refs.systemLabel.textContent = "Console unavailable";
    refs.systemDetail.textContent = error.message;
  }
}

function updateCaseMeta() {
  const item = state.config?.cases.find((entry) => entry.case_id === refs.caseSelect.value);
  refs.caseMeta.textContent = item ? `seed ${item.seed} · ${item.max_turns} turns · ${item.timeout_s}s watchdog` : "Frozen manifest";
}

function updateModelReadout() {
  refs.thinkingReadout.textContent = refs.actionWireCapability.value === "native_single_tool"
    ? "disabled · 512"
    : "provider profile";
}

document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
  state.goalMode = button.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("active", item === button));
  refs.goalModelField.hidden = state.goalMode === "disabled";
}));
refs.caseSelect.addEventListener("change", updateCaseMeta);
refs.actionModel.addEventListener("change", updateModelReadout);
refs.actionWireCapability.addEventListener("change", updateModelReadout);

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
    resetRun();
    attachRun(run);
  } catch (error) {
    refs.formError.textContent = error.message;
  }
});

refs.stopButton.addEventListener("click", async () => {
  if (!state.run) return;
  await api(`/api/runs/${state.run.run_id}/stop`, { method: "POST", body: "{}" });
  await poll();
});

refs.copyButton.addEventListener("click", async () => {
  if (!state.selected) return;
  await navigator.clipboard.writeText(JSON.stringify(state.selected, null, 2));
  refs.copyButton.textContent = "Copied";
  setTimeout(() => { refs.copyButton.textContent = "Copy JSON"; }, 900);
});

refs.stdoutToggle.addEventListener("click", () => {
  refs.stdoutOutput.hidden = !refs.stdoutOutput.hidden;
  refs.stdoutToggle.querySelector("span").textContent = refs.stdoutOutput.hidden ? "＋" : "−";
});

function resetRun() {
  state.events = [];
  state.cursor = 0;
  state.selected = null;
  refs.eventRail.replaceChildren();
  refs.jsonInspector.textContent = "{}";
  refs.copyButton.disabled = true;
}

function attachRun(run) {
  state.run = run;
  refs.launchButton.disabled = run.status === "running";
  refs.stopButton.disabled = run.status !== "running";
  refs.evidencePath.textContent = run.evidence_dir;
  refs.runStatus.textContent = run.status.toUpperCase();
  startClock();
  clearInterval(state.poller);
  state.poller = setInterval(poll, 700);
  poll();
}

async function poll() {
  if (!state.run) return;
  try {
    const payload = await api(`/api/runs/${state.run.run_id}/events?after=${state.cursor}`);
    state.run = payload.run;
    state.cursor = payload.next_cursor;
    payload.events.forEach(addEvent);
    refs.launchButton.disabled = state.run.status === "running";
    refs.stopButton.disabled = state.run.status !== "running";
    refs.runStatus.textContent = state.run.status.toUpperCase();
    refs.stdoutOutput.textContent = state.run.stdout_tail.join("\n") || "No runner output yet.";
    updateMetrics();
    if (state.run.status !== "running") clearInterval(state.poller);
  } catch (error) {
    refs.formError.textContent = error.message;
  }
}

function addEvent(event) {
  state.events.push(event);
  refs.emptyState?.remove();
  const button = document.createElement("button");
  button.type = "button";
  button.className = "trace-event";
  const summary = summarize(event);
  button.innerHTML = `
    <span class="event-seq">${String(event.sequence || state.events.length).padStart(3, "0")}</span>
    <span class="event-main"><b>${escapeHtml(summary.title)}</b><small>${escapeHtml(summary.detail)}</small></span>
    <span class="event-badge ${summary.failed ? "failed" : ""}">${escapeHtml(summary.badge)}</span>`;
  button.addEventListener("click", () => selectEvent(event, button, summary));
  refs.eventRail.append(button);
  refs.eventRail.scrollTop = refs.eventRail.scrollHeight;
  if (state.events.length === 1) selectEvent(event, button, summary);
}

function summarize(event) {
  if (event.event === "goal_compiler_completed") {
    const d = event.diagnostic || {};
    return { title: "Goal compiler", detail: `${d.final_disposition || "unknown"} · ${d.provider_attempt_count || 0} provider attempts`, badge: "GOAL", failed: d.final_disposition === "failed" };
  }
  if (event.event === "model_turn") {
    const attempts = event.generation_attempts || [];
    const ms = attempts.reduce((sum, item) => sum + Number(item.latency_ms || 0), 0);
    return { title: `Policy · ${event.outcome || "unknown"}`, detail: `${attempts.length} attempts · ${(ms / 1000).toFixed(2)}s`, badge: "MODEL", failed: event.outcome === "PolicyFailure" };
  }
  if (event.event === "step_completed") {
    return { title: `Step ${event.step}`, detail: event.result?.feedback || event.result?.status_after || "completed", badge: event.result?.execution ? "EXEC" : "STEP", failed: event.result?.status_after === "failed" };
  }
  if (event.event === "run_finished") return { title: "Run finished", detail: `${event.status} · ${event.execution_count || 0} executions`, badge: "FINAL", failed: event.status !== "done" };
  if (event.event === "run_error") return { title: "Run error", detail: event.exception_class || event.error || "error", badge: "ERROR", failed: true };
  return { title: event.event || "Trace event", detail: event.observation_id || event.run_id || "recorded", badge: "TRACE", failed: false };
}

function selectEvent(event, button, summary) {
  state.selected = event;
  document.querySelectorAll(".trace-event").forEach((item) => item.classList.toggle("selected", item === button));
  refs.inspectorSummary.innerHTML = `<span>${escapeHtml(summary.title)}</span><p>${escapeHtml(summary.detail)}</p>`;
  refs.jsonInspector.textContent = JSON.stringify(event, null, 2);
  refs.copyButton.disabled = false;
}

function updateMetrics() {
  refs.eventCount.textContent = state.events.length;
  refs.turnCount.textContent = state.events.filter((item) => item.event === "model_turn").length;
  refs.executionCount.textContent = state.events.filter((item) => item.event === "step_completed" && item.result?.execution).length;
  refs.outcomeReadout.textContent = state.run?.report ? Object.keys(state.run.report.outcome_counts || {})[0] || "—" : state.run?.status || "—";
}

function startClock() {
  clearInterval(state.timer);
  const tick = () => {
    if (!state.run) return;
    const elapsed = Math.max(0, Date.now() - Date.parse(state.run.started_at));
    const seconds = Math.floor(elapsed / 1000);
    refs.runClock.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  };
  tick();
  state.timer = setInterval(tick, 1000);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

initialize();
