import { describe, expect, it } from "vitest";
import { parse } from "valibot";
import { vRuntimeSessionSnapshot, vShellEventEnvelope } from "@/generated/valibot.gen";
import { classifyEvent } from "./use-shell-session";

const snapshot = parse(vRuntimeSessionSnapshot, {
  schema_version: "interaction-shell.v4",
  session_id: "session-1",
  event_epoch: "event-epoch-00000001",
  event_cursor: 4,
  expires_at: "2026-08-27T12:00:00Z",
  task_id: null,
  task_text: null,
  completion: null,
  checkpoint_id: null,
  last_control_outcome: null,
  effect_reconciliation: null,
  control_lease_id: null,
  surface: { status: "unavailable", reason_code: "surface_not_configured" },
});

function event(cursor: number, epoch = snapshot.event_epoch) {
  return parse(vShellEventEnvelope, {
    type: "CUSTOM",
    name: "snapshot.updated",
    value: {
      schema_version: "interaction-shell.v4",
      type: "snapshot.updated",
      session_id: snapshot.session_id,
      event_epoch: epoch,
      cursor,
      emitted_at: "2026-08-27T12:00:00Z",
      snapshot: { ...snapshot, event_epoch: epoch, event_cursor: cursor },
    },
  });
}

describe("causal event admission", () => {
  it("applies only the next event", () => expect(classifyEvent(snapshot, event(5))).toBe("apply"));
  it("ignores duplicate and old events", () => expect(classifyEvent(snapshot, event(4))).toBe("duplicate"));
  it("requires resync for gaps", () => expect(classifyEvent(snapshot, event(7))).toBe("resync"));
  it("requires resync for epoch changes", () => expect(classifyEvent(snapshot, event(5, "event-epoch-00000002"))).toBe("resync"));
  it.each([
    { snapshot: { session_id: "other-session" } },
    { snapshot: { event_epoch: "nested-event-epoch" } },
    { snapshot: { event_cursor: 4 } },
  ])("fails closed when nested snapshot causality disagrees with its envelope", (change) => {
    const candidate = event(5);
    const malformed = {
      ...candidate,
      value: {
        ...candidate.value,
        snapshot: { ...candidate.value.snapshot, ...change.snapshot },
      },
    };
    expect(classifyEvent(snapshot, malformed)).toBe("protocol_mismatch");
  });
  it("fails closed on an unknown event kind", () => expect(() => parse(vShellEventEnvelope, { type: "CUSTOM", name: "unknown", value: {} })).toThrow());
  it("fails closed on an unknown nested event field", () => expect(() => parse(vShellEventEnvelope, { ...event(5), value: { ...event(5).value, unknown: true } })).toThrow());
});
