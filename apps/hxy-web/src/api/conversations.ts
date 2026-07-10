export type ConversationRole = "user" | "assistant";

export interface AnswerSource {
  title: string;
  excerpt: string;
  strength: string;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: ConversationRole;
  content: string;
  created_at: string;
  answer_id: string | null;
  answer_status: string | null;
  confidence: string | null;
  needs_review: boolean | null;
  sources: AnswerSource[];
  next_actions: string[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  message_count: number;
  last_message: ConversationMessage | null;
}

export interface ConversationDetailResponse {
  conversation: ConversationSummary;
  messages: ConversationMessage[];
}

export interface CreateConversationResponse {
  conversation: ConversationSummary;
}

export interface ConversationListResponse {
  items: ConversationSummary[];
}

export interface SendMessageRequest {
  content: string;
  client_message_id: string;
}

export interface SendMessageResponse {
  conversation: ConversationSummary;
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
}

export interface ConversationClient {
  listConversations: () => Promise<ConversationListResponse>;
  getConversation: (
    conversationId: string,
  ) => Promise<ConversationDetailResponse>;
  createConversation: () => Promise<CreateConversationResponse>;
  sendMessage: (
    conversationId: string,
    request: SendMessageRequest,
  ) => Promise<SendMessageResponse>;
}

export class ConversationRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("Conversation request failed");
    this.name = "ConversationRequestError";
    this.status = status;
  }
}

async function productRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");

  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new ConversationRequestError(response.status);
  return (await response.json()) as T;
}

export const productConversationClient: ConversationClient = {
  listConversations: () =>
    productRequest<ConversationListResponse>("/api/v1/conversations"),
  getConversation: (conversationId) =>
    productRequest<ConversationDetailResponse>(
      `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
    ),
  createConversation: () =>
    productRequest<CreateConversationResponse>("/api/v1/conversations", {
      method: "POST",
      body: "{}",
    }),
  sendMessage: (conversationId, request) =>
    productRequest<SendMessageResponse>(
      `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: "POST",
        body: JSON.stringify(request),
      },
    ),
};
