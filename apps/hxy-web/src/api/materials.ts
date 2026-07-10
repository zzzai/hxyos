export type MaterialStatus =
  | "received"
  | "understood"
  | "understanding_failed";

export interface MaterialReceipt {
  status: "已收到";
  message: string;
}

export interface MaterialOriginal {
  url: string;
  can_preview: boolean;
}

export interface MaterialUnderstanding {
  summary: string;
  document_type: string;
  source_origin: "internal" | "external" | "unknown";
  authority_level:
    | "working_material"
    | "claimed_official"
    | "reference"
    | "fragment";
  knowledge_scale: "macro" | "meso" | "micro" | "unknown";
  domain:
    | "brand"
    | "product"
    | "operations"
    | "store"
    | "customer"
    | "finance"
    | "organization"
    | "compliance"
    | "external"
    | "general";
  parse_status:
    | "extracted"
    | "metadata_only"
    | "needs_multimodal"
    | "needs_deep_parse";
  confidence: "high" | "medium" | "low";
  warnings: string[];
  official_use_allowed: false;
  use_boundary: string;
}

export interface ProductMaterial {
  id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  status: MaterialStatus;
  receipt: MaterialReceipt;
  original: MaterialOriginal;
  understanding: MaterialUnderstanding;
  created_at: string;
  updated_at: string;
}

export interface MaterialListResponse {
  items: ProductMaterial[];
  count: number;
}

export interface UploadMaterialResponse {
  material: ProductMaterial;
}

export interface MaterialClient {
  listMaterials: () => Promise<MaterialListResponse>;
  uploadMaterial: (
    file: File,
    note: string,
    clientUploadId: string,
  ) => Promise<UploadMaterialResponse>;
  retryUnderstanding: (materialId: string) => Promise<UploadMaterialResponse>;
}

export class MaterialRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("Material request failed");
    this.name = "MaterialRequestError";
    this.status = status;
  }
}

async function materialRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw new MaterialRequestError(response.status);
  return (await response.json()) as T;
}

export const productMaterialClient: MaterialClient = {
  listMaterials: () =>
    materialRequest<MaterialListResponse>("/api/v1/materials?limit=1"),
  uploadMaterial: (file, note, clientUploadId) => {
    const body = new FormData();
    body.set("file", file);
    body.set("note", note);
    body.set("client_upload_id", clientUploadId);
    return materialRequest<UploadMaterialResponse>("/api/v1/materials", {
      method: "POST",
      body,
    });
  },
  retryUnderstanding: (materialId) =>
    materialRequest<UploadMaterialResponse>(
      `/api/v1/materials/${encodeURIComponent(materialId)}/understanding`,
      { method: "POST" },
    ),
};
