"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createSession, postCommand, subscribeEvents } from "@/lib/api";
import type { Snapshot } from "@/lib/types";

export function useShellSession() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [sessionKey, setSessionKey] = useState("");
  const [connection, setConnection] = useState<"connecting" | "live" | "offline">("connecting");
  const [notice, setNotice] = useState("");
  const cursor = useRef(0);
  const eventEpoch = useRef("");
  const sessionOpening = useRef<ReturnType<typeof createSession> | null>(null);
  const sessionId = snapshot?.session_id;

  useEffect(() => {
    let active = true;
    sessionOpening.current ??= createSession();
    sessionOpening.current
      .then((created) => {
        if (!active) return;
        setSessionKey(created.session_key);
        setSnapshot(created.snapshot);
        eventEpoch.current = created.snapshot.event_epoch;
        cursor.current = created.snapshot.event_cursor;
      })
      .catch(() => setConnection("offline"));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!sessionId || !sessionKey) return;
    const controller = new AbortController();
    subscribeEvents(
      sessionId,
      sessionKey,
      eventEpoch.current,
      cursor.current,
      (event) => {
        if (event.event_epoch !== eventEpoch.current) {
          throw new Error("shell_event_epoch_changed");
        }
        cursor.current = event.cursor;
        const projected = event.data?.snapshot as Snapshot | undefined;
        if (projected) setSnapshot(projected);
        setConnection("live");
      },
      () => setConnection("live"),
      controller.signal,
    ).catch(() => {
      if (!controller.signal.aborted) setConnection("offline");
    });
    return () => controller.abort();
  }, [sessionId, sessionKey]);

  const send = useCallback(
    async (path: string, body: Record<string, unknown>) => {
      if (!snapshot || !sessionKey) return null;
      const admission = await postCommand(snapshot.session_id, sessionKey, path, body);
      setSnapshot(admission.snapshot);
      setNotice(
        admission.kind === "accepted"
          ? "Command admitted; task outcome still comes from Runtime."
          : admission.kind === "unsupported"
            ? `Unavailable: ${admission.reason}`
            : `${admission.kind}: ${"code" in admission ? admission.code : "rejected"}`,
      );
      return admission;
    },
    [sessionKey, snapshot],
  );

  const commandBase = useCallback(
    (kind: string) => ({
      kind,
      command_id: crypto.randomUUID(),
      expected_task_revision: snapshot?.task_revision ?? 0,
      expected_run_status: snapshot?.run_status ?? "idle",
    }),
    [snapshot],
  );

  const submitMessage = useCallback(
    async (message: string) => {
      if (!snapshot) return;
      if (snapshot.run_status === "idle") {
        await send("tasks", { ...commandBase("start_task"), task: message });
      } else if (snapshot.run_status === "waiting_user" && snapshot.pending_question) {
        await send("commands/answer", {
          ...commandBase("answer_question"),
          request_id: snapshot.pending_question.request_id,
          answer: message,
        });
      } else {
        await send("commands/optional", { ...commandBase("revise_task"), message });
      }
    },
    [commandBase, send, snapshot],
  );

  const confirm = useCallback(
    async (approved: boolean) => {
      if (!snapshot?.pending_confirmation) return;
      await send(approved ? "commands/approve" : "commands/reject", {
        ...commandBase(approved ? "approve_action" : "reject_action"),
        request_id: snapshot.pending_confirmation.request_id,
      });
    },
    [commandBase, send, snapshot],
  );

  return { snapshot, connection, notice, submitMessage, confirm };
}
