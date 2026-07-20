import { useCallback, useEffect, useRef, useState } from "react";

import type { OnboardingClient } from "../../api/client";
import {
  type ConversationClient,
  type ConversationMessage,
  type ConversationSummary,
} from "../../api/conversations";
import type { MaterialClient } from "../../api/materials";
import type { LearningClient } from "../../api/learning";
import {
  type OrganizationRecord,
  type OrganizationRecordClient,
} from "../../api/records";
import type { TodayBriefItem, TodayClient } from "../../api/today";
import { UniversalComposer } from "../composer/UniversalComposer";
import { ConversationView } from "../conversation/ConversationView";
import { OrganizationPanel } from "../onboarding/OrganizationPanel";
import { LearningView } from "../learning/LearningView";
import { RecordDetail } from "../records/RecordDetail";
import { RecordsView } from "../records/RecordsView";
import { useSession } from "../session/SessionProvider";
import { TodayView } from "../today/TodayView";
import { Navigation, type FrontstageView } from "./Navigation";

type LoadStatus = "loading" | "ready" | "error";
type ConversationStatus = "idle" | "loading" | "sending" | "error";

export interface ProductShellProps {
  todayClient: TodayClient;
  recordClient: OrganizationRecordClient;
  conversationClient: ConversationClient;
  materialClient: MaterialClient;
  learningClient: LearningClient;
  clientIdFactory: () => string;
  uploadIdFactory: () => string;
  onboardingClient?: OnboardingClient;
  logout: () => Promise<void>;
  onLoggedOut: () => void;
}

interface ReceiptState {
  kind: "record" | "material" | "error";
  message: string;
}

interface UploadedAssetState {
  file: File;
  id: string;
}

interface PendingSubmissionState {
  id: string;
  text: string;
  file: File | null;
  recordPersisted: boolean;
}

export function ProductShell({
  todayClient,
  recordClient,
  conversationClient,
  materialClient,
  learningClient,
  clientIdFactory,
  uploadIdFactory,
  onboardingClient,
  logout,
  onLoggedOut,
}: ProductShellProps) {
  const { session, status } = useSession();
  const assignment = session?.active_assignment;
  const canReadRecords = assignment?.capabilities.includes("records:read") ?? false;
  const canCreateRecords = assignment?.capabilities.includes("records:create") ?? false;
  const canAsk = assignment?.capabilities.includes("conversation:use") ?? false;
  const canUpload = assignment?.capabilities.includes("materials:create") ?? false;
  const canLearn = assignment?.capabilities.includes("training:practice") ?? false;
  const [activeView, setActiveView] = useState<FrontstageView>(() =>
    canReadRecords ? "today" : canAsk ? "conversation" : "me",
  );
  const [draft, setDraft] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadedAsset, setUploadedAsset] = useState<UploadedAssetState | null>(null);
  const [pendingSubmission, setPendingSubmission] =
    useState<PendingSubmissionState | null>(null);
  const [composerPending, setComposerPending] = useState(false);
  const [receipt, setReceipt] = useState<ReceiptState | null>(null);
  const [todayItems, setTodayItems] = useState<TodayBriefItem[]>([]);
  const [todayStatus, setTodayStatus] = useState<LoadStatus>("loading");
  const [records, setRecords] = useState<OrganizationRecord[]>([]);
  const [recordsStatus, setRecordsStatus] = useState<LoadStatus>("loading");
  const [selectedRecord, setSelectedRecord] = useState<OrganizationRecord | null>(null);
  const [recordDetailLoading, setRecordDetailLoading] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [conversationStatus, setConversationStatus] =
    useState<ConversationStatus>("idle");
  const [contextRecord, setContextRecord] = useState<OrganizationRecord | null>(null);
  const [fallbackLogoutPending, setFallbackLogoutPending] = useState(false);
  const [fallbackLogoutFailed, setFallbackLogoutFailed] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const todayRequest = useRef(0);
  const recordsRequest = useRef(0);
  const conversationListRequest = useRef(0);
  const recordDetailRequest = useRef(0);
  const conversationDetailRequest = useRef(0);

  const loadToday = useCallback(async () => {
    const request = ++todayRequest.current;
    if (!canReadRecords) {
      setTodayItems([]);
      setTodayStatus("ready");
      return;
    }
    setTodayStatus("loading");
    try {
      const response = await todayClient.getToday(3);
      if (request !== todayRequest.current) return;
      setTodayItems(response.items.slice(0, 3));
      setTodayStatus("ready");
    } catch {
      if (request !== todayRequest.current) return;
      setTodayStatus("error");
    }
  }, [canReadRecords, todayClient]);

  const loadRecords = useCallback(async () => {
    const request = ++recordsRequest.current;
    if (!canReadRecords) {
      setRecords([]);
      setRecordsStatus("ready");
      return;
    }
    setRecordsStatus("loading");
    try {
      const response = await recordClient.listRecords(50);
      if (request !== recordsRequest.current) return;
      setRecords(response.records);
      setRecordsStatus("ready");
    } catch {
      if (request !== recordsRequest.current) return;
      setRecordsStatus("error");
    }
  }, [canReadRecords, recordClient]);

  const loadConversations = useCallback(async () => {
    const request = ++conversationListRequest.current;
    if (!canAsk) {
      setConversations([]);
      return;
    }
    try {
      const response = await conversationClient.listConversations();
      if (request !== conversationListRequest.current) return;
      setConversations(response.items);
    } catch {
      // Conversation remains usable even when recent history cannot load.
    }
  }, [canAsk, conversationClient]);

  useEffect(() => {
    void loadToday();
    void loadRecords();
    void loadConversations();
  }, [loadConversations, loadRecords, loadToday, assignment?.assignment_id]);

  useEffect(
    () => () => {
      todayRequest.current += 1;
      recordsRequest.current += 1;
      conversationListRequest.current += 1;
      recordDetailRequest.current += 1;
      conversationDetailRequest.current += 1;
    },
    [],
  );

  useEffect(() => {
    const unavailable =
      ((activeView === "today" || activeView === "records") && !canReadRecords) ||
      (activeView === "conversation" && !canAsk);
    const learningUnavailable = activeView === "learning" && !canLearn;
    if (unavailable || learningUnavailable) {
      setActiveView(canReadRecords ? "today" : canAsk ? "conversation" : "me");
    }
  }, [activeView, canAsk, canLearn, canReadRecords]);

  useEffect(() => {
    if (activeView === "today" || activeView === "conversation") {
      composerRef.current?.focus();
    }
  }, [activeView, contextRecord]);

  if (status !== "authenticated" || !session || !assignment) return null;

  const navigate = (view: FrontstageView) => {
    if (view === "today" && !canReadRecords) return;
    if (view === "records" && !canReadRecords) return;
    if (view === "conversation" && !canAsk) return;
    if (view === "learning" && !canLearn) return;
    recordDetailRequest.current += 1;
    setSelectedRecord(null);
    setActiveView(view);
  };

  const startNewInput = () => {
    if (!canCreateRecords && !canAsk) return;
    setSelectedRecord(null);
    setActiveView(canReadRecords ? "today" : canAsk ? "conversation" : "me");
    setContextRecord(null);
    setReceipt(null);
    composerRef.current?.focus();
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const openRecord = async (recordId: string) => {
    if (!canReadRecords) return;
    const request = ++recordDetailRequest.current;
    setRecordDetailLoading(true);
    setSelectedRecord(records.find((record) => record.id === recordId) ?? null);
    try {
      const response = await recordClient.getRecord(recordId);
      if (request !== recordDetailRequest.current) return;
      setSelectedRecord(response.record);
    } catch {
      if (request !== recordDetailRequest.current) return;
      setReceipt({ kind: "error", message: "这条记录暂时无法打开" });
    } finally {
      if (request === recordDetailRequest.current) setRecordDetailLoading(false);
    }
  };

  const askAboutRecord = (record: OrganizationRecord) => {
    if (!canAsk) return;
    recordDetailRequest.current += 1;
    setSelectedRecord(null);
    setContextRecord(record);
    setActiveView("conversation");
    setDraft("");
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const openConversation = async (id: string) => {
    if (!canAsk) return;
    const request = ++conversationDetailRequest.current;
    setActiveView("conversation");
    setSelectedRecord(null);
    setContextRecord(null);
    setConversationStatus("loading");
    try {
      const response = await conversationClient.getConversation(id);
      if (request !== conversationDetailRequest.current) return;
      setConversationId(response.conversation.id);
      setMessages(response.messages);
      setConversationStatus("idle");
    } catch {
      if (request !== conversationDetailRequest.current) return;
      setConversationStatus("error");
    }
  };

  const startNewConversation = () => {
    conversationDetailRequest.current += 1;
    setConversationId(null);
    setMessages([]);
    setContextRecord(null);
    setConversationStatus("idle");
    setDraft("");
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const submitInput = async () => {
    const text = draft.trim();
    const file = selectedFile;
    if ((!text && !file) || (!canCreateRecords && !canAsk)) return;

    const reusableSubmission =
      pendingSubmission?.text === text && pendingSubmission.file === file
        ? pendingSubmission
        : null;
    const submission: PendingSubmissionState =
      reusableSubmission ?? {
        id: clientIdFactory(),
        text,
        file,
        recordPersisted: false,
      };
    let recordPersisted = submission.recordPersisted;

    setPendingSubmission(submission);
    setComposerPending(true);
    setReceipt({ kind: file ? "material" : "record", message: "已收到，正在处理" });
    if (text && canAsk) {
      setConversationStatus("sending");
      setActiveView("conversation");
    }

    try {
      let sourceAssetIds: string[] = [];
      if (file) {
        if (!canUpload || !canCreateRecords) throw new Error("upload_not_allowed");
        if (uploadedAsset?.file === file) {
          sourceAssetIds = [uploadedAsset.id];
        } else {
          const response = await materialClient.uploadMaterial(
            file,
            text,
            uploadIdFactory(),
          );
          sourceAssetIds = [response.material.id];
          setUploadedAsset({ file, id: response.material.id });
        }
      }

      if (canCreateRecords && !recordPersisted) {
        const response = await recordClient.createRecord({
          clientRecordId: submission.id,
          text,
          sourceAssetIds,
        });
        recordPersisted = true;
        setPendingSubmission({ ...submission, recordPersisted: true });
        setRecords((current) => [
          response.record,
          ...current.filter((record) => record.id !== response.record.id),
        ]);
        setRecordsStatus("ready");
      }

      if (text && canAsk) {
        const content = contextRecord
          ? `基于组织记录“${contextRecord.preview}”：${text}`
          : text;
        let targetConversationId = conversationId;
        if (!targetConversationId) {
          const created = await conversationClient.createConversation();
          targetConversationId = created.conversation.id;
          setConversationId(targetConversationId);
        }
        const response = await conversationClient.sendMessage(targetConversationId, {
          content,
          client_message_id: submission.id,
        });
        setMessages((current) => [
          ...current,
          { ...response.user_message, content: text },
          response.assistant_message,
        ]);
        setConversations((current) => [
          response.conversation,
          ...current.filter((item) => item.id !== response.conversation.id),
        ]);
      }

      setDraft("");
      setSelectedFile(null);
      setUploadedAsset(null);
      setPendingSubmission(null);
      setConversationStatus("idle");
    } catch {
      setConversationStatus("idle");
      setReceipt({
        kind: "error",
        message:
          recordPersisted && text && canAsk
            ? "内容已保存，回答暂时没有完成，请重试"
            : "没有提交成功，请重试",
      });
    } finally {
      setComposerPending(false);
    }
  };

  const showComposer = activeView === "today" || activeView === "conversation";
  const scopeLabel = assignment.store?.name ?? assignment.organization.name;

  return (
    <div className={`frontstage-shell${selectedRecord ? " has-record-detail" : ""}`}>
      <Navigation
        activeView={activeView}
        conversations={conversations}
        identityLabel={session.user.display_name}
        scopeLabel={`${assignment.role_label} · ${scopeLabel}`}
        canAsk={canAsk}
        canCreateRecords={canCreateRecords}
        canLearn={canLearn}
        canReadRecords={canReadRecords}
        onNavigate={navigate}
        onNewInput={startNewInput}
        onOpenConversation={(id) => void openConversation(id)}
      />

      <main className="frontstage-workspace">
        <header className="mobile-context-bar">
          <strong>HXYOS</strong>
          <button type="button" onClick={() => navigate("me")}>
            {scopeLabel}
          </button>
        </header>

        <div className="frontstage-content">
          {activeView === "today" ? (
            <TodayView
              items={todayItems}
              status={todayStatus}
              onOpenRecord={(id) => void openRecord(id)}
              onRetry={() => void loadToday()}
            />
          ) : null}
          {activeView === "conversation" ? (
            <ConversationView
              messages={messages}
              status={conversationStatus}
              contextRecord={contextRecord}
              onNewConversation={startNewConversation}
              onRetry={() => {
                if (conversationId) void openConversation(conversationId);
                else setConversationStatus("idle");
              }}
            />
          ) : null}
          {activeView === "records" ? (
            <RecordsView
              records={records}
              status={recordsStatus}
              onOpenRecord={(id) => void openRecord(id)}
              onRetry={() => void loadRecords()}
            />
          ) : null}
          {activeView === "learning" && canLearn ? (
            <LearningView client={learningClient} />
          ) : null}
          {activeView === "me" ? (
            <section className="profile-view" aria-label="当前身份">
              {onboardingClient ? (
                <OrganizationPanel
                  active
                  user={session.user}
                  assignment={assignment}
                  client={onboardingClient}
                  logout={logout}
                  onLoggedOut={onLoggedOut}
                />
              ) : (
                <div className="basic-profile">
                  <h1>{session.user.display_name}</h1>
                  <p>{assignment.role_label}</p>
                  <span>{scopeLabel}</span>
                  <button
                    type="button"
                    disabled={fallbackLogoutPending}
                    onClick={() => {
                      setFallbackLogoutPending(true);
                      setFallbackLogoutFailed(false);
                      void logout().then(
                        onLoggedOut,
                        () => {
                          setFallbackLogoutPending(false);
                          setFallbackLogoutFailed(true);
                        },
                      );
                    }}
                  >
                    {fallbackLogoutPending ? "正在退出" : "退出登录"}
                  </button>
                  {fallbackLogoutFailed ? <p role="alert">没有退出，请重试</p> : null}
                </div>
              )}
            </section>
          ) : null}
        </div>

        {showComposer ? (
          <div className="composer-dock">
            {receipt ? (
              <p
                className={`composer-receipt is-${receipt.kind}`}
                role={receipt.kind === "error" ? "alert" : "status"}
              >
                {receipt.message}
              </p>
            ) : null}
            <UniversalComposer
              value={draft}
              selectedFile={selectedFile}
              pending={composerPending}
              disabled={!canAsk && !canCreateRecords}
              canAttach={canUpload && canCreateRecords}
              inputRef={composerRef}
              onValueChange={(value) => {
                setDraft(value);
                setPendingSubmission(null);
              }}
              onFileChange={(file) => {
                setSelectedFile(file);
                setUploadedAsset(null);
                setPendingSubmission(null);
              }}
              onSubmit={() => void submitInput()}
            />
          </div>
        ) : null}
      </main>

      {recordDetailLoading && !selectedRecord ? (
        <aside className="record-detail detail-loading" role="status">
          正在打开组织记录
        </aside>
      ) : null}
      {selectedRecord ? (
        <RecordDetail
          record={selectedRecord}
          canAsk={canAsk}
          onClose={() => {
            recordDetailRequest.current += 1;
            setSelectedRecord(null);
          }}
          onAsk={askAboutRecord}
        />
      ) : null}
    </div>
  );
}
