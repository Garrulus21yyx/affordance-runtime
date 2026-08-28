import type { CommandOfferKind, Snapshot } from "./types";

export type ShellViewModel = ReturnType<typeof projectShellView>;

type RunStatus = Snapshot["run_status"];
type ControlOwner = Snapshot["control_owner"];

function assertNever(value: never): never {
  throw new Error(`Unhandled public contract variant: ${String(value)}`);
}

export function statusPresentation(status: RunStatus, controlOwner: ControlOwner) {
  if (status === "paused" && controlOwner === "user") {
    return { label: "你正在控制界面", tone: "user_control" as const };
  }
  switch (status) {
    case "idle":
      return { label: "等待消息", tone: "idle" as const };
    case "running":
      return { label: "正在处理", tone: "running" as const };
    case "paused":
      return { label: "任务已暂停", tone: "paused" as const };
    case "waiting_user":
      return { label: "等待你的回答", tone: "waiting_user" as const };
    case "waiting_confirmation":
      return { label: "等待操作确认", tone: "waiting_confirmation" as const };
    case "done":
      return { label: "回答完成", tone: "done" as const };
    case "cancelled":
      return { label: "任务已取消", tone: "cancelled" as const };
    case "failed":
      return { label: "处理失败", tone: "failed" as const };
    case "blocked":
      return { label: "需要处理后才能继续", tone: "blocked" as const };
    default:
      return assertNever(status);
  }
}

export function projectShellView(snapshot: Snapshot | null) {
  const offers = snapshot?.command_offers ?? [];
  const offered = (kind: CommandOfferKind) => offers.some((offer) => offer.kind === kind);
  const question = offers.find((offer) => offer.kind === "answer_question");
  const interaction = offers.find((offer) => offer.kind === "respond_interaction");
  const confirmation = offers.find((offer) => offer.kind === "confirm_action");
  const surface = snapshot?.surface ?? {
    status: "unavailable" as const,
    reason_code: "surface_not_configured",
  };
  const composerMode = interaction?.kind === "respond_interaction"
    ? interaction.request.response_kind === "free_text" ? "answer" : "interaction"
    : offered("answer_question")
      ? "answer"
    : offered("start_task")
      ? "start"
      : offered("revise_task")
        ? "revise"
        : "unavailable";
  const status = statusPresentation(
    snapshot?.run_status ?? "idle",
    snapshot?.control_owner ?? "agent",
  );
  const goal = snapshot?.feed.toReversed().find((block) => block.kind === "goal_accepted") ?? null;

  return {
    snapshot,
    runStatus: snapshot?.run_status ?? "idle",
    taskRevision: snapshot?.task_revision ?? 0,
    taskText: snapshot?.task_text ?? "等待消息",
    steps: snapshot?.public_steps ?? [],
    completion: snapshot?.completion ?? null,
    effectReconciliation: snapshot?.effect_reconciliation ?? null,
    lastControlOutcome: snapshot?.last_control_outcome ?? null,
    question: question?.kind === "answer_question" ? question : null,
    interaction: interaction?.kind === "respond_interaction" ? interaction.request : null,
    confirmation: confirmation?.kind === "confirm_action" ? confirmation : null,
    feed: snapshot?.feed ?? [],
    goal,
    status,
    composer: {
      mode: composerMode,
      placeholder: composerMode === "answer"
        ? "Answer the question…"
        : composerMode === "start"
          ? "问任何问题，或描述需要完成的任务…"
          : composerMode === "revise"
            ? "Revise the active goal…"
            : composerMode === "interaction"
              ? "Respond with the decision card above…"
              : "No text command is available right now…",
      enabled: composerMode === "answer" || composerMode === "start" || composerMode === "revise",
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
