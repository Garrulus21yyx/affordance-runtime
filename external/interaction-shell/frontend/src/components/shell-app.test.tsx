import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LiveView, Progress } from "./shell-app";
import type { Snapshot } from "@/lib/types";

describe("public fact renderers", () => {
  it("renders typed unavailable instead of building a media stream", () => {
    render(<LiveView snapshot={null} />);
    expect(screen.getByTestId("viewer-unavailable")).toHaveTextContent("viewer_not_configured");
    expect(screen.getByText(/takeover unsupported/i)).toBeInTheDocument();
  });

  it("renders only owner-projected operator progress", () => {
    const snapshot = {
      task_text: "Choose an option",
      run_status: "active",
      public_steps: [{ step: 1, stage: "intake", status: "finished", label: "Task started", attempt: 1, retry_count: 0, recovery_count: 0, latency_ms: 42, evidence_refs: [] }],
    } as unknown as Snapshot;
    render(<Progress snapshot={snapshot} />);
    expect(screen.getByText("Task started")).toBeInTheDocument();
    expect(screen.queryByText(/latency/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/token/i)).not.toBeInTheDocument();
  });
});
