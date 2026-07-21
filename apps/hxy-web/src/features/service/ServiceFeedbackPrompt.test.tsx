import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MaterialClient } from "../../api/materials";
import type { ServiceClient, ServiceContext } from "../../api/services";
import { ServiceFeedbackPrompt } from "./ServiceFeedbackPrompt";

const ACTIVE_CONTEXT: ServiceContext = {
  id: "66000000-0000-0000-0000-000000000001",
  status: "provisional",
  occurred_at: "2026-07-21T09:00:00Z",
  service_label: "足部舒缓服务",
  customer_display: "王女士 · 尾号 1234",
  feedback_count: 0,
  created_at: "2026-07-21T09:00:00Z",
};

const COMPLETED_CONTEXT: ServiceContext = {
  ...ACTIVE_CONTEXT,
  id: "66000000-0000-0000-0000-000000000002",
  occurred_at: "2026-07-21T10:00:00Z",
  customer_display: "李女士 · 尾号 5678",
  feedback_count: 1,
};

const ASSET_ID = "79000000-0000-0000-0000-000000000001";

function serviceClient(
  overrides: Partial<ServiceClient> = {},
): ServiceClient {
  return {
    listRecent: vi.fn().mockResolvedValue({
      contexts: [COMPLETED_CONTEXT, ACTIVE_CONTEXT],
    }),
    addFeedback: vi.fn().mockResolvedValue({
      feedback: {
        id: "77000000-0000-0000-0000-000000000001",
        context_id: ACTIVE_CONTEXT.id,
        status: "received",
        created_at: "2026-07-21T10:05:00Z",
      },
      context: { ...ACTIVE_CONTEXT, feedback_count: 1 },
    }),
    ...overrides,
  };
}

function materialClient(): MaterialClient {
  return {
    listMaterials: vi.fn(),
    getMaterial: vi.fn(),
    retryUnderstanding: vi.fn(),
    uploadMaterial: vi.fn().mockResolvedValue({
      material: {
        id: ASSET_ID,
        file_name: "service-feedback.webm",
        media_type: "audio/webm",
        size_bytes: 12,
        status: "processing",
        receipt: { status: "已收到", message: "资料已进入待处理区。" },
        original: { url: `/api/v1/materials/${ASSET_ID}/content`, can_preview: true },
        understanding: {
          summary: "资料已收到，系统正在理解。",
          document_type: "服务反馈录音",
          source_origin: "internal",
          authority_level: "working_material",
          knowledge_scale: "micro",
          domain: "customer",
          parse_status: "needs_multimodal",
          confidence: "low",
          warnings: [],
          official_use_allowed: false,
          use_boundary: "仅作为门店服务反馈使用。",
        },
        created_at: "2026-07-21T10:00:00Z",
        updated_at: "2026-07-21T10:00:00Z",
      },
    }),
  };
}

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
  vi.stubGlobal("navigator", {
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) },
  });
  vi.stubGlobal("MediaRecorder", FakeVoiceRecorder);
}

function renderPrompt(options: {
  services?: ServiceClient;
  materials?: MaterialClient;
  onActiveChange?: (active: boolean) => void;
} = {}) {
  return render(
    <ServiceFeedbackPrompt
      serviceClient={options.services ?? serviceClient()}
      materialClient={options.materials ?? materialClient()}
      clientFeedbackIdFactory={() => "78000000-0000-0000-0000-000000000001"}
      uploadIdFactory={() => "7a000000-0000-0000-0000-000000000001"}
      onActiveChange={options.onActiveChange}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ServiceFeedbackPrompt", () => {
  it("selects one recent unfinished service and displays masked identity only", async () => {
    renderPrompt();

    expect(await screen.findByText("王女士 · 尾号 1234")).toBeVisible();
    expect(screen.getByText("足部舒缓服务")).toBeVisible();
    expect(screen.queryByText("李女士 · 尾号 5678")).not.toBeInTheDocument();
    expect(screen.queryByText(/13800138000/)).not.toBeInTheDocument();
  });

  it("submits a short text feedback without browser supplied assignment scope", async () => {
    const user = userEvent.setup();
    const services = serviceClient();
    renderPrompt({ services });

    await user.type(
      await screen.findByRole("textbox", { name: "服务反馈" }),
      "顾客反馈力度合适，肩颈仍有些紧。",
    );
    await user.click(screen.getByRole("button", { name: "提交服务反馈" }));

    await waitFor(() => expect(services.addFeedback).toHaveBeenCalledOnce());
    expect(services.addFeedback).toHaveBeenCalledWith(ACTIVE_CONTEXT.id, {
      clientFeedbackId: "78000000-0000-0000-0000-000000000001",
      text: "顾客反馈力度合适，肩颈仍有些紧。",
      sourceAssetIds: [],
      durationMs: expect.any(Number),
    });
    expect(JSON.stringify(vi.mocked(services.addFeedback).mock.calls)).not.toMatch(
      /organization|store|assignment/,
    );
    expect(await screen.findByText("服务反馈已记录")).toBeVisible();
  });

  it("uploads a voice note as a protected asset before feedback submission", async () => {
    enableVoiceCapture();
    const user = userEvent.setup();
    const services = serviceClient();
    const materials = materialClient();
    renderPrompt({ services, materials });

    await screen.findByText("王女士 · 尾号 1234");
    await user.click(screen.getByRole("button", { name: "录音反馈" }));
    await user.click(await screen.findByRole("button", { name: "结束录音" }));

    await waitFor(() => expect(materials.uploadMaterial).toHaveBeenCalledOnce());
    expect(materials.uploadMaterial).toHaveBeenCalledWith(
      expect.objectContaining({ type: "audio/webm" }),
      "服务反馈录音",
      "7a000000-0000-0000-0000-000000000001",
    );
    expect(await screen.findByText("录音已添加")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "提交服务反馈" }));
    await waitFor(() => expect(services.addFeedback).toHaveBeenCalledOnce());
    expect(services.addFeedback).toHaveBeenCalledWith(
      ACTIVE_CONTEXT.id,
      expect.objectContaining({ text: "", sourceAssetIds: [ASSET_ID] }),
    );
  });

  it("shows a retry action when recent services cannot load", async () => {
    const user = userEvent.setup();
    const services = serviceClient({
      listRecent: vi
        .fn()
        .mockRejectedValueOnce(new Error("offline"))
        .mockResolvedValueOnce({ contexts: [ACTIVE_CONTEXT] }),
    });
    renderPrompt({ services });

    expect(
      await screen.findByText("最近服务暂时没有加载出来"),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "重新加载服务" }));

    expect(await screen.findByText("王女士 · 尾号 1234")).toBeVisible();
    expect(services.listRecent).toHaveBeenCalledTimes(2);
  });

  it("reports whether it occupies one Today attention slot", async () => {
    const onActiveChange = vi.fn();
    renderPrompt({ onActiveChange });

    await screen.findByText("王女士 · 尾号 1234");
    expect(onActiveChange).toHaveBeenLastCalledWith(true);
  });
});
