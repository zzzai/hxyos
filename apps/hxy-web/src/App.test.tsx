import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { MeRequestError } from "./api/client";

const TEST_SESSION = {
  user: {
    account_id: "account-test-employee",
    display_name: "测试店员",
  },
  active_assignment: {
    assignment_id: "assignment-test-employee",
    organization: { id: "organization-test", name: "测试组织" },
    store: { id: "store-test", name: "测试门店" },
    role: "store_employee" as const,
    role_label: "门店员工",
    capabilities: [
      "conversation:use",
      "issues:create",
      "store:read",
      "tasks:read",
      "training:practice",
    ],
  },
  available_assignments: [],
};

function renderApp() {
  return render(<App initialSession={TEST_SESSION} />);
}

function conversationGateway(overrides: Record<string, unknown> = {}) {
  return {
    listConversations: vi.fn().mockResolvedValue({ items: [] }),
    getConversation: vi.fn(),
    createConversation: vi.fn().mockResolvedValue({
      conversation: {
        id: "conversation-new",
        title: "新对话",
        created_at: "2026-07-10T09:00:00Z",
        updated_at: "2026-07-10T09:00:00Z",
        last_message_at: null,
        message_count: 0,
        last_message: null,
      },
    }),
    sendMessage: vi.fn().mockResolvedValue({
      conversation: {
        id: "conversation-new",
        title: "顾客问泡脚能不能治失眠",
        created_at: "2026-07-10T09:00:00Z",
        updated_at: "2026-07-10T09:00:02Z",
        last_message_at: "2026-07-10T09:00:02Z",
        message_count: 2,
        last_message: null,
      },
      user_message: {
        id: "message-user",
        conversation_id: "conversation-new",
        role: "user",
        content: "顾客问泡脚能不能治失眠，我该怎么说？",
        created_at: "2026-07-10T09:00:01Z",
        answer_id: null,
        answer_status: null,
        confidence: null,
        needs_review: null,
        sources: [],
        next_actions: [],
      },
      assistant_message: {
        id: "message-assistant",
        conversation_id: "conversation-new",
        role: "assistant",
        content: "可以说泡脚有助于放松，但不能替代医疗诊断或治疗。",
        created_at: "2026-07-10T09:00:02Z",
        answer_status: "已批准",
        confidence: "high",
        needs_review: false,
        sources: [
          {
            title: "员工标准话术",
            excerpt: "不承诺治疗效果",
            strength: "high",
          },
        ],
        next_actions: [],
        answer_id: "50000000-0000-0000-0000-000000000010",
      },
    }),
    ...overrides,
  };
}

const FORBIDDEN_FRONTSTAGE_TERMS = [
  "claim",
  "chunk_id",
  "review queue",
  "/root/hxy",
];

describe("HXYOS product shell", () => {
  it("shows one accessible composer in the main experience", () => {
    renderApp();

    expect(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
    ).toBeEnabled();
    expect(screen.getAllByTestId("composer")).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "添加附件（即将开放）" }),
    ).toBeDisabled();
  });

  it("limits primary navigation to conversation, tasks, and profile", () => {
    renderApp();

    const primaryNavigation = screen.getByRole("navigation", {
      name: "主要导航",
    });
    const labels = within(primaryNavigation)
      .getAllByRole("button")
      .map((item) => item.textContent?.trim());

    expect(labels).toEqual(["对话", "待办", "我的"]);
  });

  it("keeps internal terminology out of the frontstage", () => {
    const { container } = renderApp();
    const frontstageText = container.textContent?.toLowerCase() ?? "";

    for (const forbidden of FORBIDDEN_FRONTSTAGE_TERMS) {
      expect(frontstageText).not.toContain(forbidden);
    }
  });

  it("shows no more than three context-aware suggestions", () => {
    renderApp();

    const suggestions = within(screen.getByTestId("suggestions")).getAllByRole(
      "button",
    );
    expect(suggestions.length).toBeGreaterThan(0);
    expect(suggestions.length).toBeLessThanOrEqual(3);
  });

  it("derives role, store, and suggestions from the authenticated session", () => {
    renderApp();

    expect(screen.getByText("门店员工")).toBeVisible();
    expect(screen.getByText("测试门店")).toBeVisible();
    expect(screen.getByRole("button", { name: "询问该怎么说" })).toBeVisible();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("gates composer and role actions while identity is loading", () => {
    render(<App sessionLoader={() => new Promise(() => undefined)} />);

    expect(screen.getByRole("status")).toHaveTextContent("正在加载身份");
    expect(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "查看当前对话详情" })).toBeDisabled();
    for (const label of ["对话", "待办", "我的"]) {
      expect(screen.getByRole("button", { name: label })).toBeDisabled();
    }
    expect(screen.queryByTestId("suggestions")).not.toBeInTheDocument();
  });

  it.each([
    ["unauthorized", new MeRequestError(401, "Unauthorized"), "登录已失效"],
    ["error", new Error("network unavailable"), "身份加载失败"],
  ])(
    "gates actions, announces %s, and keeps retry available",
    async (_state, failure, message) => {
      const loader = vi.fn().mockRejectedValue(failure);
      render(<App sessionLoader={loader} />);

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(
        screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      ).toBeDisabled();
      expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "重试身份加载" }),
      ).toBeEnabled();
    },
  );

  it("opens and closes truthful current-conversation details on demand", async () => {
    const user = userEvent.setup();
    const { container } = renderApp();

    expect(
      screen.queryByRole("complementary", { name: "当前对话详情" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "查看来源" }),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "查看当前对话详情" }),
    );
    const details = screen.getByRole("dialog", {
      name: "当前对话详情",
    });
    expect(details).toBeVisible();
    expect(container.querySelector(".left-rail")).toHaveAttribute("inert");
    expect(container.querySelector(".conversation-stage")).toHaveAttribute(
      "inert",
    );
    expect(
      within(details).getByText("发送问题后，这里会显示回答状态和来源"),
    ).toBeVisible();
    expect(
      within(details).queryByRole("heading", { name: "来源" }),
    ).not.toBeInTheDocument();

    const closeButton = screen.getByRole("button", {
      name: "关闭当前对话详情",
    });
    expect(closeButton).toHaveFocus();
    await user.tab();
    expect(closeButton).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("dialog", { name: "当前对话详情" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "查看当前对话详情" }),
    ).toHaveFocus();
    expect(container.querySelector(".left-rail")).not.toHaveAttribute("inert");
    expect(container.querySelector(".conversation-stage")).not.toHaveAttribute(
      "inert",
    );
  });

  it("keeps non-conversation views independent after a message is sent", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "检查今天的开业任务",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(screen.getByText("检查今天的开业任务")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "待办" }));
    expect(
      screen.queryByText("检查今天的开业任务"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "今天的待办" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "我的" }));
    expect(screen.getByRole("heading", { name: "我的" })).toBeVisible();
  });

  it("creates a conversation on first send and renders the real assistant answer", async () => {
    const user = userEvent.setup();
    const gateway = conversationGateway();
    render(
      <App
        initialSession={TEST_SESSION}
        conversationClient={gateway}
        clientMessageIdFactory={() => "50000000-0000-0000-0000-000000000001"}
      />,
    );

    const composer = screen.getByRole("textbox", {
      name: "告诉 HXYOS 你要做什么",
    });
    await user.type(composer, "顾客问泡脚能不能治失眠，我该怎么说？");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(gateway.createConversation).toHaveBeenCalledTimes(1);
    expect(gateway.sendMessage).toHaveBeenCalledWith("conversation-new", {
      content: "顾客问泡脚能不能治失眠，我该怎么说？",
      client_message_id: "50000000-0000-0000-0000-000000000001",
    });
    expect(
      await screen.findByText("可以说泡脚有助于放松，但不能替代医疗诊断或治疗。"),
    ).toBeVisible();
    expect(
      screen.queryByText("50000000-0000-0000-0000-000000000010"),
    ).not.toBeInTheDocument();
  });

  it("restores the most recent conversation for the authenticated assignment", async () => {
    const gateway = conversationGateway({
      listConversations: vi.fn().mockResolvedValue({
        items: [
          {
            id: "conversation-recent",
            title: "今天的门店问题",
            created_at: "2026-07-10T08:00:00Z",
            updated_at: "2026-07-10T08:05:00Z",
            last_message_at: "2026-07-10T08:05:00Z",
            message_count: 2,
            last_message: null,
          },
        ],
      }),
      getConversation: vi.fn().mockResolvedValue({
        conversation: {
          id: "conversation-recent",
          title: "今天的门店问题",
          created_at: "2026-07-10T08:00:00Z",
          updated_at: "2026-07-10T08:05:00Z",
          last_message_at: "2026-07-10T08:05:00Z",
          message_count: 2,
          last_message: null,
        },
        messages: [
          {
            id: "message-restored-user",
            conversation_id: "conversation-recent",
            role: "user",
            content: "新员工接待时总是先推项目，怎么纠正？",
            created_at: "2026-07-10T08:04:00Z",
            answer_id: null,
            answer_status: null,
            confidence: null,
            needs_review: null,
            sources: [],
            next_actions: [],
          },
          {
            id: "message-restored-assistant",
            conversation_id: "conversation-recent",
            role: "assistant",
            content: "先训练员工问顾客当下状态，再给出克制的服务建议。",
            created_at: "2026-07-10T08:05:00Z",
            answer_id: null,
            answer_status: null,
            confidence: null,
            needs_review: null,
            sources: [],
            next_actions: [],
          },
        ],
      }),
    });

    render(
      <App
        initialSession={TEST_SESSION}
        conversationClient={gateway}
      />,
    );

    expect(
      await screen.findByText("新员工接待时总是先推项目，怎么纠正？"),
    ).toBeVisible();
    expect(
      screen.getByText("先训练员工问顾客当下状态，再给出克制的服务建议。"),
    ).toBeVisible();
    expect(gateway.getConversation).toHaveBeenCalledWith("conversation-recent");
  });

  it("does not let a late history response replace a newly started conversation", async () => {
    const user = userEvent.setup();
    let resolveList: (value: Record<string, unknown>) => void = () => undefined;
    const gateway = conversationGateway({
      listConversations: vi.fn(
        () =>
          new Promise<Record<string, unknown>>((resolve) => {
            resolveList = resolve;
          }),
      ),
      getConversation: vi.fn().mockResolvedValue({
        conversation: {
          id: "conversation-old",
          title: "旧对话",
          created_at: "2026-07-10T07:00:00Z",
          updated_at: "2026-07-10T07:05:00Z",
          last_message_at: "2026-07-10T07:05:00Z",
          message_count: 1,
          last_message: null,
        },
        messages: [
          {
            id: "message-old",
            conversation_id: "conversation-old",
            role: "assistant",
            content: "这是一条旧回答",
            created_at: "2026-07-10T07:05:00Z",
            answer_id: null,
            answer_status: null,
            confidence: null,
            needs_review: null,
            sources: [],
            next_actions: [],
          },
        ],
      }),
    });
    render(
      <App
        initialSession={TEST_SESSION}
        conversationClient={gateway}
        clientMessageIdFactory={() => "50000000-0000-0000-0000-000000000002"}
      />,
    );

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "这是刚发出的新问题",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(gateway.sendMessage).toHaveBeenCalledTimes(1),
    );

    act(() =>
      resolveList({
        items: [
          {
            id: "conversation-old",
            title: "旧对话",
            created_at: "2026-07-10T07:00:00Z",
            updated_at: "2026-07-10T07:05:00Z",
            last_message_at: "2026-07-10T07:05:00Z",
            message_count: 1,
            last_message: null,
          },
        ],
      }),
    );

    expect(
      await screen.findByText("可以说泡脚有助于放松，但不能替代医疗诊断或治疗。"),
    ).toBeVisible();
    await act(async () => Promise.resolve());
    expect(screen.queryByText("这是一条旧回答")).not.toBeInTheDocument();
  });
});
