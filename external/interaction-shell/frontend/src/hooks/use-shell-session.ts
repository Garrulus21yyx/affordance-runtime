"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createSession, postCommand, recoverSession, subscribeEvents } from "@/lib/api";
import type { Snapshot } from "@/lib/types";

export function useShellSession() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [sessionKey, setSessionKey] = useState("");
  const [connection, setConnection] = useState<"connecting" | "live" | "offline">("connecting");
  const [notice, setNotice] = useState("");
  const [streamGeneration, setStreamGeneration] = useState(0);
  const cursor = useRef(0);
  const eventEpoch = useRef("");
  const latestSnapshot = useRef<Snapshot | null>(null);
  const attemptedRecovery = useRef("");
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
        latestSnapshot.current = created.snapshot;
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
        if (projected) {
          latestSnapshot.current = projected;
          setSnapshot(projected);
        }
        setConnection("live");
      },
      () => setConnection("live"),
      controller.signal,
    ).catch(async () => {
      if (controller.signal.aborted) return;
      const current = latestSnapshot.current;
      const recoveryIdentity = `${eventEpoch.current}:${current?.checkpoint_id ?? ""}`;
      if (
        current?.run_status === "paused"
        && current.resume_eligible
        && current.checkpoint_id
        && attemptedRecovery.current !== recoveryIdentity
      ) {
        attemptedRecovery.current = recoveryIdentity;
        try {
          const recovered = await recoverSession(
            current.session_id,
            sessionKey,
            current.checkpoint_id,
          );
          if (controller.signal.aborted) return;
          latestSnapshot.current = recovered.snapshot;
          eventEpoch.current = recovered.snapshot.event_epoch;
          cursor.current = recovered.snapshot.event_cursor;
          setSnapshot(recovered.snapshot);
          setConnection("live");
          setStreamGeneration((generation) => generation + 1);
          return;
        } catch {
          // One bounded recovery attempt per epoch/checkpoint; remain fail-closed.
        }
      }
      setConnection("offline");
    });
    return () => controller.abort();
  }, [sessionId, sessionKey, streamGeneration]);

  const send = useCallback(
    async (path: string, body: Record<string, unknown>) => {
      if (!snapshot || !sessionKey) return null;
      const admission = await postCommand(snapshot.session_id, sessionKey, path, body);
      latestSnapshot.current = admission.snapshot;
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

  const cancel = useCallback(async () => {
    if (!snapshot?.capabilities.includes("cancel_task")) return;
    await send("commands/optional", commandBase("cancel_task"));
  }, [commandBase, send, snapshot]);

  const pause = useCallback(async () => {
    if (!snapshot?.capabilities.includes("pause_task")) return;
    await send("commands/optional", commandBase("pause_task"));
  }, [commandBase, send, snapshot]);

  const resume = useCallback(async () => {
    if (
      !snapshot?.capabilities.includes("resume_task")
      || !snapshot.checkpoint_id
      || !snapshot.resume_eligible
    ) return;
    await send("commands/resume", {
      ...commandBase("resume_task"),
      checkpoint_id: snapshot.checkpoint_id,
    });
  }, [commandBase, send, snapshot]);

  return { snapshot, connection, notice, submitMessage, confirm, cancel, pause, resume };
}
