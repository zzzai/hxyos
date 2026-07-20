export interface LearningAction {
  id: string;
  title: string;
  purpose: string;
  estimated_minutes: number;
  scenario: { customer_message: string };
  response_modes: Array<"text" | "voice">;
}

export interface PrivateLearningProgress {
  visibility: "private";
  attempts: number;
  mastered: string[];
  practicing: string[];
  needs_attention: string[];
}

export interface LearningHome {
  next_action: LearningAction;
  progress: PrivateLearningProgress;
  limitations: string[];
}

export interface LearningPracticeResult extends LearningHome {
  attempt: {
    id: string;
    score: number;
    level: "excellent" | "pass" | "retrain";
    needs_retrain: boolean;
    standard_script: string;
    correction_points: string[];
    physical_technique: "not_assessed";
  };
}

export interface LearningClient {
  loadLearning: () => Promise<LearningHome>;
  submitPractice: (request: {
    action_id: string;
    employee_answer: string;
  }) => Promise<LearningPracticeResult>;
}

async function learningRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new Error("Learning request failed");
  return (await response.json()) as T;
}

export const productLearningClient: LearningClient = {
  loadLearning: () => learningRequest("/api/v1/learning"),
  submitPractice: (request) =>
    learningRequest("/api/v1/learning/practice", {
      method: "POST",
      body: JSON.stringify(request),
    }),
};
