import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EffectReconciliationNotice, LiveView, Progress } from "./shell-app";
import type { Snapshot } from "@/lib/types";

describe("public fact renderers", () => {
  it("renders typed unavailable instead of building a media stream", () => {
    render(<LiveView snapshot={null} />);
    expect(screen.getByTestId("viewer-unavailable")).toHaveTextContent("viewer_not_configured");
    expect(screen.getByText(/takeover unsupported/i)).toBeInTheDocument();
  });

  it("renders only the owner-projected same-origin read-only viewer path", () => {
    const snapshot = {
      viewer: {
        status: "available",
        provider: "steel",
        protected_path: "/viewer/shell-session",
        reason_code: "",
        read_only: true,
      },
    } as unknown as Snapshot;

    render(<LiveView snapshot={snapshot} />);

    const frame = screen.getByTitle("Read-only browser live view");
    expect(frame).toHaveAttribute("src", "/viewer/shell-session");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin");
    expect(frame).not.toHaveAttribute("allow");
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

  it("renders the Runtime-owned reconciliation summary without execution details", () => {
    const snapshot = {
      effect_reconciliation: {
        status: "needs_input",
        code: "compensation_unverified",
        original_effect_ref: `effect:sha256:${"a".repeat(64)}`,
        original_action: "set_state",
        resource_ref: "account:second",
        reversibility: "reversible",
        compensation_effect_ref: "",
      },
    } as unknown as Snapshot;

    render(<EffectReconciliationNotice snapshot={snapshot} />);

    expect(screen.getByTestId("effect-reconciliation")).toHaveTextContent("needs_input");
    expect(screen.getByTestId("effect-reconciliation")).toHaveTextContent("account:second");
    expect(screen.getByTestId("effect-reconciliation")).toHaveTextContent("compensation_unverified");
    expect(screen.queryByText(/selector|coordinate|backend/i)).not.toBeInTheDocument();
  });
});
