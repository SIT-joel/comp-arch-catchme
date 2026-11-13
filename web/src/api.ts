// API client: cookie session + CSRF token for mutations (see docs/INTERFACES.md).

export interface UserSummary {
  id: string;
  username: string;
  display_name: string;
  points: number;
  lifetime_xp: number;
  level: number;
}

export interface PartnerSummary {
  id: string;
  display_name: string;
  level: number;
  location_sharing: boolean;
}

export interface DeviceSummary {
  id: string;
  name: string;
  firmware_alias: number;
  claimed_at: string | null;
}

export interface Me {
  user: UserSummary;
  partner: PartnerSummary | null;
  device: DeviceSummary | null;
  pet: PetSummary | null;
}

// --- Pet (v2) ---

export interface PetSummary {
  species: "spark" | "fluff" | "pip" | null;
  name: string | null;
  level: number;
  lifetime_xp: number;
  evolution_stage: 1 | 2 | 3;
  care_streak: number;
  cared_today: boolean;
  last_care_date: string | null;
}

export interface Landmark {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius_m: number;
}

export interface Quest {
  quest_id: "together" | "explore" | "raid" | "quiz" | "heart_challenge";
  name: string;
  description: string;
  evidence: string;
  normal_duration_ms: number;
  demo_duration_ms: number;
  geofence_configured: boolean;
}

export interface Participant {
  user_id: string;
  display_name: string;
  accepted: boolean;
}

export interface Session {
  id: string;
  quest_id: Quest["quest_id"];
  demo: boolean;
  state: "pending" | "active" | "completed" | "cancelled";
  created_by: string;
  created_at: string;
  activated_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  target_ms: number | null;
  progress_ms: number;
  participants: Participant[];
  token: string | null;
  geofence: { latitude: number; longitude: number; radius_m: number | null } | null;
  landmark: { id: string; name: string; latitude: number; longitude: number; radius_m: number } | null;
  raid_outcome: "win" | "lose" | null;
}

export interface Interaction {
  session_id: string;
  quest_id: Quest["quest_id"];
  version: number;
  phase: string;
  phase_started_at: string | null;
  timing_started_at: string | null;
  progress_ms: number;
  target_ms: number;
  completed_evidence_ms: number;
  stage: "start" | "end" | null;
  own_code: string | null;
  own_code_version: number | null;
  own_code_expires_at: string | null;
  own_code_confirmed_by_partner: boolean;
  partner_code_version: number | null;
  partner_code_expires_at: string | null;
  partner_code_confirmed_by_me: boolean;
  round_index: number;
  active_user_id: string | null;
  prompt_kind: "truth" | "dare" | null;
  prompt_id: string | null;
  prompt: string | null;
  results: Record<string, unknown>;
}

export interface Reward {
  id: string;
  name: string;
  description: string;
  price: number;
  owned: boolean;
}

export interface Transaction {
  id: number;
  kind: string;
  delta: number;
  xp_delta: number;
  balance_after: number;
  session_id: string | null;
  reward_id: string | null;
  created_at: string;
}

export interface Reading {
  user_id: string;
  is_self: boolean;
  captured_at: string;
  heart_rate: { valid: boolean; bpm: number | null; status: string | null };
  gps: { valid: boolean };
  peer: { observed: boolean };
}

// --- Nearby discovery (docs/DISCOVERY_PLAN.md) ---

export const INTEREST_TAGS = [
  "gaming", "music", "fitness", "food", "movies", "travel", "reading", "outdoors",
] as const;

export interface DiscoveryProfile {
  display_name: string;
  age: number | null;
  pref_min_age: number | null;
  pref_max_age: number | null;
  interests: string[];
  radius_m: number;
  bluetooth_enabled: boolean;
  gps_enabled: boolean;
  complete: boolean;
}

export interface DiscoveryNotice {
  code: string;
  message: string;
  age_seconds?: number | null;
}

export interface DiscoveryResult {
  user_id: string;
  display_name: string;
  shared_interests: string[];
  shared_count: number;
  sources: ("bluetooth" | "gps")[];
  bluetooth: { label: string; observed_at: string } | null;
  gps: {
    distance_m: number;
    freshness: "fresh" | "last_known";
    my_age_seconds: number | null;
    their_age_seconds: number | null;
    labels: string[];
  } | null;
}

export interface DiscoverySnapshot {
  generated_at: string;
  position_state: "fresh" | "last_known" | "expired" | "missing";
  notices: DiscoveryNotice[];
  results: DiscoveryResult[];
}

export interface Invitation {
  id: string;
  from_user_id: string;
  from_name: string;
  to_user_id: string;
  to_name: string;
  status: string;
  created_at: string;
  expires_at: string;
  responded_at: string | null;
}

export interface PartnershipInfo {
  id: string;
  since: string;
  ended_at: string | null;
  ended_by: string | null;
  partner: PartnerSummary | null;
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let csrfToken: string | null = localStorage.getItem("csrf_token");

export function setCsrfToken(token: string) {
  csrfToken = token;
  localStorage.setItem("csrf_token", token);
}

async function request<T>(method: string, path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
  const headers: Record<string, string> = { ...(extraHeaders ?? {}) };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken && method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string } }).error;
    throw new ApiError(response.status, err?.code ?? "error", err?.message ?? response.statusText);
  }
  return data as T;
}

export const api = {
  login: async (username: string, password: string) => {
    const out = await request<{ user: UserSummary; token: string; csrf_token: string; expires_at: string }>(
      "POST",
      "/auth/login",
      { username, password },
    );
    setCsrfToken(out.csrf_token);
    return out;
  },
  logout: () => request<void>("POST", "/auth/logout"),
  me: () => request<Me>("GET", "/me"),
  quests: () => request<{ quests: Quest[] }>("GET", "/quests"),
  setLocationSharing: (enabled: boolean) => request<void>("PUT", "/me/location-sharing", { enabled }),
  createSession: (questId: string, demo: boolean, landmarkId?: string) =>
    request<Session>("POST", "/sessions", {
      quest_id: questId,
      demo,
      ...(landmarkId ? { landmark_id: landmarkId } : {}),
    }),
  landmarks: () => request<{ landmarks: Landmark[] }>("GET", "/landmarks"),
  pet: () => request<PetSummary>("GET", "/me/pet"),
  updatePet: (species: string, name: string) =>
    request<PetSummary>("PUT", "/me/pet", { species, name }),
  petCare: (date: string) =>
    request<PetSummary>("POST", "/me/pet/care", { date }),
  acceptSession: (id: string) => request<Session>("POST", `/sessions/${id}/accept`),
  cancelSession: (id: string) => request<Session>("POST", `/sessions/${id}/cancel`),
  getSession: (id: string) => request<Session>("GET", `/sessions/${id}`),
  interaction: (id: string) => request<Interaction>("GET", `/sessions/${id}/interaction`),
  submitPin: (id: string, stage: "start" | "end", pin: string, codeVersion: number) =>
    request<Interaction>("POST", `/sessions/${id}/interaction/pin/submit`, {
      stage, pin, code_version: codeVersion, command_id: crypto.randomUUID(),
    }),
  refreshPin: (id: string, stage: "start" | "end") =>
    request<Interaction>("POST", `/sessions/${id}/interaction/pin/refresh`, {
      stage, command_id: crypto.randomUUID(),
    }),
  // v2 removed the heart-quest choice/skip routes.
  listSessions: () => request<{ sessions: Session[] }>("GET", "/sessions"),
  readings: (id: string) => request<{ session_id: string; readings: Reading[] }>("GET", `/sessions/${id}/readings`),
  rewards: () => request<{ points: number; rewards: Reward[] }>("GET", "/rewards"),
  purchase: (rewardId: string, idempotencyKey: string) =>
    request<{ reward_id: string; price: number; balance_after: number; owned: boolean }>(
      "POST",
      "/purchases",
      { reward_id: rewardId },
      { "Idempotency-Key": idempotencyKey },
    ),
  transactions: () => request<{ transactions: Transaction[] }>("GET", "/transactions"),

  // Discovery (docs/DISCOVERY_PLAN.md)
  discoveryProfile: () => request<DiscoveryProfile>("GET", "/me/discovery-profile"),
  putDiscoveryProfile: (p: {
    display_name: string; age: number; pref_min_age: number; pref_max_age: number;
    interests: string[]; radius_m: number;
  }) => request<DiscoveryProfile>("PUT", "/me/discovery-profile", p),
  putDiscoverySettings: (bluetooth_enabled: boolean, gps_enabled: boolean) =>
    request<DiscoveryProfile>("PUT", "/me/discovery-settings", { bluetooth_enabled, gps_enabled }),
  discovery: () => request<DiscoverySnapshot>("GET", "/me/discovery"),
  invitations: () => request<{ incoming: Invitation[]; outgoing: Invitation[] }>("GET", "/invitations"),
  createInvitation: (toUserId: string) => request<Invitation>("POST", "/invitations", { to_user_id: toUserId }),
  acceptInvitation: (id: string) => request<PartnershipInfo>("POST", `/invitations/${id}/accept`),
  declineInvitation: (id: string) => request<Invitation>("POST", `/invitations/${id}/decline`),
  partnership: () => request<PartnershipInfo>("GET", "/me/partnership"),
  endPartnership: () => request<PartnershipInfo>("DELETE", "/me/partnership"),
};
