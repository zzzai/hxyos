export type ServiceContextStatus = "provisional" | "reconciled" | "closed";

export interface ServiceContext {
  id: string;
  status: ServiceContextStatus;
  occurred_at: string;
  service_label: string;
  customer_display: string;
  feedback_count: number;
  created_at: string;
}

export interface ServiceContextListResponse {
  contexts: ServiceContext[];
}

export interface ServiceFeedbackReceipt {
  id: string;
  context_id: string;
  status: "received";
  created_at: string;
}

export interface ServiceFeedbackResponse {
  feedback: ServiceFeedbackReceipt;
  context: ServiceContext;
}

export interface AddServiceFeedbackInput {
  clientFeedbackId: string;
  text: string;
  sourceAssetIds: string[];
}

export interface ServiceClient {
  listRecent: (limit?: number) => Promise<ServiceContextListResponse>;
  addFeedback: (
    contextId: string,
    input: AddServiceFeedbackInput,
  ) => Promise<ServiceFeedbackResponse>;
}

export class ServiceRequestError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail = "Service request failed") {
    super(detail);
    this.name = "ServiceRequestError";
    this.status = status;
    this.detail = detail;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isServiceContext(value: unknown): value is ServiceContext {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    (value.status === "provisional" ||
      value.status === "reconciled" ||
      value.status === "closed") &&
    typeof value.occurred_at === "string" &&
    typeof value.service_label === "string" &&
    typeof value.customer_display === "string" &&
    Number.isInteger(value.feedback_count) &&
    Number(value.feedback_count) >= 0 &&
    typeof value.created_at === "string"
  );
}

function isContextListResponse(value: unknown): value is ServiceContextListResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.contexts) &&
    value.contexts.every(isServiceContext)
  );
}

function isFeedbackResponse(value: unknown): value is ServiceFeedbackResponse {
  if (!isRecord(value) || !isServiceContext(value.context)) return false;
  const feedback = value.feedback;
  return (
    isRecord(feedback) &&
    typeof feedback.id === "string" &&
    typeof feedback.context_id === "string" &&
    feedback.status === "received" &&
    typeof feedback.created_at === "string"
  );
}

function boundedLimit(value: number): number {
  if (!Number.isFinite(value)) return 3;
  return Math.max(1, Math.min(Math.trunc(value), 10));
}

async function serviceRequest(
  path: string,
  validator: (value: unknown) => boolean,
  init?: RequestInit,
): Promise<unknown> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new ServiceRequestError(response.status);
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ServiceRequestError(response.status, "Invalid service response");
  }
  if (!validator(payload)) {
    throw new ServiceRequestError(response.status, "Invalid service response");
  }
  return payload;
}

export const productServiceClient: ServiceClient = {
  listRecent: async (limit = 3) =>
    (await serviceRequest(
      `/api/v1/service-contexts/recent?limit=${boundedLimit(limit)}`,
      isContextListResponse,
    )) as ServiceContextListResponse,
  addFeedback: async (contextId, input) =>
    (await serviceRequest(
      `/api/v1/service-contexts/${encodeURIComponent(contextId)}/feedback`,
      isFeedbackResponse,
      {
        method: "POST",
        body: JSON.stringify({
          client_feedback_id: input.clientFeedbackId,
          text: input.text.trim(),
          source_asset_ids: input.sourceAssetIds,
        }),
      },
    )) as ServiceFeedbackResponse,
};
