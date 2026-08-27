import { NextResponse } from "next/server";

/** CopilotKit view metadata only: deliberately advertises no chat agent. */
export function GET() {
  return NextResponse.json({
    version: "interaction-shell-ui-v1",
    agents: {},
    audioFileTranscriptionEnabled: false,
  });
}
