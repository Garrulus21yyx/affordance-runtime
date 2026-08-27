import { createClient } from "@/generated/client";

const BASE_URL = "/shell-api";

export const shellClient = createClient({ baseUrl: BASE_URL });

export function authenticatedShellClient(sessionKey: string) {
  return createClient({ baseUrl: BASE_URL, auth: sessionKey });
}
