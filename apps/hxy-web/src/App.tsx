import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowUp,
  FileText,
  Info,
  ListTodo,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  SquarePen,
  Store,
  UserRound,
  X,
} from "lucide-react";

import {
  logoutSession,
  MeRequestError,
  productOnboardingClient,
  type CanonicalRole,
  type MeResponse,
  type OnboardingClient,
} from "./api/client";
import {
  type ConversationClient,
  type ConversationMessage,
  productConversationClient,
} from "./api/conversations";
import {
  type MaterialClient,
  type ProductMaterial,
  productMaterialClient,
} from "./api/materials";
import {
  type JourneyClient,
  type JourneySuggestion,
  type TrainingJourneyResult,
  productJourneyClient,
} from "./api/journeys";
import {
  type HxyTask,
  type TaskClient,
  productTaskClient,
} from "./api/tasks";
import {
  SessionProvider,
  type SessionGrantExchanger,
  type SessionLoader,
  useSession,
} from "./features/session/SessionProvider";
import { OrganizationPanel } from "./features/onboarding/OrganizationPanel";

type PrimaryView = "conversation" | "tasks" | "profile";

const roleSuggestions: Record<CanonicalRole, readonly JourneySuggestion[]> = {
  founder: [
    { type: "ask", label: "询问当前开业进度", prompt: "现在开业进度怎么样？" },
    { type: "tasks", label: "查看今天的关键事项" },
  ],
  hq_operations: [
    { type: "tasks", label: "查看门店待办" },
    { type: "issue", label: "上报一个运营问题" },
  ],
  store_manager: [
    { type: "tasks", label: "打开今天的待办" },
    { type: "issue", label: "上报一个门店问题" },
  ],
  store_employee: [
    { type: "ask", label: "询问该怎么说", prompt: "顾客这样问时我该怎么说？" },
    { type: "training", label: "练习一次接待话术" },
    { type: "issue", label: "上报一个门店问题" },
  ],
  system_admin: [
    { type: "ask", label: "询问系统状态", prompt: "当前系统有哪些需要处理的问题？" },
  ],
};

const navigationItems = [
  { id: "conversation", label: "对话", icon: MessageSquare },
  { id: "tasks", label: "待办", icon: ListTodo },
  { id: "profile", label: "我的", icon: UserRound },
] as const;

const viewHeadings: Record<PrimaryView, string> = {
  conversation: "今天想先处理什么？",
  tasks: "今天的待办",
  profile: "我的",
};

interface PendingMessage {
  content: string;
  clientMessageId: string;
  localMessageId: string;
}

interface FailedMaterialUpload {
  file: File;
  clientUploadId: string;
}

interface ProductShellProps {
  conversationClient: ConversationClient;
  materialClient: MaterialClient;
  taskClient: TaskClient;
  journeyClient: JourneyClient;
  clientMessageIdFactory: () => string;
  materialUploadIdFactory: () => string;
  onboardingClient: OnboardingClient;
  logout: () => Promise<void>;
  onLoggedOut: () => void;
}

function normalizeAccessCode(value: string): string | null {
  const trimmed = value.trim();
  let candidate = trimmed;

  if (trimmed.includes("#")) {
    try {
      const url = new URL(trimmed);
      const params = new URLSearchParams(url.hash.slice(1));
      candidate = params.get("hxy_session_grant") ?? "";
    } catch {
      return null;
    }
  }

  return candidate.length >= 43 &&
    candidate.length <= 256 &&
    /^[A-Za-z0-9._~-]+$/.test(candidate)
    ? candidate
    : null;
}

interface AccessGateProps {
  status: "loading" | "unauthorized" | "error";
  authenticate: (grant: string) => Promise<void>;
  retry: () => void;
}

function AccessGate({ status, authenticate, retry }: AccessGateProps) {
  const [accessCode, setAccessCode] = useState("");
  const [accessError, setAccessError] = useState("");
  const normalizedAccessCode = normalizeAccessCode(accessCode);

  const submitAccessCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!normalizedAccessCode || status === "loading") return;

    setAccessError("");
    try {
      await authenticate(normalizedAccessCode);
    } catch (error: unknown) {
      setAccessCode("");
      setAccessError(
        error instanceof MeRequestError &&
          (error.status === 401 || error.status === 403 || error.status === 422)
          ? "访问码无效或已过期，请重新获取"
          : "暂时无法连接，请稍后重试",
      );
    }
  };

  return (
    <main className="access-gate">
      <div className="access-gate-content">
        <div className="access-brand" aria-label="HXYOS">
          <span className="brand-mark" aria-hidden="true">H</span>
          <span>HXYOS</span>
        </div>

        {status === "loading" ? (
          <p className="access-loading" role="status">正在连接 HXYOS</p>
        ) : status === "error" ? (
          <div className="access-state">
            <h1>暂时无法连接 HXYOS</h1>
            <p>请检查网络后重新连接。</p>
            <button className="access-primary-button" type="button" onClick={retry}>
              重新连接
            </button>
          </div>
        ) : (
          <div className="access-state">
            <h1>进入 HXYOS</h1>
            <p>打开管理员发送的一次性访问链接，或输入访问码。</p>
            <form className="access-form" onSubmit={submitAccessCode}>
              <label htmlFor="hxy-access-code">一次性访问码</label>
              <input
                id="hxy-access-code"
                type="password"
                autoComplete="one-time-code"
                spellCheck={false}
                value={accessCode}
                onChange={(event) => {
                  setAccessCode(event.target.value);
                  setAccessError("");
                }}
              />
              {accessError ? <p className="access-error" role="alert">{accessError}</p> : null}
              <button
                className="access-primary-button"
                type="submit"
                disabled={!normalizedAccessCode}
              >
                进入
              </button>
            </form>
          </div>
        )}
      </div>
    </main>
  );
}

function ProductShell({
  conversationClient,
  materialClient,
  taskClient,
  journeyClient,
  clientMessageIdFactory,
  materialUploadIdFactory,
  onboardingClient,
  logout,
  onLoggedOut,
}: ProductShellProps) {
  const { authenticate, retry, session, status } = useSession();
  const [activeView, setActiveView] = useState<PrimaryView>("conversation");
  const [profileEverVisited, setProfileEverVisited] = useState(false);
  const [isRailCompact, setIsRailCompact] = useState(true);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<PendingMessage | null>(
    null,
  );
  const [latestMaterial, setLatestMaterial] = useState<ProductMaterial | null>(
    null,
  );
  const [uploadingFileName, setUploadingFileName] = useState<string | null>(
    null,
  );
  const [failedMaterial, setFailedMaterial] =
    useState<FailedMaterialUpload | null>(null);
  const [isRetryingUnderstanding, setIsRetryingUnderstanding] = useState(false);
  const [understandingRetryFailed, setUnderstandingRetryFailed] =
    useState(false);
  const [tasks, setTasks] = useState<HxyTask[]>([]);
  const [isTasksLoading, setIsTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState(false);
  const [completingTaskId, setCompletingTaskId] = useState<string | null>(null);
  const [completionResult, setCompletionResult] = useState("");
  const [taskActionPending, setTaskActionPending] = useState(false);
  const [journeySuggestions, setJourneySuggestions] = useState<{
    assignmentId: string | null;
    items: JourneySuggestion[] | null;
  }>({ assignmentId: null, items: null });
  const [journeyMode, setJourneyMode] = useState<"training" | "issue" | null>(null);
  const [customerQuestion, setCustomerQuestion] = useState(
    "顾客问：这个能不能治疗失眠？",
  );
  const [employeeAnswer, setEmployeeAnswer] = useState("");
  const [trainingResult, setTrainingResult] =
    useState<TrainingJourneyResult | null>(null);
  const [issueTitle, setIssueTitle] = useState("");
  const [issueDetails, setIssueDetails] = useState("");
  const [issueSourceTask, setIssueSourceTask] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [journeyPending, setJourneyPending] = useState(false);
  const [journeyError, setJourneyError] = useState(false);
  const materialInputRef = useRef<HTMLInputElement>(null);
  const detailsTriggerRef = useRef<HTMLButtonElement>(null);
  const detailsDrawerRef = useRef<HTMLElement>(null);
  const detailsCloseRef = useRef<HTMLButtonElement>(null);
  const detailsWasOpen = useRef(false);
  const messageListEndRef = useRef<HTMLDivElement>(null);
  const historyRequestVersionRef = useRef(0);
  const materialRequestVersionRef = useRef(0);
  const taskRequestVersionRef = useRef(0);
  const journeyRequestVersionRef = useRef(0);
  const journeyMutationVersionRef = useRef(0);
  const activeAssignmentIdRef = useRef<string | null>(null);
  const assignment = session?.active_assignment;
  activeAssignmentIdRef.current = assignment?.assignment_id ?? null;
  const isAuthenticated = status === "authenticated" && assignment !== undefined;
  const canCreateMaterials =
    assignment?.capabilities.includes("materials:create") ?? false;
  const canReadMaterials =
    assignment?.capabilities.includes("materials:read") ?? false;
  const canReadTasks = assignment?.capabilities.includes("tasks:read") ?? false;
  const canManageTasks =
    assignment?.capabilities.includes("tasks:manage") ?? false;
  const canPracticeTraining =
    assignment?.capabilities.includes("training:practice") ?? false;
  const canCreateIssues =
    assignment?.capabilities.includes("issues:create") ?? false;
  const isJourneyActionAllowed = (action: JourneySuggestion) => {
    if (action.type === "tasks") return canReadTasks;
    if (action.type === "training") return canPracticeTraining;
    if (action.type === "issue") return canCreateIssues;
    if (action.type === "material_upload") return canCreateMaterials;
    return assignment?.capabilities.includes("conversation:use") ?? false;
  };
  const suggestions = assignment
    ? (
        journeySuggestions.assignmentId === assignment.assignment_id
          ? journeySuggestions.items
          : null
      ) ?? roleSuggestions[assignment.role]
    : [];
  const visibleSuggestions = suggestions.filter(isJourneyActionAllowed).slice(0, 3);
  const roleLabel =
    assignment?.role_label ??
    (status === "loading"
      ? "正在加载身份"
      : status === "unauthorized"
        ? "登录已失效"
        : "身份加载失败");
  const scopeLabel =
    assignment?.store?.name ??
    assignment?.organization.name ??
    (status === "loading" ? "HXYOS" : "请重试");
  const isConversationEmpty =
    activeView === "conversation" && messages.length === 0 && journeyMode === null;

  const latestAnswer = [...messages]
    .reverse()
    .find(
      (message) =>
        message.role === "assistant" &&
        (message.answer_status !== null || message.sources.length > 0),
    );

  useEffect(() => {
    if (!isAuthenticated || !assignment) {
      setConversationId(null);
      setMessages([]);
      setIsHistoryLoading(false);
      return;
    }

    let active = true;
    const requestVersion = historyRequestVersionRef.current + 1;
    historyRequestVersionRef.current = requestVersion;
    setIsHistoryLoading(true);
    setConversationId(null);
    setMessages([]);
    setSendError(false);
    setPendingMessage(null);
    void conversationClient
      .listConversations()
      .then(async ({ items }) => {
        if (
          !active ||
          historyRequestVersionRef.current !== requestVersion ||
          items.length === 0
        ) {
          return;
        }
        const conversation = await conversationClient.getConversation(
          items[0].id,
        );
        if (
          !active ||
          historyRequestVersionRef.current !== requestVersion
        ) {
          return;
        }
        setConversationId(conversation.conversation.id);
        setMessages(conversation.messages);
      })
      .catch(() => undefined)
      .finally(() => {
        if (
          active &&
          historyRequestVersionRef.current === requestVersion
        ) {
          setIsHistoryLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [assignment?.assignment_id, conversationClient, isAuthenticated]);

  useEffect(() => {
    const requestVersion = materialRequestVersionRef.current + 1;
    materialRequestVersionRef.current = requestVersion;
    setLatestMaterial(null);
    setUploadingFileName(null);
    setFailedMaterial(null);
    setUnderstandingRetryFailed(false);

    if (!isAuthenticated || !canReadMaterials) return;

    let active = true;
    void materialClient
      .listMaterials()
      .then(({ items }) => {
        if (
          active &&
          materialRequestVersionRef.current === requestVersion &&
          items.length > 0
        ) {
          setLatestMaterial(items[0]);
        }
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [
    assignment?.assignment_id,
    canReadMaterials,
    isAuthenticated,
    materialClient,
  ]);

  const loadTasks = async () => {
    if (!isAuthenticated || !canReadTasks) return;
    const requestVersion = taskRequestVersionRef.current + 1;
    taskRequestVersionRef.current = requestVersion;
    setIsTasksLoading(true);
    setTasksError(false);
    try {
      const result = await taskClient.listTasks();
      if (taskRequestVersionRef.current === requestVersion) {
        setTasks(result.items);
      }
    } catch {
      if (taskRequestVersionRef.current === requestVersion) {
        setTasksError(true);
      }
    } finally {
      if (taskRequestVersionRef.current === requestVersion) {
        setIsTasksLoading(false);
      }
    }
  };

  useEffect(() => {
    taskRequestVersionRef.current += 1;
    setTasks([]);
    setCompletingTaskId(null);
    setCompletionResult("");
    if (isAuthenticated && canReadTasks) void loadTasks();
  }, [assignment?.assignment_id, canReadTasks, isAuthenticated, taskClient]);

  useEffect(() => {
    const requestVersion = journeyRequestVersionRef.current + 1;
    journeyRequestVersionRef.current = requestVersion;
    journeyMutationVersionRef.current += 1;
    setJourneyPending(false);
    setJourneySuggestions({
      assignmentId: assignment?.assignment_id ?? null,
      items: null,
    });
    setJourneyMode(null);
    setTrainingResult(null);
    setJourneyError(false);
    if (!isAuthenticated || !assignment) return;
    const assignmentId = assignment.assignment_id;
    void journeyClient
      .loadSuggestions()
      .then(({ items }) => {
        if (journeyRequestVersionRef.current === requestVersion) {
          setJourneySuggestions({ assignmentId, items: items.slice(0, 3) });
        }
      })
      .catch(() => undefined);
  }, [assignment?.assignment_id, isAuthenticated, journeyClient]);

  useEffect(() => {
    if (
      !isAuthenticated ||
      !canReadMaterials ||
      latestMaterial?.status !== "processing"
    ) {
      return;
    }
    let active = true;
    const interval = window.setInterval(() => {
      void materialClient
        .getMaterial(latestMaterial.id)
        .then(({ material }) => {
          if (active) setLatestMaterial(material);
        })
        .catch(() => undefined);
    }, 2500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [
    canReadMaterials,
    isAuthenticated,
    latestMaterial?.id,
    latestMaterial?.status,
    materialClient,
  ]);

  useEffect(() => {
    if (isDetailsOpen) {
      detailsCloseRef.current?.focus();
    } else if (detailsWasOpen.current) {
      detailsTriggerRef.current?.focus();
    }
    detailsWasOpen.current = isDetailsOpen;
  }, [isDetailsOpen]);

  useEffect(() => {
    const scrollIntoView = messageListEndRef.current?.scrollIntoView;
    if (typeof scrollIntoView === "function") {
      scrollIntoView.call(messageListEndRef.current, { block: "nearest" });
    }
  }, [failedMaterial, isSending, latestMaterial, messages, uploadingFileName]);

  const uploadMaterial = async (file: File, clientUploadId: string) => {
    if (!isAuthenticated || !canCreateMaterials || uploadingFileName) return;
    materialRequestVersionRef.current += 1;
    setActiveView("conversation");
    setUploadingFileName(file.name);
    setFailedMaterial(null);
    try {
      const { material } = await materialClient.uploadMaterial(
        file,
        "",
        clientUploadId,
      );
      setLatestMaterial(material);
    } catch {
      setFailedMaterial({ file, clientUploadId });
    } finally {
      setUploadingFileName(null);
    }
  };

  const handleMaterialSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (file) void uploadMaterial(file, materialUploadIdFactory());
  };

  const retryMaterialUnderstanding = async (material: ProductMaterial) => {
    if (!isAuthenticated || !canCreateMaterials || isRetryingUnderstanding) {
      return;
    }
    setIsRetryingUnderstanding(true);
    setUnderstandingRetryFailed(false);
    try {
      const result = await materialClient.retryUnderstanding(material.id);
      setLatestMaterial(result.material);
    } catch {
      setUnderstandingRetryFailed(true);
    } finally {
      setIsRetryingUnderstanding(false);
    }
  };

  const sendPendingMessage = async (pending: PendingMessage) => {
    historyRequestVersionRef.current += 1;
    setIsHistoryLoading(false);
    setIsSending(true);
    setSendError(false);
    try {
      let targetConversationId = conversationId;
      if (!targetConversationId) {
        const { conversation } = await conversationClient.createConversation();
        targetConversationId = conversation.id;
        setConversationId(targetConversationId);
      }
      const result = await conversationClient.sendMessage(
        targetConversationId,
        {
          content: pending.content,
          client_message_id: pending.clientMessageId,
        },
      );
      setMessages((current) => [
        ...current.filter(
          (message) => message.id !== pending.localMessageId,
        ),
        {
          ...result.user_message,
          content: pending.content,
        },
        result.assistant_message,
      ]);
      setPendingMessage(null);
    } catch {
      setSendError(true);
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isAuthenticated || isSending) return;
    const message = draft.trim();
    if (!message) return;

    const clientMessageId = clientMessageIdFactory();
    const pending = {
      content: message,
      clientMessageId,
      localMessageId: `local:${clientMessageId}`,
    };
    setMessages((current) => [
      ...current,
      {
        id: pending.localMessageId,
        conversation_id: conversationId ?? "local",
        role: "user",
        content: message,
        created_at: new Date().toISOString(),
        answer_id: null,
        answer_status: null,
        confidence: null,
        needs_review: null,
        sources: [],
        next_actions: [],
      },
    ]);
    setPendingMessage(pending);
    setDraft("");
    void sendPendingMessage(pending);
  };

  const startNewConversation = () => {
    historyRequestVersionRef.current += 1;
    journeyMutationVersionRef.current += 1;
    setConversationId(null);
    setMessages([]);
    setPendingMessage(null);
    setSendError(false);
    setIsDetailsOpen(false);
    setJourneyPending(false);
    setJourneyMode(null);
    setIssueSourceTask(null);
    setTrainingResult(null);
    setJourneyError(false);
  };

  const completeTask = async (task: HxyTask) => {
    const result = completionResult.trim();
    if (!result || taskActionPending) return;
    taskRequestVersionRef.current += 1;
    setIsTasksLoading(false);
    setTaskActionPending(true);
    setTasksError(false);
    try {
      const response = await taskClient.updateTask(task.id, {
        status: "completed",
        result,
      });
      setTasks((current) =>
        current.map((item) =>
          item.id === response.task.id ? response.task : item,
        ),
      );
      setCompletingTaskId(null);
      setCompletionResult("");
    } catch {
      setTasksError(true);
    } finally {
      setTaskActionPending(false);
    }
  };

  const createTaskFromAnswer = async (message: ConversationMessage) => {
    const title = message.next_actions[0]?.trim() || "跟进本次回答";
    if (!assignment || !title || taskActionPending) return;
    taskRequestVersionRef.current += 1;
    setIsTasksLoading(false);
    setTaskActionPending(true);
    setTasksError(false);
    try {
      const response = await taskClient.createTask({
        title: title.slice(0, 160),
        details: message.content.slice(0, 5000),
        priority: "normal",
        visibility: "assignee",
        assignee_assignment_id: assignment.assignment_id,
        source_conversation_id: conversationId ?? undefined,
        source_message_id: message.id,
      });
      setTasks((current) => [response.task, ...current]);
      setActiveView("tasks");
    } catch {
      setTasksError(true);
    } finally {
      setTaskActionPending(false);
    }
  };

  const handleAnswerTaskAction = (message: ConversationMessage) => {
    const action = (message.actions || []).find((item) => item.type === "tasks");
    if (message.result_type === "system_capability" && action) {
      openJourneyAction({ type: "tasks", label: action.label });
      return;
    }
    void createTaskFromAnswer(message);
  };

  const openJourneyAction = (
    action: JourneySuggestion,
    contextQuestion?: string,
  ) => {
    if (!isJourneyActionAllowed(action)) return;
    journeyMutationVersionRef.current += 1;
    setJourneyPending(false);
    setJourneyError(false);
    setIssueSourceTask(null);
    if (action.type === "tasks") {
      setActiveView("tasks");
      return;
    }
    setActiveView("conversation");
    if (action.type === "material_upload") {
      materialInputRef.current?.click();
      return;
    }
    if (action.type === "ask") {
      setJourneyMode(null);
      setDraft(action.prompt || action.label);
      return;
    }
    if (action.type === "training") {
      setJourneyMode("training");
      if (contextQuestion?.trim()) {
        setCustomerQuestion(contextQuestion.trim());
      }
      setTrainingResult(null);
      setEmployeeAnswer("");
      return;
    }
    setJourneyMode("issue");
    setIssueSourceTask(null);
    setIssueTitle("");
    setIssueDetails("");
  };

  const openTaskIssue = (task: HxyTask) => {
    journeyMutationVersionRef.current += 1;
    setJourneyPending(false);
    setJourneyError(false);
    setActiveView("conversation");
    setJourneyMode("issue");
    setIssueSourceTask({ id: task.id, title: task.title });
    setIssueTitle("");
    setIssueDetails("");
  };

  const closeJourney = () => {
    journeyMutationVersionRef.current += 1;
    setJourneyPending(false);
    setJourneyMode(null);
    setIssueSourceTask(null);
    setJourneyError(false);
  };

  const selectPrimaryView = (view: PrimaryView) => {
    journeyMutationVersionRef.current += 1;
    setJourneyPending(false);
    setJourneyMode(null);
    setIssueSourceTask(null);
    setJourneyError(false);
    if (view === "profile") setProfileEverVisited(true);
    setActiveView(view);
  };

  const submitTraining = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = customerQuestion.trim();
    const answer = employeeAnswer.trim();
    const assignmentId = assignment?.assignment_id;
    if (!question || !answer || !assignmentId || journeyPending) return;
    const requestVersion = journeyMutationVersionRef.current + 1;
    journeyMutationVersionRef.current = requestVersion;
    setJourneyPending(true);
    setJourneyError(false);
    try {
      const result = await journeyClient.evaluateTraining({
        customer_question: question,
        employee_answer: answer,
      });
      if (
        journeyMutationVersionRef.current !== requestVersion ||
        activeAssignmentIdRef.current !== assignmentId
      ) {
        return;
      }
      setTrainingResult(result);
    } catch {
      if (journeyMutationVersionRef.current === requestVersion) {
        setJourneyError(true);
      }
    } finally {
      if (journeyMutationVersionRef.current === requestVersion) {
        setJourneyPending(false);
      }
    }
  };

  const submitIssue = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const title = issueTitle.trim();
    const details = issueDetails.trim();
    const assignmentId = assignment?.assignment_id;
    if (!title || !details || !assignmentId || journeyPending) return;
    const requestVersion = journeyMutationVersionRef.current + 1;
    journeyMutationVersionRef.current = requestVersion;
    setJourneyPending(true);
    setJourneyError(false);
    try {
      const response = await journeyClient.reportIssue({
        title,
        details,
        ...(issueSourceTask ? { source_task_id: issueSourceTask.id } : {}),
      });
      if (
        journeyMutationVersionRef.current !== requestVersion ||
        activeAssignmentIdRef.current !== assignmentId
      ) {
        return;
      }
      taskRequestVersionRef.current += 1;
      setIsTasksLoading(false);
      const reportedTask: HxyTask = {
        ...response.primary_result.task,
        visibility: "store",
        store_id: assignment?.store?.id ?? null,
        assignee_assignment_id: null,
        source_conversation_id: null,
        source_message_id: null,
      };
      setTasks((current) => [
        reportedTask,
        ...current.filter((task) => task.id !== reportedTask.id),
      ]);
      setJourneyMode(null);
      setIssueSourceTask(null);
      setIssueTitle("");
      setIssueDetails("");
      setActiveView("tasks");
    } catch {
      if (journeyMutationVersionRef.current === requestVersion) {
        setJourneyError(true);
      }
    } finally {
      if (journeyMutationVersionRef.current === requestVersion) {
        setJourneyPending(false);
      }
    }
  };

  const handleDetailsKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setIsDetailsOpen(false);
      return;
    }

    if (event.key !== "Tab") return;
    const focusable = Array.from(
      detailsDrawerRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [],
    );
    if (!focusable.length) {
      event.preventDefault();
      detailsDrawerRef.current?.focus();
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

  if (!isAuthenticated) {
    return (
      <AccessGate
        status={status === "authenticated" ? "error" : status}
        authenticate={authenticate}
        retry={retry}
      />
    );
  }

  return (
    <div
      className={`app-shell${isRailCompact ? " rail-compact" : ""}${
        isDetailsOpen ? " has-details" : ""
      }`}
    >
      <aside
        className="left-rail"
        aria-label="HXYOS 导航栏"
        inert={isDetailsOpen}
      >
        <div className="rail-header">
          <span className="brand-mark" aria-hidden="true">
            H
          </span>
          <span className="brand-name">HXYOS</span>
          <button
            className="icon-button rail-toggle"
            type="button"
            aria-label={isRailCompact ? "展开导航栏" : "收起导航栏"}
            title={isRailCompact ? "展开导航栏" : "收起导航栏"}
            onClick={() => setIsRailCompact((current) => !current)}
          >
            {isRailCompact ? <PanelLeftOpen /> : <PanelLeftClose />}
          </button>
        </div>

        <nav className="primary-navigation" aria-label="主要导航">
          {navigationItems.map(({ id, label, icon: Icon }) => (
            <button
              className="navigation-item"
              type="button"
              key={id}
              aria-current={activeView === id ? "page" : undefined}
              title={label}
              disabled={!isAuthenticated}
              onClick={() => selectPrimaryView(id)}
            >
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main
        className={`conversation-stage${
          isConversationEmpty ? " is-conversation-empty" : ""
        }`}
        inert={isDetailsOpen}
      >
        <header className="stage-header">
          <div
            className="context-line"
            aria-label="当前身份和门店"
          >
            <Store aria-hidden="true" />
            <span className="context-role">{roleLabel}</span>
            <span className="context-separator" aria-hidden="true">
              /
            </span>
            <span className="context-scope">{scopeLabel}</span>
          </div>
          <div className="stage-actions">
            {activeView === "conversation" ? (
              <>
                {messages.length > 0 ? (
                  <button
                    className="icon-button stage-icon-button"
                    type="button"
                    aria-label="新建对话"
                    title="新建对话"
                    disabled={!isAuthenticated || isSending}
                    onClick={startNewConversation}
                  >
                    <SquarePen aria-hidden="true" />
                  </button>
                ) : null}
                <button
                  ref={detailsTriggerRef}
                  className="source-button"
                  type="button"
                  aria-label="查看当前对话详情"
                  disabled={!isAuthenticated}
                  onClick={() => setIsDetailsOpen(true)}
                >
                  <Info aria-hidden="true" />
                  <span>查看详情</span>
                </button>
              </>
            ) : null}
          </div>
        </header>

        <section
          className="conversation-content"
          aria-live="polite"
          aria-busy={isHistoryLoading || isSending}
        >
          {activeView === "tasks" ? (
            <div className="task-view">
              <div className="task-view-heading">
                <div>
                  <h1>{viewHeadings.tasks}</h1>
                  <p>只显示当前岗位可以处理的事项</p>
                </div>
                <button type="button" onClick={() => void loadTasks()}>
                  刷新
                </button>
              </div>
              {isTasksLoading ? <p role="status">正在加载待办</p> : null}
              {tasksError ? (
                <div className="task-error" role="alert">
                  <span>待办没有更新</span>
                  <button type="button" onClick={() => void loadTasks()}>
                    重试
                  </button>
                </div>
              ) : null}
              {!isTasksLoading && tasks.length === 0 ? (
                <div className="task-empty">
                  <ListTodo aria-hidden="true" />
                  <p>暂时没有待办</p>
                </div>
              ) : (
                <div className="task-list">
                  {tasks.map((task) => (
                    <article className="task-item" key={task.id}>
                      <div className="task-item-head">
                        <div>
                          <span className={`task-priority is-${task.priority}`}>
                            {task.priority === "urgent"
                              ? "紧急"
                              : task.priority === "high"
                                ? "重要"
                                : "普通"}
                          </span>
                          <h2>{task.title}</h2>
                        </div>
                        <span className="task-status">
                          {task.status === "completed"
                            ? "已完成"
                            : task.status === "in_progress"
                              ? "进行中"
                              : "待处理"}
                        </span>
                      </div>
                      {task.details ? <p>{task.details}</p> : null}
                      {task.result ? (
                        <p className="task-result">结果：{task.result}</p>
                      ) : null}
                      {canCreateIssues &&
                      (task.status === "open" || task.status === "in_progress") ? (
                        <button
                          className="task-feedback-button"
                          type="button"
                          aria-label={`反馈${task.title}的问题`}
                          onClick={() => openTaskIssue(task)}
                        >
                          反馈问题
                        </button>
                      ) : null}
                      {task.available_actions?.includes("complete") ? (
                        completingTaskId === task.id ? (
                          <div className="task-completion">
                            <textarea
                              rows={3}
                              aria-label="执行结果"
                              value={completionResult}
                              onChange={(event) =>
                                setCompletionResult(event.target.value)
                              }
                            />
                            <div>
                              <button
                                type="button"
                                onClick={() => {
                                  setCompletingTaskId(null);
                                  setCompletionResult("");
                                }}
                              >
                                取消
                              </button>
                              <button
                                type="button"
                                disabled={!completionResult.trim() || taskActionPending}
                                onClick={() => void completeTask(task)}
                              >
                                确认完成
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            className="task-complete-button"
                            type="button"
                            onClick={() => setCompletingTaskId(task.id)}
                          >
                            完成任务
                          </button>
                        )
                      ) : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
          ) : activeView === "profile" ? (
            null
          ) : journeyMode === "training" ? (
            <div className="journey-panel">
              <div className="journey-heading">
                <div>
                  <span>门店练习</span>
                  <h1>接待话术练习</h1>
                </div>
                <button type="button" onClick={closeJourney}>
                  返回对话
                </button>
              </div>
              <form className="journey-form" onSubmit={submitTraining}>
                <label>
                  顾客的问题
                  <textarea
                    rows={2}
                    aria-label="顾客的问题"
                    value={customerQuestion}
                    onChange={(event) => setCustomerQuestion(event.target.value)}
                  />
                </label>
                <label>
                  我的回答
                  <textarea
                    rows={4}
                    aria-label="我的回答"
                    value={employeeAnswer}
                    onChange={(event) => setEmployeeAnswer(event.target.value)}
                  />
                </label>
                <button
                  type="submit"
                  disabled={!customerQuestion.trim() || !employeeAnswer.trim() || journeyPending}
                >
                  {journeyPending ? "正在评分" : "提交练习"}
                </button>
              </form>
              {journeyError ? <p role="alert">练习没有完成，请重试</p> : null}
              {trainingResult ? (
                <article className="training-result">
                  <div className="training-score">
                    <strong>{trainingResult.primary_result.score} 分</strong>
                    <span>
                      {trainingResult.primary_result.needs_retrain
                        ? "需要再练"
                        : "本次通过"}
                    </span>
                  </div>
                  {trainingResult.primary_result.correction_points.length > 0 ? (
                    <section>
                      <h2>需要调整</h2>
                      <ul>
                        {trainingResult.primary_result.correction_points.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                  ) : null}
                  {trainingResult.primary_result.standard_script ? (
                    <section>
                      <h2>参考说法</h2>
                      <p>{trainingResult.primary_result.standard_script}</p>
                    </section>
                  ) : null}
                  {trainingResult.actions
                    .filter(
                      (action) =>
                        action.type === "training" &&
                        isJourneyActionAllowed({
                          type: "training",
                          label: action.label,
                        }),
                    )
                    .map((action) => (
                      <button
                        className="journey-next-button"
                        type="button"
                        key={`${action.type}-${action.label}`}
                        onClick={() =>
                          openJourneyAction({
                            type: "training",
                            label: action.label,
                          })
                        }
                      >
                        {action.label}
                      </button>
                    ))}
                  {trainingResult.limitations.map((limitation) => (
                    <p className="journey-limit" key={limitation}>
                      {limitation}
                    </p>
                  ))}
                </article>
              ) : null}
            </div>
          ) : journeyMode === "issue" ? (
            <div className="journey-panel">
              <div className="journey-heading">
                <div>
                  <span>现场反馈</span>
                  <h1>上报门店问题</h1>
                </div>
                <button type="button" onClick={closeJourney}>
                  返回对话
                </button>
              </div>
              <form className="journey-form" onSubmit={submitIssue}>
                {issueSourceTask ? (
                  <p className="journey-context">关联待办：{issueSourceTask.title}</p>
                ) : null}
                <label>
                  问题标题
                  <input
                    aria-label="问题标题"
                    value={issueTitle}
                    onChange={(event) => setIssueTitle(event.target.value)}
                  />
                </label>
                <label>
                  问题详情
                  <textarea
                    rows={5}
                    aria-label="问题详情"
                    value={issueDetails}
                    onChange={(event) => setIssueDetails(event.target.value)}
                  />
                </label>
                <button
                  type="submit"
                  disabled={!issueTitle.trim() || !issueDetails.trim() || journeyPending}
                >
                  {journeyPending ? "正在提交" : "提交问题"}
                </button>
              </form>
              {journeyError ? <p role="alert">问题没有提交，请重试</p> : null}
            </div>
          ) : messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-symbol" aria-hidden="true">
                <MessageSquare />
              </div>
              <h1>{viewHeadings.conversation}</h1>
              {isAuthenticated && visibleSuggestions.length > 0 ? (
                <div className="suggestions" data-testid="suggestions">
                  {visibleSuggestions.map((suggestion) => (
                    <button
                      type="button"
                      key={`${suggestion.type}-${suggestion.label}`}
                      onClick={() => openJourneyAction(suggestion)}
                    >
                      {suggestion.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="message-list" aria-label="当前对话">
              {messages.map((message, messageIndex) =>
                message.role === "user" ? (
                  <p className="user-message" key={message.id}>
                    {message.content}
                  </p>
                ) : (
                  <article
                    className="assistant-message"
                    key={message.id}
                  >
                    <p>{message.content}</p>
                    {(message.result_type === "system_capability"
                      ? canReadTasks
                      : canManageTasks) &&
                    (message.next_actions.length > 0 ||
                      (message.actions || []).some((action) => action.type === "tasks")) ? (
                      <button
                        className="answer-task-button"
                        type="button"
                        disabled={taskActionPending}
                        onClick={() => handleAnswerTaskAction(message)}
                      >
                        {(message.actions || []).find((action) => action.type === "tasks")
                          ?.label || "转为待办"}
                      </button>
                    ) : null}
                    {(message.actions || [])
                      .filter(
                        (action) => {
                          if (
                            action.type !== "training" &&
                            action.type !== "issue" &&
                            action.type !== "material_upload"
                          ) {
                            return false;
                          }
                          return isJourneyActionAllowed({
                            type: action.type,
                            label: action.label,
                          });
                        },
                      )
                      .map((action) => (
                        <button
                          className="answer-journey-button"
                          type="button"
                          key={`${message.id}-${action.type}`}
                          onClick={() =>
                            openJourneyAction({
                              type: action.type as "training" | "issue" | "material_upload",
                              label: action.label,
                            },
                            action.type === "training"
                              ? messages
                                  .slice(0, messageIndex)
                                  .reverse()
                                  .find((candidate) => candidate.role === "user")
                                  ?.content
                              : undefined)
                          }
                        >
                          {action.label}
                        </button>
                      ))}
                  </article>
                ),
              )}
              {isSending ? (
                <div className="assistant-pending" role="status">
                  <span aria-hidden="true" />
                  <span aria-hidden="true" />
                  <span aria-hidden="true" />
                  <span className="visually-hidden">正在生成回答</span>
                </div>
              ) : null}
              {sendError && pendingMessage ? (
                <div className="message-error" role="alert">
                  <span>回答没有完成</span>
                  <button
                    type="button"
                    onClick={() => void sendPendingMessage(pendingMessage)}
                  >
                    重试
                  </button>
                </div>
              ) : null}
              <div ref={messageListEndRef} />
            </div>
          )}
          {profileEverVisited && session && assignment ? (
            <OrganizationPanel
              active={activeView === "profile"}
              user={session.user}
              assignment={assignment}
              client={onboardingClient}
              logout={logout}
              onLoggedOut={onLoggedOut}
            />
          ) : null}
        </section>

        {activeView === "conversation" ? (
          <div
            className="composer-wrap"
            data-testid="composer-region"
            aria-live="polite"
          >
          {latestMaterial ? (
            <article className="material-receipt">
              <div className="material-receipt-heading">
                <FileText aria-hidden="true" />
                <strong>{latestMaterial.file_name}</strong>
                <span>
                  {latestMaterial.status === "processing"
                    ? "正在理解"
                    : latestMaterial.status === "ready"
                      ? "可以使用"
                      : "需要关注"}
                </span>
              </div>
              <p>{latestMaterial.understanding.summary}</p>
              <a
                href={latestMaterial.original.url}
                target="_blank"
                rel="noreferrer"
              >
                查看原文
              </a>
              {latestMaterial.status === "needs_attention" ? (
                <button
                  className="material-retry-button"
                  type="button"
                  aria-label="重新理解资料"
                  disabled={isRetryingUnderstanding}
                  onClick={() => void retryMaterialUnderstanding(latestMaterial)}
                >
                  {isRetryingUnderstanding ? "正在理解" : "重新理解"}
                </button>
              ) : null}
              {understandingRetryFailed ? (
                <span className="material-retry-error" role="alert">
                  理解没有完成，可稍后重试
                </span>
              ) : null}
            </article>
          ) : null}
          {uploadingFileName ? (
            <div className="material-progress" role="status">
              <span aria-hidden="true" />
              <span>正在接收{uploadingFileName}</span>
            </div>
          ) : null}
          {failedMaterial ? (
            <div className="material-error" role="alert">
              <span>{failedMaterial.file.name} 没有上传完成</span>
              <button
                type="button"
                aria-label="重新上传"
                onClick={() =>
                  void uploadMaterial(
                    failedMaterial.file,
                    failedMaterial.clientUploadId,
                  )
                }
              >
                重试
              </button>
            </div>
          ) : null}
          <form
            className="composer"
            data-testid="composer"
            aria-label="HXYOS 对话输入"
            onSubmit={handleSubmit}
          >
            <textarea
              value={draft}
              rows={2}
              aria-label="告诉 HXYOS 你要做什么"
              placeholder="告诉 HXYOS 你要做什么"
              disabled={!isAuthenticated || isSending}
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="composer-actions">
              <input
                ref={materialInputRef}
                className="visually-hidden"
                type="file"
                tabIndex={-1}
                accept=".csv,.doc,.docx,.jpeg,.jpg,.json,.md,.pdf,.png,.ppt,.pptx,.txt,.webp,.xls,.xlsx"
                disabled={
                  !isAuthenticated || !canCreateMaterials || !!uploadingFileName
                }
                onChange={handleMaterialSelection}
              />
              <button
                className="icon-button attachment-button"
                type="button"
                aria-label="添加资料"
                title="添加资料"
                disabled={
                  !isAuthenticated || !canCreateMaterials || !!uploadingFileName
                }
                onClick={() => materialInputRef.current?.click()}
              >
                <Paperclip aria-hidden="true" />
              </button>
              <button
                className="icon-button send-button"
                type="submit"
                aria-label="发送"
                title="发送"
                disabled={!isAuthenticated || isSending || !draft.trim()}
              >
                <ArrowUp aria-hidden="true" />
              </button>
            </div>
          </form>
          </div>
        ) : null}
      </main>

      {isDetailsOpen ? (
        <aside
          ref={detailsDrawerRef}
          className="details-drawer"
          role="dialog"
          aria-label="当前对话详情"
          aria-modal="true"
          tabIndex={-1}
          onKeyDown={handleDetailsKeyDown}
        >
          <header>
            <div>
              <span className="drawer-eyebrow">当前对话</span>
              <h2>对话详情</h2>
            </div>
            <button
              ref={detailsCloseRef}
              className="icon-button"
              type="button"
              aria-label="关闭当前对话详情"
              title="关闭当前对话详情"
              onClick={() => setIsDetailsOpen(false)}
            >
              <X aria-hidden="true" />
            </button>
          </header>
          {latestAnswer ? (
            <div className="answer-details">
              <dl>
                <div>
                  <dt>状态</dt>
                  <dd>{latestAnswer.answer_status || "待确认"}</dd>
                </div>
                <div>
                  <dt>可靠程度</dt>
                  <dd>
                    {latestAnswer.confidence === "high"
                      ? "较高"
                      : latestAnswer.confidence === "medium"
                        ? "一般"
                        : "需核对"}
                  </dd>
                </div>
              </dl>
              {latestAnswer.sources.length > 0 ? (
                <section aria-label="回答来源">
                  <h3>来源</h3>
                  <ul className="source-list">
                    {latestAnswer.sources.map((source, index) => (
                      <li key={`${source.title}-${index}`}>
                        <strong>{source.title}</strong>
                        {source.excerpt ? <p>{source.excerpt}</p> : null}
                        {source.url ? (
                          <a
                            href={source.url}
                            target="_blank"
                            rel="noreferrer"
                            aria-label={`查看${source.title}`}
                          >
                            查看资料
                          </a>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </div>
          ) : (
            <div className="drawer-empty">
              <Info aria-hidden="true" />
              <p>发送问题后，这里会显示回答状态和来源</p>
            </div>
          )}
        </aside>
      ) : null}
    </div>
  );
}

interface AppProps {
  initialSession?: MeResponse;
  sessionLoader?: SessionLoader;
  grantExchanger?: SessionGrantExchanger;
  conversationClient?: ConversationClient;
  materialClient?: MaterialClient;
  taskClient?: TaskClient;
  journeyClient?: JourneyClient;
  clientMessageIdFactory?: () => string;
  materialUploadIdFactory?: () => string;
  onboardingClient?: OnboardingClient;
  logout?: () => Promise<void>;
  onLoggedOut?: () => void;
}

function reloadAfterLogout() {
  window.location.reload();
}

export default function App({
  initialSession,
  sessionLoader,
  grantExchanger,
  conversationClient = productConversationClient,
  materialClient = productMaterialClient,
  taskClient = productTaskClient,
  journeyClient = productJourneyClient,
  clientMessageIdFactory = () => crypto.randomUUID(),
  materialUploadIdFactory = () => crypto.randomUUID(),
  onboardingClient = productOnboardingClient,
  logout = logoutSession,
  onLoggedOut = reloadAfterLogout,
}: AppProps) {
  return (
    <SessionProvider
      loader={sessionLoader}
      grantExchanger={grantExchanger}
      initialSession={initialSession}
    >
      <ProductShell
        conversationClient={conversationClient}
        materialClient={materialClient}
        taskClient={taskClient}
        journeyClient={journeyClient}
        clientMessageIdFactory={clientMessageIdFactory}
        materialUploadIdFactory={materialUploadIdFactory}
        onboardingClient={onboardingClient}
        logout={logout}
        onLoggedOut={onLoggedOut}
      />
    </SessionProvider>
  );
}
