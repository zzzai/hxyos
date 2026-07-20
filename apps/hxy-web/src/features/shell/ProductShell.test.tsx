import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MeResponse } from "../../api/client";
import type { ConversationClient } from "../../api/conversations";
import type { MaterialClient } from "../../api/materials";
import type { LearningClient } from "../../api/learning";
import type { ServiceClient, ServiceContext } from "../../api/services";
import type {
  OrganizationRecord,
  OrganizationRecordClient,
} from "../../api/records";
import type { TodayBriefItem, TodayClient } from "../../api/today";
import { SessionProvider } from "../session/SessionProvider";
import { ProductShell } from "./ProductShell";

const RECORD_ID = "12000000-0000-4000-8000-000000000001";
const ASSET_ID = "13000000-0000-4000-8000-000000000001";
const TEST_SESSION = {
  user: { account_id: "account-employee", display_name: "李师傅" },
  active_assignment: {
    assignment_id: "assignment-employee",
    organization: { id: "organization-hxy", name: "荷小悦" },
    store: { id: "store-first", name: "荷小悦首店" },
    role: "store_employee" as const,
    role_label: "技师",
    capabilities: [
      "conversation:use",
      "materials:create",
      "materials:read",
      "records:create",
      "records:read",
      "training:practice",
      "services:feedback",
      "services:read",
    ],
  },
  available_assignments: [],
};

const RECORD: OrganizationRecord = {
  id: RECORD_ID,
  source_types: ["text"],
  preview: "施工方尚未收到最终水电图",
  submitted_by: "项目负责人",
  store_id: "store-first",
  captured_at: "2026-07-20T08:30:00Z",
  occurred_at: null,
  processing_status: "ready",
  original: {
    text: "施工方尚未收到最终水电图，今天需要确认。",
    assets: [],
  },
  interpretation: {
    version: "v1",
    summary: "最终水电图仍待确认。",
    facts: [],
    decisions: [],
    progress: [],
    risks: [
      {
        statement: "水电施工可能延迟",
        evidence: [
          {
            source_record_id: RECORD_ID,
            source_asset_id: null,
            quote: "施工方尚未收到最终水电图",
            locator: null,
          },
        ],
      },
    ],
    missing_information: [],
    confidence: 0.91,
    official_knowledge: false,
  },
};

class FakeVoiceRecorder {
  readonly mimeType = "audio/webm";
  state: RecordingState = "inactive";
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(_stream: MediaStream) {}

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({
      data: new Blob(["voice"], { type: "audio/webm" }),
    } as BlobEvent);
    this.onstop?.(new Event("stop"));
  }
}

function enableVoiceCapture() {
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeVoiceRecorder);
  return { getUserMedia, stop };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function brief(index: number): TodayBriefItem {
  return {
    id: `brief-${index}`,
    kind: index === 1 ? "risk" : index === 2 ? "decision" : "progress",
    severity: index === 1 ? "high" : null,
    statement: index === 1 ? "水电图仍待确认" : `今日进展 ${index}`,
    why_it_matters: "可能影响首店筹备节奏",
    source_record_id: RECORD_ID,
    evidence: [
      {
        source_record_id: RECORD_ID,
        source_asset_id: null,
        quote: "施工方尚未收到最终水电图",
        locator: null,
      },
    ],
    captured_at: "2026-07-20T08:30:00Z",
    next_action: {
      type: "open_record",
      label: "查看依据",
      prompt: null,
    },
  };
}

function todayClient(
  items = [brief(1), brief(2), brief(3), brief(4)],
  roleAction: Awaited<ReturnType<TodayClient["getToday"]>>["role_action"] = null,
): TodayClient {
  return { getToday: vi.fn().mockResolvedValue({ items, role_action: roleAction }) };
}

function serviceClient(contexts: ServiceContext[] = []): ServiceClient {
  return {
    listRecent: vi.fn().mockResolvedValue({ contexts }),
    addFeedback: vi.fn().mockResolvedValue({
      feedback: {
        id: "77000000-0000-0000-0000-000000000001",
        context_id: contexts[0]?.id ?? "66000000-0000-0000-0000-000000000001",
        status: "received",
        created_at: "2026-07-21T10:05:00Z",
      },
      context: {
        ...(contexts[0] ?? {
          id: "66000000-0000-0000-0000-000000000001",
          status: "provisional" as const,
          occurred_at: "2026-07-21T09:00:00Z",
          service_label: "足部舒缓服务",
          customer_display: "顾客",
          feedback_count: 0,
          created_at: "2026-07-21T09:00:00Z",
        }),
        feedback_count: 1,
      },
    }),
  };
}

function recordClient(
  overrides: Partial<OrganizationRecordClient> = {},
): OrganizationRecordClient {
  return {
    listRecords: vi.fn().mockResolvedValue({ records: [RECORD] }),
    getRecord: vi.fn().mockResolvedValue({ record: RECORD }),
    createRecord: vi.fn().mockResolvedValue({
      record: { ...RECORD, processing_status: "processing" },
    }),
    ...overrides,
  };
}

function conversationClient(): ConversationClient {
  return {
    listConversations: vi.fn().mockResolvedValue({ items: [] }),
    getConversation: vi.fn(),
    createConversation: vi.fn().mockResolvedValue({
      conversation: {
        id: "conversation-new",
        title: "新对话",
        created_at: "2026-07-20T09:00:00Z",
        updated_at: "2026-07-20T09:00:00Z",
        last_message_at: null,
        message_count: 0,
        last_message: null,
      },
    }),
    sendMessage: vi.fn().mockResolvedValue({
      conversation: {
        id: "conversation-new",
        title: "水电图风险",
        created_at: "2026-07-20T09:00:00Z",
        updated_at: "2026-07-20T09:00:01Z",
        last_message_at: "2026-07-20T09:00:01Z",
        message_count: 2,
        last_message: null,
      },
      user_message: {
        id: "message-user",
        conversation_id: "conversation-new",
        role: "user",
        content: "这会影响什么？",
        created_at: "2026-07-20T09:00:00Z",
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
        content: "可能影响水电施工进场时间，应先确认最终图纸。",
        created_at: "2026-07-20T09:00:01Z",
        answer_id: "answer-one",
        answer_status: "工作判断",
        confidence: "high",
        needs_review: false,
        sources: [],
        next_actions: [],
      },
    }),
  };
}

function materialClient(): MaterialClient {
  return {
    listMaterials: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    getMaterial: vi.fn(),
    retryUnderstanding: vi.fn(),
    uploadMaterial: vi.fn().mockResolvedValue({
      material: {
        id: ASSET_ID,
        file_name: "装修现场.jpg",
        media_type: "image/jpeg",
        size_bytes: 12,
        status: "processing",
        receipt: { status: "已收到", message: "资料已进入待处理区。" },
        original: { url: `/api/v1/materials/${ASSET_ID}/content`, can_preview: true },
        understanding: {
          summary: "资料已收到，系统正在理解。",
          document_type: "现场图片",
          source_origin: "internal",
          authority_level: "working_material",
          knowledge_scale: "micro",
          domain: "store",
          parse_status: "needs_multimodal",
          confidence: "low",
          warnings: [],
          official_use_allowed: false,
          use_boundary: "仅作为组织资料使用。",
        },
        created_at: "2026-07-20T09:00:00Z",
        updated_at: "2026-07-20T09:00:00Z",
      },
    }),
  };
}

function learningClient(): LearningClient {
  return {
    loadLearning: vi.fn().mockResolvedValue({
      next_action: {
        id: "service-boundary-v1",
        title: "回应顾客不适",
        purpose: "练习先回应感受，再守住非医疗服务边界。",
        estimated_minutes: 3,
        scenario: { customer_message: "顾客说：做完以后还是不舒服，我该怎么办？" },
        response_modes: ["text", "voice"],
      },
      progress: {
        visibility: "private",
        attempts: 0,
        mastered: [],
        practicing: ["服务边界表达"],
        needs_attention: [],
      },
      limitations: [
        "AI 只评估沟通表达、服务意识和风险边界。",
        "推拿或按摩手法必须由有资质的培训人员现场评估。",
      ],
    }),
    submitPractice: vi.fn(),
  };
}

function shellElement(options: {
  session?: MeResponse;
  today?: TodayClient;
  records?: OrganizationRecordClient;
  conversations?: ConversationClient;
  materials?: MaterialClient;
  learning?: LearningClient;
  services?: ServiceClient;
  logout?: () => Promise<void>;
  onLoggedOut?: () => void;
  onboardingClient?: undefined;
  clientIdFactory?: () => string;
} = {}) {
  return (
    <SessionProvider initialSession={options.session ?? TEST_SESSION}>
      <ProductShell
        todayClient={options.today ?? todayClient()}
        recordClient={options.records ?? recordClient()}
        conversationClient={options.conversations ?? conversationClient()}
        materialClient={options.materials ?? materialClient()}
        learningClient={options.learning ?? learningClient()}
        serviceClient={options.services ?? serviceClient()}
        clientIdFactory={
          options.clientIdFactory ??
          (() => "15000000-0000-4000-8000-000000000001")
        }
        uploadIdFactory={() => "16000000-0000-4000-8000-000000000001"}
        logout={options.logout ?? vi.fn().mockResolvedValue(undefined)}
        onLoggedOut={options.onLoggedOut ?? vi.fn()}
      />
    </SessionProvider>
  );
}

function renderShell(options: Parameters<typeof shellElement>[0] = {}) {
  return render(shellElement(options));
}

describe("minimal HXYOS frontstage", () => {
  it("opens Today with no more than three attention items", async () => {
    renderShell();

    const briefing = await screen.findByRole("list", { name: "今日重点" });
    expect(within(briefing).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByText("今日进展 4")).not.toBeInTheDocument();
  });

  it("shows one unfinished technician service and keeps Today to three actions", async () => {
    const context: ServiceContext = {
      id: "66000000-0000-0000-0000-000000000001",
      status: "provisional",
      occurred_at: "2026-07-21T09:00:00Z",
      service_label: "足部舒缓服务",
      customer_display: "王女士 · 尾号 1234",
      feedback_count: 0,
      created_at: "2026-07-21T09:00:00Z",
    };
    renderShell({ services: serviceClient([context]) });

    expect(await screen.findByText("王女士 · 尾号 1234")).toBeVisible();
    const briefing = screen.getByRole("list", { name: "今日重点" });
    expect(within(briefing).getAllByRole("listitem")).toHaveLength(2);
  });

  it("lets a store manager start the server-derived closing review in the composer", async () => {
    const user = userEvent.setup();
    const records = recordClient();
    const managerSession: MeResponse = {
      ...TEST_SESSION,
      user: { account_id: "account-manager", display_name: "周店长" },
      active_assignment: {
        ...TEST_SESSION.active_assignment,
        assignment_id: "assignment-manager",
        role: "store_manager",
        role_label: "店长",
        capabilities: [
          "conversation:use",
          "materials:create",
          "materials:read",
          "records:create",
          "records:read",
        ],
      },
    };
    renderShell({
      session: managerSession,
      records,
      today: todayClient([brief(1), brief(2), brief(3)], {
        type: "closing_review",
        label: "记录闭店复盘",
        prompt: "闭店复盘：",
      }),
    });

    await user.click(await screen.findByRole("button", { name: "记录闭店复盘" }));
    const composer = screen.getByRole("textbox", {
      name: "问问题，或记录刚刚发生的事",
    });
    expect(composer).toHaveValue("闭店复盘：");
    await user.type(composer, "今日客流平稳，无未处理客诉。");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(records.createRecord).toHaveBeenCalledOnce());
    expect(records.createRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "闭店复盘：今日客流平稳，无未处理客诉。",
      }),
    );
  });

  it("persists and routes text without asking for a mode, category, or tag", async () => {
    const user = userEvent.setup();
    const records = recordClient();
    const conversations = conversationClient();
    renderShell({ records, conversations });

    await user.type(
      screen.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
      "线上运营今天正式入职",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(records.createRecord).toHaveBeenCalledOnce());
    expect(records.createRecord).toHaveBeenCalledWith({
      clientRecordId: "15000000-0000-4000-8000-000000000001",
      text: "线上运营今天正式入职",
      sourceAssetIds: [],
    });
    expect(conversations.sendMessage).toHaveBeenCalledWith(
      "conversation-new",
      expect.objectContaining({
        content: "线上运营今天正式入职",
        client_message_id: "15000000-0000-4000-8000-000000000001",
      }),
    );
    expect(screen.queryByRole("button", { name: "提问" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "记录" })).not.toBeInTheDocument();
    expect(screen.queryByText(/标签|分类|权威级别/)).not.toBeInTheDocument();
    expect(await screen.findByText("已收到，正在处理")).toBeVisible();
  });

  it("uploads a file and shows its immediate receipt", async () => {
    const user = userEvent.setup();
    const records = recordClient();
    const materials = materialClient();
    renderShell({ records, materials });

    const file = new File(["site-photo"], "装修现场.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText("添加资料"), file);
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(materials.uploadMaterial).toHaveBeenCalledOnce());
    expect(records.createRecord).toHaveBeenCalledWith(
      expect.objectContaining({ sourceAssetIds: [ASSET_ID] }),
    );
    expect(await screen.findByText("已收到，正在处理")).toBeVisible();
  });

  it("uses one submission id for text, attachment, and conversation", async () => {
    const user = userEvent.setup();
    const records = recordClient();
    const conversations = conversationClient();
    const materials = materialClient();
    renderShell({ records, conversations, materials });

    await user.type(
      screen.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
      "这是今天确认的门店效果图",
    );
    await user.upload(
      screen.getByLabelText("添加资料"),
      new File(["render"], "门店效果图.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(conversations.sendMessage).toHaveBeenCalledOnce());
    expect(records.createRecord).toHaveBeenCalledWith({
      clientRecordId: "15000000-0000-4000-8000-000000000001",
      text: "这是今天确认的门店效果图",
      sourceAssetIds: [ASSET_ID],
    });
    expect(conversations.sendMessage).toHaveBeenCalledWith(
      "conversation-new",
      expect.objectContaining({
        content: "这是今天确认的门店效果图",
        client_message_id: "15000000-0000-4000-8000-000000000001",
      }),
    );
  });

  it("does not ask the model when original persistence fails", async () => {
    const user = userEvent.setup();
    const records = recordClient({
      createRecord: vi.fn().mockRejectedValue(new Error("offline")),
    });
    const conversations = conversationClient();
    renderShell({ records, conversations });

    await user.type(
      screen.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
      "施工方今天没有进场",
    );
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("没有提交成功");
    expect(conversations.createConversation).not.toHaveBeenCalled();
    expect(conversations.sendMessage).not.toHaveBeenCalled();
  });

  it("reuses an uploaded asset when record creation is retried", async () => {
    const user = userEvent.setup();
    const clientIdFactory = vi
      .fn()
      .mockReturnValueOnce("15000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("15000000-0000-4000-8000-000000000002");
    const records = recordClient({
      createRecord: vi
        .fn()
        .mockRejectedValueOnce(new Error("offline"))
        .mockResolvedValueOnce({
          record: { ...RECORD, processing_status: "processing" },
        }),
    });
    const materials = materialClient();
    renderShell({ records, materials, clientIdFactory });

    await user.upload(
      screen.getByLabelText("添加资料"),
      new File(["site-photo"], "装修现场.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("没有提交成功");

    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(records.createRecord).toHaveBeenCalledTimes(2));
    expect(materials.uploadMaterial).toHaveBeenCalledOnce();
    expect(clientIdFactory).toHaveBeenCalledOnce();
    expect(records.createRecord).toHaveBeenLastCalledWith(
      expect.objectContaining({
        clientRecordId: "15000000-0000-4000-8000-000000000001",
        sourceAssetIds: [ASSET_ID],
      }),
    );
  });

  it("records voice and submits it through protected material intake", async () => {
    const user = userEvent.setup();
    enableVoiceCapture();
    const records = recordClient();
    const materials = materialClient();
    renderShell({ records, materials });

    await user.click(screen.getByRole("button", { name: "开始录音" }));
    expect(await screen.findByRole("button", { name: "停止录音" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "停止录音" }));

    expect(await screen.findByText(/^voice-.*\.webm$/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(materials.uploadMaterial).toHaveBeenCalledOnce());
    expect(materials.uploadMaterial).toHaveBeenCalledWith(
      expect.objectContaining({ type: "audio/webm" }),
      "",
      "16000000-0000-4000-8000-000000000001",
    );
    expect(records.createRecord).toHaveBeenCalledWith(
      expect.objectContaining({ sourceAssetIds: [ASSET_ID] }),
    );
  });

  it("cancels an active voice capture without adding an attachment", async () => {
    const user = userEvent.setup();
    const { stop } = enableVoiceCapture();
    renderShell();

    await user.click(screen.getByRole("button", { name: "开始录音" }));
    await user.click(await screen.findByRole("button", { name: "取消录音" }));

    expect(await screen.findByRole("button", { name: "开始录音" })).toBeVisible();
    expect(screen.queryByText(/^voice-.*\.webm$/)).not.toBeInTheDocument();
    expect(stop).toHaveBeenCalledOnce();
  });

  it("supports hold-to-record on touch devices", async () => {
    enableVoiceCapture();
    renderShell();

    const microphone = screen.getByRole("button", { name: "开始录音" });
    fireEvent.pointerDown(microphone, { pointerId: 7, pointerType: "touch" });
    const stopRecording = await screen.findByRole("button", { name: "停止录音" });
    fireEvent.pointerUp(stopRecording, { pointerId: 7, pointerType: "touch" });

    expect(await screen.findByText(/^voice-.*\.webm$/)).toBeVisible();
  });

  it("honors touch release while microphone permission is still pending", async () => {
    let resolvePermission: ((stream: MediaStream) => void) | undefined;
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    const getUserMedia = vi.fn(
      () =>
        new Promise<MediaStream>((resolve) => {
          resolvePermission = resolve;
        }),
    );
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("MediaRecorder", FakeVoiceRecorder);
    renderShell();

    fireEvent.pointerDown(screen.getByRole("button", { name: "开始录音" }), {
      pointerId: 8,
      pointerType: "touch",
    });
    const requesting = await screen.findByRole("button", {
      name: "正在请求麦克风",
    });
    expect(requesting).toBeEnabled();
    fireEvent.pointerUp(requesting, { pointerId: 8, pointerType: "touch" });
    await act(async () => resolvePermission?.(stream));

    expect(await screen.findByText(/^voice-.*\.webm$/)).toBeVisible();
    expect(stop).toHaveBeenCalledOnce();
  });

  it("opens evidence-backed record detail from a briefing row", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(await screen.findByRole("button", { name: /水电图仍待确认/ }));

    const detail = await screen.findByRole("region", { name: "组织记录详情" });
    expect(within(detail).getByText("施工方尚未收到最终水电图，今天需要确认。")).toBeVisible();
    expect(within(detail).getByText("施工方尚未收到最终水电图")).toBeVisible();
  });

  it("opens an original attachment from record detail", async () => {
    const user = userEvent.setup();
    const recordWithAsset: OrganizationRecord = {
      ...RECORD,
      original: {
        ...RECORD.original,
        assets: [
          {
            id: ASSET_ID,
            file_name: "最终水电图.pdf",
            media_type: "application/pdf",
            size_bytes: 512,
            status: "ready",
          },
        ],
      },
    };
    renderShell({
      records: recordClient({
        getRecord: vi.fn().mockResolvedValue({ record: recordWithAsset }),
      }),
    });

    await user.click(await screen.findByRole("button", { name: /水电图仍待确认/ }));

    expect(screen.getByRole("link", { name: "打开原始资料 最终水电图.pdf" })).toHaveAttribute(
      "href",
      `/api/v1/materials/${ASSET_ID}/content`,
    );
  });

  it("starts a sourced contextual question from a record", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(await screen.findByRole("button", { name: /水电图仍待确认/ }));
    await user.click(screen.getByRole("button", { name: "基于这条记录提问" }));

    expect(screen.getByRole("heading", { name: "对话" })).toBeVisible();
    expect(screen.getByText("正在基于：施工方尚未收到最终水电图")).toBeVisible();
    expect(
      screen.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
    ).toHaveFocus();
  });

  it("shows only employee-safe identity and records", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(screen.getByRole("button", { name: "我的" }));

    const identity = screen.getByRole("region", { name: "当前身份" });
    expect(within(identity).getByText("李师傅")).toBeVisible();
    expect(within(identity).getByText("技师")).toBeVisible();
    expect(within(identity).getByText("荷小悦首店")).toBeVisible();
    expect(screen.queryByText(/审核|模型运行|知识治理|成员管理/)).not.toBeInTheDocument();
  });

  it("opens one role-scoped learning action from primary navigation", async () => {
    const user = userEvent.setup();
    const learning = learningClient();
    renderShell({ learning });

    await user.click(screen.getByRole("button", { name: "学习" }));

    expect(await screen.findByRole("heading", { name: "回应顾客不适" })).toBeVisible();
    expect(learning.loadLearning).toHaveBeenCalledOnce();
    expect(screen.getByText("仅自己可见")).toBeVisible();
    expect(screen.queryByText(/课程目录|排行榜|审核|知识治理/)).not.toBeInTheDocument();
  });

  it("all primary navigation and composer controls perform an action", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(screen.getByRole("button", { name: "组织记录" }));
    expect(await screen.findByRole("heading", { name: "组织记录" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "对话" }));
    expect(screen.getByRole("heading", { name: "对话" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "今日" }));
    expect(screen.getByRole("heading", { name: "今日" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "学习" }));
    expect(await screen.findByRole("heading", { name: "学习" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "新输入" }));
    expect(screen.queryByRole("button", { name: "提问" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "记录" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
    ).toHaveFocus();
  });

  it("does not render record controls without record capabilities", async () => {
    const adminSession: MeResponse = {
      user: { account_id: "account-admin", display_name: "系统管理员" },
      active_assignment: {
        assignment_id: "assignment-admin",
        organization: { id: "organization-hxy", name: "荷小悦" },
        store: null,
        role: "system_admin",
        role_label: "系统管理员",
        capabilities: ["conversation:use"],
      },
      available_assignments: [],
    };
    renderShell({ session: adminSession });

    expect(await screen.findByRole("heading", { name: "对话" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "新输入" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "组织记录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开今日简报" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "快速输入" })).not.toBeInTheDocument();
  });

  it("keeps a failed question in the composer for a direct retry", async () => {
    const user = userEvent.setup();
    const records = recordClient();
    const conversations = conversationClient();
    vi.mocked(conversations.sendMessage)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({
        conversation: {
          id: "conversation-new",
          title: "装修进度",
          created_at: "2026-07-20T09:00:00Z",
          updated_at: "2026-07-20T09:00:01Z",
          last_message_at: "2026-07-20T09:00:01Z",
          message_count: 2,
          last_message: null,
        },
        user_message: {
          id: "message-retry-user",
          conversation_id: "conversation-new",
          role: "user",
          content: "装修进度怎么样？",
          created_at: "2026-07-20T09:00:00Z",
          answer_id: null,
          answer_status: null,
          confidence: null,
          needs_review: null,
          sources: [],
          next_actions: [],
        },
        assistant_message: {
          id: "message-retry-assistant",
          conversation_id: "conversation-new",
          role: "assistant",
          content: "当前仍需确认最终水电图。",
          created_at: "2026-07-20T09:00:01Z",
          answer_id: "answer-retry",
          answer_status: "工作判断",
          confidence: "high",
          needs_review: false,
          sources: [],
          next_actions: [],
        },
      });
    renderShell({ records, conversations });
    const input = screen.getByRole("textbox", {
      name: "问问题，或记录刚刚发生的事",
    });

    await user.type(input, "装修进度怎么样？");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "内容已保存，回答暂时没有完成",
    );
    expect(input).toHaveValue("装修进度怎么样？");
    expect(screen.queryByText("对话暂时没有加载出来")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("当前仍需确认最终水电图。")).toBeVisible();
    expect(records.createRecord).toHaveBeenCalledOnce();
    expect(conversations.createConversation).toHaveBeenCalledOnce();
    expect(conversations.sendMessage).toHaveBeenCalledTimes(2);
    expect(vi.mocked(conversations.sendMessage).mock.calls[0][1]).toEqual(
      expect.objectContaining({
        client_message_id: vi.mocked(conversations.sendMessage).mock.calls[1][1]
          .client_message_id,
      }),
    );
  });

  it("shows a recoverable error when fallback logout fails", async () => {
    const user = userEvent.setup();
    const logout = vi.fn().mockRejectedValue(new Error("offline"));
    renderShell({ logout });

    await user.click(screen.getByRole("button", { name: "我的" }));
    await user.click(screen.getByRole("button", { name: "退出登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("没有退出，请重试");
    expect(screen.getByRole("button", { name: "退出登录" })).toBeEnabled();
  });

  it("ignores a stale Today response after its client changes", async () => {
    let resolveFirst: ((value: { items: TodayBriefItem[] }) => void) | undefined;
    const first: TodayClient = {
      getToday: vi.fn(
        () =>
          new Promise<{ items: TodayBriefItem[] }>((resolve) => {
            resolveFirst = resolve;
          }),
      ),
    };
    const freshItem = { ...brief(1), id: "fresh", statement: "最新关键变化" };
    const second: TodayClient = {
      getToday: vi.fn().mockResolvedValue({ items: [freshItem] }),
    };
    const view = renderShell({ today: first });

    view.rerender(shellElement({ today: second }));
    expect(await screen.findByText("最新关键变化")).toBeVisible();

    resolveFirst?.({ items: [{ ...brief(1), id: "stale", statement: "过期变化" }] });
    await waitFor(() => expect(first.getToday).toHaveBeenCalledOnce());
    expect(screen.queryByText("过期变化")).not.toBeInTheDocument();
  });
});
