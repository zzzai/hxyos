export type RecordSourceType =
  | "text"
  | "link"
  | "image"
  | "audio"
  | "video"
  | "document"
  | "file";

export type RecordProcessingStatus =
  | "received"
  | "processing"
  | "ready"
  | "needs_attention";

export interface RecordEvidence {
  source_record_id: string;
  source_asset_id: string | null;
  quote: string;
  locator: string | null;
}

export interface RecordInterpretationItem {
  statement: string;
  evidence: RecordEvidence[];
}

export interface RecordInterpretation {
  version: string;
  summary: string;
  facts: RecordInterpretationItem[];
  decisions: RecordInterpretationItem[];
  progress: RecordInterpretationItem[];
  risks: RecordInterpretationItem[];
  missing_information: string[];
  confidence: number;
  official_knowledge: false;
}

export interface OrganizationRecordAsset {
  id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  status: RecordProcessingStatus;
}

export interface OrganizationRecord {
  id: string;
  source_types: RecordSourceType[];
  preview: string;
  submitted_by: string;
  store_id: string | null;
  captured_at: string;
  occurred_at: string | null;
  processing_status: RecordProcessingStatus;
  original: {
    text: string;
    assets: OrganizationRecordAsset[];
  };
  interpretation: RecordInterpretation | null;
}

export interface OrganizationRecordResponse {
  record: OrganizationRecord;
}

export interface OrganizationRecordListResponse {
  records: OrganizationRecord[];
}

export interface CreateOrganizationRecordRequest {
  clientRecordId: string;
  text: string;
  sourceAssetIds: string[];
}

export interface OrganizationRecordClient {
  listRecords: (limit?: number) => Promise<OrganizationRecordListResponse>;
  getRecord: (recordId: string) => Promise<OrganizationRecordResponse>;
  createRecord: (
    request: CreateOrganizationRecordRequest,
  ) => Promise<OrganizationRecordResponse>;
}

export class OrganizationRecordRequestError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail = "Organization record request failed") {
    super(detail);
    this.name = "OrganizationRecordRequestError";
    this.status = status;
    this.detail = detail;
  }
}

export class OrganizationRecordInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OrganizationRecordInputError";
  }
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function boundedLimit(value: number, fallback: number, maximum: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(1, Math.min(Math.trunc(value), maximum));
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

async function parseJson(
  response: Response,
  invalidDetail: string,
): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new OrganizationRecordRequestError(response.status, invalidDetail);
  }
}

async function recordRequest<T>(
  path: string,
  init: RequestInit | undefined,
  validate: (payload: unknown) => boolean,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // The HTTP status remains authoritative when the error body is not JSON.
    }
    throw new OrganizationRecordRequestError(
      response.status,
      responseDetail(payload, "Organization record request failed"),
    );
  }
  const payload = await parseJson(response, "Invalid organization record response");
  if (!validate(payload)) {
    throw new OrganizationRecordRequestError(
      response.status,
      "Invalid organization record response",
    );
  }
  return payload as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRecordResponse(value: unknown): boolean {
  return isRecord(value) && isRecord(value.record);
}

function isRecordListResponse(value: unknown): boolean {
  return isRecord(value) && Array.isArray(value.records);
}

function validateCreateRequest(request: CreateOrganizationRecordRequest): void {
  if (!UUID_PATTERN.test(request.clientRecordId)) {
    throw new OrganizationRecordInputError("clientRecordId must be a UUID");
  }
  if (request.text.length > 20_000) {
    throw new OrganizationRecordInputError("text exceeds 20000 characters");
  }
  if (request.sourceAssetIds.length > 20) {
    throw new OrganizationRecordInputError("sourceAssetIds exceeds 20 items");
  }
  if (request.sourceAssetIds.some((assetId) => !UUID_PATTERN.test(assetId))) {
    throw new OrganizationRecordInputError("sourceAssetIds must contain UUIDs");
  }
  if (!request.text.trim() && request.sourceAssetIds.length === 0) {
    throw new OrganizationRecordInputError("text or sourceAssetIds is required");
  }
}

export const productRecordClient: OrganizationRecordClient = {
  listRecords: (limit = 50) => {
    const normalizedLimit = boundedLimit(limit, 50, 100);
    return recordRequest<OrganizationRecordListResponse>(
      `/api/v1/organization-records?limit=${normalizedLimit}`,
      undefined,
      isRecordListResponse,
    );
  },
  getRecord: (recordId) =>
    recordRequest<OrganizationRecordResponse>(
      `/api/v1/organization-records/${encodeURIComponent(recordId)}`,
      undefined,
      isRecordResponse,
    ),
  createRecord: async (request) => {
    validateCreateRequest(request);
    return recordRequest<OrganizationRecordResponse>(
      "/api/v1/organization-records",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_record_id: request.clientRecordId,
          text: request.text,
          source_asset_ids: request.sourceAssetIds,
        }),
      },
      isRecordResponse,
    );
  },
};
