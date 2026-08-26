import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CreatedSession } from "@/lib/types";

const api = vi.hoisted(() => ({
  createSession: vi.fn(),
  postCommand: vi.fn(),
  subscribeEvents: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

import { useShellSession } from "./use-shell-session";

const created = {
  session_key: "session-key",
  snapshot: {
    schema_version: "interaction-shell.v1",
    session_id: "session:strict-mode",
    task_id: null,
    task_revision: 0,
    task_text: null,
    run_status: "idle",
    event_epoch: "epoch:strict-mode",
    event_cursor: 0,
    pending_question: null,
    pending_confirmation: null,
    completion: null,
    capabilities: ["start_task", "close_session"],
    viewer: {
      status: "unavailable",
      provider: null,
      protected_path: null,
      reason_code: "viewer_provider_not_configured",
      read_only: true,
    },
    usage: {
      prompt_tokens: 0,
      completion_tokens: 0,
      cost_usd: null,
      model_latency_ms: 0,
      runtime_latency_ms: 0,
    },
    public_steps: [],
    resume_eligible: false,
    expires_at: "2026-08-26T13:00:00Z",
  },
} as CreatedSession;

function Probe() {
  const shell = useShellSession();
  return <div data-testid="session-id">{shell.snapshot?.session_id ?? "opening"}</div>;
}

function CancelProbe() {
  const shell = useShellSession();
  return <button onClick={shell.cancel}>cancel</button>;
}

function PauseProbe() {
  const shell = useShellSession();
  return <button onClick={shell.pause}>pause</button>;
}

describe("session acquisition", () => {
  beforeEach(() => {
    api.createSession.mockReset();
    api.createSession.mockResolvedValue(created);
    api.postCommand.mockReset();
    api.subscribeEvents.mockReset();
    api.subscribeEvents.mockReturnValue(new Promise(() => undefined));
  });

  it("opens one backend session across the React StrictMode effect replay", async () => {
    render(
      <StrictMode>
        <Probe />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByTestId("session-id")).toHaveTextContent("session:strict-mode"));
    expect(api.createSession).toHaveBeenCalledTimes(1);
  });

  it("sends the advertised cooperative cancel command through the optional route", async () => {
    const active = {
      ...created,
      snapshot: {
        ...created.snapshot,
        task_id: "session:strict-mode",
        task_revision: 1,
        task_text: "Choose an option",
        run_status: "running" as const,
        capabilities: ["start_task", "cancel_task", "close_session"] as const,
      },
    } as CreatedSession;
    api.createSession.mockResolvedValue(active);
    api.postCommand.mockResolvedValue({ kind: "accepted", command_id: "cancel", snapshot: active.snapshot });
    render(<CancelProbe />);
    await waitFor(() => expect(api.createSession).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "cancel" }));

    await waitFor(() => expect(api.postCommand).toHaveBeenCalledTimes(1));
    expect(api.postCommand).toHaveBeenCalledWith(
      "session:strict-mode",
      "session-key",
      "commands/optional",
      expect.objectContaining({
        kind: "cancel_task",
        expected_task_revision: 1,
        expected_run_status: "running",
      }),
    );
  });

  it("sends the advertised durable pause command through the optional route", async () => {
    const active = {
      ...created,
      snapshot: {
        ...created.snapshot,
        task_id: "session:strict-mode",
        task_revision: 1,
        task_text: "Choose an option",
        run_status: "running" as const,
        capabilities: ["start_task", "pause_task", "close_session"] as const,
      },
    } as CreatedSession;
    api.createSession.mockResolvedValue(active);
    api.postCommand.mockResolvedValue({ kind: "accepted", command_id: "pause", snapshot: active.snapshot });
    render(<PauseProbe />);
    await waitFor(() => expect(api.createSession).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "pause" }));

    await waitFor(() => expect(api.postCommand).toHaveBeenCalledTimes(1));
    expect(api.postCommand).toHaveBeenCalledWith(
      "session:strict-mode",
      "session-key",
      "commands/optional",
      expect.objectContaining({
        kind: "pause_task",
        expected_task_revision: 1,
        expected_run_status: "running",
      }),
    );
  });
});
