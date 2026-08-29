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
  RecoveryAction,
  ProposeActionResponse,
  ExecuteActionResponse,
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
  });

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
  getAuditLogs: (params?: { page?: number; limit?: number; action?: string; actor?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", params.page.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.action) q.set("action", params.action);
    if (params?.actor) q.set("actor", params.actor);
    if (params?.search) q.set("search", params.search);
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
  getAction: (actionId: string) =>
    fetcher<RecoveryAction>(`/api/v1/actions/${actionId}`),

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

  // Health
  getHealth: () => fetcher<{ status: string; service: string; database: string }>("/api/v1/health"),
};
