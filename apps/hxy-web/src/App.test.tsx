import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { MeRequestError } from "./api/client";

const TEST_SESSION = {
  user: { account_id: "account-employee", display_name: "测试员工" },
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
    ],
  },
  available_assignments: [],
};

const todayClient = { getToday: vi.fn().mockResolvedValue({ items: [] }) };
const recordClient = {
  listRecords: vi.fn().mockResolvedValue({ records: [] }),
  getRecord: vi.fn(),
  createRecord: vi.fn(),
};
const conversationClient = {
  listConversations: vi.fn().mockResolvedValue({ items: [] }),
  getConversation: vi.fn(),
  createConversation: vi.fn(),
  sendMessage: vi.fn(),
};
const materialClient = {
  listMaterials: vi.fn(),
  getMaterial: vi.fn(),
  retryUnderstanding: vi.fn(),
  uploadMaterial: vi.fn(),
};

function renderAuthenticatedApp() {
  return render(
    <App
      initialSession={TEST_SESSION}
      todayClient={todayClient}
      recordClient={recordClient}
      conversationClient={conversationClient}
      materialClient={materialClient}
    />,
  );
}

describe("HXYOS application entry", () => {
  it("opens the minimal Today frontstage for an authenticated assignment", async () => {
    renderAuthenticatedApp();

    expect(await screen.findByRole("heading", { name: "今日" })).toBeVisible();
    expect(
      screen.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
    ).toBeEnabled();
    expect(screen.queryByRole("button", { name: "提问" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "记录" })).not.toBeInTheDocument();
    expect(screen.queryByText("今天的待办")).not.toBeInTheDocument();
  });

  it("shows a focused connection state while identity is loading", () => {
    render(<App sessionLoader={() => new Promise(() => undefined)} />);

    expect(screen.getByRole("status")).toHaveTextContent("正在连接 HXYOS");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("shows the access gate after an unauthorized identity response", async () => {
    const loader = vi.fn().mockRejectedValue(new MeRequestError(401, "Unauthorized"));
    render(<App sessionLoader={loader} />);

    expect(await screen.findByRole("heading", { name: "进入 HXYOS" })).toBeVisible();
    expect(screen.getByLabelText("一次性访问码")).toBeEnabled();
    expect(screen.getByRole("button", { name: "进入" })).toBeDisabled();
  });

  it("exchanges a one-time access code and opens the frontstage", async () => {
    const user = userEvent.setup();
    const grant = "g".repeat(64);
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new MeRequestError(401, "Unauthorized"))
      .mockResolvedValueOnce(TEST_SESSION);
    const grantExchanger = vi.fn().mockResolvedValue(undefined);

    render(
      <App
        sessionLoader={loader}
        grantExchanger={grantExchanger}
        todayClient={todayClient}
        recordClient={recordClient}
        conversationClient={conversationClient}
        materialClient={materialClient}
      />,
    );

    await user.type(await screen.findByLabelText("一次性访问码"), grant);
    await user.click(screen.getByRole("button", { name: "进入" }));

    expect(grantExchanger).toHaveBeenCalledWith(grant);
    expect(await screen.findByRole("heading", { name: "今日" })).toBeVisible();
  });

  it("keeps the access gate usable after an invalid code", async () => {
    const user = userEvent.setup();
    const loader = vi.fn().mockRejectedValue(new MeRequestError(401, "Unauthorized"));
    const grantExchanger = vi
      .fn()
      .mockRejectedValue(new MeRequestError(401, "Unauthorized"));

    render(<App sessionLoader={loader} grantExchanger={grantExchanger} />);

    await user.type(await screen.findByLabelText("一次性访问码"), "x".repeat(64));
    await user.click(screen.getByRole("button", { name: "进入" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("访问码无效或已过期");
    expect(screen.getByLabelText("一次性访问码")).toHaveValue("");
  });
});
