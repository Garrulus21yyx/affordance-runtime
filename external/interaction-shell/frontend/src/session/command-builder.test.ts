import { describe, expect, it } from "vitest";
import { parse } from "valibot";
import { vRuntimeSessionSnapshot } from "@/generated/valibot.gen";
import { buildCommand, offerFor, type CommandIntent } from "./command-builder";

const intents: CommandIntent[] = [
  { kind: "start_task", text: "start" },
  { kind: "answer_question", text: "answer" },
  { kind: "confirm_action", approved: true },
  { kind: "cancel_task" },
  { kind: "pause_task" },
  { kind: "resume_task" },
  { kind: "revise_task", text: "revise" },
  { kind: "take_over" },
  { kind: "return_control" },
  { kind: "close_session" },
];

const snapshot = parse(vRuntimeSessionSnapshot, {
  schema_version: "interaction-shell.v3",
  session_id: "session-1",
  event_epoch: "event-epoch-00000001",
  expires_at: "2026-08-27T12:00:00Z",
  task_id: null,
  task_text: null,
  completion: null,
  last_control_outcome: null,
  effect_reconciliation: null,
  run_status: "paused",
  task_revision: 3,
  checkpoint_id: "checkpoint-1",
  control_owner: "user",
  control_lease_id: `lease:${"x".repeat(32)}`,
  command_offers: [
    { kind: "start_task" },
    { kind: "answer_question", request_id: "question-1", prompt: "Question?" },
    { kind: "confirm_action", request_id: "confirmation-1", summary: "Confirm", risk: "medium" },
    { kind: "cancel_task" }, { kind: "pause_task" }, { kind: "resume_task" },
    { kind: "revise_task" }, { kind: "take_over" }, { kind: "return_control" }, { kind: "close_session" },
  ],
  surface: { status: "interactive", surface_kind: "web", presentation: "live_media", protected_path: "/viewer/session-1", input_mode: "native" },
});

describe("typed command builder", () => {
  it.each(intents)("builds only offered $kind commands with one currentness frame", (intent) => {
    const offer = offerFor(snapshot, intent.kind);
    expect(offer).toBeDefined();
    const command = buildCommand(snapshot, offer!, intent, "command-1");
    expect(command.command_id).toBe("command-1");
    expect(command.expected_task_revision).toBe(3);
    expect(command.expected_run_status).toBe("paused");
  });

  it("copies interaction refs, checkpoint and lease only from owner offers/snapshot", () => {
    expect(buildCommand(snapshot, offerFor(snapshot, "answer_question")!, { kind: "answer_question", text: "yes" }, "c1")).toMatchObject({ request_id: "question-1" });
    expect(buildCommand(snapshot, offerFor(snapshot, "take_over")!, { kind: "take_over" }, "c2")).toMatchObject({ checkpoint_id: "checkpoint-1" });
    expect(buildCommand(snapshot, offerFor(snapshot, "return_control")!, { kind: "return_control" }, "c3")).toMatchObject({ control_lease_id: snapshot.control_lease_id });
  });

  it("rejects an intent that does not match the selected offer", () => {
    expect(() => buildCommand(snapshot, offerFor(snapshot, "pause_task")!, { kind: "cancel_task" }, "c1")).toThrow("command_offer_intent_mismatch");
  });
});
