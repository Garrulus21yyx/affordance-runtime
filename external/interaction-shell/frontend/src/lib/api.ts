import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { Admission, CreatedSession, Diagnosis, ShellEvent, Snapshot } from "./types";

const API = "/shell-api";

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`shell_api_${response.status}`);
  return response.json() as Promise<T>;
}

export async function createSession(): Promise<CreatedSession> {
  return checked(
    await fetch(`${API}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ttl_seconds: 1800 }),
    }),
  );
}

export async function getSnapshot(sessionId: string, key: string): Promise<Snapshot> {
  return checked(await fetch(`${API}/sessions/${sessionId}`, { headers: { "X-Session-Key": key } }));
}

export async function postCommand(
  sessionId: string,
  key: string,
  path: string,
  body: Record<string, unknown>,
): Promise<Admission> {
  return checked(
    await fetch(`${API}/sessions/${sessionId}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Session-Key": key },
      body: JSON.stringify(body),
    }),
  );
}

export function subscribeEvents(
  sessionId: string,
  key: string,
  cursor: number,
  onEvent: (event: ShellEvent) => void,
  onOpen: () => void,
  signal: AbortSignal,
) {
  return fetchEventSource(`${API}/sessions/${sessionId}/events?cursor=${cursor}`, {
    headers: { "X-Session-Key": key },
    signal,
    openWhenHidden: true,
    onopen: async (response) => {
      if (!response.ok) throw new Error(`shell_sse_${response.status}`);
      onOpen();
    },
    onmessage(message) {
      if (message.data) {
        const agui = JSON.parse(message.data) as { type: "CUSTOM"; name: string; value: ShellEvent };
        onEvent(agui.value);
      }
    },
  });
}

export async function listDiagnoses(): Promise<Diagnosis[]> {
  return checked(await fetch(`${API}/diagnostics`));
}
