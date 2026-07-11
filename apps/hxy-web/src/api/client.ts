export type CanonicalRole =
  | "founder"
  | "hq_operations"
  | "store_manager"
  | "store_employee"
  | "system_admin";

export interface UserContext {
  account_id: string;
  display_name: string;
}

export interface OrganizationContext {
  id: string;
  name: string;
}

export interface StoreContext {
  id: string;
  name: string;
}

export interface AssignmentContext {
  assignment_id: string;
  organization: OrganizationContext;
  store: StoreContext | null;
  role: CanonicalRole;
  role_label: string;
  capabilities: string[];
}

export interface MeResponse {
  user: UserContext;
  active_assignment: AssignmentContext;
  available_assignments: AssignmentContext[];
}

export class MeRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "MeRequestError";
    this.status = status;
  }
}

export async function exchangeSessionGrant(grant: string): Promise<void> {
  const response = await fetch("/api/v1/auth/session-grant", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ grant }),
  });
  if (!response.ok) {
    throw new MeRequestError(response.status, "Unable to exchange session grant");
  }
}

export async function loadMe(): Promise<MeResponse> {
  // The relative URL intentionally keeps credentialed requests same-origin.
  const response = await fetch("/api/v1/me", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new MeRequestError(response.status, "Unable to load session");
  }
  return (await response.json()) as MeResponse;
}
