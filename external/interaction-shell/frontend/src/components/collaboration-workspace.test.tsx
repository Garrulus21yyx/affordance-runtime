import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parse } from "valibot";
import type { InteractionOption } from "@/generated/types.gen";
import { vRuntimeSessionSnapshot } from "@/generated/valibot.gen";
import { projectShellView } from "@/session/view-model";
import {
  ArtifactPanel,
  ConversationFeed,
  EvidenceBadge,
  InteractionRequestPanel,
  OptionCard,
  RevisionDiff,
} from "./collaboration-workspace";

afterEach(cleanup);

const option = (title: string, attributes: InteractionOption["attributes"]): InteractionOption => ({
  option_id: `option-${title}`,
  title,
  description: `关于${title}的说明`,
  media_ref: "",
  attributes,
  evidence_refs: ["evidence-1", "evidence-2"],
  uncertainties: ["一项属性无法确认"],
});

describe("generic collaboration components", () => {
  it("uses one OptionCard schema for products, files, flights, and chart elements", () => {
    const fixtures = [
      option("红色背包", [{ label: "价格", value: "¥399" }, { label: "尺码", value: "M" }]),
      option("季度报告.pdf", [{ label: "路径", value: "/reports" }, { label: "修改时间", value: "今天" }]),
      option("CA123", [{ label: "出发", value: "08:20" }, { label: "经停", value: "0" }]),
      option("收入折线", [{ label: "图层", value: "Series 2" }, { label: "颜色", value: "蓝色" }]),
    ];
    const rendered = render(<>{fixtures.map((item) => <OptionCard key={item.option_id} option={item} selected={false} interactive={false} selectionMode="single" onSelect={() => undefined} />)}</>);
    expect(rendered.container.querySelectorAll("[data-testid='option-card']")).toHaveLength(4);
    for (const item of fixtures) expect(screen.getByText(item.title)).toBeInTheDocument();
    for (const evidence of rendered.container.querySelectorAll(".option-evidence")) {
      expect(evidence).toHaveTextContent("结构/视觉证据 · 2");
    }
    expect(screen.getAllByText("1 项无法确认")).toHaveLength(4);
  });

  it("shows useful evidence state without low-level implementation details", () => {
    render(<EvidenceBadge kind="visual" status="observed" confidence={0.91} count={2} />);
    expect(screen.getByTestId("evidence-badge")).toHaveTextContent("视觉证据 · 已确认");
    expect(screen.getByTestId("evidence-badge")).toHaveTextContent("91%");
    expect(screen.queryByText(/selector|coordinate|prompt|provider/i)).not.toBeInTheDocument();
  });

  it("submits the selected generic option as a typed interaction response", () => {
    const respond = vi.fn(async () => null);
    render(<InteractionRequestPanel request={{
      request_id: "request-select",
      prompt: "请选择一个候选",
      response_kind: "single_select",
      public_intent: "我需要你决定采用哪个实体。",
      fields: [],
      options: [option("候选 A", [{ label: "类型", value: "文件" }])],
    }} active respond={respond} />);
    fireEvent.click(screen.getByRole("button", { name: "选择" }));
    expect(respond).toHaveBeenCalledWith({
      kind: "single_select",
      request_id: "request-select",
      option_id: "option-候选 A",
    });
  });

  it("renders deterministic revision differences and generic artifacts", () => {
    render(<>
      <RevisionDiff block={{
        block_id: "revision-3",
        kind: "revision_applied",
        occurred_at: "2026-08-28T10:00:00Z",
        task_revision: 3,
        removed: ["仅处理当前页面"],
        added: ["同时检查下一页"],
        retained: ["不要提交表单"],
        goal_description_changed: true,
      }} />
      <ArtifactPanel artifact={{
        artifact_id: "artifact-1",
        title: "比较报告",
        summary: "已整理三个候选。",
        items: [{ item_id: "item-1", title: "候选 A", summary: "可供复核", attributes: [{ label: "评分", value: "4.8" }], evidence_refs: ["e-1"] }],
        links: [{ title: "下载报告", artifact_ref: "/artifacts/report" }],
        evidence_refs: ["e-1"],
      }} />
    </>);
    expect(screen.getByTestId("revision-diff")).toHaveTextContent("目标已更新 · revision 3");
    expect(screen.getByTestId("revision-diff")).toHaveTextContent("同时检查下一页");
    expect(screen.getByTestId("artifact-panel")).toHaveTextContent("比较报告");
    expect(screen.getByRole("link", { name: /下载报告/ })).toHaveAttribute("href", "/artifacts/report");
  });

  it("renders the closed feed without adding developer data to ordinary blocks", () => {
    const snapshot = parse(vRuntimeSessionSnapshot, {
      schema_version: "interaction-shell.v4",
      session_id: "session-feed",
      event_epoch: "event-epoch-feed",
      event_cursor: 10,
      expires_at: "2026-08-28T12:00:00Z",
      task_id: "task-1",
      task_text: "比较可见候选",
      task_revision: 2,
      run_status: "waiting_user",
      control_owner: "agent",
      resume_eligible: false,
      public_steps: [],
      completion: null,
      checkpoint_id: null,
      last_control_outcome: null,
      effect_reconciliation: null,
      control_lease_id: null,
      command_offers: [{ kind: "respond_interaction", request: {
        request_id: "request-feed",
        prompt: "请选择候选",
        response_kind: "free_text",
        public_intent: "我需要你的补充。",
        fields: [],
        options: [],
      } }, { kind: "revise_task" }, { kind: "close_session" }],
      surface: { status: "unavailable", reason_code: "surface_not_configured" },
      feed: [
        { block_id: "b1", kind: "user_turn", occurred_at: "2026-08-28T10:00:00Z", content: "比较候选" },
        { block_id: "b2", kind: "goal_accepted", occurred_at: "2026-08-28T10:00:01Z", summary: "比较候选", constraints: ["不要提交"], task_revision: 1 },
        { block_id: "b3", kind: "agent_intent", occurred_at: "2026-08-28T10:00:02Z", content: "我先检查当前页面中可见的候选。" },
        { block_id: "b4", kind: "runtime_activity", occurred_at: "2026-08-28T10:00:03Z", label: "已读取当前界面", status: "completed", evidence_refs: [] },
        { block_id: "b5", kind: "evidence_summary", occurred_at: "2026-08-28T10:00:04Z", evidence_kind: "mixed", status: "partial", confidence: 0.82, message: "两个候选已确认。", evidence_refs: ["e-1"] },
        { block_id: "b6", kind: "interaction_request", occurred_at: "2026-08-28T10:00:05Z", request: { request_id: "request-feed", prompt: "请选择候选", response_kind: "free_text", public_intent: "我需要你的补充。", fields: [], options: [] } },
        { block_id: "b7", kind: "revision_applied", occurred_at: "2026-08-28T10:00:06Z", task_revision: 2, removed: [], added: ["检查下一页"], retained: ["不要提交"], goal_description_changed: true },
        { block_id: "b8", kind: "confirmation_required", occurred_at: "2026-08-28T10:00:07Z", request_id: "confirmation-old", summary: "提交表单", risk: "会产生外部效果" },
        { block_id: "b9", kind: "completion", occurred_at: "2026-08-28T10:00:08Z", completion: { outcome: "success", code: "done", message: "比较完成", evidence_refs: [], artifact: null } },
        { block_id: "b10", kind: "failure", occurred_at: "2026-08-28T10:00:09Z", code: "later_failure", message: "后续运行失败" },
      ],
    });
    render(<ConversationFeed view={projectShellView(snapshot)} respond={async () => null} confirm={async () => null} />);
    expect(screen.getByTestId("conversation-feed")).toHaveTextContent("我先检查当前页面中可见的候选");
    expect(screen.getByTestId("conversation-feed")).toHaveTextContent("结构 + 视觉证据");
    expect(screen.getByTestId("conversation-feed")).toHaveTextContent("比较完成");
    expect(screen.queryByText(/token|raw trace|provider|json/i)).not.toBeInTheDocument();
  });
});
