import type { ReactNode } from "react";

export function CopilotChatView() {
  return <div data-testid="copilot-chat" />;
}

export function CopilotKitProvider({ children }: { children: ReactNode }) {
  return children;
}
