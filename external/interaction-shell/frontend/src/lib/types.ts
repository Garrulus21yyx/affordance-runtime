import type { components } from "@/generated/api";

export type Snapshot = components["schemas"]["RuntimeSessionSnapshot"];
export type ShellEvent = components["schemas"]["ShellEvent"];
export type Admission =
  | components["schemas"]["Accepted"]
  | components["schemas"]["Conflict"]
  | components["schemas"]["Unsupported"]
  | components["schemas"]["Rejected"];
export type Diagnosis = components["schemas"]["CaseDiagnosis"];
export type CreatedSession = components["schemas"]["CreateSessionResponse"];
