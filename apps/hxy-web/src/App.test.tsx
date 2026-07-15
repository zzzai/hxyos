import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { MeRequestError, type OnboardingClient } from "./api/client";
import shellCss from "./styles/shell.css?raw";

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
      "materials:create",
      "materials:read",
      "store:read",
      "tasks:read",
      "training:practice",
    ],
  },
  available_assignments: [],
};

const MANAGER_SESSION = {
  ...TEST_SESSION,
  user: {
    account_id: "account-test-manager",
    display_name: "测试店长",
  },
  active_assignment: {
    ...TEST_SESSION.active_assignment,
    assignment_id: "assignment-test-manager",
    role: "store_manager" as const,
    role_label: "店长",
    capabilities: [
      "conversation:use",
      "issues:create",
      "materials:create",
      "materials:read",
      "store:operate",
      "store:read",
      "tasks:manage",
      "tasks:read",
    ],
  },
};

const HQ_SESSION = {
  ...TEST_SESSION,
  user: {
    account_id: "account-test-hq",
    display_name: "测试总部运营",
  },
  active_assignment: {
    ...TEST_SESSION.active_assignment,
    assignment_id: "assignment-test-hq",
    store: null,
    role: "hq_operations" as const,
    role_label: "总部运营",
    capabilities: [
      "conversation:use",
      "materials:create",
      "materials:read",
      "operations:manage",
      "organization:read",
      "stores:read",
      "tasks:manage",
      "tasks:read",
    ],
  },
};

const FOUNDER_SESSION = {
  ...TEST_SESSION,
  user: {
    account_id: "account-test-founder",
    display_name: "测试创始人",
  },
  active_assignment: {
    ...TEST_SESSION.active_assignment,
    assignment_id: "assignment-test-founder",
    store: null,
    role: "founder" as const,
    role_label: "创始人",
    capabilities: [
      "conversation:use",
      "organization:read",
      "stores:read",
      "tasks:manage",
      "tasks:read",
    ],
  },
};

function renderApp() {
  return render(<App initialSession={TEST_SESSION} />);
}

function onboardingGateway(
  overrides: Partial<OnboardingClient> = {},
): OnboardingClient {
  return {
    listStores: vi.fn().mockResolvedValue([]),
    createStore: vi.fn(),
    listMembers: vi.fn().mockResolvedValue([]),
    listInvites: vi.fn().mockResolvedValue([]),
    createInvite: vi.fn(),
    revokeInvite: vi.fn(),
    deactivateMember: vi.fn(),
    redeemInvite: vi.fn(),
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
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
            url: null,
          },
        ],
        next_actions: [],
        answer_id: "50000000-0000-0000-0000-000000000010",
      },
    }),
    ...overrides,
  };
}

function materialGateway(overrides: Record<string, unknown> = {}) {
  return {
    listMaterials: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    getMaterial: vi.fn().mockResolvedValue({
      material: UNDERSTOOD_MATERIAL,
    }),
    retryUnderstanding: vi.fn().mockResolvedValue({
      material: PROCESSING_MATERIAL,
    }),
    uploadMaterial: vi.fn().mockResolvedValue({
      material: PROCESSING_MATERIAL,
    }),
    ...overrides,
  };
}

function taskGateway(overrides: Record<string, unknown> = {}) {
  return {
    listTasks: vi.fn().mockResolvedValue({
      items: [
        {
          id: "task-one",
          title: "完成今日开店检查",
          details: "检查环境、物料和接待准备。",
          priority: "high",
          status: "open",
          visibility: "store",
          store_id: "store-test",
          assignee_assignment_id: null,
          source_conversation_id: null,
          source_message_id: null,
          result: null,
          due_at: null,
          completed_at: null,
          created_at: "2026-07-12T09:00:00Z",
          updated_at: "2026-07-12T09:00:00Z",
        },
      ],
      count: 1,
    }),
    createTask: vi.fn(),
    updateTask: vi.fn().mockResolvedValue({
      task: {
        id: "task-one",
        title: "完成今日开店检查",
        details: "检查环境、物料和接待准备。",
        priority: "high",
        status: "completed",
        visibility: "store",
        store_id: "store-test",
        assignee_assignment_id: null,
        source_conversation_id: null,
        source_message_id: null,
        result: "已完成检查。",
        due_at: null,
        completed_at: "2026-07-12T10:00:00Z",
        created_at: "2026-07-12T09:00:00Z",
        updated_at: "2026-07-12T10:00:00Z",
      },
    }),
    ...overrides,
  };
}

function journeyGateway(overrides: Record<string, unknown> = {}) {
  return {
    loadSuggestions: vi.fn().mockResolvedValue({
      items: [
        { type: "ask", label: "询问该怎么说", prompt: "顾客这样问时我该怎么说？" },
        { type: "training", label: "练习一次接待话术", prompt: null },
        { type: "issue", label: "上报一个门店问题", prompt: null },
      ],
    }),
    evaluateTraining: vi.fn().mockResolvedValue({
      result_type: "training_result",
      primary_result: {
        score: 68,
        level: "retrain",
        needs_retrain: true,
        standard_script: "可以说泡脚有助于放松，但不能替代医疗诊断或治疗。",
        correction_points: ["不要承诺治疗效果", "先回应顾客感受"],
      },
      actions: [{ type: "training", label: "再练一次合规表达" }],
      sources: [],
      limitations: ["训练结果用于岗位练习，不替代店长现场验收。"],
      artifact: { type: "training_session", id: "training-one" },
    }),
    reportIssue: vi.fn().mockResolvedValue({
      result_type: "issue_report",
      primary_result: {
        task: {
          id: "task-from-issue",
          title: "顾客听不懂项目区别",
          details: "连续两位顾客提出相同问题。",
          priority: "normal",
          status: "open",
          visibility: "store",
          store_id: "store-test",
          assignee_assignment_id: null,
          source_conversation_id: null,
          source_message_id: null,
          result: null,
          due_at: null,
          completed_at: null,
          created_at: "2026-07-12T12:00:00Z",
          updated_at: "2026-07-12T12:00:00Z",
        },
      },
      actions: [{ type: "tasks", label: "查看门店待办" }],
      sources: [],
      limitations: ["问题已进入当前门店待办，处理结论需由负责人填写。"],
      artifact: { type: "task", id: "task-from-issue" },
    }),
    ...overrides,
  };
}

const UNDERSTOOD_MATERIAL = {
  id: "70000000-0000-0000-0000-000000000001",
  file_name: "首店接待流程.md",
  media_type: "text/markdown",
  size_bytes: 36,
  status: "ready",
  receipt: {
    status: "已收到",
    message: "资料已安全保存，当前不会自动变成正式知识。",
  },
  original: {
    url: "/api/v1/materials/70000000-0000-0000-0000-000000000001/content",
    can_preview: true,
  },
  understanding: {
    summary: "首店员工接待流程草稿，重点是先问顾客状态，再介绍服务。",
    document_type: "门店流程资料",
    source_origin: "internal",
    authority_level: "working_material",
    knowledge_scale: "micro",
    domain: "operations",
    parse_status: "extracted",
    confidence: "medium",
    warnings: [],
    official_use_allowed: false,
    use_boundary: "可用于整理候选流程，不能直接作为正式 SOP。",
  },
  created_at: "2026-07-10T10:00:00Z",
  updated_at: "2026-07-10T10:00:00Z",
} as const;

const PROCESSING_MATERIAL = {
  ...UNDERSTOOD_MATERIAL,
  status: "processing",
  understanding: {
    ...UNDERSTOOD_MATERIAL.understanding,
    summary: "资料已收到，系统正在继续理解。",
    parse_status: "needs_deep_parse",
    confidence: "low",
  },
} as const;

const CLIENT_UPLOAD_ID = "80000000-0000-0000-0000-000000000001";

const FORBIDDEN_FRONTSTAGE_TERMS = [
  "claim",
  "chunk_id",
  "review queue",
  "/root/hxy",
];

describe("HXYOS product shell", () => {
  it("marks the final header scope as the shrinkable context value", () => {
    renderApp();

    const context = screen.getByLabelText("当前身份和门店");
    expect(within(context).getByText("门店员工")).toHaveClass("context-role");
    expect(within(context).getByText("测试门店")).toHaveClass("context-scope");
  });

  it("keeps mobile organization controls at 44px and clips header context", () => {
    expect(shellCss).toMatch(
      /\.stage-header\s*{[^}]*min-width:\s*0;[^}]*overflow:\s*hidden;/s,
    );
    expect(shellCss).toMatch(
      /\.context-line\s*{[^}]*flex:\s*1 1 0;[^}]*min-width:\s*0;/s,
    );
    expect(shellCss).toMatch(
      /\.context-scope\s*{[^}]*min-width:\s*0;[^}]*text-overflow:\s*ellipsis;/s,
    );
    expect(shellCss).toMatch(
      /\.context-role,\s*\.context-separator\s*{[^}]*flex:\s*0 0 auto;/s,
    );
    expect(shellCss).toMatch(
      /\.organization-identity-meta span\s*{[^}]*overflow-wrap:\s*anywhere;/s,
    );
    const mobileCss = shellCss.slice(
      shellCss.indexOf("@media (max-width: 720px)"),
    );
    expect(mobileCss).toMatch(
      /\.organization-panel button,[^}]*min-height:\s*44px;/s,
    );
    expect(mobileCss).toMatch(
      /\.organization-form input,[^}]*min-height:\s*44px;/s,
    );
    expect(mobileCss).toMatch(
      /\.organization-icon-button\s*{[^}]*width:\s*44px;[^}]*height:\s*44px;/s,
    );
    expect(mobileCss).toMatch(
      /\.invite-link-result\s*{[^}]*44px 44px;/s,
    );
  });

  it("mounts employee profile without organization reads and completes logout", async () => {
    const user = userEvent.setup();
    const onboardingClient = onboardingGateway();
    const logout = vi.fn().mockResolvedValue(undefined);
    const onLoggedOut = vi.fn();

    render(
      <App
        initialSession={TEST_SESSION}
        onboardingClient={onboardingClient}
        logout={logout}
        onLoggedOut={onLoggedOut}
      />,
    );

    expect(onboardingClient.listStores).not.toHaveBeenCalled();
    expect(onboardingClient.listMembers).not.toHaveBeenCalled();
    expect(onboardingClient.listInvites).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "我的" }));

    const identity = screen.getByRole("region", { name: "测试店员" });
    expect(within(identity).getByRole("heading", { name: "测试店员" })).toBeVisible();
    expect(within(identity).getByText("门店员工")).toBeVisible();
    expect(within(identity).getByText("测试门店")).toBeVisible();
    expect(onboardingClient.listStores).not.toHaveBeenCalled();
    expect(onboardingClient.listMembers).not.toHaveBeenCalled();
    expect(onboardingClient.listInvites).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "查看当前对话详情" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "退出登录" }));

    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
    expect(onLoggedOut).toHaveBeenCalledOnce();
  });

  it("loads founder organization data only after the profile panel mounts", async () => {
    const user = userEvent.setup();
    const onboardingClient = onboardingGateway();
    render(
      <App
        initialSession={FOUNDER_SESSION}
        onboardingClient={onboardingClient}
      />,
    );

    expect(onboardingClient.listStores).not.toHaveBeenCalled();
    expect(onboardingClient.listMembers).not.toHaveBeenCalled();
    expect(onboardingClient.listInvites).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "我的" }));

    expect(await screen.findByRole("heading", { name: "门店与成员" })).toBeVisible();
    expect(onboardingClient.listStores).toHaveBeenCalledOnce();
    expect(onboardingClient.listMembers).toHaveBeenCalledOnce();
    expect(onboardingClient.listInvites).toHaveBeenCalledOnce();
  });

  it("retains a private invite result across profile navigation until dismissal", async () => {
    const user = userEvent.setup();
    const inviteResult = deferred<
      Awaited<ReturnType<OnboardingClient["createInvite"]>>
    >();
    const oneTimeLink = "https://hxy.example/#invite=retained-private-link";
    const onboardingClient = onboardingGateway({
      listStores: vi.fn().mockResolvedValue([
        {
          id: "store-retained",
          name: "荷小悦首店",
          city: "长沙",
          address: "芙蓉路 1 号",
          status: "active",
        },
      ]),
      createInvite: vi.fn(() => inviteResult.promise),
    });
    const { container } = render(
      <App
        initialSession={FOUNDER_SESSION}
        onboardingClient={onboardingClient}
      />,
    );

    expect(onboardingClient.listStores).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "我的" }));
    await screen.findByText("荷小悦首店");
    await user.click(screen.getByRole("button", { name: "邀请店长" }));
    await user.type(screen.getByRole("textbox", { name: "成员姓名" }), "王店长");
    await user.click(screen.getByRole("button", { name: "生成邀请" }));

    await user.click(screen.getByRole("button", { name: "对话" }));
    expect(screen.getByRole("heading", { name: "今天想先处理什么？" })).toBeVisible();
    expect(container.querySelector(".organization-panel")).toHaveAttribute("hidden");
    await act(async () =>
      inviteResult.resolve({
        invite: {
          id: "invite-retained",
          role: "store_manager",
          display_name: "王店长",
          expires_at: "2026-07-15T10:00:00Z",
        },
        one_time_link: oneTimeLink,
      }),
    );
    expect(document.body).not.toHaveTextContent(oneTimeLink);
    expect(screen.queryByRole("region", { name: "测试创始人" })).not.toBeInTheDocument();
    expect(onboardingClient.listStores).toHaveBeenCalledOnce();
    expect(onboardingClient.listMembers).toHaveBeenCalledOnce();
    expect(onboardingClient.listInvites).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "我的" }));
    expect(await screen.findByText(oneTimeLink)).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "关闭一次性邀请链接" }),
    );
    await user.click(screen.getByRole("button", { name: "对话" }));
    await user.click(screen.getByRole("button", { name: "我的" }));
    expect(screen.queryByText(oneTimeLink)).not.toBeInTheDocument();
  });

  it("shows one accessible composer in the main experience", () => {
    renderApp();

    expect(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
    ).toBeEnabled();
    expect(screen.getAllByTestId("composer")).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "添加资料" }),
    ).toBeEnabled();
  });

  it("uses the centered empty-conversation state only before work starts", async () => {
    const user = userEvent.setup();
    const gateway = conversationGateway();
    const { container } = render(
      <App initialSession={TEST_SESSION} conversationClient={gateway} />,
    );

    expect(container.querySelector(".conversation-stage")).toHaveClass(
      "is-conversation-empty",
    );

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "检查今天的开业任务",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() =>
      expect(container.querySelector(".conversation-stage")).not.toHaveClass(
        "is-conversation-empty",
      ),
    );
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

  it("shows role-scoped tasks and completes work with a result", async () => {
    const user = userEvent.setup();
    const gateway = taskGateway();
    render(<App initialSession={TEST_SESSION} taskClient={gateway} />);

    await user.click(screen.getByRole("button", { name: "待办" }));

    expect(
      await screen.findByRole("heading", { name: "完成今日开店检查" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "完成任务" }));
    await user.type(
      screen.getByRole("textbox", { name: "执行结果" }),
      "已完成检查。",
    );
    await user.click(screen.getByRole("button", { name: "确认完成" }));

    await waitFor(() =>
      expect(gateway.updateTask).toHaveBeenCalledWith("task-one", {
        status: "completed",
        result: "已完成检查。",
      }),
    );
  });

  it("turns an answer action into a task without copying text", async () => {
    const user = userEvent.setup();
    const conversations = conversationGateway({
      listConversations: vi.fn().mockResolvedValue({
        items: [
          {
            id: "conversation-new",
            title: "开业检查",
            created_at: "2026-07-12T09:00:00Z",
            updated_at: "2026-07-12T09:00:00Z",
            last_message_at: "2026-07-12T09:00:00Z",
            message_count: 2,
            last_message: null,
          },
        ],
      }),
      getConversation: vi.fn().mockResolvedValue({
        conversation: {
          id: "conversation-new",
          title: "开业检查",
          created_at: "2026-07-12T09:00:00Z",
          updated_at: "2026-07-12T09:00:00Z",
          last_message_at: "2026-07-12T09:00:00Z",
          message_count: 2,
          last_message: null,
        },
        messages: [
          {
            id: "answer-message",
            conversation_id: "conversation-new",
            role: "assistant",
            content: "先完成开店前环境和物料检查。",
            created_at: "2026-07-12T09:00:00Z",
            answer_id: null,
            answer_status: "AI 草稿",
            confidence: "medium",
            needs_review: true,
            sources: [],
            next_actions: ["完成开店前检查"],
          },
        ],
      }),
    });
    const tasks = taskGateway({
      listTasks: vi.fn().mockResolvedValue({ items: [], count: 0 }),
      createTask: vi.fn().mockResolvedValue({
        task: {
          id: "task-from-answer",
          title: "完成开店前检查",
          details: "先完成开店前环境和物料检查。",
          priority: "normal",
          status: "open",
          visibility: "assignee",
          store_id: "store-test",
          assignee_assignment_id: "assignment-test-manager",
          source_conversation_id: "conversation-new",
          source_message_id: "answer-message",
          result: null,
          due_at: null,
          completed_at: null,
          created_at: "2026-07-12T09:00:00Z",
          updated_at: "2026-07-12T09:00:00Z",
        },
      }),
    });
    render(
      <App
        initialSession={MANAGER_SESSION}
        conversationClient={conversations}
        taskClient={tasks}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "转为待办" }));

    expect(tasks.createTask).toHaveBeenCalledWith({
      title: "完成开店前检查",
      details: "先完成开店前环境和物料检查。",
      priority: "normal",
      visibility: "assignee",
      assignee_assignment_id: "assignment-test-manager",
      source_conversation_id: "conversation-new",
      source_message_id: "answer-message",
    });
    expect(
      await screen.findByRole("heading", { name: "完成开店前检查" }),
    ).toBeVisible();
  });

  it("creates a useful founder task from the task action without next actions", async () => {
    const user = userEvent.setup();
    const baseResponse = await conversationGateway().sendMessage();
    const conversations = conversationGateway({
      sendMessage: vi.fn().mockResolvedValue({
        ...baseResponse,
        assistant_message: {
          ...baseResponse.assistant_message,
          content: "首店已进入现场验收阶段。",
          next_actions: [],
          actions: [{ type: "tasks", label: "转为下一项任务" }],
        },
      }),
    });
    const tasks = taskGateway({
      listTasks: vi.fn().mockResolvedValue({ items: [], count: 0 }),
      createTask: vi.fn().mockResolvedValue({
        task: {
          id: "task-founder-follow-up",
          title: "跟进本次回答",
          details: "首店已进入现场验收阶段。",
          priority: "normal",
          status: "open",
          visibility: "assignee",
          store_id: null,
          assignee_assignment_id: "assignment-test-manager",
          source_conversation_id: "conversation-new",
          source_message_id: "message-assistant",
          result: null,
          due_at: null,
          completed_at: null,
          created_at: "2026-07-12T09:00:00Z",
          updated_at: "2026-07-12T09:00:00Z",
        },
      }),
    });
    render(
      <App
        initialSession={MANAGER_SESSION}
        conversationClient={conversations}
        taskClient={tasks}
      />,
    );

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "开业进度怎么样？",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await user.click(
      await screen.findByRole("button", { name: "转为下一项任务" }),
    );

    expect(tasks.createTask).toHaveBeenCalledWith(
      expect.objectContaining({ title: "跟进本次回答" }),
    );
  });

  it("does not let an older task request overwrite a newer refresh", async () => {
    const user = userEvent.setup();
    let resolveOlder: ((value: unknown) => void) | undefined;
    const older = new Promise((resolve) => {
      resolveOlder = resolve;
    });
    const gateway = taskGateway({
      listTasks: vi
        .fn()
        .mockReturnValueOnce(older)
        .mockResolvedValueOnce({
          items: [
            {
              id: "task-newer",
              title: "最新待办",
              details: "",
              priority: "normal",
              status: "open",
              visibility: "store",
              store_id: "store-test",
              assignee_assignment_id: null,
              source_conversation_id: null,
              source_message_id: null,
              result: null,
              due_at: null,
              completed_at: null,
              created_at: "2026-07-12T10:00:00Z",
              updated_at: "2026-07-12T10:00:00Z",
            },
          ],
          count: 1,
        }),
    });
    render(<App initialSession={TEST_SESSION} taskClient={gateway} />);

    await user.click(screen.getByRole("button", { name: "待办" }));
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(
      await screen.findByRole("heading", { name: "最新待办" }),
    ).toBeVisible();

    await act(async () => {
      resolveOlder?.({
        items: [
          {
            id: "task-older",
            title: "过期待办",
            details: "",
            priority: "normal",
            status: "open",
            visibility: "store",
            store_id: "store-test",
            assignee_assignment_id: null,
            source_conversation_id: null,
            source_message_id: null,
            result: null,
            due_at: null,
            completed_at: null,
            created_at: "2026-07-12T09:00:00Z",
            updated_at: "2026-07-12T09:00:00Z",
          },
        ],
        count: 1,
      });
    });

    expect(screen.getByRole("heading", { name: "最新待办" })).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "过期待办" }),
    ).not.toBeInTheDocument();
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

  it("respects an intentionally empty server suggestion set", async () => {
    const journeys = journeyGateway({
      loadSuggestions: vi.fn().mockResolvedValue({ items: [] }),
    });
    render(<App initialSession={TEST_SESSION} journeyClient={journeys} />);

    await waitFor(() => {
      expect(journeys.loadSuggestions).toHaveBeenCalled();
      expect(screen.queryByTestId("suggestions")).not.toBeInTheDocument();
    });
  });

  it("does not show a fallback action outside the assignment capabilities", async () => {
    const journeys = journeyGateway({
      loadSuggestions: vi.fn().mockRejectedValue(new Error("unavailable")),
    });
    render(<App initialSession={HQ_SESSION} journeyClient={journeys} />);

    expect(await screen.findByRole("button", { name: "查看门店待办" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "上报一个运营问题" }),
    ).not.toBeInTheDocument();
  });

  it("opens training directly from a server-provided role action", async () => {
    const user = userEvent.setup();
    const journeys = journeyGateway();
    render(<App initialSession={TEST_SESSION} journeyClient={journeys} />);

    await user.click(
      await screen.findByRole("button", { name: "练习一次接待话术" }),
    );

    expect(
      screen.getByRole("heading", { name: "接待话术练习" }),
    ).toBeVisible();
    expect(screen.getByRole("textbox", { name: "顾客的问题" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "我的回答" })).toBeVisible();
  });

  it("scores a practice answer and shows concrete correction", async () => {
    const user = userEvent.setup();
    const journeys = journeyGateway();
    render(<App initialSession={TEST_SESSION} journeyClient={journeys} />);

    await user.click(
      await screen.findByRole("button", { name: "练习一次接待话术" }),
    );
    await user.clear(screen.getByRole("textbox", { name: "顾客的问题" }));
    await user.type(
      screen.getByRole("textbox", { name: "顾客的问题" }),
      "这个能治疗失眠吗？",
    );
    await user.type(
      screen.getByRole("textbox", { name: "我的回答" }),
      "肯定可以治好。",
    );
    await user.click(screen.getByRole("button", { name: "提交练习" }));

    expect(await screen.findByText("68 分")).toBeVisible();
    expect(screen.getByText("不要承诺治疗效果")).toBeVisible();
    expect(
      screen.getByText("可以说泡脚有助于放松，但不能替代医疗诊断或治疗。"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "再练一次合规表达" })).toBeVisible();
    expect(
      screen.getByText("训练结果用于岗位练习，不替代店长现场验收。"),
    ).toBeVisible();
    expect(journeys.evaluateTraining).toHaveBeenCalledWith({
      customer_question: "这个能治疗失眠吗？",
      employee_answer: "肯定可以治好。",
    });
  });

  it("starts answer practice with the actual customer question", async () => {
    const user = userEvent.setup();
    const baseResponse = await conversationGateway().sendMessage();
    const conversations = conversationGateway({
      sendMessage: vi.fn().mockResolvedValue({
        ...baseResponse,
        assistant_message: {
          ...baseResponse.assistant_message,
          actions: [{ type: "training", label: "练习这个说法" }],
        },
      }),
    });
    render(
      <App initialSession={TEST_SESSION} conversationClient={conversations} />,
    );

    const question = "顾客皮肤敏感，应该怎么介绍泡脚服务？";
    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      question,
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await user.click(
      await screen.findByRole("button", { name: "练习这个说法" }),
    );

    expect(screen.getByRole("textbox", { name: "顾客的问题" })).toHaveValue(
      question,
    );
  });

  it("reports a store issue and moves it into visible tasks", async () => {
    const user = userEvent.setup();
    const journeys = journeyGateway();
    const tasks = taskGateway({
      listTasks: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    });
    render(
      <App
        initialSession={TEST_SESSION}
        journeyClient={journeys}
        taskClient={tasks}
      />,
    );

    await user.click(
      await screen.findByRole("button", { name: "上报一个门店问题" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "问题标题" }),
      "顾客听不懂项目区别",
    );
    await user.type(
      screen.getByRole("textbox", { name: "问题详情" }),
      "连续两位顾客提出相同问题。",
    );
    await user.click(screen.getByRole("button", { name: "提交问题" }));

    expect(
      await screen.findByRole("heading", { name: "顾客听不懂项目区别" }),
    ).toBeVisible();
    expect(journeys.reportIssue).toHaveBeenCalledWith({
      title: "顾客听不懂项目区别",
      details: "连续两位顾客提出相同问题。",
    });
  });

  it("links a manager issue to the task it came from", async () => {
    const user = userEvent.setup();
    const journeys = journeyGateway();
    render(
      <App
        initialSession={MANAGER_SESSION}
        journeyClient={journeys}
        taskClient={taskGateway()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "待办" }));
    await user.click(
      await screen.findByRole("button", { name: "反馈完成今日开店检查的问题" }),
    );
    expect(screen.getByText("关联待办：完成今日开店检查")).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "问题标题" }), "物料不足");
    await user.type(screen.getByRole("textbox", { name: "问题详情" }), "缺少顾客须知");
    await user.click(screen.getByRole("button", { name: "提交问题" }));

    expect(journeys.reportIssue).toHaveBeenCalledWith({
      title: "物料不足",
      details: "缺少顾客须知",
      source_task_id: "task-one",
    });
  });

  it("ignores a late issue response after the user leaves that journey", async () => {
    const user = userEvent.setup();
    let resolveIssue: ((value: unknown) => void) | undefined;
    const pendingIssue = new Promise((resolve) => {
      resolveIssue = resolve;
    });
    const journeys = journeyGateway({
      reportIssue: vi.fn().mockReturnValue(pendingIssue),
    });
    render(<App initialSession={TEST_SESSION} journeyClient={journeys} />);

    await user.click(
      await screen.findByRole("button", { name: "上报一个门店问题" }),
    );
    await user.type(screen.getByRole("textbox", { name: "问题标题" }), "旧问题");
    await user.type(screen.getByRole("textbox", { name: "问题详情" }), "旧详情");
    await user.click(screen.getByRole("button", { name: "提交问题" }));
    await user.click(screen.getByRole("button", { name: "返回对话" }));
    await user.click(screen.getByRole("button", { name: "练习一次接待话术" }));

    await act(async () => {
      resolveIssue?.(await journeyGateway().reportIssue());
    });

    expect(screen.getByRole("heading", { name: "接待话术练习" })).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "顾客听不懂项目区别" }),
    ).not.toBeInTheDocument();
  });

  it("ignores a late issue response after starting a new conversation", async () => {
    const user = userEvent.setup();
    let resolveIssue: ((value: unknown) => void) | undefined;
    const pendingIssue = new Promise((resolve) => {
      resolveIssue = resolve;
    });
    const baseResponse = await conversationGateway().sendMessage();
    const conversations = conversationGateway({
      sendMessage: vi.fn().mockResolvedValue({
        ...baseResponse,
        assistant_message: {
          ...baseResponse.assistant_message,
          actions: [{ type: "issue", label: "上报现场问题" }],
        },
      }),
    });
    const journeys = journeyGateway({
      reportIssue: vi.fn().mockReturnValue(pendingIssue),
    });
    render(
      <App
        initialSession={TEST_SESSION}
        conversationClient={conversations}
        journeyClient={journeys}
      />,
    );

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "今天遇到一个问题",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await user.click(await screen.findByRole("button", { name: "上报现场问题" }));
    await user.type(screen.getByRole("textbox", { name: "问题标题" }), "旧问题");
    await user.type(screen.getByRole("textbox", { name: "问题详情" }), "旧详情");
    await user.click(screen.getByRole("button", { name: "提交问题" }));
    await user.click(screen.getByRole("button", { name: "新建对话" }));

    await act(async () => {
      resolveIssue?.(await journeyGateway().reportIssue());
    });

    expect(screen.getByRole("heading", { name: "今天想先处理什么？" })).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "顾客听不懂项目区别" }),
    ).not.toBeInTheDocument();
  });

  it("hides persisted journey actions outside current capabilities", async () => {
    const conversations = conversationGateway({
      listConversations: vi.fn().mockResolvedValue({
        items: [
          {
            id: "conversation-old-role",
            title: "旧岗位对话",
            created_at: "2026-07-12T09:00:00Z",
            updated_at: "2026-07-12T09:00:00Z",
            last_message_at: "2026-07-12T09:00:00Z",
            message_count: 1,
            last_message: null,
          },
        ],
      }),
      getConversation: vi.fn().mockResolvedValue({
        conversation: {
          id: "conversation-old-role",
          title: "旧岗位对话",
          created_at: "2026-07-12T09:00:00Z",
          updated_at: "2026-07-12T09:00:00Z",
          last_message_at: "2026-07-12T09:00:00Z",
          message_count: 1,
          last_message: null,
        },
        messages: [
          {
            id: "message-old-role",
            conversation_id: "conversation-old-role",
            role: "assistant",
            content: "旧岗位回答",
            created_at: "2026-07-12T09:00:00Z",
            answer_id: null,
            answer_status: "AI 草稿",
            confidence: "medium",
            needs_review: true,
            sources: [],
            next_actions: [],
            actions: [
              { type: "training", label: "练习这个说法" },
              { type: "issue", label: "上报现场问题" },
            ],
          },
        ],
      }),
    });
    render(
      <App initialSession={HQ_SESSION} conversationClient={conversations} />,
    );

    expect(await screen.findByText("旧岗位回答")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "练习这个说法" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "上报现场问题" }),
    ).not.toBeInTheDocument();
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
    expect(screen.getByRole("heading", { name: "测试店员" })).toBeVisible();
  });

  it("opens an authorized material citation from the existing details drawer", async () => {
    const user = userEvent.setup();
    const baseResponse = await conversationGateway().sendMessage();
    const client = conversationGateway({
      sendMessage: vi.fn().mockResolvedValue({
        ...baseResponse,
        assistant_message: {
          ...baseResponse.assistant_message,
          answer_status: "AI 草稿",
          needs_review: true,
          sources: [
            {
              title: "首店接待资料.md",
              excerpt: "先询问顾客当下状态。",
              strength: "reference",
              url: "/api/v1/materials/70000000-0000-0000-0000-000000000021/content",
            },
          ],
        },
      }),
    });
    render(<App initialSession={TEST_SESSION} conversationClient={client} />);

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "刚上传的接待资料讲了什么？",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await user.click(
      await screen.findByRole("button", { name: "查看当前对话详情" }),
    );

    expect(
      screen.getByRole("link", { name: "查看首店接待资料.md" }),
    ).toHaveAttribute(
      "href",
      "/api/v1/materials/70000000-0000-0000-0000-000000000021/content",
    );
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

  it("uploads a selected file and shows one useful receipt with original access", async () => {
    const user = userEvent.setup();
    const materials = materialGateway();
    const { container } = render(
      <App
        initialSession={TEST_SESSION}
        conversationClient={conversationGateway()}
        materialClient={materials}
        materialUploadIdFactory={() => CLIENT_UPLOAD_ID}
      />,
    );
    const file = new File(["先问顾客状态，再介绍服务。"], "首店接待流程.md", {
      type: "text/markdown",
    });
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );

    expect(input).not.toBeNull();
    await user.upload(input!, file);

    expect(materials.uploadMaterial).toHaveBeenCalledWith(
      file,
      "",
      CLIENT_UPLOAD_ID,
    );
    expect(await screen.findByText("首店接待流程.md")).toBeVisible();
    expect(
      within(screen.getByTestId("composer-region")).getByText(
        "首店接待流程.md",
      ),
    ).toBeVisible();
    expect(screen.queryByLabelText("当前对话")).not.toBeInTheDocument();
    expect(screen.getByText("正在理解")).toBeVisible();
    expect(
      screen.getByText("资料已收到，系统正在继续理解。"),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "查看原文" })).toHaveAttribute(
      "href",
      "/api/v1/materials/70000000-0000-0000-0000-000000000001/content",
    );
    expect(screen.queryByText("working_material")).not.toBeInTheDocument();
  });

  it("does not offer material upload without the assignment capability", () => {
    const session = {
      ...TEST_SESSION,
      active_assignment: {
        ...TEST_SESSION.active_assignment,
        capabilities: TEST_SESSION.active_assignment.capabilities.filter(
          (capability) => capability !== "materials:create",
        ),
      },
    };

    render(<App initialSession={session} materialClient={materialGateway()} />);

    expect(screen.getByRole("button", { name: "添加资料" })).toBeDisabled();
  });

  it("opens the existing file picker from an assistant material action", async () => {
    const user = userEvent.setup();
    const defaultResponse = await conversationGateway().sendMessage(
      "conversation-new",
      { content: "我要上传资料", client_message_id: "message-client" },
    );
    const conversations = conversationGateway({
      sendMessage: vi.fn().mockResolvedValue({
        ...defaultResponse,
        assistant_message: {
          ...defaultResponse.assistant_message,
          content: "可以，选择资料后我会继续理解。",
          result_type: "material_ingestion",
          actions: [{ type: "material_upload", label: "选择资料" }],
        },
      }),
    });
    const { container } = render(
      <App initialSession={TEST_SESSION} conversationClient={conversations} />,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const picker = vi.spyOn(input!, "click").mockImplementation(() => undefined);

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "我要上传资料",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await user.click(await screen.findByRole("button", { name: "选择资料" }));

    expect(picker).toHaveBeenCalledTimes(1);
  });

  it("opens existing tasks instead of creating one from a capability action", async () => {
    const user = userEvent.setup();
    const defaultResponse = await conversationGateway().sendMessage(
      "conversation-new",
      { content: "你会什么", client_message_id: "message-client" },
    );
    const conversations = conversationGateway({
      sendMessage: vi.fn().mockResolvedValue({
        ...defaultResponse,
        assistant_message: {
          ...defaultResponse.assistant_message,
          content: "我可以帮你处理门店问题和跟进任务。",
          result_type: "system_capability",
          actions: [{ type: "tasks", label: "查看门店待办" }],
        },
      }),
    });
    const tasks = taskGateway({
      listTasks: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    });
    render(
      <App
        initialSession={MANAGER_SESSION}
        conversationClient={conversations}
        taskClient={tasks}
      />,
    );

    await user.type(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
      "你会什么",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await user.click(
      await screen.findByRole("button", { name: "查看门店待办" }),
    );

    expect(screen.getByRole("heading", { name: "今天的待办" })).toBeVisible();
    expect(tasks.createTask).not.toHaveBeenCalled();
  });

  it("restores the latest material receipt for the authenticated assignment", async () => {
    const materials = materialGateway({
      listMaterials: vi.fn().mockResolvedValue({
        items: [UNDERSTOOD_MATERIAL],
        count: 1,
      }),
    });

    render(<App initialSession={TEST_SESSION} materialClient={materials} />);

    expect(await screen.findByText("首店接待流程.md")).toBeVisible();
    expect(materials.listMaterials).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "查看原文" })).toBeVisible();
  });

  it("keeps the original visible when system understanding is incomplete", async () => {
    const materials = materialGateway({
      listMaterials: vi.fn().mockResolvedValue({
        items: [
          {
            ...UNDERSTOOD_MATERIAL,
            status: "needs_attention",
            understanding: {
              ...UNDERSTOOD_MATERIAL.understanding,
              summary: "资料已保存，但本次系统理解没有完成。",
              parse_status: "metadata_only",
              confidence: "low",
            },
          },
        ],
        count: 1,
      }),
    });

    render(<App initialSession={TEST_SESSION} materialClient={materials} />);

    expect(await screen.findByText("需要关注")).toBeVisible();
    expect(
      screen.getByText("资料已保存，但本次系统理解没有完成。"),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "查看原文" })).toBeVisible();
    expect(screen.queryByText("已理解")).not.toBeInTheDocument();
  });

  it("retries understanding against the saved original", async () => {
    const user = userEvent.setup();
    const failedMaterial = {
      ...UNDERSTOOD_MATERIAL,
      status: "needs_attention" as const,
      understanding: {
        ...UNDERSTOOD_MATERIAL.understanding,
        summary: "资料已保存，但本次系统理解没有完成。",
        parse_status: "metadata_only" as const,
        confidence: "low" as const,
      },
    };
    const materials = materialGateway({
      listMaterials: vi.fn().mockResolvedValue({
        items: [failedMaterial],
        count: 1,
      }),
      retryUnderstanding: vi.fn().mockResolvedValue({
        material: PROCESSING_MATERIAL,
      }),
    });

    render(<App initialSession={TEST_SESSION} materialClient={materials} />);

    await user.click(
      await screen.findByRole("button", { name: "重新理解资料" }),
    );

    expect(materials.retryUnderstanding).toHaveBeenCalledWith(
      UNDERSTOOD_MATERIAL.id,
    );
    expect(
      await screen.findByText("正在理解"),
    ).toBeVisible();
  });

  it("refreshes a processing material without asking the employee to act", async () => {
    vi.useFakeTimers();
    try {
      const materials = materialGateway({
        listMaterials: vi.fn().mockResolvedValue({
          items: [PROCESSING_MATERIAL],
          count: 1,
        }),
        getMaterial: vi.fn().mockResolvedValue({
          material: UNDERSTOOD_MATERIAL,
        }),
      });

      render(<App initialSession={TEST_SESSION} materialClient={materials} />);
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText("正在理解")).toBeVisible();

      await act(async () => {
        vi.advanceTimersByTime(3000);
        await Promise.resolve();
      });

      expect(materials.getMaterial).toHaveBeenCalledWith(
        UNDERSTOOD_MATERIAL.id,
      );
      expect(screen.getByText("可以使用")).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it("announces material upload progress and prevents duplicate selection", async () => {
    const user = userEvent.setup();
    let resolveUpload: (value: { material: typeof UNDERSTOOD_MATERIAL }) => void =
      () => undefined;
    const materials = materialGateway({
      uploadMaterial: vi.fn(
        () =>
          new Promise<{ material: typeof UNDERSTOOD_MATERIAL }>((resolve) => {
            resolveUpload = resolve;
          }),
      ),
    });
    const { container } = render(
      <App initialSession={TEST_SESSION} materialClient={materials} />,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    const file = new File(["门店资料"], "门店资料.md", {
      type: "text/markdown",
    });

    await user.upload(input!, file);

    expect(screen.getByRole("status")).toHaveTextContent("正在接收门店资料.md");
    expect(screen.getByRole("button", { name: "添加资料" })).toBeDisabled();

    await act(async () => resolveUpload({ material: UNDERSTOOD_MATERIAL }));
    expect(await screen.findByText("首店接待流程.md")).toBeVisible();
  });

  it("keeps a failed material available for one-click retry", async () => {
    const user = userEvent.setup();
    const materials = materialGateway({
      uploadMaterial: vi
        .fn()
        .mockRejectedValueOnce(new Error("network unavailable"))
        .mockResolvedValueOnce({ material: UNDERSTOOD_MATERIAL }),
    });
    const { container } = render(
      <App
        initialSession={TEST_SESSION}
        materialClient={materials}
        materialUploadIdFactory={() => CLIENT_UPLOAD_ID}
      />,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    const file = new File(["门店资料"], "门店资料.md", {
      type: "text/markdown",
    });

    await user.upload(input!, file);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "门店资料.md 没有上传完成",
    );
    await user.click(screen.getByRole("button", { name: "重新上传" }));

    expect(materials.uploadMaterial).toHaveBeenCalledTimes(2);
    expect(materials.uploadMaterial).toHaveBeenNthCalledWith(
      1,
      file,
      "",
      CLIENT_UPLOAD_ID,
    );
    expect(materials.uploadMaterial).toHaveBeenNthCalledWith(
      2,
      file,
      "",
      CLIENT_UPLOAD_ID,
    );
    expect(await screen.findByText("首店接待流程.md")).toBeVisible();
  });
});
