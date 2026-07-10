import { render, screen, within } from "@testing-library/react";
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
      within(details).getByText("回答服务尚未接入，当前没有可显示的回答详情"),
    ).toBeVisible();
    expect(within(details).queryByText(/来源/)).not.toBeInTheDocument();

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
});
