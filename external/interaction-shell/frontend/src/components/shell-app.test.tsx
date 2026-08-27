import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { parse } from "valibot";
import { vRuntimeSessionSnapshot } from "@/generated/valibot.gen";
import { projectShellView } from "@/session/view-model";
import { EffectReconciliationNotice, LiveView, Progress } from "./shell-app";

const base = () => parse(vRuntimeSessionSnapshot, {
  schema_version: "interaction-shell.v3",
  session_id: "session-1",
  event_epoch: "event-epoch-00000001",
  event_cursor: 0,
  expires_at: "2026-08-27T12:00:00Z",
  task_id: null,
  task_text: null,
  completion: null,
  checkpoint_id: null,
  last_control_outcome: null,
  effect_reconciliation: null,
  control_lease_id: null,
  command_offers: [{ kind: "start_task" }, { kind: "close_session" }],
  surface: { status: "unavailable", reason_code: "surface_not_configured" },
});

afterEach(cleanup);

describe("public fact renderers", () => {
  it("renders typed unavailable without provider or lease inference", () => {
    render(<LiveView view={projectShellView(base())} />);
    expect(screen.getByTestId("surface-unavailable")).toHaveTextContent("surface_not_configured");
    expect(screen.queryByText(/provider|lease/i)).not.toBeInTheDocument();
  });

  it("renders only the owner-projected same-origin read-only surface", () => {
    const snapshot = parse(vRuntimeSessionSnapshot, {
      ...base(),
      surface: { status: "read_only", surface_kind: "web", presentation: "live_media", protected_path: "/viewer/session-1" },
    });
    const rendered = render(<LiveView view={projectShellView(snapshot)} />);
    const scope = within(rendered.container);
    const frame = scope.getByTitle("Read-only live surface");
    expect(frame).toHaveAttribute("src", "/viewer/session-1");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin");
    expect(scope.getByTestId("surface-control-state")).toHaveTextContent("Agent 控制");
  });

  it("reloads an interactive surface when the opaque lease changes", () => {
    const snapshot = parse(vRuntimeSessionSnapshot, {
      ...base(),
      run_status: "paused",
      control_owner: "user",
      control_lease_id: `lease:${"u".repeat(32)}`,
      command_offers: [{ kind: "return_control" }, { kind: "close_session" }],
      surface: { status: "interactive", surface_kind: "web", presentation: "live_media", protected_path: "/viewer/session-1", input_mode: "native" },
    });
    const rendered = render(<LiveView view={projectShellView(snapshot)} />);
    const scope = within(rendered.container);
    const first = scope.getByTitle("Interactive live surface");
    rendered.rerender(<LiveView view={projectShellView({ ...snapshot, control_lease_id: `lease:${"v".repeat(32)}` })} />);
    expect(scope.getByTitle("Interactive live surface")).not.toBe(first);
  });

  it("renders only owner-projected progress", () => {
    const snapshot = parse(vRuntimeSessionSnapshot, {
      ...base(),
      task_text: "Choose an option",
      run_status: "running",
      public_steps: [{ step: 1, stage: "intake", status: "finished", label: "Task started" }],
    });
    render(<Progress view={projectShellView(snapshot)} />);
    expect(screen.getByText("Task started")).toBeInTheDocument();
    expect(screen.queryByText(/latency|token/i)).not.toBeInTheDocument();
  });

  it("renders Runtime-owned effect reconciliation without execution details", () => {
    const snapshot = parse(vRuntimeSessionSnapshot, {
      ...base(),
      effect_reconciliation: { status: "needs_input", code: "compensation_unverified", original_effect_ref: "effect-1", original_action: "set_state", resource_ref: "account:second", reversibility: "reversible" },
    });
    render(<EffectReconciliationNotice view={projectShellView(snapshot)} />);
    expect(screen.getByTestId("effect-reconciliation")).toHaveTextContent("compensation_unverified");
    expect(screen.queryByText(/selector|coordinate|backend/i)).not.toBeInTheDocument();
  });
});
