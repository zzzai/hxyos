import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  LearningClient,
  LearningHome,
  LearningPracticeResult,
} from "../../api/learning";
import { LearningView } from "./LearningView";


const HOME: LearningHome = {
  next_action: {
    id: "service-boundary-v1",
    title: "回应顾客不适",
    purpose: "练习先回应感受，再守住非医疗服务边界。",
    estimated_minutes: 3,
    scenario: {
      customer_message: "顾客说：做完以后还是不舒服，我该怎么办？",
    },
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
};

const RESULT: LearningPracticeResult = {
  attempt: {
    id: "session-one",
    score: 72,
    level: "retrain",
    needs_retrain: true,
    standard_script: "先回应顾客感受，再说明服务边界。",
    correction_points: ["不能承诺治疗效果"],
    physical_technique: "not_assessed",
  },
  next_action: HOME.next_action,
  progress: {
    ...HOME.progress,
    attempts: 1,
    needs_attention: ["不能承诺治疗效果"],
  },
  limitations: HOME.limitations,
};

function client(): LearningClient {
  return {
    loadLearning: vi.fn().mockResolvedValue(HOME),
    submitPractice: vi.fn().mockResolvedValue(RESULT),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LearningView", () => {
  it("shows only one next action instead of a course catalog", async () => {
    render(<LearningView client={client()} />);

    expect(await screen.findByRole("heading", { name: "回应顾客不适" })).toBeVisible();
    expect(screen.getByText(HOME.next_action.scenario.customer_message)).toBeVisible();
    expect(screen.getByText("约 3 分钟")).toBeVisible();
    expect(screen.queryByText(/课程目录|课程中心|排行榜|学习地图/)).not.toBeInTheDocument();
    expect(screen.getByText("仅自己可见")).toBeVisible();
  });

  it("submits the current scenario response and shows actionable feedback", async () => {
    const user = userEvent.setup();
    const learning = client();
    render(<LearningView client={learning} />);

    await user.type(
      await screen.findByRole("textbox", { name: "你会怎么回应？" }),
      "我先了解一下您现在的感受，再帮您处理。",
    );
    await user.click(screen.getByRole("button", { name: "提交练习" }));

    await waitFor(() => expect(learning.submitPractice).toHaveBeenCalledWith({
      action_id: "service-boundary-v1",
      employee_answer: "我先了解一下您现在的感受，再帮您处理。",
    }));
    expect(await screen.findByRole("heading", { name: "本次反馈" })).toBeVisible();
    expect(screen.getByText("不能承诺治疗效果")).toBeVisible();
    expect(screen.getByText("先回应顾客感受，再说明服务边界。")).toBeVisible();
    expect(screen.getByText("已练习 1 次")).toBeVisible();
  });

  it("accepts a dictated answer when browser speech input is available", async () => {
    const user = userEvent.setup();
    let recognition: {
      onresult?: (event: unknown) => void;
      onend?: () => void;
    } | null = null;
    class FakeSpeechRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult?: (event: unknown) => void;
      onerror?: () => void;
      onend?: () => void;

      constructor() {
        recognition = this;
      }

      start() {
        this.onresult?.({ results: [[{ transcript: "我先了解您的感受" }]] });
        this.onend?.();
      }

      stop() {
        this.onend?.();
      }
    }
    vi.stubGlobal("webkitSpeechRecognition", FakeSpeechRecognition);
    render(<LearningView client={client()} />);

    await user.click(await screen.findByRole("button", { name: "语音输入" }));

    expect(recognition).not.toBeNull();
    expect(screen.getByRole("textbox", { name: "你会怎么回应？" })).toHaveValue(
      "我先了解您的感受",
    );
  });

  it("shows a recoverable load error", async () => {
    const learning = client();
    vi.mocked(learning.loadLearning)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(HOME);
    const user = userEvent.setup();
    render(<LearningView client={learning} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("暂时没有加载出来");
    await user.click(screen.getByRole("button", { name: "重新加载" }));

    expect(await screen.findByRole("heading", { name: "回应顾客不适" })).toBeVisible();
  });
});
