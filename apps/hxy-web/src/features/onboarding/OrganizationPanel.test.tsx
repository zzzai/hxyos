import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  AssignmentContext,
  OnboardingClient,
  OrganizationInvite,
  OrganizationMember,
  OrganizationStore,
  UserContext,
} from "../../api/client";
import { OrganizationPanel } from "./OrganizationPanel";

const USER: UserContext = {
  account_id: "account-private",
  display_name: "周悦",
};

const FOUNDER: AssignmentContext = {
  assignment_id: "assignment-founder-private",
  organization: { id: "organization-private", name: "荷小悦" },
  store: null,
  role: "founder",
  role_label: "创始人",
  capabilities: [],
};

const MANAGER: AssignmentContext = {
  ...FOUNDER,
  assignment_id: "assignment-manager-private",
  store: { id: "store-1", name: "荷小悦一店" },
  role: "store_manager",
  role_label: "店长",
};

const EMPLOYEE: AssignmentContext = {
  ...MANAGER,
  assignment_id: "assignment-employee-private",
  role: "store_employee",
  role_label: "门店员工",
};

const STORES: OrganizationStore[] = [
  {
    id: "store-1",
    name: "荷小悦一店",
    city: "长沙",
    address: "芙蓉路 1 号",
    status: "active",
  },
  {
    id: "store-2",
    name: "荷小悦二店",
    city: "长沙",
    address: "湘江路 2 号",
    status: "active",
  },
];

const MEMBERS: OrganizationMember[] = [
  {
    assignment_id: MANAGER.assignment_id,
    store_id: "store-1",
    display_name: "周店长",
    role: "store_manager",
    status: "active",
  },
  {
    assignment_id: "assignment-other-manager-private",
    store_id: "store-2",
    display_name: "李店长",
    role: "store_manager",
    status: "active",
  },
  {
    assignment_id: "assignment-employee-2-private",
    store_id: "store-1",
    display_name: "陈员工",
    role: "store_employee",
    status: "active",
  },
];

const PENDING_INVITE: OrganizationInvite = {
  id: "invite-private",
  store_id: "store-2",
  role: "store_manager",
  display_name: "待入职店长",
  status: "pending",
  expires_at: "2026-07-15T10:00:00Z",
};

function onboardingClient(
  overrides: Partial<OnboardingClient> = {},
): OnboardingClient {
  return {
    listStores: vi.fn().mockResolvedValue(STORES),
    createStore: vi.fn().mockResolvedValue(STORES[0]),
    listMembers: vi.fn().mockResolvedValue(MEMBERS),
    listInvites: vi.fn().mockResolvedValue([PENDING_INVITE]),
    createInvite: vi.fn(),
    revokeInvite: vi.fn().mockResolvedValue({
      ...PENDING_INVITE,
      status: "revoked",
    }),
    deactivateMember: vi.fn().mockResolvedValue({
      ...MEMBERS[1],
      status: "inactive",
    }),
    redeemInvite: vi.fn(),
    ...overrides,
  };
}

function renderPanel(
  assignment: AssignmentContext,
  client = onboardingClient(),
  logout = vi.fn().mockResolvedValue(undefined),
) {
  const onLoggedOut = vi.fn();
  return {
    client,
    logout,
    onLoggedOut,
    ...render(
      <div className="app-shell" data-testid="app-shell">
        <OrganizationPanel
          active
          user={USER}
          assignment={assignment}
          client={client}
          logout={logout}
          onLoggedOut={onLoggedOut}
        />
      </div>,
    ),
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

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("OrganizationPanel", () => {
  it("shows founder stores, members, pending invites, and founder-only actions", async () => {
    const inviteWithSecret = {
      ...PENDING_INVITE,
      token_hash: "secret-token-hash",
      one_time_link: "https://hxy.example/#invite=list-link-must-not-render",
    } as OrganizationInvite;
    const client = onboardingClient({
      listInvites: vi.fn().mockResolvedValue([
        inviteWithSecret,
        {
          ...PENDING_INVITE,
          id: "invite-used",
          display_name: "已加入的人",
          status: "redeemed",
        },
      ]),
    });

    renderPanel(FOUNDER, client);

    expect(screen.getByRole("status")).toHaveTextContent("正在加载门店与成员");
    expect(await screen.findByText("荷小悦一店")).toBeVisible();
    expect(screen.getByText("李店长")).toBeVisible();
    expect(screen.getByText("待入职店长")).toBeVisible();
    expect(screen.getByRole("button", { name: "新建门店" })).toBeVisible();
    expect(screen.getByRole("button", { name: "邀请店长" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "邀请员工" })).not.toBeInTheDocument();
    expect(client.listStores).toHaveBeenCalledOnce();
    expect(client.listMembers).toHaveBeenCalledOnce();
    expect(client.listInvites).toHaveBeenCalledOnce();
    expect(screen.queryByText("已加入的人")).not.toBeInTheDocument();

    const visibleText = document.body.textContent ?? "";
    for (const forbidden of [
      "organization-private",
      "assignment-other-manager-private",
      "secret-token-hash",
      "list-link-must-not-render",
      "审核队列",
      "治理",
      "pending",
    ]) {
      expect(visibleText).not.toContain(forbidden);
    }
  });

  it("shows only manager-scope controls and never fetches the store list", async () => {
    const managerInvite = {
      ...PENDING_INVITE,
      id: "employee-invite-private",
      store_id: "store-1",
      role: "store_employee" as const,
      display_name: "待入职员工",
    };
    const client = onboardingClient({
      listInvites: vi.fn().mockResolvedValue([PENDING_INVITE, managerInvite]),
    });
    renderPanel(MANAGER, client);

    expect(await screen.findByText("陈员工")).toBeVisible();
    expect(screen.getByRole("button", { name: "邀请员工" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "邀请店长" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建门店" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(client.listStores).not.toHaveBeenCalled();
    expect(client.listMembers).toHaveBeenCalledOnce();
    expect(client.listInvites).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "停用周店长" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "停用陈员工" })).toBeVisible();
    expect(screen.getByText("待入职员工")).toBeVisible();
    expect(screen.getByRole("button", { name: "撤销待入职员工的邀请" })).toBeVisible();
  });

  it("shows an employee identity and logout only without management fetches", () => {
    const client = onboardingClient();
    renderPanel(EMPLOYEE, client);

    const identity = screen.getByRole("region", { name: "周悦" });
    expect(within(identity).getByText("门店员工")).toBeVisible();
    expect(within(identity).getByText("荷小悦一店")).toBeVisible();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeVisible();
    expect(screen.queryByText("门店与成员")).not.toBeInTheDocument();
    expect(screen.queryByText("待处理邀请")).not.toBeInTheDocument();
    expect(client.listStores).not.toHaveBeenCalled();
    expect(client.listMembers).not.toHaveBeenCalled();
    expect(client.listInvites).not.toHaveBeenCalled();
  });

  it("creates a store and refreshes the verified store rows", async () => {
    const user = userEvent.setup();
    const newStore = {
      id: "store-3",
      name: "荷小悦三店",
      city: "株洲",
      address: "建设路 3 号",
      status: "active" as const,
    };
    const client = onboardingClient({
      createStore: vi.fn().mockResolvedValue(newStore),
      listStores: vi
        .fn()
        .mockResolvedValueOnce(STORES)
        .mockResolvedValueOnce([...STORES, newStore]),
    });
    renderPanel(FOUNDER, client);
    await screen.findByText("荷小悦一店");

    await user.click(screen.getByRole("button", { name: "新建门店" }));
    await user.type(screen.getByRole("textbox", { name: "门店名称" }), "荷小悦三店");
    await user.type(screen.getByRole("textbox", { name: "城市" }), "株洲");
    await user.type(screen.getByRole("textbox", { name: "地址" }), "建设路 3 号");
    await user.click(screen.getByRole("button", { name: "创建门店" }));

    expect(client.createStore).toHaveBeenCalledWith({
      name: "荷小悦三店",
      city: "株洲",
      address: "建设路 3 号",
    });
    expect(await screen.findByText("荷小悦三店")).toBeVisible();
    expect(client.listStores).toHaveBeenCalledTimes(2);
  });

  it("serializes pending store creation and prevents a form switch", async () => {
    const user = userEvent.setup();
    const createdStore = deferred<OrganizationStore>();
    const client = onboardingClient({
      createStore: vi.fn(() => createdStore.promise),
    });
    renderPanel(FOUNDER, client);
    await screen.findByText("荷小悦一店");

    await user.click(screen.getByRole("button", { name: "新建门店" }));
    await user.type(screen.getByRole("textbox", { name: "门店名称" }), "新门店");
    await user.type(screen.getByRole("textbox", { name: "城市" }), "长沙");
    await user.type(screen.getByRole("textbox", { name: "地址" }), "测试路 1 号");
    await user.click(screen.getByRole("button", { name: "创建门店" }));

    expect(screen.getByRole("button", { name: "正在创建" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新建门店" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "邀请店长" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "撤销待入职店长的邀请" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "停用李店长" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "邀请店长" }));
    expect(screen.getByRole("textbox", { name: "门店名称" })).toBeVisible();
    expect(
      screen.queryByRole("textbox", { name: "成员姓名" }),
    ).not.toBeInTheDocument();

    await act(async () => createdStore.resolve(STORES[0]));
  });

  it("waits for verified stores before enabling founder invitations", async () => {
    const stores = deferred<OrganizationStore[]>();
    const client = onboardingClient({
      listStores: vi.fn(() => stores.promise),
    });
    renderPanel(FOUNDER, client);

    expect(screen.getByRole("button", { name: "邀请店长" })).toBeDisabled();
    await act(async () => stores.resolve(STORES));
    expect(await screen.findByText("荷小悦一店")).toBeVisible();
    expect(screen.getByRole("button", { name: "邀请店长" })).toBeEnabled();
  });

  it("invites a manager for a verified store and keeps the link transient", async () => {
    const user = userEvent.setup();
    const oneTimeLink = "https://hxy.example/#invite=one-time-private-link";
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const client = onboardingClient({
      createInvite: vi.fn().mockResolvedValue({
        invite: {
          id: "created-invite-private",
          role: "store_manager",
          display_name: "王店长",
          expires_at: "2026-07-15T10:00:00Z",
        },
        one_time_link: oneTimeLink,
      }),
    });
    renderPanel(FOUNDER, client);
    await screen.findByText("荷小悦一店");

    await user.click(screen.getByRole("button", { name: "邀请店长" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "邀请门店" }), "store-2");
    await user.type(screen.getByRole("textbox", { name: "成员姓名" }), "王店长");
    await user.click(screen.getByRole("button", { name: "生成邀请" }));

    expect(client.createInvite).toHaveBeenCalledWith({
      store_id: "store-2",
      role: "store_manager",
      display_name: "王店长",
    });
    const result = await screen.findByRole("status", { name: "一次性邀请链接" });
    expect(result).toHaveTextContent(oneTimeLink);
    expect(within(result).queryByText("store-2")).not.toBeInTheDocument();
    await user.click(within(result).getByRole("button", { name: "复制一次性邀请链接" }));
    expect(writeText).toHaveBeenCalledWith(oneTimeLink);
    await user.click(within(result).getByRole("button", { name: "关闭一次性邀请链接" }));
    expect(screen.queryByText(oneTimeLink)).not.toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "一次性邀请链接" })).not.toBeInTheDocument();
  });

  it("blocks a second mutation while a one-time link awaits dismissal", async () => {
    const user = userEvent.setup();
    const client = onboardingClient({
      createInvite: vi.fn().mockResolvedValue({
        invite: {
          id: "guarded-invite-private",
          role: "store_manager",
          display_name: "王店长",
          expires_at: "2026-07-15T10:00:00Z",
        },
        one_time_link: "https://hxy.example/#invite=guarded-private-link",
      }),
    });
    renderPanel(FOUNDER, client);
    await screen.findByText("荷小悦一店");
    await user.click(screen.getByRole("button", { name: "邀请店长" }));
    await user.type(screen.getByRole("textbox", { name: "成员姓名" }), "王店长");
    await user.click(screen.getByRole("button", { name: "生成邀请" }));
    await screen.findByText(/guarded-private-link/);
    await screen.findByText("待入职店长");

    expect(screen.getByRole("button", { name: "新建门店" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "邀请店长" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "撤销待入职店长的邀请" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "停用李店长" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "邀请店长" }));
    expect(client.createInvite).toHaveBeenCalledOnce();

    await user.click(
      screen.getByRole("button", { name: "关闭一次性邀请链接" }),
    );
    expect(screen.getByRole("button", { name: "邀请店长" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeEnabled();
  });

  it("invites an employee without sending a store selector and bounds copy failure", async () => {
    const user = userEvent.setup();
    const oneTimeLink = "https://hxy.example/#invite=employee-private-link";
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    const client = onboardingClient({
      createInvite: vi.fn().mockResolvedValue({
        invite: {
          id: "created-employee-invite-private",
          role: "store_employee",
          display_name: "新员工",
          expires_at: "2026-07-15T10:00:00Z",
        },
        one_time_link: oneTimeLink,
      }),
    });
    renderPanel(MANAGER, client);
    await screen.findByText("陈员工");

    await user.click(screen.getByRole("button", { name: "邀请员工" }));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "成员姓名" }), "新员工");
    await user.click(screen.getByRole("button", { name: "生成邀请" }));

    expect(client.createInvite).toHaveBeenCalledWith({
      role: "store_employee",
      display_name: "新员工",
    });
    await user.click(await screen.findByRole("button", { name: "复制一次性邀请链接" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("链接没有复制，请重试");
  });

  it("requires confirmation before revoke and restores focus on Escape", async () => {
    const user = userEvent.setup();
    const revoke = deferred<OrganizationInvite>();
    const client = onboardingClient({
      revokeInvite: vi.fn(() => revoke.promise),
      listInvites: vi
        .fn()
        .mockResolvedValueOnce([PENDING_INVITE])
        .mockResolvedValueOnce([]),
    });
    renderPanel(FOUNDER, client);
    const shell = screen.getByTestId("app-shell");
    const trigger = await screen.findByRole("button", { name: "撤销待入职店长的邀请" });

    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "撤销邀请" });
    expect(client.revokeInvite).not.toHaveBeenCalled();
    expect(dialog.closest(".app-shell")).toBeNull();
    expect(shell).toHaveAttribute("inert");
    expect(screen.getByRole("button", { name: "取消" })).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(shell).not.toHaveAttribute("inert");
    expect(client.revokeInvite).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "继续撤销" }));
    expect(client.revokeInvite).toHaveBeenCalledWith(PENDING_INVITE.id);
    expect(screen.getByRole("button", { name: "正在撤销" })).toBeDisabled();
    const pendingDialog = screen.getByRole("dialog", { name: "撤销邀请" });
    await waitFor(() => expect(pendingDialog).toHaveFocus());
    fireEvent.keyDown(pendingDialog, { key: "Tab" });
    expect(pendingDialog).toHaveFocus();
    fireEvent.keyDown(pendingDialog, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "撤销邀请" })).toBeVisible();
    expect(shell).toHaveAttribute("inert");
    await act(async () => revoke.resolve({ ...PENDING_INVITE, status: "revoked" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(shell).not.toHaveAttribute("inert");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "邀请店长" })).toHaveFocus(),
    );
    expect(client.listInvites).toHaveBeenCalledTimes(2);
  });

  it("requires confirmation before deactivation and honors cancel", async () => {
    const user = userEvent.setup();
    const client = onboardingClient();
    renderPanel(FOUNDER, client);
    await screen.findByText("李店长");

    const trigger = screen.getByRole("button", { name: "停用李店长" });
    await user.click(trigger);
    expect(client.deactivateMember).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "取消" }));
    expect(client.deactivateMember).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
    expect(screen.getByTestId("app-shell")).not.toHaveAttribute("inert");

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "确认停用" }));
    expect(client.deactivateMember).toHaveBeenCalledWith(MEMBERS[1].assignment_id);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(client.listMembers).toHaveBeenCalledTimes(2);
  });

  it("restores an app shell that was already inert before the dialog", async () => {
    const client = onboardingClient();
    renderPanel(FOUNDER, client);
    const shell = screen.getByTestId("app-shell");
    const trigger = await screen.findByRole("button", {
      name: "撤销待入职店长的邀请",
    });
    shell.setAttribute("inert", "existing");

    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "撤销邀请" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(shell).toHaveAttribute("inert", "existing");
  });

  it("uses the new role fallback when a scope change closes the dialog", async () => {
    const user = userEvent.setup();
    const client = onboardingClient();
    const logout = vi.fn().mockResolvedValue(undefined);
    const onLoggedOut = vi.fn();
    const view = render(
      <div className="app-shell">
        <OrganizationPanel
          active
          user={USER}
          assignment={FOUNDER}
          client={client}
          logout={logout}
          onLoggedOut={onLoggedOut}
        />
      </div>,
    );
    await user.click(
      await screen.findByRole("button", {
        name: "撤销待入职店长的邀请",
      }),
    );
    expect(screen.getByRole("dialog", { name: "撤销邀请" })).toBeVisible();

    view.rerender(
      <div className="app-shell">
        <OrganizationPanel
          active
          user={USER}
          assignment={MANAGER}
          client={client}
          logout={logout}
          onLoggedOut={onLoggedOut}
        />
      </div>,
    );

    expect(await screen.findByRole("button", { name: "邀请员工" })).toBeEnabled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "邀请员工" })).toHaveFocus(),
    );
  });

  it("closes a failed confirmation and returns focus to its trigger", async () => {
    const user = userEvent.setup();
    const client = onboardingClient({
      revokeInvite: vi.fn().mockRejectedValue(new Error("offline")),
    });
    renderPanel(FOUNDER, client);
    const trigger = await screen.findByRole("button", {
      name: "撤销待入职店长的邀请",
    });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "撤销邀请" });

    await user.click(within(dialog).getByRole("button", { name: "继续撤销" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "操作没有完成，请重试",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("app-shell")).not.toHaveAttribute("inert");
    expect(trigger).toHaveFocus();
  });

  it("shows bounded loading, error, retry, and empty states", async () => {
    const user = userEvent.setup();
    const stores = deferred<OrganizationStore[]>();
    const client = onboardingClient({
      listStores: vi.fn().mockImplementationOnce(() => stores.promise).mockResolvedValueOnce([]),
      listMembers: vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce([]),
      listInvites: vi.fn().mockResolvedValue([]),
    });
    renderPanel(FOUNDER, client);

    expect(screen.getByRole("status")).toHaveTextContent("正在加载门店与成员");
    await act(async () => stores.resolve([]));
    expect(await screen.findByRole("alert")).toHaveTextContent("门店与成员没有加载完成");
    await user.click(screen.getByRole("button", { name: "重试" }));

    expect(await screen.findByText("还没有门店")).toBeVisible();
    expect(screen.getByText("还没有成员")).toBeVisible();
    expect(screen.getByText("没有待处理邀请")).toBeVisible();
    expect(client.listStores).toHaveBeenCalledTimes(2);
    expect(client.listMembers).toHaveBeenCalledTimes(2);
    expect(client.listInvites).toHaveBeenCalledTimes(2);
  });

  it("ignores stale founder responses after the active role changes", async () => {
    const founderStores = deferred<OrganizationStore[]>();
    const founderMembers = deferred<OrganizationMember[]>();
    const founderInvites = deferred<OrganizationInvite[]>();
    const managerMember = { ...MEMBERS[2], display_name: "当前门店员工" };
    const client = onboardingClient({
      listStores: vi.fn(() => founderStores.promise),
      listMembers: vi
        .fn()
        .mockImplementationOnce(() => founderMembers.promise)
        .mockResolvedValueOnce([managerMember]),
      listInvites: vi
        .fn()
        .mockImplementationOnce(() => founderInvites.promise)
        .mockResolvedValueOnce([]),
    });
    const view = renderPanel(FOUNDER, client);

    view.rerender(
      <OrganizationPanel
        active
        user={USER}
        assignment={MANAGER}
        client={client}
        logout={view.logout}
        onLoggedOut={view.onLoggedOut}
      />,
    );
    expect(await screen.findByText("当前门店员工")).toBeVisible();

    await act(async () => {
      founderStores.resolve([{ ...STORES[0], name: "旧门店" }]);
      founderMembers.resolve([{ ...MEMBERS[1], display_name: "旧店长" }]);
      founderInvites.resolve([PENDING_INVITE]);
    });
    expect(screen.queryByText("旧门店")).not.toBeInTheDocument();
    expect(screen.queryByText("旧店长")).not.toBeInTheDocument();
    expect(screen.getByText("当前门店员工")).toBeVisible();
  });

  it("ignores an invite result after switching away and back to a role", async () => {
    const user = userEvent.setup();
    const invite = deferred<Awaited<ReturnType<OnboardingClient["createInvite"]>>>();
    const client = onboardingClient({
      createInvite: vi.fn(() => invite.promise),
    });
    const view = renderPanel(FOUNDER, client);
    await screen.findByText("荷小悦一店");
    await user.click(screen.getByRole("button", { name: "邀请店长" }));
    await user.type(screen.getByRole("textbox", { name: "成员姓名" }), "旧请求店长");
    await user.click(screen.getByRole("button", { name: "生成邀请" }));

    view.rerender(
      <OrganizationPanel
        active
        user={USER}
        assignment={MANAGER}
        client={client}
        logout={view.logout}
        onLoggedOut={view.onLoggedOut}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "邀请员工" })).toBeEnabled(),
    );
    view.rerender(
      <OrganizationPanel
        active
        user={USER}
        assignment={FOUNDER}
        client={client}
        logout={view.logout}
        onLoggedOut={view.onLoggedOut}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "邀请店长" })).toBeEnabled(),
    );

    await act(async () =>
      invite.resolve({
        invite: {
          id: "stale-invite-private",
          role: "store_manager",
          display_name: "旧请求店长",
          expires_at: "2026-07-15T10:00:00Z",
        },
        one_time_link: "https://hxy.example/#invite=stale-private-link",
      }),
    );

    expect(screen.queryByText(/stale-private-link/)).not.toBeInTheDocument();
  });

  it("disables logout while pending and recovers from a bounded failure", async () => {
    const user = userEvent.setup();
    const logout = deferred<void>();
    renderPanel(EMPLOYEE, onboardingClient(), vi.fn(() => logout.promise));

    await user.click(screen.getByRole("button", { name: "退出登录" }));
    expect(screen.getByRole("button", { name: "正在退出" })).toBeDisabled();
    await act(async () => logout.reject(new Error("offline")));
    expect(await screen.findByRole("alert")).toHaveTextContent("没有退出，请重试");
    expect(screen.getByRole("button", { name: "退出登录" })).toBeEnabled();
  });
});
