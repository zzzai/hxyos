import type { HxyTask } from "./tasks";

export type JourneyActionType =
  | "ask"
  | "tasks"
  | "training"
  | "issue"
  | "material_upload";

export interface JourneySuggestion {
  type: JourneyActionType;
  label: string;
  prompt?: string | null;
}

export interface TrainingJourneyResult {
  result_type: "training_result";
  primary_result: {
    score: number;
    level: string;
    needs_retrain: boolean;
    standard_script: string;
    correction_points: string[];
  };
  actions: Array<{ type: string; label: string }>;
  sources: unknown[];
  limitations: string[];
  artifact: { type: string; id: string } | null;
}

export interface IssueJourneyResult {
  result_type: "issue_report";
  primary_result: {
    task: Pick<
      HxyTask,
      | "id"
      | "title"
      | "details"
      | "priority"
      | "status"
      | "result"
      | "due_at"
      | "completed_at"
      | "created_at"
      | "updated_at"
      | "available_actions"
    >;
  };
  actions: Array<{ type: string; label: string }>;
  sources: unknown[];
  limitations: string[];
  artifact: { type: string; id: string } | null;
}

export interface JourneyClient {
  loadSuggestions: () => Promise<{ items: JourneySuggestion[] }>;
  evaluateTraining: (request: {
    customer_question: string;
    employee_answer: string;
  }) => Promise<TrainingJourneyResult>;
  reportIssue: (request: {
    title: string;
    details: string;
    source_task_id?: string;
  }) => Promise<IssueJourneyResult>;
}

async function journeyRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new Error("Journey request failed");
  return (await response.json()) as T;
}

export const productJourneyClient: JourneyClient = {
  loadSuggestions: () => journeyRequest("/api/v1/journeys/suggestions"),
  evaluateTraining: (request) =>
    journeyRequest("/api/v1/journeys/training/evaluate", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  reportIssue: (request) =>
    journeyRequest("/api/v1/issues", {
      method: "POST",
      body: JSON.stringify(request),
    }),
};
