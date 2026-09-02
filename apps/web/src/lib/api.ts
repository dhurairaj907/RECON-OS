import {
  DashboardMetrics,
  RevenueEvent,
  Payment,
  Customer,
  RecoveryCase,
  AuditLog,
  PaginatedResponse,
  SimulateEventRequest,
  SimulateEventResponse,
  IntelligenceEnvelope,
  IntelligenceListItem,
  IntentEnvelope,
  RecoveryAction,
  ProposeActionResponse,
  ExecuteActionResponse,
  ReconcileActionResponse,
  AnalyticsMetrics,
  PolicyOverview,
  MeResponse,
  MessageResponse,
  OrgUserListResponse,
  OrgUser,
  Communication,
  CommunicationListResponse,
  SendCommunicationResponse,
  AiPredictionsResponse,
  ConnectionsOverview,
  PaymentReconciliation,
  ReconciliationMismatchListResponse,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetcher<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    cache: "no-store",
    // Session auth is an httponly cookie — every request must carry it.
    credentials: "include",
  });

  if (res.status === 401 && typeof window !== "undefined" && !endpoint.startsWith("/api/v1/auth/")) {
    // The backend is the sole authority here — this only redirects the UI;
    // it never grants access. Avoid looping if already on the session page.
    if (!window.location.pathname.startsWith("/session-expired") && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/session-expired";
    }
  }

  if (!res.ok) {
    let errorMessage = `API Error: ${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorMessage = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {}
    throw new Error(errorMessage);
  }

  return res.json();
}

export const api = {
  // Dashboard
  getDashboardMetrics: () => fetcher<DashboardMetrics>("/api/v1/dashboard/metrics"),

  // Events
  getEvents: (params?: { page?: number; limit?: number; event_type?: string; status?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.event_type) q.set("event_type", params.event_type);
    if (params?.status) q.set("status", params.status);
    if (params?.search) q.set("search", params.search);
    return fetcher<PaginatedResponse<RevenueEvent>>(`/api/v1/events?${q.toString()}`);
  },
  getEventById: (id: string) => fetcher<RevenueEvent>(`/api/v1/events/${id}`),

  // Payments
  getPayments: (params?: { page?: number; limit?: number; status?: string; method?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.status) q.set("status", params.status);
    if (params?.method) q.set("method", params.method);
    if (params?.search) q.set("search", params.search);
    return fetcher<PaginatedResponse<Payment>>(`/api/v1/payments?${q.toString()}`);
  },
  getPaymentById: (id: string) => fetcher<Payment>(`/api/v1/payments/${id}`),

  // Customers
  getCustomers: (params?: { page?: number; limit?: number; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.search) q.set("search", params.search);
    return fetcher<PaginatedResponse<Customer>>(`/api/v1/customers?${q.toString()}`);
  },
  getCustomerById: (id: string) => fetcher<Customer>(`/api/v1/customers/${id}`),

  // Recovery Cases
  getRecoveryCases: (params?: { page?: number; limit?: number; status?: string; priority?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.status) q.set("status", params.status);
    if (params?.priority) q.set("priority", params.priority);
    if (params?.search) q.set("search", params.search);
    return fetcher<PaginatedResponse<RecoveryCase>>(`/api/v1/recovery-cases?${q.toString()}`);
  },
  getRecoveryCaseById: (id: string) => fetcher<RecoveryCase>(`/api/v1/recovery-cases/${id}`),

  // Audit Logs
  getAuditLogs: (params?: { page?: number; limit?: number; action?: string; actor?: string; search?: string; caseId?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.action) q.set("action", params.action);
    if (params?.actor) q.set("actor", params.actor);
    if (params?.search) q.set("search", params.search);
    if (params?.caseId) q.set("case_id", params.caseId);
    return fetcher<PaginatedResponse<AuditLog>>(`/api/v1/audit-logs?${q.toString()}`);
  },

  // Intelligence (Phase 2 — THINK)
  getCaseIntelligence: (caseId: string) =>
    fetcher<IntelligenceEnvelope>(`/api/v1/recovery-cases/${caseId}/intelligence`),
  analyzeCase: (caseId: string) =>
    fetcher<IntelligenceEnvelope>(
      `/api/v1/recovery-cases/${caseId}/intelligence:analyze`,
      { method: "POST" }
    ),
  getIntelligenceList: (params?: { page?: number; limit?: number; verdict?: string; band?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.verdict) q.set("verdict", params.verdict);
    if (params?.band) q.set("band", params.band);
    return fetcher<PaginatedResponse<IntelligenceListItem>>(`/api/v1/intelligence?${q.toString()}`);
  },

  // Intent-aware recovery (Phase 10) — also embedded in getCaseIntelligence's
  // IntelligenceEnvelope.intent; this dedicated endpoint is for a focused read.
  getCaseIntent: (caseId: string) =>
    fetcher<IntentEnvelope>(`/api/v1/recovery-cases/${caseId}/intent`),

  // Actions (Phase 3 — ACT)
  getCaseActions: (caseId: string) =>
    fetcher<{ items: RecoveryAction[]; total: number }>(
      `/api/v1/recovery-cases/${caseId}/actions`
    ),
  proposeAction: (caseId: string) =>
    fetcher<ProposeActionResponse>(
      `/api/v1/recovery-cases/${caseId}/actions/propose`,
      { method: "POST" }
    ),
  executeAction: (actionId: string) =>
    fetcher<ExecuteActionResponse>(`/api/v1/actions/${actionId}/execute`, {
      method: "POST",
    }),
  approveAction: (actionId: string) =>
    fetcher<ExecuteActionResponse>(`/api/v1/actions/${actionId}/approve`, {
      method: "POST",
    }),
  rejectAction: (actionId: string) =>
    fetcher<ExecuteActionResponse>(`/api/v1/actions/${actionId}/reject`, {
      method: "POST",
    }),
  verifyUnknownAction: (actionId: string) =>
    fetcher<ExecuteActionResponse>(`/api/v1/actions/${actionId}/verify-unknown`, {
      method: "POST",
    }),
  reconcileAction: (actionId: string) =>
    fetcher<ReconcileActionResponse>(`/api/v1/actions/${actionId}/reconcile`, {
      method: "POST",
    }),
  getAction: (actionId: string) =>
    fetcher<RecoveryAction>(`/api/v1/actions/${actionId}`),
  getAllActions: (params?: { page?: number; limit?: number; status?: string; outcome?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.status) q.set("status", params.status);
    if (params?.outcome) q.set("outcome", params.outcome);
    return fetcher<{ items: RecoveryAction[]; total: number }>(`/api/v1/actions?${q.toString()}`);
  },

  // Simulator
  triggerSimulation: (request: SimulateEventRequest) =>
    fetcher<SimulateEventResponse>("/api/v1/simulator/events", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  simulatePaymentLinkPaid: (actionId: string) =>
    fetcher<SimulateEventResponse>("/api/v1/simulator/payment-link-paid", {
      method: "POST",
      body: JSON.stringify({ action_id: actionId }),
    }),

  // Analytics (Phase 4 — PROVE)
  getAnalytics: () => fetcher<AnalyticsMetrics>("/api/v1/analytics"),

  // Policies (Phase 4 — PROVE)
  getPolicies: () => fetcher<PolicyOverview>("/api/v1/policies"),

  // Auth (Phase 5)
  register: (data: { email: string; password: string; organization_name: string }) =>
    fetcher<MeResponse>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) =>
    fetcher<MeResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(data) }),
  logout: () => fetcher<MessageResponse>("/api/v1/auth/logout", { method: "POST" }),
  forgotPassword: (email: string) =>
    fetcher<MessageResponse>("/api/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (data: { token: string; new_password: string }) =>
    fetcher<MessageResponse>("/api/v1/auth/reset-password", { method: "POST", body: JSON.stringify(data) }),
  me: () => fetcher<MeResponse>("/api/v1/auth/me"),

  // Users (Phase 5 — ADMIN only)
  getOrgUsers: () => fetcher<OrgUserListResponse>("/api/v1/users"),
  updateUserRole: (userId: string, role: string) =>
    fetcher<OrgUser>(`/api/v1/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role }) }),

  // Communications (Phase 5)
  getCaseCommunications: (caseId: string) =>
    fetcher<CommunicationListResponse>(`/api/v1/recovery-cases/${caseId}/communications`),
  sendCommunication: (caseId: string, channel: string, messageType: string) =>
    fetcher<SendCommunicationResponse>(`/api/v1/recovery-cases/${caseId}/communications/send`, {
      method: "POST",
      body: JSON.stringify({ channel, message_type: messageType }),
    }),

  // AI model predictions (Phase 6) — advisory only, never authoritative;
  // the Policy Engine's verdict above is computed independently of these.
  getCaseAiPredictions: (caseId: string) =>
    fetcher<AiPredictionsResponse>(`/api/v1/recovery-cases/${caseId}/ai-predictions`),

  // Connections (read-only provider status)
  getConnections: () => fetcher<ConnectionsOverview>("/api/v1/connections"),

  // Reconciliation (Phase 9)
  getPaymentReconciliation: (paymentId: string) =>
    fetcher<PaymentReconciliation>(`/api/v1/payments/${paymentId}/reconciliation`),
  getReconciliationMismatches: (params?: { page?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    return fetcher<ReconciliationMismatchListResponse>(`/api/v1/reconciliation/mismatches?${q.toString()}`);
  },

  // Health
  getHealth: () => fetcher<{ status: string; service: string; database: string }>("/api/v1/health"),
};
