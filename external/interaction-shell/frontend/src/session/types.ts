import type { InferOutput } from "valibot";
import {
  vCompletedRunSummary,
  vRuntimeSessionSnapshot,
  vShellEventEnvelope,
  vSubmitCommandResponse,
} from "@/generated/valibot.gen";

export type Snapshot = InferOutput<typeof vRuntimeSessionSnapshot>;
export type CommandOffer = Snapshot["command_offers"][number];
export type CommandOfferKind = CommandOffer["kind"];
export type ShellEventEnvelope = InferOutput<typeof vShellEventEnvelope>;
export type CommandAdmission = InferOutput<typeof vSubmitCommandResponse>;
export type CompletedRunSummary = InferOutput<typeof vCompletedRunSummary>;

export type ConnectionState =
  | "connecting"
  | "live"
  | "offline"
  | "protocol_mismatch";
