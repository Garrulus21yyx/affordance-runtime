import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ listCompletedRuns: vi.fn() }));
vi.mock("@/generated/sdk.gen", () => api);

import { DiagnosticsWorkbench } from "./diagnostics-workbench";

describe("completed-run summary surface", () => {
  beforeEach(() => api.listCompletedRuns.mockReset());

  it("renders bounded owner values and independent link availability", async () => {
    api.listCompletedRuns.mockResolvedValue({ data: [
      {
        schema_version: "interaction-shell.completed-run.v1",
        locator_id: "a".repeat(32),
        run_attempt_id: `attempt:${"b".repeat(32)}`,
        case_id: "case-1",
        benchmark_result: "available",
        status: "done",
        turns: 3,
        provider_input_tokens: 100,
        provider_output_tokens: 20,
        recoveries: 1,
        control_stalls: 1,
        state_oscillations: 0,
        detour_disposition: "not_assessed",
        langfuse_url: null,
        local_evidence_url: `/diagnostics/evidence/${"a".repeat(32)}/result`,
      },
    ] });

    render(<DiagnosticsWorkbench />);

    await waitFor(() => expect(screen.getByTestId("completed-run-summary")).toBeVisible());
    expect(screen.getByText("Langfuse unavailable")).toBeVisible();
    expect(screen.getByRole("link", { name: /Local result/i })).toHaveAttribute(
      "href",
      `/shell-api/diagnostics/evidence/${"a".repeat(32)}/result`,
    );
    expect(screen.queryByText(/system tokens|history share|likely upstream/i)).not.toBeInTheDocument();
  });
});
