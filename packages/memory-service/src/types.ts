export type HxyMemoryType =
  | "claim"
  | "decision"
  | "hypothesis"
  | "validation_task"
  | "review_task"
  | "conflict"
  | "insight";

export type HxyMemoryStatus =
  | "draft"
  | "current_candidate"
  | "confirmed"
  | "validated"
  | "deprecated"
  | "conflicted"
  | "needs_review"
  | "open"
  | "closed";

export type HxyMemoryItem = {
  memoryId: string;
  memoryType: HxyMemoryType;
  title: string;
  body: string;
  projectStage?: string;
  status: HxyMemoryStatus;
  confidence?: number;
  version: string;
  sourceKind: string;
  sourcePath?: string;
  sourceObjectId?: string;
  payload: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  reviewAt?: string;
};

export type HxyMemoryEvidenceLink = {
  memoryId: string;
  evidenceId: string;
  sourcePath?: string;
  snippet?: string;
  payload: Record<string, unknown>;
};

export type HxyMemoryTransition = {
  transitionId?: number;
  memoryId: string;
  fromStatus?: HxyMemoryStatus;
  toStatus: HxyMemoryStatus;
  reason?: string;
  actor?: string;
  payload: Record<string, unknown>;
  createdAt: string;
};

export type HxyMemoryImportRun = {
  importId: string;
  sourceDir: string;
  startedAt: string;
  finishedAt?: string;
  status: "started" | "completed" | "failed";
  itemCount: number;
  payload: Record<string, unknown>;
};

export type HxyMemoryItemFilter = {
  memoryType?: HxyMemoryType;
  status?: HxyMemoryStatus;
  projectStage?: string;
  limit?: number;
};
