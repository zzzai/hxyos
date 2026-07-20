import { isRecordEvidence, type RecordEvidence } from "./records";


export type TodayBriefKind = "risk" | "decision" | "progress";
export type TodayBriefSeverity = "low" | "medium" | "high" | "critical";

export interface TodayNextAction {
  type: "open_record" | "ask_about_record";
  label: string;
  prompt: string | null;
}

export interface TodayBriefItem {
  id: string;
  kind: TodayBriefKind;
  severity: TodayBriefSeverity | null;
  statement: string;
  why_it_matters: string;
  source_record_id: string;
  evidence: RecordEvidence[];
  captured_at: string;
  next_action: TodayNextAction;
}

export interface TodayResponse {
  items: TodayBriefItem[];
}

export interface TodayClient {
  getToday: (limit?: number) => Promise<TodayResponse>;
}

export class TodayRequestError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail = "Today request failed") {
    super(detail);
    this.name = "TodayRequestError";
    this.status = status;
    this.detail = detail;
  }
}

function boundedLimit(value: number): number {
  if (!Number.isFinite(value)) return 3;
  return Math.max(1, Math.min(Math.trunc(value), 3));
}

function isTodayResponse(value: unknown): value is TodayResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every(isTodayBriefItem)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isTodayBriefItem(value: unknown): value is TodayBriefItem {
  if (!isRecord(value)) return false;
  const action = value.next_action;
  return (
    typeof value.id === "string" &&
    (value.kind === "risk" ||
      value.kind === "decision" ||
      value.kind === "progress") &&
    (value.severity === null ||
      value.severity === "low" ||
      value.severity === "medium" ||
      value.severity === "high" ||
      value.severity === "critical") &&
    typeof value.statement === "string" &&
    typeof value.why_it_matters === "string" &&
    typeof value.source_record_id === "string" &&
    Array.isArray(value.evidence) &&
    value.evidence.every(isRecordEvidence) &&
    typeof value.captured_at === "string" &&
    isRecord(action) &&
    (action.type === "open_record" || action.type === "ask_about_record") &&
    typeof action.label === "string" &&
    isNullableString(action.prompt)
  );
}

function responseDetail(payload: unknown, fallback: string): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string" &&
    payload.detail.trim()
  ) {
    return payload.detail.trim();
  }
  if (
    isRecord(payload) &&
    Array.isArray(payload.detail) &&
    payload.detail.length > 0
  ) {
    const first = payload.detail[0];
    if (isRecord(first) && typeof first.msg === "string" && first.msg.trim()) {
      const field = Array.isArray(first.loc)
        ? [...first.loc].reverse().find((part) => typeof part === "string")
        : undefined;
      return field
        ? `${field}: ${first.msg.trim()}`
        : first.msg.trim();
    }
  }
  return fallback;
}

export const productTodayClient: TodayClient = {
  getToday: async (limit = 3) => {
    const normalizedLimit = boundedLimit(limit);
    const response = await fetch(`/api/v1/today?limit=${normalizedLimit}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        // The HTTP status remains authoritative when the error body is not JSON.
      }
      throw new TodayRequestError(
        response.status,
        responseDetail(payload, "Today request failed"),
      );
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new TodayRequestError(response.status, "Invalid Today response");
    }
    if (!isTodayResponse(payload)) {
      throw new TodayRequestError(response.status, "Invalid Today response");
    }
    return payload;
  },
};
