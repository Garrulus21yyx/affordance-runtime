import type { CommandOfferKind, Snapshot } from "./types";

export type ShellViewModel = ReturnType<typeof projectShellView>;

export function projectShellView(snapshot: Snapshot | null) {
  const offers = snapshot?.command_offers ?? [];
  const offered = (kind: CommandOfferKind) => offers.some((offer) => offer.kind === kind);
  const question = offers.find((offer) => offer.kind === "answer_question");
  const confirmation = offers.find((offer) => offer.kind === "confirm_action");
  const surface = snapshot?.surface ?? {
    status: "unavailable" as const,
    reason_code: "surface_not_configured",
  };
  const composerMode = offered("answer_question")
    ? "answer"
    : offered("start_task")
      ? "start"
      : "unavailable";

  return {
    snapshot,
    runStatus: snapshot?.run_status ?? "idle",
    taskText: snapshot?.task_text ?? "Waiting for a task",
    steps: snapshot?.public_steps ?? [],
    completion: snapshot?.completion ?? null,
    effectReconciliation: snapshot?.effect_reconciliation ?? null,
    lastControlOutcome: snapshot?.last_control_outcome ?? null,
    question: question?.kind === "answer_question" ? question : null,
    confirmation: confirmation?.kind === "confirm_action" ? confirmation : null,
    composer: {
      mode: composerMode,
      placeholder: composerMode === "answer"
        ? "Answer the question…"
        : composerMode === "start"
          ? "Describe a task…"
          : "Use Revise task to change the active goal…",
      enabled: composerMode !== "unavailable",
    },
    actions: {
      cancel: offered("cancel_task"),
      pause: offered("pause_task"),
      resume: offered("resume_task"),
      revise: offered("revise_task"),
      takeOver: offered("take_over"),
      returnControl: offered("return_control"),
      close: offered("close_session"),
    },
    surface: surface.status === "unavailable"
      ? {
          status: "unavailable" as const,
          reasonCode: surface.reason_code,
        }
      : {
          status: surface.status,
          protectedPath: surface.protected_path,
          surfaceKind: surface.surface_kind,
          presentation: surface.presentation,
          interactive: surface.status === "interactive",
          frameKey: `${surface.protected_path}:${surface.status}:${snapshot?.control_lease_id ?? "no-lease"}`,
        },
  };
}
