import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
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
  user: UserContext;
  assignment: AssignmentContext;
  client: OnboardingClient;
  logout: () => Promise<void>;
  onLoggedOut: () => void;
}

type DataStatus = "idle" | "loading" | "ready" | "error";
type OpenForm = "store" | "invite" | null;
type Confirmation =
  | { kind: "revoke"; id: string; name: string }
  | { kind: "deactivate"; id: string; name: string };

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
  const [isCreatingStore, setIsCreatingStore] = useState(false);
  const [isCreatingInvite, setIsCreatingInvite] = useState(false);
  const [mutationFailed, setMutationFailed] = useState(false);
  const [oneTimeLink, setOneTimeLink] = useState<string | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);
  const scopeRef = useRef(scope);
  const scopeGenerationRef = useRef({ scope, generation: 0 });
  const mountedRef = useRef(false);
  const confirmationTriggerRef = useRef<HTMLButtonElement | null>(null);
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
    setIsCreatingStore(false);
    setIsCreatingInvite(false);
    setMutationFailed(false);
    setOneTimeLink(null);
    setCopyFailed(false);
    setCopied(false);
    setConfirmation(null);
    setIsConfirming(false);
  }, [scope]);

  useEffect(() => {
    if (!canManage) {
      setData(emptyData(scope, "idle"));
      return;
    }

    let active = true;
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
        if (!active) return;
        setData({ scope, status: "ready", stores, members, invites });
      },
      () => {
        if (active) setData(emptyData(scope, "error"));
      },
    );

    return () => {
      active = false;
    };
  }, [canManage, client, isFounder, refreshVersion, scope]);

  useEffect(() => {
    if (confirmation) cancelRef.current?.focus();
  }, [confirmation]);

  const refreshData = () => setRefreshVersion((current) => current + 1);
  const requestIsCurrent = (requestScope: string, generation: number) =>
    mountedRef.current &&
    scopeRef.current === requestScope &&
    scopeGenerationRef.current.generation === generation;

  const openStoreForm = () => {
    setOpenForm("store");
    setMutationFailed(false);
  };

  const openInviteForm = () => {
    setInviteStoreId(invitableStores[0]?.id ?? "");
    setOpenForm("invite");
    setMutationFailed(false);
  };

  const closeForm = () => {
    if (isCreatingStore || isCreatingInvite) return;
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
    if (!request.name || !request.city || !request.address) return;

    setIsCreatingStore(true);
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
        setIsCreatingStore(false);
      }
    }
  };

  const submitInvite = async (event: FormEvent) => {
    event.preventDefault();
    const displayName = inviteName.trim();
    const requestScope = scope;
    const requestGeneration = scopeGenerationRef.current.generation;
    if (!displayName) return;
    if (isFounder && !invitableStores.some((store) => store.id === inviteStoreId)) {
      return;
    }

    setIsCreatingInvite(true);
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
        setIsCreatingInvite(false);
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
    confirmationTriggerRef.current = trigger;
    setMutationFailed(false);
    setConfirmation(nextConfirmation);
  };

  const closeConfirmation = () => {
    if (isConfirming) return;
    const trigger = confirmationTriggerRef.current;
    setConfirmation(null);
    trigger?.focus();
  };

  const handleDialogKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeConfirmation();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
      ) ?? [],
    );
    if (focusable.length === 0) return;
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
    if (!confirmation) return;
    const requestScope = scope;
    const requestGeneration = scopeGenerationRef.current.generation;
    const currentConfirmation = confirmation;
    setIsConfirming(true);
    setMutationFailed(false);
    try {
      if (currentConfirmation.kind === "revoke") {
        await client.revokeInvite(currentConfirmation.id);
      } else {
        await client.deactivateMember(currentConfirmation.id);
      }
      if (!requestIsCurrent(requestScope, requestGeneration)) return;
      setConfirmation(null);
      refreshData();
    } catch {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setMutationFailed(true);
      }
    } finally {
      if (requestIsCurrent(requestScope, requestGeneration)) {
        setIsConfirming(false);
      }
    }
  };

  const handleLogout = async () => {
    setIsLoggingOut(true);
    setLogoutFailed(false);
    try {
      await logout();
      onLoggedOut();
    } catch {
      setLogoutFailed(true);
      setIsLoggingOut(false);
    }
  };

  const storeName = (storeId: string) =>
    visibleStores.find((store) => store.id === storeId)?.name ??
    assignment.store?.name ??
    "当前门店";

  return (
    <div className="organization-panel">
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
                <button type="button" onClick={openStoreForm}>
                  <Plus aria-hidden="true" />
                  新建门店
                </button>
              ) : null}
              <button
                type="button"
                disabled={
                  scopedData.status !== "ready" ||
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
                <button type="button" disabled={isCreatingStore} onClick={closeForm}>
                  取消
                </button>
                <button
                  type="submit"
                  disabled={
                    isCreatingStore ||
                    !storeDraft.name.trim() ||
                    !storeDraft.city.trim() ||
                    !storeDraft.address.trim()
                  }
                >
                  {isCreatingStore ? "正在创建" : "创建门店"}
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
                <button type="button" disabled={isCreatingInvite} onClick={closeForm}>
                  取消
                </button>
                <button
                  type="submit"
                  disabled={
                    isCreatingInvite ||
                    !inviteName.trim() ||
                    (isFounder && !invitableStores.some((store) => store.id === inviteStoreId))
                  }
                >
                  {isCreatingInvite ? "正在生成" : "生成邀请"}
                </button>
              </div>
            </form>
          ) : null}

          {oneTimeLink ? (
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
          className="organization-logout"
          type="button"
          disabled={isLoggingOut}
          onClick={() => void handleLogout()}
        >
          <LogOut aria-hidden="true" />
          {isLoggingOut ? "正在退出" : "退出登录"}
        </button>
        {logoutFailed ? <p role="alert">没有退出，请重试</p> : null}
      </footer>

      {confirmation ? (
        <div className="organization-dialog-backdrop">
          <div
            ref={dialogRef}
            className="organization-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={dialogHeadingId}
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
            {mutationFailed ? (
              <p className="organization-alert" role="alert">
                操作没有完成，请重试
              </p>
            ) : null}
            <div className="organization-dialog-actions">
              <button
                ref={cancelRef}
                type="button"
                disabled={isConfirming}
                onClick={closeConfirmation}
              >
                取消
              </button>
              <button
                type="button"
                disabled={isConfirming}
                onClick={() => void confirmMutation()}
              >
                {confirmation.kind === "revoke"
                  ? isConfirming ? "正在撤销" : "继续撤销"
                  : isConfirming ? "正在停用" : "确认停用"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
