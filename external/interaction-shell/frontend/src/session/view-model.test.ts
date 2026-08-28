import { describe, expect, it } from "vitest";
import { parse } from "valibot";
import { vRuntimeSessionSnapshot } from "@/generated/valibot.gen";
import { projectShellView, statusPresentation } from "./view-model";

const base = () => parse(vRuntimeSessionSnapshot, {
  schema_version: "interaction-shell.v4",
  session_id: "session-view-model",
  event_epoch: "event-epoch-view-model",
  event_cursor: 0,
  expires_at: "2026-08-28T12:00:00Z",
  task_id: null,
  task_text: null,
  task_revision: 0,
  run_status: "idle",
  control_owner: "agent",
  resume_eligible: false,
  public_steps: [],
  feed: [],
  completion: null,
  checkpoint_id: null,
  last_control_outcome: null,
  effect_reconciliation: null,
  control_lease_id: null,
  command_offers: [{ kind: "start_task" }, { kind: "close_session" }],
  surface: { status: "unavailable", reason_code: "surface_not_configured" },
});

describe("projectShellView", () => {
  it("keeps every Runtime status distinct and derives user control orthogonally", () => {
    expect(statusPresentation("waiting_user", "agent").label).toBe("等待你的回答");
    expect(statusPresentation("waiting_confirmation", "agent").label).toBe("等待操作确认");
    expect(statusPresentation("paused", "agent").label).toBe("任务已暂停");
    expect(statusPresentation("paused", "user")).toEqual({ label: "你正在控制界面", tone: "user_control" });
    expect(statusPresentation("blocked", "agent").label).toBe("需要处理后才能继续");
    expect(statusPresentation("failed", "agent").label).toBe("处理失败");
  });

  it("derives composer behavior from exact command offers", () => {
    const snapshot = {
      ...base(),
      run_status: "waiting_user" as const,
      task_revision: 2,
      command_offers: [{
        kind: "respond_interaction" as const,
        request: {
          request_id: "request-1",
          prompt: "Choose one",
          response_kind: "single_select" as const,
          fields: [],
          options: [],
          public_intent: "I need a decision.",
        },
      }, { kind: "revise_task" as const }],
    };
    const view = projectShellView(snapshot);
    expect(view.interaction?.request_id).toBe("request-1");
    expect(view.composer).toMatchObject({ mode: "interaction", enabled: false });
    expect(view.actions.revise).toBe(true);
  });

  it("offers generic live-surface takeover directly at a waiting-user boundary", () => {
    const view = projectShellView({
      ...base(),
      run_status: "waiting_user",
      task_revision: 1,
      command_offers: [{ kind: "take_over" }, { kind: "close_session" }],
      surface: { status: "read_only", surface_kind: "web", presentation: "live_media", protected_path: "/viewer/session-view-model" },
    });

    expect(view.actions.takeOver).toBe(true);
    expect(view.snapshot?.checkpoint_id).toBeNull();
  });

  it("does not invent a confirmation or text action from run status", () => {
    const view = projectShellView({
      ...base(),
      run_status: "waiting_confirmation",
      command_offers: [{ kind: "close_session" }],
    });
    expect(view.confirmation).toBeNull();
    expect(view.composer).toMatchObject({ mode: "unavailable", enabled: false });
  });

  it("projects the latest Runtime-authored goal and bounded feed", () => {
    const snapshot = {
      ...base(),
      task_revision: 2,
      feed: [{
        block_id: "goal-1",
        kind: "goal_accepted" as const,
        occurred_at: "2026-08-28T10:00:00Z",
        summary: "First goal",
        constraints: [],
        task_revision: 1,
      }, {
        block_id: "goal-2",
        kind: "goal_accepted" as const,
        occurred_at: "2026-08-28T10:01:00Z",
        summary: "Revised goal",
        constraints: ["Do not submit"],
        task_revision: 2,
      }],
    };
    const view = projectShellView(snapshot);
    expect(view.feed).toHaveLength(2);
    expect(view.goal?.summary).toBe("Revised goal");
  });
});
