import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "./App";

const FORBIDDEN_FRONTSTAGE_TERMS = [
  "claim",
  "chunk_id",
  "review queue",
  "/root/hxy",
];

describe("HXYOS product shell", () => {
  it("shows one accessible composer in the main experience", () => {
    render(<App />);

    expect(
      screen.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
    ).toBeVisible();
    expect(screen.getAllByTestId("composer")).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "添加附件（即将开放）" }),
    ).toBeDisabled();
  });

  it("limits primary navigation to conversation, tasks, and profile", () => {
    render(<App />);

    const primaryNavigation = screen.getByRole("navigation", {
      name: "主要导航",
    });
    const labels = within(primaryNavigation)
      .getAllByRole("button")
      .map((item) => item.textContent?.trim());

    expect(labels).toEqual(["对话", "待办", "我的"]);
  });

  it("keeps internal terminology out of the frontstage", () => {
    const { container } = render(<App />);
    const frontstageText = container.textContent?.toLowerCase() ?? "";

    for (const forbidden of FORBIDDEN_FRONTSTAGE_TERMS) {
      expect(frontstageText).not.toContain(forbidden);
    }
  });

  it("shows no more than three context-aware suggestions", () => {
    render(<App />);

    const suggestions = within(screen.getByTestId("suggestions")).getAllByRole(
      "button",
    );
    expect(suggestions.length).toBeGreaterThan(0);
    expect(suggestions.length).toBeLessThanOrEqual(3);
  });

  it("opens and closes source details on demand", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(
      screen.queryByRole("complementary", { name: "来源详情" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "查看来源" }));
    expect(
      screen.getByRole("complementary", { name: "来源详情" }),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "关闭来源详情" }));
    expect(
      screen.queryByRole("complementary", { name: "来源详情" }),
    ).not.toBeInTheDocument();
  });
});
