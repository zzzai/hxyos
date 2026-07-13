import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  Copy,
  LogOut,
  Plus,
  Store,
  Trash2,
  UserMinus,
  UserPlus,
  X,
} from "lucide-react";

import type {
  AssignmentContext,
  OnboardingClient,
  OrganizationInvite,
  OrganizationMember,
  OrganizationStore,
  UserContext,
} from "../../api/client";

interface OrganizationPanelProps {
  active: boolean;
  user: UserContext;
  assignment: AssignmentContext;
  client: OnboardingClient;
  logout: () => Promise<void>;
  onLoggedOut: () => void;
}

type DataStatus = "idle" | "loading" | "ready" | "error";
type OpenForm = "store" | "invite" | null;
type BusyAction =
  | "create-store"
  | "create-invite"
  | "confirm"
  | "logout"
  | null;
type Confirmation =
  | { kind: "revoke"; id: string; name: string }
  | { kind: "deactivate"; id: string; name: string };
type FocusRestoreMode = "trigger" | "fallback";

interface OrganizationData {
  scope: string;
  status: DataStatus;
  stores: OrganizationStore[];
  members: OrganizationMember[];
  invites: OrganizationInvite[];
}

function emptyData(scope: string, status: DataStatus): OrganizationData {
  return { scope, status, stores: [], members: [], invites: [] };
}

function roleName(role: OrganizationMember["role"]) {
  return role === "store_manager" ? "店长" : "门店员工";
}

export function OrganizationPanel({
  active,
  user,
  assignment,
  client,
  logout,
  onLoggedOut,
}: OrganizationPanelProps) {
  const identityHeadingId = useId();
  const dialogHeadingId = useId();
  const isFounder = assignment.role === "founder";
  const isManager = assignment.role === "store_manager";
  const canManage = isFounder || isManager;
  const scope = `${assignment.assignment_id}:${assignment.role}`;
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [data, setData] = useState<OrganizationData>(() =>
    emptyData(scope, canManage ? "loading" : "idle"),
  );
  const [openForm, setOpenForm] = useState<OpenForm>(null);
  const [storeDraft, setStoreDraft] = useState({
    name: "",
    city: "",
    address: "",
  });
  const [inviteName, setInviteName] = useState("");
  const [inviteStoreId, setInviteStoreId] = useState("");
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [mutationFailed, setMutationFailed] = useState(false);
  const [oneTimeLink, setOneTimeLink] = useState<string | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [logoutFailed, setLogoutFailed] = useState(false);
  const scopeRef = useRef(scope);
  const scopeGenerationRef = useRef({ scope, generation: 0 });
  const mountedRef = useRef(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const confirmationTriggerRef = useRef<HTMLButtonElement | null>(null);
  const focusRestoreModeRef = useRef<FocusRestoreMode | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  scopeRef.current = scope;
  if (scopeGenerationRef.current.scope !== scope) {
    scopeGenerationRef.current = {
      scope,
      generation: scopeGenerationRef.current.generation + 1,
    };
  }

  const scopedData = data.scope === scope
    ? data
    : emptyData(scope, canManage ? "loading" : "idle");
  const visibleStores = scopedData.stores;
  const invitableStores = visibleStores.filter(
    (store) => store.status === "active",
  );
  const isBusy = busyAction !== null;
  const interactionsBlocked = isBusy || oneTimeLink !== null;
  const visibleMembers = isManager && assignment.store
    ? scopedData.members.filter(
        (member) => member.store_id === assignment.store?.id,
      )
    : scopedData.members;
  const visibleInvites = scopedData.invites.filter(
    (invite) =>
      invite.status === "pending" &&
      (isFounder
        ? invite.role === "store_manager"
        : invite.role === "store_employee" &&
          invite.store_id === assignment.store?.id),
  );
  const dialogOpen = confirmation !== null;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setOpenForm(null);
    setStoreDraft({ name: "", city: "", address: "" });
    setInviteName("");
    setInviteStoreId("");
    setBusyAction(null);
    setMutationFailed(false);
    setOneTimeLink(null);
    setCopyFailed(false);
    setCopied(false);
    if (confirmation !== null) focusRestoreModeRef.current = "fallback";
    setConfirmation(null);
  }, [scope]);

  useEffect(() => {
    if (!canManage && active) {
      setData(emptyData(scope, "idle"));
      return;
    }
    if (!active) return;

    let requestActive = true;
    setData(emptyData(scope, "loading"));
    const storesRequest = isFounder
      ? client.listStores()
      : Promise.resolve<OrganizationStore[]>([]);

    void Promise.all([
      storesRequest,
      client.listMembers(),
      client.listInvites(),
    ]).then(
      ([stores, members, invites]) => {
        if (!requestActive) return;
        setData({ scope, status: "ready", stores, members, invites });
      },
      () => {
        if (requestActive) setData(emptyData(scope, "error"));
      },
    );

    return () => {
      requestActive = false;
    };
  }, [active, canManage, client, isFounder, refreshVersion, scope]);

  useLayoutEffect(() => {
    if (!dialogOpen) return;
    const shell = panelRef.current?.closest<HTMLElement>(".app-shell");
    if (!shell) return;
    const previousInert = shell.getAttribute("inert");
    shell.setAttribute("inert", "");
    return () => {
      if (previousInert === null) shell.removeAttribute("inert");
      else shell.setAttribute("inert", previousInert);
    };
  }, [dialogOpen]);

  useLayoutEffect(() => {
    if (!dialogOpen) return;
    if (busyAction === "confirm") {
      dialogRef.current?.focus();
      return;
    }
    if (!dialogRef.current?.contains(document.activeElement)) {
      (cancelRef.current ?? dialogRef.current)?.focus();
    }
  }, [busyAction, dialogOpen]);

  useLayoutEffect(() => {
    if (dialogOpen || focusRestoreModeRef.current === null) return;
    const mode = focusRestoreModeRef.current;
    const trigger = confirmationTriggerRef.current;
    const primaryFallback = panelRef.current?.querySelector<HTMLButtonElement>(
      '[data-organization-focus-fallback="primary"]',
    );
    const secondaryFallback = panelRef.current?.querySelector<HTMLButtonElement>(
      '[data-organization-focus-fallback="secondary"]:not(:disabled)',
    );
    const fallback = primaryFallback
      ? primaryFallback.disabled ? null : primaryFallback
      : secondaryFallback;
    const target = mode === "trigger" && trigger?.isConnected
      ? trigger
      : fallback;
    if (!target) return;
    focusRestoreModeRef.current = null;
    target.focus();
  }, [busyAction, dialogOpen, scope, scopedData.status]);

  const refreshData = () => setRefreshVersion((current) => current + 1);
  const requestIsCurrent = (requestScope: string, generation: number) =>
    mountedRef.current &&
    scopeRef.current === requestScope &&
    scopeGenerationRef.current.generation === generation;

  const openStoreForm = () => {
    if (interactionsBlocked) return;
    setOpenForm("store");
    setMutationFailed(false);
  };

  const openInviteForm = () => {
    if (interactionsBlocked) return;
    setInviteStoreId(invitableStores[0]?.id ?? "");
    setOpenForm("invite");
    setMutationFailed(false);
  };

  const closeForm = () => {
    if (isBusy) return;
    setOpenForm(null);
    setMutationFailed(false);
  };

  const submitStore = async (event: FormEvent) => {
    event.preventDefault();
    const requestScope = scope;
    const requestGeneration = scopeGenerationRef.current.generation;
    const request = {
      name: storeDraft.name.trim(),
      city: storeDraft.city.trim(),
      address: storeDraft.address.trim(),
    };
    if (
      interactionsBlocked ||
      !request.name ||
      !request.city ||
      !request.address
    ) {
      return;
    }

    setBusyAction("create-store");
    setMutationFailed(false);
    try {
      await client.createStore(request);
      if (!requestIsCurrent(requestScope, requestGeneration)) return;
      setStoreDraft({ name: "", city: "", address: "" });
      setOpenForm(null);
      refreshData();
    } catch {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setMutationFailed(true);
      }
    } finally {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setBusyAction(null);
      }
    }
  };

  const submitInvite = async (event: FormEvent) => {
    event.preventDefault();
    const displayName = inviteName.trim();
    const requestScope = scope;
    const requestGeneration = scopeGenerationRef.current.generation;
    if (interactionsBlocked || !displayName) return;
    if (isFounder && !invitableStores.some((store) => store.id === inviteStoreId)) {
      return;
    }

    setBusyAction("create-invite");
    setMutationFailed(false);
    setCopyFailed(false);
    setCopied(false);
    try {
      const result = await client.createInvite({
        ...(isFounder ? { store_id: inviteStoreId } : {}),
        role: isFounder ? "store_manager" : "store_employee",
        display_name: displayName,
      });
      if (!requestIsCurrent(requestScope, requestGeneration)) return;
      setInviteName("");
      setOpenForm(null);
      setOneTimeLink(result.one_time_link);
      refreshData();
    } catch {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setMutationFailed(true);
      }
    } finally {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setBusyAction(null);
      }
    }
  };

  const copyInviteLink = async () => {
    if (!oneTimeLink) return;
    setCopyFailed(false);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(oneTimeLink);
      setCopied(true);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  };

  const dismissInviteLink = () => {
    setOneTimeLink(null);
    setCopied(false);
    setCopyFailed(false);
  };

  const openConfirmation = (
    nextConfirmation: Confirmation,
    trigger: HTMLButtonElement,
  ) => {
    if (interactionsBlocked) return;
    confirmationTriggerRef.current = trigger;
    focusRestoreModeRef.current = null;
    setMutationFailed(false);
    setConfirmation(nextConfirmation);
  };

  const finishConfirmation = (mode: FocusRestoreMode) => {
    focusRestoreModeRef.current = mode;
    setConfirmation(null);
  };

  const closeConfirmation = () => {
    if (busyAction === "confirm") return;
    finishConfirmation("trigger");
  };

  const handleDialogKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      if (busyAction === "confirm") return;
      closeConfirmation();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
      ) ?? [],
    );
    if (focusable.length === 0) {
      event.preventDefault();
      dialogRef.current?.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      (event.shiftKey && document.activeElement === first) ||
      (!event.shiftKey && document.activeElement === last)
    ) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  };

  const confirmMutation = async () => {
    if (!confirmation || interactionsBlocked) return;
    const requestScope = scope;
    const requestGeneration = scopeGenerationRef.current.generation;
    const currentConfirmation = confirmation;
    setBusyAction("confirm");
    setMutationFailed(false);
    try {
      if (currentConfirmation.kind === "revoke") {
        await client.revokeInvite(currentConfirmation.id);
      } else {
        await client.deactivateMember(currentConfirmation.id);
      }
      if (!requestIsCurrent(requestScope, requestGeneration)) return;
      finishConfirmation("fallback");
      refreshData();
    } catch {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setMutationFailed(true);
        finishConfirmation("trigger");
      }
    } finally {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setBusyAction(null);
      }
    }
  };

  const handleLogout = async () => {
    if (interactionsBlocked) return;
    setBusyAction("logout");
    setLogoutFailed(false);
    try {
      await logout();
      onLoggedOut();
    } catch {
      setLogoutFailed(true);
      setBusyAction(null);
    }
  };

  const storeName = (storeId: string) =>
    visibleStores.find((store) => store.id === storeId)?.name ??
    assignment.store?.name ??
    "当前门店";

  return (
    <div ref={panelRef} className="organization-panel" hidden={!active}>
      <section
        className="organization-identity"
        aria-labelledby={identityHeadingId}
      >
        <h1 id={identityHeadingId}>{user.display_name}</h1>
        <div className="organization-identity-meta">
          <span>{assignment.role_label}</span>
          <span aria-hidden="true">/</span>
          <span>{assignment.store?.name ?? assignment.organization.name}</span>
        </div>
      </section>

      {canManage ? (
        <section className="organization-management" aria-labelledby="management-heading">
          <div className="organization-section-heading">
            <h2 id="management-heading">门店与成员</h2>
            <div className="organization-actions">
              {isFounder ? (
                <button
                  type="button"
                  disabled={interactionsBlocked}
                  onClick={openStoreForm}
                >
                  <Plus aria-hidden="true" />
                  新建门店
                </button>
              ) : null}
              <button
                data-organization-focus-fallback="primary"
                type="button"
                disabled={
                  scopedData.status !== "ready" ||
                  interactionsBlocked ||
                  (isFounder && invitableStores.length === 0)
                }
                onClick={openInviteForm}
              >
                <UserPlus aria-hidden="true" />
                {isFounder ? "邀请店长" : "邀请员工"}
              </button>
            </div>
          </div>

          {openForm === "store" ? (
            <form className="organization-form" onSubmit={(event) => void submitStore(event)}>
              <label>
                门店名称
                <input
                  aria-label="门店名称"
                  value={storeDraft.name}
                  onChange={(event) =>
                    setStoreDraft((current) => ({ ...current, name: event.target.value }))
                  }
                />
              </label>
              <label>
                城市
                <input
                  aria-label="城市"
                  value={storeDraft.city}
                  onChange={(event) =>
                    setStoreDraft((current) => ({ ...current, city: event.target.value }))
                  }
                />
              </label>
              <label className="organization-form-wide">
                地址
                <input
                  aria-label="地址"
                  value={storeDraft.address}
                  onChange={(event) =>
                    setStoreDraft((current) => ({ ...current, address: event.target.value }))
                  }
                />
              </label>
              <div className="organization-form-actions organization-form-wide">
                <button type="button" disabled={isBusy} onClick={closeForm}>
                  取消
                </button>
                <button
                  type="submit"
                  disabled={
                    isBusy ||
                    !storeDraft.name.trim() ||
                    !storeDraft.city.trim() ||
                    !storeDraft.address.trim()
                  }
                >
                  {busyAction === "create-store" ? "正在创建" : "创建门店"}
                </button>
              </div>
            </form>
          ) : null}

          {openForm === "invite" ? (
            <form
              className="organization-form organization-invite-form"
              onSubmit={(event) => void submitInvite(event)}
            >
              {isFounder ? (
                <label>
                  邀请门店
                  <select
                    aria-label="邀请门店"
                    value={inviteStoreId}
                    onChange={(event) => setInviteStoreId(event.target.value)}
                  >
                    {invitableStores.map((store) => (
                      <option key={store.id} value={store.id}>
                        {store.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label>
                成员姓名
                <input
                  aria-label="成员姓名"
                  value={inviteName}
                  onChange={(event) => setInviteName(event.target.value)}
                />
              </label>
              <div className="organization-form-actions">
                <button type="button" disabled={isBusy} onClick={closeForm}>
                  取消
                </button>
                <button
                  type="submit"
                  disabled={
                    isBusy ||
                    !inviteName.trim() ||
                    (isFounder && !invitableStores.some((store) => store.id === inviteStoreId))
                  }
                >
                  {busyAction === "create-invite" ? "正在生成" : "生成邀请"}
                </button>
              </div>
            </form>
          ) : null}

          {active && oneTimeLink ? (
            <div
              className="invite-link-result"
              role="status"
              aria-label="一次性邀请链接"
            >
              <div>
                <strong>一次性邀请链接</strong>
                <code>{oneTimeLink}</code>
              </div>
              {copied ? <span>已复制</span> : null}
              <button
                className="organization-icon-button"
                type="button"
                aria-label="复制一次性邀请链接"
                title="复制一次性邀请链接"
                onClick={() => void copyInviteLink()}
              >
                <Copy aria-hidden="true" />
              </button>
              <button
                className="organization-icon-button"
                type="button"
                aria-label="关闭一次性邀请链接"
                title="关闭一次性邀请链接"
                onClick={dismissInviteLink}
              >
                <X aria-hidden="true" />
              </button>
            </div>
          ) : null}
          {copyFailed ? (
            <p className="organization-alert" role="alert">
              链接没有复制，请重试
            </p>
          ) : null}
          {mutationFailed && !confirmation ? (
            <p className="organization-alert" role="alert">
              操作没有完成，请重试
            </p>
          ) : null}

          {scopedData.status === "loading" ? (
            <div className="organization-loading" role="status">
              <span aria-hidden="true" />
              <span aria-hidden="true" />
              <span>正在加载门店与成员</span>
            </div>
          ) : scopedData.status === "error" ? (
            <div className="organization-load-error" role="alert">
              <span>门店与成员没有加载完成</span>
              <button type="button" onClick={refreshData}>重试</button>
            </div>
          ) : scopedData.status === "ready" ? (
            <div className="organization-data">
              {isFounder ? (
                <section className="organization-list-section" aria-labelledby="stores-heading">
                  <h3 id="stores-heading">门店</h3>
                  {visibleStores.length === 0 ? (
                    <p className="organization-empty">还没有门店</p>
                  ) : (
                    <ul className="organization-list">
                      {visibleStores.map((store) => (
                        <li className="organization-row organization-store-row" key={store.id}>
                          <Store aria-hidden="true" />
                          <div>
                            <strong>{store.name}</strong>
                            <span>{store.city} · {store.address}</span>
                          </div>
                          {store.status === "paused" ? <span>已暂停</span> : null}
                          {store.status === "closed" ? <span>已关闭</span> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ) : null}

              <section className="organization-list-section" aria-labelledby="members-heading">
                <h3 id="members-heading">成员</h3>
                {visibleMembers.length === 0 ? (
                  <p className="organization-empty">还没有成员</p>
                ) : (
                  <ul className="organization-list">
                    {visibleMembers.map((member) => {
                      const canDeactivate =
                        member.status === "active" &&
                        member.assignment_id !== assignment.assignment_id &&
                        ((isFounder && member.role === "store_manager") ||
                          (isManager && member.role === "store_employee"));
                      return (
                        <li className="organization-row" key={member.assignment_id}>
                          <div>
                            <strong>{member.display_name}</strong>
                            <span>
                              {roleName(member.role)}
                              {isFounder ? ` · ${storeName(member.store_id)}` : ""}
                              {member.status === "inactive" ? " · 已停用" : ""}
                            </span>
                          </div>
                          {canDeactivate ? (
                            <button
                              className="organization-icon-button"
                              type="button"
                              disabled={interactionsBlocked}
                              aria-label={`停用${member.display_name}`}
                              title={`停用${member.display_name}`}
                              onClick={(event) =>
                                openConfirmation(
                                  {
                                    kind: "deactivate",
                                    id: member.assignment_id,
                                    name: member.display_name,
                                  },
                                  event.currentTarget,
                                )
                              }
                            >
                              <UserMinus aria-hidden="true" />
                            </button>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>

              <section className="organization-list-section" aria-labelledby="invites-heading">
                <h3 id="invites-heading">待处理邀请</h3>
                {visibleInvites.length === 0 ? (
                  <p className="organization-empty">没有待处理邀请</p>
                ) : (
                  <ul className="organization-list">
                    {visibleInvites.map((invite) => (
                      <li className="organization-row" key={invite.id}>
                        <div>
                          <strong>{invite.display_name}</strong>
                          <span>
                            {roleName(invite.role)}
                            {isFounder ? ` · ${storeName(invite.store_id)}` : ""}
                          </span>
                        </div>
                        <button
                          className="organization-icon-button"
                          type="button"
                          disabled={interactionsBlocked}
                          aria-label={`撤销${invite.display_name}的邀请`}
                          title={`撤销${invite.display_name}的邀请`}
                          onClick={(event) =>
                            openConfirmation(
                              { kind: "revoke", id: invite.id, name: invite.display_name },
                              event.currentTarget,
                            )
                          }
                        >
                          <Trash2 aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          ) : null}
        </section>
      ) : null}

      <footer className="organization-footer">
        <button
          data-organization-focus-fallback="secondary"
          className="organization-logout"
          type="button"
          disabled={interactionsBlocked}
          onClick={() => void handleLogout()}
        >
          <LogOut aria-hidden="true" />
          {busyAction === "logout" ? "正在退出" : "退出登录"}
        </button>
        {logoutFailed ? <p role="alert">没有退出，请重试</p> : null}
      </footer>

      {confirmation ? createPortal(
        <div className="organization-dialog-backdrop">
          <div
            ref={dialogRef}
            className="organization-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={dialogHeadingId}
            tabIndex={-1}
            onKeyDown={handleDialogKeyDown}
          >
            <h2 id={dialogHeadingId}>
              {confirmation.kind === "revoke" ? "撤销邀请" : "停用成员"}
            </h2>
            <p>
              {confirmation.kind === "revoke"
                ? `撤销 ${confirmation.name} 的邀请？`
                : `停用 ${confirmation.name}？`}
            </p>
            <div className="organization-dialog-actions">
              <button
                ref={cancelRef}
                type="button"
                disabled={busyAction === "confirm"}
                onClick={closeConfirmation}
              >
                取消
              </button>
              <button
                type="button"
                disabled={busyAction === "confirm"}
                onClick={() => void confirmMutation()}
              >
                {confirmation.kind === "revoke"
                  ? busyAction === "confirm" ? "正在撤销" : "继续撤销"
                  : busyAction === "confirm" ? "正在停用" : "确认停用"}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
