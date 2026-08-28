"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { parse, ValiError } from "valibot";
import {
  createSession as createSessionRequest,
  getSession,
  recoverSession,
  submitCommand,
  subscribeSessionEvents,
} from "@/generated/sdk.gen";
import {
  vCreateSessionResponse,
  vGetSessionResponse,
  vRecoverSessionResponse,
  vShellEventEnvelope,
  vSubmitCommandResponse,
} from "@/generated/valibot.gen";
import { buildCommand, offerFor, type CommandIntent } from "@/session/command-builder";
import { authenticatedShellClient, shellClient } from "@/session/client";
import type { CommandAdmission, ConnectionState, ShellEventEnvelope, Snapshot } from "@/session/types";
import type { InteractionResponse } from "@/generated/types.gen";
import { projectShellView } from "@/session/view-model";

export type CausalEventDecision = "apply" | "duplicate" | "resync" | "protocol_mismatch";

export function classifyEvent(snapshot: Snapshot, event: ShellEventEnvelope): CausalEventDecision {
  const update = event.value;
  if (
    update.snapshot.session_id !== update.session_id
    || update.snapshot.event_epoch !== update.event_epoch
    || update.snapshot.event_cursor < update.cursor
  ) {
    return "protocol_mismatch";
  }
  if (update.session_id !== snapshot.session_id || update.event_epoch !== snapshot.event_epoch) {
    return "resync";
  }
  if (update.cursor <= snapshot.event_cursor) return "duplicate";
  if (update.cursor !== snapshot.event_cursor + 1) return "resync";
  return "apply";
}

export function useShellSession() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [sessionKey, setSessionKey] = useState("");
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [notice, setNotice] = useState("");
  const [streamGeneration, setStreamGeneration] = useState(0);
  const latestSnapshot = useRef<Snapshot | null>(null);
  const attemptedRecovery = useRef("");
  const attemptedResync = useRef("");
  const opening = useRef<ReturnType<typeof openSession> | null>(null);

  const install = useCallback((next: Snapshot) => {
    latestSnapshot.current = next;
    setSnapshot(next);
  }, []);

  useEffect(() => {
    let active = true;
    opening.current ??= openSession();
    opening.current.then((created) => {
      if (!active) return;
      setSessionKey(created.session_key);
      install(created.snapshot);
    }).catch((error: unknown) => {
      if (!active) return;
      setConnection(error instanceof ValiError ? "protocol_mismatch" : "offline");
    });
    return () => { active = false; };
  }, [install]);

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 2600);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  const sessionId = snapshot?.session_id;
  useEffect(() => {
    if (!sessionId || !sessionKey || connection === "protocol_mismatch") return;
    const abort = new AbortController();
    const client = authenticatedShellClient(sessionKey);

    const resyncOnce = async () => {
      const current = latestSnapshot.current;
      if (!current) return false;
      const identity = `${current.event_epoch}:${current.event_cursor}`;
      if (attemptedResync.current === identity) return false;
      attemptedResync.current = identity;
      const response = await getSession({
        client,
        path: { session_id: current.session_id },
        throwOnError: true,
      });
      const lookup = parse(vGetSessionResponse, response.data);
      if (lookup.kind === "live_session") {
        install(lookup.snapshot);
        setStreamGeneration((generation) => generation + 1);
        return true;
      }
      if (lookup.kind !== "recovery_required") return false;
      const recoveryIdentity = `${current.session_id}:${lookup.checkpoint_id}`;
      if (attemptedRecovery.current === recoveryIdentity) return false;
      attemptedRecovery.current = recoveryIdentity;
      const recoveredResponse = await recoverSession({
        client,
        path: { session_id: current.session_id },
        body: { checkpoint_id: lookup.checkpoint_id },
        throwOnError: true,
      });
      const recovered = parse(vRecoverSessionResponse, recoveredResponse.data);
      if (recovered.kind !== "recovered") return false;
      install(recovered.snapshot);
      setStreamGeneration((generation) => generation + 1);
      return true;
    };

    const subscribe = async () => {
      const current = latestSnapshot.current;
      if (!current) return;
      const result = await subscribeSessionEvents({
        client,
        path: { session_id: current.session_id },
        query: { event_epoch: current.event_epoch, cursor: current.event_cursor },
        signal: abort.signal,
        sseMaxRetryAttempts: 1,
      });
      for await (const rawEvent of result.stream) {
        const event = parse(vShellEventEnvelope, rawEvent);
        const active = latestSnapshot.current;
        if (!active) continue;
        const decision = classifyEvent(active, event);
        if (decision === "protocol_mismatch") {
          setConnection("protocol_mismatch");
          abort.abort();
          return;
        }
        if (decision === "duplicate") {
          setConnection("live");
          continue;
        }
        if (decision === "resync") {
          if (!await resyncOnce()) setConnection("offline");
          return;
        }
        install(event.value.snapshot);
        attemptedResync.current = "";
        setConnection("live");
      }
      if (!abort.signal.aborted) {
        if (!await resyncOnce()) setConnection("offline");
      }
    };

    subscribe().catch((error: unknown) => {
      if (abort.signal.aborted) return;
      if (error instanceof ValiError) {
        setConnection("protocol_mismatch");
        abort.abort();
      } else {
        setConnection("offline");
      }
    });
    return () => abort.abort();
  }, [connection, install, sessionId, sessionKey, streamGeneration]);

  const sendIntent = useCallback(async (intent: CommandIntent): Promise<CommandAdmission | null> => {
    const current = latestSnapshot.current;
    if (!current || !sessionKey) return null;
    const offer = offerFor(current, intent.kind);
    if (!offer) return null;
    const command = buildCommand(current, offer, intent, crypto.randomUUID());
    const response = await submitCommand({
      client: authenticatedShellClient(sessionKey),
      path: { session_id: current.session_id },
      body: command,
      throwOnError: true,
    });
    const admission = parse(vSubmitCommandResponse, response.data);
    install(admission.snapshot);
    setNotice(admissionNotice(admission));
    return admission;
  }, [install, sessionKey]);

  const submitMessage = useCallback(async (text: string) => {
    const current = latestSnapshot.current;
    if (!current) return;
    const interaction = offerFor(current, "respond_interaction");
    if (interaction?.kind === "respond_interaction") {
      const request = interaction.request;
      if (request.response_kind === "free_text") {
        await sendIntent({
          kind: "respond_interaction",
          response: { kind: "free_text", request_id: request.request_id, text },
        });
      } else if (
        request.response_kind === "structured_fields"
        && request.fields.length === 1
        && request.fields[0].kind === "text"
      ) {
        await sendIntent({
          kind: "respond_interaction",
          response: {
            kind: "structured_fields",
            request_id: request.request_id,
            values: [{ kind: "text", field_id: request.fields[0].field_id, text }],
          },
        });
      }
    } else if (offerFor(current, "answer_question")) {
      await sendIntent({ kind: "answer_question", text });
    } else if (offerFor(current, "start_task")) {
      await sendIntent({ kind: "start_task", text });
    }
  }, [sendIntent]);

  const revise = useCallback(async (text: string) => {
    await sendIntent({ kind: "revise_task", text });
  }, [sendIntent]);

  const viewModel = useMemo(() => projectShellView(snapshot), [snapshot]);
  const newSession = useCallback(async () => {
    const current = latestSnapshot.current;
    if (current && offerFor(current, "close_session")) {
      await sendIntent({ kind: "close_session" });
    }
    opening.current = openSession();
    const created = await opening.current;
    setSessionKey(created.session_key);
    install(created.snapshot);
    attemptedRecovery.current = "";
    attemptedResync.current = "";
    setConnection("connecting");
    setStreamGeneration((generation) => generation + 1);
    setNotice("");
  }, [install, sendIntent]);
  return {
    snapshot,
    viewModel,
    connection,
    notice,
    submitMessage,
    revise,
    respondInteraction: (response: InteractionResponse) => sendIntent({
      kind: "respond_interaction",
      response,
    }),
    confirm: (approved: boolean) => sendIntent({ kind: "confirm_action", approved }),
    cancel: () => sendIntent({ kind: "cancel_task" }),
    pause: () => sendIntent({ kind: "pause_task" }),
    resume: () => sendIntent({ kind: "resume_task" }),
    takeOver: () => sendIntent({ kind: "take_over" }),
    returnControl: () => sendIntent({ kind: "return_control" }),
    close: () => sendIntent({ kind: "close_session" }),
    newSession,
  };
}

async function openSession() {
  const response = await createSessionRequest({
    client: shellClient,
    body: {},
    throwOnError: true,
  });
  return parse(vCreateSessionResponse, response.data);
}

function admissionNotice(admission: CommandAdmission): string {
  switch (admission.kind) {
    case "accepted":
      return "Command admitted; task outcome still comes from Runtime.";
    case "conflict":
      return `Conflict: ${admission.code}`;
    case "unsupported":
      return `Unavailable: ${admission.code}`;
    case "rejected":
      return `Rejected: ${admission.code}`;
  }
}
