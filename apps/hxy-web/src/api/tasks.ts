export type TaskPriority = "low" | "normal" | "high" | "urgent";
export type TaskStatus = "open" | "in_progress" | "completed" | "cancelled";
export type TaskVisibility = "assignee" | "store";

export interface HxyTask {
  id: string;
  title: string;
  details: string;
  priority: TaskPriority;
  status: TaskStatus;
  visibility: TaskVisibility;
  store_id: string | null;
  assignee_assignment_id: string | null;
  source_conversation_id: string | null;
  source_message_id: string | null;
  result: string | null;
  due_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  available_actions?: "complete"[];
}

export interface CreateTaskRequest {
  title: string;
  details?: string;
  priority?: TaskPriority;
  visibility: TaskVisibility;
  assignee_assignment_id?: string;
  store_id?: string;
  source_conversation_id?: string;
  source_message_id?: string;
  due_at?: string;
}

export interface UpdateTaskRequest {
  status: "in_progress" | "completed" | "cancelled";
  result?: string;
}

export interface TaskClient {
  listTasks: () => Promise<{ items: HxyTask[]; count: number }>;
  createTask: (request: CreateTaskRequest) => Promise<{ task: HxyTask }>;
  updateTask: (
    taskId: string,
    request: UpdateTaskRequest,
  ) => Promise<{ task: HxyTask }>;
}

class TaskRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("Task request failed");
    this.name = "TaskRequestError";
    this.status = status;
  }
}

async function taskRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new TaskRequestError(response.status);
  return (await response.json()) as T;
}

export const productTaskClient: TaskClient = {
  listTasks: () => taskRequest("/api/v1/tasks"),
  createTask: (request) =>
    taskRequest("/api/v1/tasks", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  updateTask: (taskId, request) =>
    taskRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      body: JSON.stringify(request),
    }),
};
