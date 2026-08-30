/**
 * RECON OS — Frontend Type Definitions
 * Directly aligned with backend Pydantic models & PostgreSQL schema.
 */

export interface RevenueEvent {
  id: string;
  razorpay_event_id: string;
  merchant_id: string;
  event_type: string;
  source: string;
  processing_status: "received" | "processing" | "processed" | "failed";
  error_message?: string | null;
  raw_payload: Record<string, any>;
  normalized_data?: Record<string, any> | null;
  received_at: string;
  processed_at?: string | null;
  created_at: string;
}

export interface Payment {
  id: string;
  razorpay_payment_id: string;
  merchant_id: string;
  customer_id?: string | null;
  razorpay_order_id?: string | null;
  amount: string;
  amount_paise: number;
  currency: string;
  status: "created" | "authorized" | "captured" | "failed" | "refunded" | string;
  method?: string | null;
  error_code?: string | null;
  error_description?: string | null;
  error_reason?: string | null;
  razorpay_data?: Record<string, any> | null;
  razorpay_created_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Customer {
  id: string;
  merchant_id: string;
  razorpay_customer_id?: string | null;
  email?: string | null;
  phone?: string | null;
  name?: string | null;
  total_payment_amount: string;
  successful_payment_count: number;
  failed_payment_count: number;
  last_payment_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecoveryCase {
  id: string;
  case_number: string;
  intelligence?: IntelligenceSummary | null;
  merchant_id: string;
  customer_id?: string | null;
  payment_id?: string | null;
  amount_at_risk: string;
  amount_recovered: string;
  currency: string;
  failure_reason?: string | null;
  failure_code?: string | null;
  status: "DETECTED" | "OPEN" | "RESOLVED" | "CLOSED" | string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  attempt_count: number;
  max_attempts: number;
  opened_at: string;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
  customer?: Customer | null;
  payment?: Payment | null;
}

/* ------------------------------------------------------------------ */
/* Phase 2 (THINK) — Intelligence                                      */
/* ------------------------------------------------------------------ */

export interface DiagnosisResult {
  failure_category: string;
  probable_cause: string;
  confidence: number;
  rationale: string;
  evidence: string[];
  provider: string;
  provider_version?: string | null;
  fallback_reason?: string | null;
}

export interface FeatureContribution {
  feature: string;
  value: string;
  contribution: number;
  direction: "positive" | "negative" | "neutral";
  note?: string | null;
}

export interface PredictionResult {
  recovery_probability: number;
  band: "LOW" | "MEDIUM" | "HIGH";
  confidence: number;
  base_rate: number;
  features_used: FeatureContribution[];
  rationale: string;
  provider: string;
}

export interface StrategyAlternative {
  action: string;
  reason: string;
}

export interface StrategyResult {
  action: string;
  params: Record<string, any>;
  rationale: string;
  confidence: number;
  alternatives: StrategyAlternative[];
  provider: string;
}

export interface PolicyRuleResult {
  rule_id: string;
  name: string;
  description: string;
  passed: boolean;
  detail: string;
}

export interface PolicyResult {
  verdict: "APPROVED" | "NEEDS_APPROVAL" | "REJECTED";
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  requires_human: boolean;
  reason: string;
  evaluated_rules: PolicyRuleResult[];
  violated_rules: string[];
  allowed_actions: string[];
  provider: string;
}

export interface IntelligenceEnvelope {
  case_id: string;
  case_number: string;
  analyzed: boolean;
  intelligence_enabled: boolean;
  status: string;
  provider?: string | null;
  provider_version?: string | null;
  intelligence_version?: string | null;
  diagnosis_source?: string | null;
  version?: string | null;
  analyzed_at?: string | null;
  diagnosis?: DiagnosisResult | null;
  prediction?: PredictionResult | null;
  strategy?: StrategyResult | null;
  policy?: PolicyResult | null;
  context?: Record<string, any> | null;
  error_message?: string | null;
}

export interface IntelligenceSummary {
  status: string;
  provider: string;
  provider_version?: string | null;
  intelligence_version?: string | null;
  diagnosis_source?: string | null;
  version: string;
  failure_category?: string | null;
  recovery_probability?: number | null;
  prediction_band?: string | null;
  recommended_action?: string | null;
  policy_verdict?: string | null;
  requires_human?: boolean | null;
  risk_level?: string | null;
  analyzed_at?: string | null;
}

export interface IntelligenceMetrics {
  cases_analyzed: number;
  high_recovery_probability: number;
  needs_approval: number;
  policy_rejected: number;
  policy_approved: number;
  ai_enhanced: number;
  deterministic: number;
  ai_configured: boolean;
}

/* ------------------------------------------------------------------ */
/* Phase 3 (ACT) — Actions                                             */
/* ------------------------------------------------------------------ */

export interface ActionProposal {
  proposable: boolean;
  action_type?: string | null;
  recovery_case_id: string;
  case_number: string;
  amount?: string | null;
  currency: string;
  reference_id?: string | null;
  reason: string;
  strategy_action?: string | null;
  policy_verdict?: string | null;
  not_proposable_reason?: string | null;
  test_mode: boolean;
  razorpay_configured: boolean;
  simulator_enabled: boolean;
}

export type ActionUiState =
  | "READY"
  | "APPROVED"
  | "EXECUTING"
  | "EXECUTED"
  | "WAITING_FOR_PAYMENT"
  | "RECOVERED"
  | "PARTIAL"
  | "FAILED"
  | "BLOCKED"
  | "NEEDS_APPROVAL"
  | "EXPIRED"
  | "CANCELLED"
  | "UNKNOWN"
  | string;

export interface RecoveryAction {
  id: string;
  recovery_case_id: string;
  case_number?: string | null;
  action_type: string;
  status: string;
  outcome: string;
  ui_state?: ActionUiState | null;
  reference_id?: string | null;
  provider?: string | null;
  provider_action_id?: string | null;
  provider_status?: string | null;
  payment_link_url?: string | null;
  amount?: string | null;
  currency: string;
  recovered_amount: string;
  simulated?: boolean;
  simulator_enabled?: boolean;
  strategy_action?: string | null;
  policy_verdict?: string | null;
  blocked_reason?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  requested_at?: string | null;
  approved_at?: string | null;
  executed_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  human_decision?: string | null;
  human_decided_at?: string | null;
  human_decided_by?: string | null;
}

export interface ProposeActionResponse {
  proposal: ActionProposal;
  action: RecoveryAction | null;
}

export interface ExecuteActionResponse {
  ok: boolean;
  message: string;
  action: RecoveryAction;
}

export interface ReconcileActionResponse {
  ok: boolean;
  recovered: boolean;
  partial: boolean;
  razorpay_status?: string | null;
  amount_paid?: string | null;
  message: string;
  action: RecoveryAction;
}

export interface ActionMetrics {
  actions_proposed: number;
  actions_executed: number;
  actions_blocked: number;
  payment_links_created: number;
  pending_recoveries: number;
  partial_recoveries: number;
  unknown_outcomes: number;
  revenue_recovered: string;
  simulated_revenue_recovered: string;
  recovery_rate: number;
  test_mode: boolean;
  razorpay_configured: boolean;
  simulator_enabled: boolean;
}

export interface IntelligenceListItem {
  case_id: string;
  case_number: string;
  customer_name?: string | null;
  amount_at_risk: string;
  currency: string;
  failure_category?: string | null;
  recovery_probability?: number | null;
  prediction_band?: string | null;
  recommended_action?: string | null;
  policy_verdict?: string | null;
  risk_level?: string | null;
  status: string;
  provider: string;
  provider_version?: string | null;
  diagnosis_source?: string | null;
  version: string;
  analyzed_at?: string | null;
}

export interface AuditLog {
  id: string;
  merchant_id: string;
  recovery_case_id?: string | null;
  actor: string;
  action: string;
  detail: string;
  metadata_json?: Record<string, any> | null;
  created_at: string;
}

export interface DailyTrendItem {
  date: string;
  failed_amount: string;
  captured_amount: string;
  failed_count: number;
  captured_count: number;
}

export interface DashboardMetrics {
  merchant_name: string;
  revenue_at_risk: string;
  revenue_secured: string;
  active_recovery_cases: number;
  payment_failures: number;
  successful_payments: number;
  events_processed: number;
  total_customers: number;
  recent_events: RevenueEvent[];
  recent_cases: RecoveryCase[];
  daily_trends: DailyTrendItem[];
  intelligence?: IntelligenceMetrics | null;
  actions?: ActionMetrics | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

export interface SimulateEventRequest {
  event_type: "payment.failed" | "payment.captured" | "payment.authorized" | string;
  customer_name: string;
  customer_email: string;
  customer_phone?: string;
  amount: number | string;
  payment_method: "upi" | "card" | "netbanking" | "wallet" | string;
  failure_code?: string;
  failure_reason?: string;
  error_description?: string;
}

export interface SimulateEventResponse {
  success: boolean;
  event_id: string;
  razorpay_event_id: string;
  razorpay_payment_id: string;
  event_type: string;
  processing_status: string;
  case_number?: string | null;
  message: string;
}

/* ------------------------------------------------------------------ */
/* Phase 4 (PROVE) — Analytics                                         */
/* ------------------------------------------------------------------ */

export interface StrategyPerformance {
  strategy: string;
  executed: number;
  recovered: number;
  success_rate: number;
}

export interface AnalyticsMetrics {
  generated_at: string;

  revenue_at_risk: string;
  potential_recoverable_revenue: string;
  revenue_recovered: string;
  simulated_revenue_recovered: string;
  recovery_rate: number;
  average_recovery_probability?: number | null;

  automation_rate?: number | null;
  human_approval_rate?: number | null;
  human_rejection_rate?: number | null;
  actions_needing_approval_total: number;
  actions_approved_by_human: number;
  actions_rejected_by_human: number;

  recovery_failure_rate?: number | null;
  unknown_cases: number;
  policy_rejection_count: number;

  average_recovery_time_hours?: number | null;
  average_recovery_attempts: number;
  total_recovery_attempts: number;

  strategy_performance: StrategyPerformance[];

  cases_analyzed: number;
  actions_total: number;
}

/* ------------------------------------------------------------------ */
/* Phase 4 (PROVE) — Policies                                          */
/* ------------------------------------------------------------------ */

export interface PolicyRuleInfo {
  rule_id: string;
  name: string;
  condition: string;
  decision: string;
  action_restriction: string;
}

export interface PolicyConfig {
  max_recovery_attempts: number;
  contact_window_hours: number;
  max_contacts_per_window: number;
  auto_approval_amount_limit: number;
  currency: string;
}

export interface PolicyOverview {
  config: PolicyConfig;
  rules: PolicyRuleInfo[];
  editable: boolean;
  note: string;
}
