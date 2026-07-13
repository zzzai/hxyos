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

export type StoreStatus = "active" | "paused" | "closed";

export interface OrganizationStore {
  id: string;
  name: string;
  city: string;
  address: string;
  status: StoreStatus;
}

export type StoreMemberRole = "store_manager" | "store_employee";

export interface OrganizationMember {
  assignment_id: string;
  store_id: string;
  display_name: string;
  role: StoreMemberRole;
  status: "active" | "inactive";
}

export type InviteRole = StoreMemberRole;

export interface OrganizationInvite {
  id: string;
  store_id: string;
  role: InviteRole;
  display_name: string;
  status: "pending" | "redeemed" | "revoked";
  expires_at: string;
}

export interface CreatedInvite {
  id: string;
  role: InviteRole;
  display_name: string;
  expires_at: string;
}

export interface CreateInviteResult {
  invite: CreatedInvite;
  one_time_link: string;
}

export interface AuthenticatedResponse {
  status: "authenticated";
}

export interface CreateStoreRequest {
  name: string;
  city: string;
  address: string;
}

export interface CreateInviteRequest {
  store_id?: string;
  role: InviteRole;
  display_name: string;
}

export interface OnboardingClient {
  listStores: () => Promise<OrganizationStore[]>;
  createStore: (request: CreateStoreRequest) => Promise<OrganizationStore>;
  listMembers: () => Promise<OrganizationMember[]>;
  listInvites: () => Promise<OrganizationInvite[]>;
  createInvite: (request: CreateInviteRequest) => Promise<CreateInviteResult>;
  revokeInvite: (inviteId: string) => Promise<OrganizationInvite>;
  deactivateMember: (assignmentId: string) => Promise<OrganizationMember>;
  redeemInvite: (token: string) => Promise<AuthenticatedResponse>;
}

export class MeRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "MeRequestError";
    this.status = status;
  }
}

export class OnboardingRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("Onboarding request failed");
    this.name = "OnboardingRequestError";
    this.status = status;
  }
}

type ResponseParser<T> = (payload: unknown) => T;

interface OnboardingRequestOptions {
  method?: "POST";
  body?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredField(
  value: Record<string, unknown>,
  field: string,
): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, field)) {
    throw new Error("Invalid onboarding response");
  }
  return value[field];
}

function requiredString(
  value: Record<string, unknown>,
  field: string,
): string {
  const candidate = requiredField(value, field);
  if (typeof candidate !== "string") {
    throw new Error("Invalid onboarding response");
  }
  return candidate;
}

function requireRecord(payload: unknown): Record<string, unknown> {
  if (!isRecord(payload)) {
    throw new Error("Invalid onboarding response");
  }
  return payload;
}

function isStoreMemberRole(value: string): value is StoreMemberRole {
  return value === "store_manager" || value === "store_employee";
}

function isInviteRole(value: string): value is InviteRole {
  return isStoreMemberRole(value);
}

function isStoreStatus(
  value: string,
): value is OrganizationStore["status"] {
  return value === "active" || value === "paused" || value === "closed";
}

function isMemberStatus(
  value: string,
): value is OrganizationMember["status"] {
  return value === "active" || value === "inactive";
}

function isInviteStatus(
  value: string,
): value is OrganizationInvite["status"] {
  return value === "pending" || value === "redeemed" || value === "revoked";
}

function isIsoTimestamp(value: string): boolean {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(
      value,
    );
  if (match === null) {
    return false;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[7] === undefined ? 0 : Number(match[7]);
  const offsetMinute = match[8] === undefined ? 0 : Number(match[8]);
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return false;
  }

  const leapYear =
    year % 400 === 0 || (year % 4 === 0 && year % 100 !== 0);
  const daysInMonth = [
    31,
    leapYear ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ];
  return day >= 1 && day <= daysInMonth[month - 1];
}

function parseStore(payload: unknown): OrganizationStore {
  const value = requireRecord(payload);
  const status = requiredString(value, "status");
  if (!isStoreStatus(status)) {
    throw new Error("Invalid onboarding response");
  }
  return {
    id: requiredString(value, "id"),
    name: requiredString(value, "name"),
    city: requiredString(value, "city"),
    address: requiredString(value, "address"),
    status,
  };
}

function parseMember(payload: unknown): OrganizationMember {
  const value = requireRecord(payload);
  const role = requiredString(value, "role");
  const status = requiredString(value, "status");
  if (!isStoreMemberRole(role) || !isMemberStatus(status)) {
    throw new Error("Invalid onboarding response");
  }
  return {
    assignment_id: requiredString(value, "assignment_id"),
    store_id: requiredString(value, "store_id"),
    display_name: requiredString(value, "display_name"),
    role,
    status,
  };
}

function parseInvite(payload: unknown): OrganizationInvite {
  const value = requireRecord(payload);
  const role = requiredString(value, "role");
  const status = requiredString(value, "status");
  const expiresAt = requiredString(value, "expires_at");
  if (
    !isInviteRole(role) ||
    !isInviteStatus(status) ||
    !isIsoTimestamp(expiresAt)
  ) {
    throw new Error("Invalid onboarding response");
  }
  return {
    id: requiredString(value, "id"),
    store_id: requiredString(value, "store_id"),
    role,
    display_name: requiredString(value, "display_name"),
    status,
    expires_at: expiresAt,
  };
}

function parseCreatedInvite(payload: unknown): CreatedInvite {
  const value = requireRecord(payload);
  const role = requiredString(value, "role");
  const expiresAt = requiredString(value, "expires_at");
  if (!isInviteRole(role) || !isIsoTimestamp(expiresAt)) {
    throw new Error("Invalid onboarding response");
  }
  return {
    id: requiredString(value, "id"),
    role,
    display_name: requiredString(value, "display_name"),
    expires_at: expiresAt,
  };
}

function parseList<T>(payload: unknown, parseItem: ResponseParser<T>): T[] {
  if (!Array.isArray(payload)) {
    throw new Error("Invalid onboarding response");
  }
  return payload.map((item) => parseItem(item));
}

function parseStores(payload: unknown): OrganizationStore[] {
  return parseList(payload, parseStore);
}

function parseMembers(payload: unknown): OrganizationMember[] {
  return parseList(payload, parseMember);
}

function parseInvites(payload: unknown): OrganizationInvite[] {
  return parseList(payload, parseInvite);
}

function parseCreateInviteResult(payload: unknown): CreateInviteResult {
  const value = requireRecord(payload);
  return {
    invite: parseCreatedInvite(requiredField(value, "invite")),
    one_time_link: requiredString(value, "one_time_link"),
  };
}

function parseAuthenticatedResponse(payload: unknown): AuthenticatedResponse {
  const value = requireRecord(payload);
  if (requiredString(value, "status") !== "authenticated") {
    throw new Error("Invalid onboarding response");
  }
  return { status: "authenticated" };
}

async function onboardingRequest<T>(
  path: string,
  parse: ResponseParser<T>,
  options?: OnboardingRequestOptions,
): Promise<T> {
  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (options?.method === "POST") {
    headers.set("Content-Type", "application/json");
  }

  const init: RequestInit = {
    credentials: "include",
    headers,
  };
  if (options?.method !== undefined) {
    init.method = options.method;
  }
  if (options?.body !== undefined) {
    init.body = options.body;
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new OnboardingRequestError(0);
  }
  if (!response.ok) {
    throw new OnboardingRequestError(response.status);
  }

  try {
    const payload: unknown = await response.json();
    return parse(payload);
  } catch {
    throw new OnboardingRequestError(response.status);
  }
}

export const productOnboardingClient: OnboardingClient = {
  listStores: () =>
    onboardingRequest("/api/v1/organization/stores", parseStores),
  createStore: (request) =>
    onboardingRequest("/api/v1/organization/stores", parseStore, {
      method: "POST",
      body: JSON.stringify({
        name: request.name,
        city: request.city,
        address: request.address,
      }),
    }),
  listMembers: () =>
    onboardingRequest("/api/v1/organization/members", parseMembers),
  listInvites: () =>
    onboardingRequest("/api/v1/organization/invites", parseInvites),
  createInvite: (request) => {
    const payload: CreateInviteRequest = {
      role: request.role,
      display_name: request.display_name,
    };
    if (request.store_id !== undefined) {
      payload.store_id = request.store_id;
    }
    return onboardingRequest(
      "/api/v1/organization/invites",
      parseCreateInviteResult,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  },
  revokeInvite: (inviteId) =>
    onboardingRequest(
      `/api/v1/organization/invites/${encodeURIComponent(inviteId)}/revoke`,
      parseInvite,
      { method: "POST" },
    ),
  deactivateMember: (assignmentId) =>
    onboardingRequest(
      `/api/v1/organization/members/${encodeURIComponent(assignmentId)}/deactivate`,
      parseMember,
      { method: "POST" },
    ),
  redeemInvite: (token) =>
    onboardingRequest(
      "/api/v1/onboarding/invites/redeem",
      parseAuthenticatedResponse,
      {
        method: "POST",
        body: JSON.stringify({ token }),
      },
    ),
};

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

export async function logoutSession(): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new MeRequestError(0, "Unable to log out");
  }
  if (!response.ok) {
    throw new MeRequestError(response.status, "Unable to log out");
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
