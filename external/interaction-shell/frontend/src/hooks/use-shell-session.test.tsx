import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
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
    expires_at: "2026-08-26T13:00:00Z",
  },
} as CreatedSession;

function Probe() {
  const shell = useShellSession();
  return <div data-testid="session-id">{shell.snapshot?.session_id ?? "opening"}</div>;
}

describe("session acquisition", () => {
  beforeEach(() => {
    api.createSession.mockReset();
    api.createSession.mockResolvedValue(created);
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
});
