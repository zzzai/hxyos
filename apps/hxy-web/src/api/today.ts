import type { RecordEvidence } from "./records";


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
    typeof value === "object" &&
    value !== null &&
    "items" in value &&
    Array.isArray(value.items)
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
