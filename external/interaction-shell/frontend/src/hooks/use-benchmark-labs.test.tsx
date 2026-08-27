import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  getCurrentLabRun: vi.fn(),
  getLabConfiguration: vi.fn(),
  getLabRunActivity: vi.fn(),
  getLabRunBrowserFrame: vi.fn(),
  getLabRunEvents: vi.fn(),
  listCompletedRuns: vi.fn(),
  listLabRuns: vi.fn(),
  startLabRun: vi.fn(),
  stopLabRun: vi.fn(),
}));

vi.mock("@/generated/sdk.gen", () => sdk);
vi.mock("@/generated/valibot.gen", () => ({
  vGetCurrentLabRunResponse: {},
  vGetLabConfigurationResponse: {},
  vGetLabRunActivityResponse: {},
  vGetLabRunEventsResponse: {},
  vListCompletedRunsResponse: {},
  vListLabRunsResponse: {},
  vStartLabRunResponse: {},
  vStopLabRunResponse: {},
}));
vi.mock("valibot", () => ({ parse: (_schema: unknown, value: unknown) => value }));
vi.mock("@/session/client", () => ({ shellClient: {} }));

import { useBenchmarkLabs } from "./use-benchmark-labs";

const run = {
  run_id: "lab-run-1",
  status: "running",
  return_code: null,
  started_at: "2026-08-27T22:00:00Z",
  spec: {
    case_id: "miniwob-60-03",
    action_model: "glm-4.6",
    goal_compiler_mode: "disabled",
    goal_compiler_model: "glm-4.7-flash",
    perception_profile: "text-only.v1",
    profile: "CONSOLE_EXPERIMENT",
    action_wire_capability: "native_single_tool",
  },
  evidence_dir: "/tmp/lab-run-1",
  stdout_tail: [],
  report: null,
} as const;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Labs polling schedule", () => {
  it("keeps the 700ms cadence when an empty poll returns a new summary object", async () => {
    sdk.getLabConfiguration.mockResolvedValue({ data: { cases: [] } });
    sdk.listLabRuns.mockResolvedValue({ data: { runs: [run] } });
    sdk.getCurrentLabRun.mockResolvedValue({ data: run });
    sdk.listCompletedRuns.mockResolvedValue({ data: [] });
    sdk.getLabRunActivity.mockImplementation(async () => ({
      data: { events: [], next_cursor: 0, run: { ...run } },
    }));
    sdk.getLabRunEvents.mockImplementation(async () => ({
      data: { events: [], next_cursor: 0, run: { ...run } },
    }));

    const rendered = renderHook(() => useBenchmarkLabs(true));
    await waitFor(() => expect(sdk.getLabRunActivity).toHaveBeenCalledTimes(1));

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    });
    expect(sdk.getLabRunActivity).toHaveBeenCalledTimes(1);
    expect(sdk.getLabRunEvents).toHaveBeenCalledTimes(1);

    await waitFor(
      () => expect(sdk.getLabRunActivity).toHaveBeenCalledTimes(2),
      { timeout: 900 },
    );
    rendered.unmount();
  });
});
