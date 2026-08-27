import type { SubmitCommandData } from "@/generated/types.gen";
import type { CommandOffer, CommandOfferKind, Snapshot } from "./types";

export type CommandIntent =
  | { kind: "start_task"; text: string }
  | { kind: "answer_question"; text: string }
  | { kind: "confirm_action"; approved: boolean }
  | { kind: "cancel_task" }
  | { kind: "pause_task" }
  | { kind: "resume_task" }
  | { kind: "revise_task"; text: string }
  | { kind: "take_over" }
  | { kind: "return_control" }
  | { kind: "close_session" };

export type ShellCommand = SubmitCommandData["body"];

export function offerFor(snapshot: Snapshot, kind: CommandOfferKind): CommandOffer | undefined {
  return snapshot.command_offers.find((offer) => offer.kind === kind);
}

export function buildCommand(
  snapshot: Snapshot,
  offer: CommandOffer,
  intent: CommandIntent,
  commandId: string,
): ShellCommand {
  if (offer.kind !== intent.kind) {
    throw new Error("command_offer_intent_mismatch");
  }
  const base = {
    command_id: commandId,
    expected_task_revision: snapshot.task_revision,
    expected_run_status: snapshot.run_status,
  } as const;

  switch (offer.kind) {
    case "start_task":
      return { ...base, kind: "start_task", task: textFrom(intent) };
    case "answer_question":
      return {
        ...base,
        kind: "answer_question",
        request_id: offer.request_id,
        answer: textFrom(intent),
      };
    case "confirm_action":
      if (intent.kind !== "confirm_action") throw new Error("command_offer_intent_mismatch");
      return {
        ...base,
        kind: intent.approved ? "approve_action" : "reject_action",
        request_id: offer.request_id,
      };
    case "cancel_task":
      return { ...base, kind: "cancel_task" };
    case "pause_task":
      return { ...base, kind: "pause_task" };
    case "resume_task":
      return { ...base, kind: "resume_task", checkpoint_id: requiredCheckpoint(snapshot) };
    case "revise_task":
      return {
        ...base,
        kind: "revise_task",
        expected_checkpoint_id: snapshot.checkpoint_id,
        text: textFrom(intent),
      };
    case "take_over":
      return { ...base, kind: "take_over", checkpoint_id: requiredCheckpoint(snapshot) };
    case "return_control":
      return { ...base, kind: "return_control", control_lease_id: requiredLease(snapshot) };
    case "close_session":
      return { ...base, kind: "close_session" };
    default:
      return assertNever(offer);
  }
}

function textFrom(intent: CommandIntent): string {
  if (intent.kind === "start_task" || intent.kind === "answer_question" || intent.kind === "revise_task") {
    return intent.text;
  }
  throw new Error("command_text_not_available");
}

function requiredCheckpoint(snapshot: Snapshot): string {
  if (!snapshot.checkpoint_id) throw new Error("command_offer_missing_checkpoint");
  return snapshot.checkpoint_id;
}

function requiredLease(snapshot: Snapshot): string {
  if (!snapshot.control_lease_id) throw new Error("command_offer_missing_control_lease");
  return snapshot.control_lease_id;
}

function assertNever(value: never): never {
  throw new Error(`unsupported_command_offer:${String(value)}`);
}
