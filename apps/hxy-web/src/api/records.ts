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
  source_asset_id?: string;
  quote: string;
  locator?: string;
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

  constructor(status: number) {
    super("Organization record request failed");
    this.name = "OrganizationRecordRequestError";
    this.status = status;
  }
}

async function recordRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new OrganizationRecordRequestError(response.status);
  return (await response.json()) as T;
}

export const productRecordClient: OrganizationRecordClient = {
  listRecords: (limit = 50) => {
    const boundedLimit = Math.max(1, Math.min(Math.trunc(limit), 100));
    return recordRequest<OrganizationRecordListResponse>(
      `/api/v1/organization-records?limit=${boundedLimit}`,
    );
  },
  getRecord: (recordId) =>
    recordRequest<OrganizationRecordResponse>(
      `/api/v1/organization-records/${encodeURIComponent(recordId)}`,
    ),
  createRecord: (request) =>
    recordRequest<OrganizationRecordResponse>("/api/v1/organization-records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_record_id: request.clientRecordId,
        text: request.text,
        source_asset_ids: request.sourceAssetIds,
      }),
    }),
};
