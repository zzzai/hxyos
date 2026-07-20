import type { RecordEvidence } from "./records";


export type TodayBriefKind = "risk" | "decision" | "progress";
export type TodayBriefSeverity = "low" | "medium" | "high" | "critical";

export interface TodayNextAction {
  type: "open_record" | "ask_about_record";
  label: string;
  prompt?: string;
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

  constructor(status: number) {
    super("Today request failed");
    this.name = "TodayRequestError";
    this.status = status;
  }
}

export const productTodayClient: TodayClient = {
  getToday: async (limit = 3) => {
    const boundedLimit = Math.max(1, Math.min(Math.trunc(limit), 3));
    const response = await fetch(`/api/v1/today?limit=${boundedLimit}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new TodayRequestError(response.status);
    return (await response.json()) as TodayResponse;
  },
};
