"use client";

import React, { useState } from "react";
import useSWR from "swr";
import {
  BrainCircuit,
  Check,
  X,
  Loader2,
  Activity,
  ShieldCheck,
  AlertTriangle,
  Ban,
  ArrowRight,
  Sparkles,
  Cpu,
  Zap,
  ExternalLink,
  Link2,
  CheckCircle2,
  HelpCircle,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { IntelligenceEnvelope, IntentResult, RecoveryAction } from "@/lib/types";
import { cn, formatDateTime, formatINR } from "@/lib/utils";
import { deriveCasePipeline, type StageStatus } from "@/components/spatial/pipeline-model";
import { NumberedSteps, type NumberedStep } from "@/components/modules/NumberedSteps";
import { CommunicationsSection } from "@/components/modules/CommunicationsSection";

const RecoveryPipeline3D = dynamic(
  () =>
    import("@/components/spatial/RecoveryPipeline3D").then(
      (m) => m.RecoveryPipeline3D
    ),
  {
    ssr: false,
    loading: () => (
      <div className="h-40 rounded-2xl border border-border bg-surface/60 animate-pulse" />
    ),
  }
);

interface Props {
  caseId: string;
  caseNumber?: string;
}

/* ---------- small primitives ------------------------------------------- */

function Meter({ value, tone }: { value: number; tone: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="w-full h-2 rounded-full bg-surface-elevated overflow-hidden">
      <div
        className={cn("h-full rounded-full transition-all duration-500", tone)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function ConfidenceRow({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[12px] font-mono text-fg-muted">
        <span>{label}</span>
        <span className="text-fg tabular-nums">{pct}%</span>
      </div>
      <Meter value={value} tone="bg-status-info/80" />
    </div>
  );
}

const bandTone: Record<string, string> = {
  HIGH: "bg-status-success/80",
  MEDIUM: "bg-status-warning/80",
  LOW: "bg-status-danger/80",
};

const verdictStyle: Record<string, { tone: string; icon: any; label: string }> = {
  APPROVED: { tone: "text-status-success border-status-success-border bg-status-success-bg", icon: ShieldCheck, label: "APPROVED" },
  NEEDS_APPROVAL: { tone: "text-status-warning border-status-warning-border bg-status-warning-bg", icon: AlertTriangle, label: "NEEDS APPROVAL" },
  REJECTED: { tone: "text-status-danger border-status-danger-border bg-status-danger-bg", icon: Ban, label: "REJECTED" },
};

const riskTone: Record<string, string> = {
  LOW: "text-status-success",
  MEDIUM: "text-status-warning",
  HIGH: "text-status-danger",
};

/** Backend-driven diagnosis source: "AI-ENHANCED" | "DETERMINISTIC FALLBACK" | "DETERMINISTIC" */
function SourceBadge({ source }: { source?: string | null }) {
  if (!source) return null;
  const isAI = source === "AI-ENHANCED";
  const isFallback = source === "DETERMINISTIC FALLBACK";
  const Icon = isAI ? Sparkles : Cpu;
  const tone = isAI
    ? "text-status-success border-status-success-border bg-status-success-bg"
    : isFallback
    ? "text-status-warning border-status-warning-border bg-status-warning-bg"
    : "text-fg-muted border-border bg-surface-elevated";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-mono font-semibold px-2 py-0.5 rounded border tracking-wide",
        tone
      )}
    >
      <Icon className="w-3 h-3" />
      {source}
    </span>
  );
}

const intentTone: Record<string, { tone: string; icon: any; label: string }> = {
  RECOVERABLE: { tone: "text-status-success border-status-success-border bg-status-success-bg", icon: ThumbsUp, label: "RECOVERABLE" },
  AMBIGUOUS: { tone: "text-status-warning border-status-warning-border bg-status-warning-bg", icon: HelpCircle, label: "AMBIGUOUS" },
  INSUFFICIENT_EVIDENCE: { tone: "text-fg-muted border-border bg-surface-elevated", icon: HelpCircle, label: "INSUFFICIENT EVIDENCE" },
  LIKELY_UNWILLING: { tone: "text-status-danger border-status-danger-border bg-status-danger-bg", icon: ThumbsDown, label: "LIKELY UNWILLING" },
};

/**
 * Phase 10 — intent-aware recovery. Distinct from the recovery-PROBABILITY
 * prediction above (how likely is this payment to recover?): this answers
 * whether RECON has evidence the customer actually wants to be recovered.
 * Purely explanatory — the Policy Engine already made its decision using
 * this same evidence (see RULE_INTENT_UNWILLING / RULE_INTENT_EVIDENCE in
 * the rules list below); nothing here can change that decision.
 */
function IntentSection({ intent }: { intent?: IntentResult | null }) {
  if (!intent) return null;
  const it = intentTone[intent.classification] || intentTone.AMBIGUOUS;
  const IIcon = it.icon;
  return (
    <div className="space-y-2 border-t border-border/60 pt-4">
      <SectionTitle>Recovery Intent</SectionTitle>
      <div className="flex items-center justify-between">
        <span className={cn("inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-1 rounded border", it.tone)}>
          <IIcon className="w-3.5 h-3.5" />
          {it.label}
        </span>
        <span className="text-fg tabular-nums text-[12px] font-mono">{Math.round(intent.confidence * 100)}% confidence</span>
      </div>
      {(intent.positive_signals.length > 0 || intent.negative_signals.length > 0) && (
        <div className="space-y-1">
          <p className="text-[11px] font-mono text-fg-faint uppercase">Why</p>
          {intent.positive_signals.map((s) => (
            <div key={s.code} className="flex items-start gap-1.5 text-[12px] font-mono text-fg-secondary">
              <span className="text-status-success">•</span>{s.description}
            </div>
          ))}
          {intent.negative_signals.map((s) => (
            <div key={s.code} className="flex items-start gap-1.5 text-[12px] font-mono text-fg-secondary">
              <span className="text-status-danger">•</span>{s.description}
            </div>
          ))}
        </div>
      )}
      <p className="text-[11px] font-mono text-fg-faint">
        Evidence completeness {Math.round(intent.evidence_completeness * 100)}% · source {intent.provider}
      </p>
    </div>
  );
}

const modelStatusTone: Record<string, string> = {
  READY: "text-status-success border-status-success-border bg-status-success-bg",
  EXPERIMENTAL: "text-status-warning border-status-warning-border bg-status-warning-bg",
  DATA_LIMITED: "text-status-warning border-status-warning-border bg-status-warning-bg",
  DISABLED: "text-fg-faint border-border bg-surface-elevated",
};

function ModelStatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wide",
        modelStatusTone[status] || "text-fg-muted border-border bg-surface-elevated"
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

/**
 * Phase 6 — advisory ML model predictions for this case. Deliberately
 * rendered as its own section, visually distinct from the POLICY DECISION
 * section above it: this data can never override or explain the policy
 * verdict, it's additional context the deterministic Policy Engine never
 * saw. Every value shown here comes straight from the model registry's own
 * recorded status/version (see apps/api/ai/inference/service.py) — a
 * DATA_LIMITED or EXPERIMENTAL model is labelled as such, never hidden.
 */
function AiPredictionsSection({ caseId }: { caseId: string }) {
  const { data } = useSWR(
    caseId ? `/api/v1/recovery-cases/${caseId}/ai-predictions` : null,
    () => api.getCaseAiPredictions(caseId)
  );
  if (!data?.analyzed) return null;
  const preds = data.predictions;
  if (!preds) {
    return (
      <div className="space-y-2 border-t border-border/60 pt-4">
        <SectionTitle>AI Model Predictions (Advisory)</SectionTitle>
        <p className="text-[12px] font-mono text-fg-faint">
          {data.note || "No trained models were available for this analysis run."}
        </p>
      </div>
    );
  }

  const recoveryProb = preds.recovery_probability;
  const recoveryTime = preds.recovery_time;
  const topStrategy = preds.strategy_ranking?.ranking?.[0];
  const topStrategyValue = preds.expected_recovery_value?.ranking?.find(
    (v: any) => v.strategy === topStrategy?.strategy
  );
  const topChannel = preds.communication_channel?.ranking?.[0];
  const churn = preds.customer_recovery;
  const anomaly = preds.anomaly;

  type Card = { label: string; value: string; status?: string; version?: string; realWorldValidation?: string };
  const opportunity: Card[] = [];
  const evidence: Card[] = [];

  if (recoveryProb) {
    opportunity.push({
      label: "Recovery Probability",
      value: `${Math.round((recoveryProb.recovery_probability ?? 0) * 100)}%`,
      status: recoveryProb.status, version: recoveryProb.model_version,
      realWorldValidation: recoveryProb.real_world_validation,
    });
  }
  if (topStrategyValue) {
    opportunity.push({
      label: "Estimated Recovery Value",
      value: formatINR(topStrategyValue.expected_recovery_value ?? 0),
    });
  }
  if (topStrategy) {
    opportunity.push({
      label: "Recommended Strategy",
      value: `${topStrategy.strategy} (${Math.round((topStrategy.score ?? 0) * 100)}%)`,
      status: preds.strategy_ranking.status, version: preds.strategy_ranking.model_version,
      realWorldValidation: preds.strategy_ranking.real_world_validation,
    });
  }
  if (recoveryTime) {
    opportunity.push({
      label: "Estimated Recovery Time",
      value: `${(recoveryTime.expected_recovery_hours ?? 0).toFixed(1)}h`,
      status: recoveryTime.status, version: recoveryTime.model_version,
      realWorldValidation: recoveryTime.real_world_validation,
    });
  }
  if (topChannel) {
    opportunity.push({
      label: "Recommended Channel",
      value: `${topChannel.channel} (${Math.round((topChannel.score ?? 0) * 100)}%)`,
      status: preds.communication_channel.status, version: preds.communication_channel.model_version,
      realWorldValidation: preds.communication_channel.real_world_validation,
    });
  }

  if (preds.diagnosis) {
    evidence.push({
      label: "Diagnosis",
      value: `${preds.diagnosis.failure_category} (${Math.round((preds.diagnosis.confidence ?? 0) * 100)}%)`,
      status: preds.diagnosis.status, version: preds.diagnosis.model_version,
      realWorldValidation: preds.diagnosis.real_world_validation,
    });
  }
  if (churn) {
    evidence.push({
      label: "Customer Recovery",
      value: `${Math.round((churn.customer_recovery_probability ?? 0) * 100)}%`,
      status: churn.status, version: churn.model_version,
      realWorldValidation: churn.real_world_validation,
    });
  }
  if (anomaly) {
    evidence.push({
      label: "Anomaly",
      value: anomaly.is_anomaly ? `${anomaly.anomaly_score} (unusual pattern)` : `${anomaly.anomaly_score} (normal)`,
      status: anomaly.status, version: anomaly.model_version,
      realWorldValidation: anomaly.real_world_validation,
    });
  }
  if (preds.message_response) {
    evidence.push({
      label: "Message Response",
      value: `${Math.round((preds.message_response.response_probability ?? 0) * 100)}%`,
      status: preds.message_response.status, version: preds.message_response.model_version,
      realWorldValidation: preds.message_response.real_world_validation,
    });
  }

  if (opportunity.length === 0 && evidence.length === 0) return null;

  // A single, honest evidence-status summary — the worst (least-validated)
  // level present across every model shown, so nothing is ever hidden behind
  // an average or a best-case number.
  const validationRank: Record<string, number> = { NONE: 0, INSUFFICIENT: 1, PARTIAL: 2, FULL: 3 };
  const allValidations = [...opportunity, ...evidence].map((c) => c.realWorldValidation).filter(Boolean) as string[];
  const worstValidation = allValidations.length
    ? allValidations.reduce((worst, v) => (validationRank[v] < validationRank[worst] ? v : worst), allValidations[0])
    : null;

  const CardGrid = ({ title, cards }: { title: string; cards: Card[] }) =>
    cards.length === 0 ? null : (
      <div className="space-y-2">
        <p className="text-[10px] font-mono text-fg-faint uppercase tracking-widest">{title}</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {cards.map((c) => (
            <div key={c.label} className="rounded-lg border border-border bg-surface-subtle/40 p-2.5 space-y-1">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[10px] font-mono text-fg-faint uppercase tracking-wide">{c.label}</span>
                <ModelStatusBadge status={c.status} />
              </div>
              <p className="text-sm font-mono font-semibold text-fg">{c.value}</p>
            </div>
          ))}
        </div>
      </div>
    );

  return (
    <div className="space-y-4 border-t border-border/60 pt-4">
      <div className="flex items-center justify-between">
        <SectionTitle>AI Model Predictions (Advisory)</SectionTitle>
        <span className="text-[11px] font-mono text-fg-faint">
          feature v{preds.feature_version} · never overrides policy
        </span>
      </div>

      <CardGrid title="Recovery Opportunity" cards={opportunity} />
      <CardGrid title="AI Evidence" cards={evidence} />

      {worstValidation && (
        <div className="rounded-lg border border-status-warning-border/40 bg-status-warning-bg/30 px-3 py-2">
          <p className="text-[11px] font-mono font-semibold text-status-warning uppercase tracking-wide">
            Evidence Status: Real-world evidence — {worstValidation.replace(/_/g, " ")}
          </p>
          <p className="text-[11px] font-mono text-fg-faint leading-relaxed mt-1">
            MODEL PREDICTION only — advisory context computed after and separate from the POLICY
            DECISION shown above; the estimated recovery value is a business-decision estimate
            (probability × amount × strategy multiplier − cost), never a guarantee of recovered
            revenue. &ldquo;{worstValidation.replace(/_/g, " ")}&rdquo; means recon_dev.db does not
            yet contain enough (or diverse enough) real outcomes to confirm at least one of these
            models&apos; real-world accuracy — those numbers come from synthetic-data training only.
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * Phase-final polish: a real, chronological reconstruction of this case's
 * lifecycle straight from the existing audit trail (GET /audit-logs?case_id=…,
 * oldest first) — every row is a real AuditLog record, never an invented
 * timestamp or step. Distinct from the "Case Lifecycle" NumberedSteps above
 * (which shows current STAGE STATUS); this is the raw, ordered EVENT LOG.
 */
function CaseAuditTimeline({ caseId }: { caseId: string }) {
  const { data } = useSWR(
    caseId ? `/api/v1/audit-logs?case_id=${caseId}&limit=100` : null,
    () => api.getAuditLogs({ caseId, limit: 100 })
  );
  const items = data?.items ? [...data.items].reverse() : [];
  if (items.length === 0) return null;

  return (
    <div className="space-y-2 border-t border-border/60 pt-4">
      <SectionTitle>Case Timeline (Audit Trail)</SectionTitle>
      <div className="space-y-0 max-h-64 overflow-y-auto pr-1">
        {items.map((a) => (
          <div key={a.id} className="flex items-start gap-3 py-1.5 border-b border-border/30 last:border-0">
            <span className="text-[11px] font-mono text-fg-faint shrink-0 w-16 tabular-nums">
              {new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <div className="min-w-0 flex-1">
              <span className="text-[12px] font-mono font-semibold text-fg-secondary">{a.action}</span>
              <p className="text-[11px] text-fg-faint truncate">{a.detail}</p>
            </div>
            <span className="text-[10px] font-mono text-fg-faint shrink-0">{a.actor}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const stageTone: Record<StageStatus, NumberedStep["tone"]> = {
  done: "success",
  active: "default",
  pending: "muted",
  blocked: "warning",
  rejected: "danger",
};

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[12px] font-mono font-semibold text-fg-secondary uppercase tracking-widest">
      {children}
    </h4>
  );
}

/* ---------- Phase 3 (ACT) — Action section ---------------------------- */

const ELIGIBLE_STRATEGIES = ["RETRY_NOW", "RETRY_DELAYED", "SEND_PAYMENT_LINK"];

const actionStateStyle: Record<string, string> = {
  RECOVERED: "text-status-success border-status-success-border bg-status-success-bg",
  WAITING_FOR_PAYMENT: "text-status-info border-status-info-border bg-status-info-bg",
  EXECUTED: "text-status-info border-status-info-border bg-status-info-bg",
  EXECUTING: "text-status-info border-status-info-border bg-status-info-bg",
  APPROVED: "text-status-success border-status-success-border bg-status-success-bg",
  READY: "text-fg-secondary border-border bg-surface-elevated",
  BLOCKED: "text-status-danger border-status-danger-border bg-status-danger-bg",
  NEEDS_APPROVAL: "text-status-warning border-status-warning-border bg-status-warning-bg",
  PARTIAL: "text-status-warning border-status-warning-border bg-status-warning-bg",
  EXPIRED: "text-status-danger border-status-danger-border bg-status-danger-bg",
  CANCELLED: "text-status-danger border-status-danger-border bg-status-danger-bg",
  FAILED: "text-status-danger border-status-danger-border bg-status-danger-bg",
  // Deliberately NOT the FAILED/danger styling — an unconfirmed outcome is not
  // a known failure. Uses the same warning tone as NEEDS_APPROVAL/PARTIAL to
  // read as "needs attention, paused" rather than "broken."
  UNKNOWN: "text-status-warning border-status-warning-border bg-status-warning-bg",
};

function ActionSection({ env, caseId }: { env: IntelligenceEnvelope; caseId: string }) {
  const { data: actionsData, mutate: mutateActions } = useSWR(
    caseId ? `/api/v1/recovery-cases/${caseId}/actions` : null,
    () => api.getCaseActions(caseId),
    { refreshInterval: 4000 }
  );
  const [busy, setBusy] = useState<null | string>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reconcileMsg, setReconcileMsg] = useState<string | null>(null);

  const action: RecoveryAction | undefined = actionsData?.items?.[0];

  const strategyAction = env.strategy?.action ?? "";
  const verdict = env.policy?.verdict ?? "";
  const amount = env.context?.amount ?? action?.amount ?? null;
  const eligible = ELIGIBLE_STRATEGIES.includes(strategyAction);

  const run = async (fn: () => Promise<any>, tag: string) => {
    setBusy(tag);
    setErr(null);
    try {
      await fn();
      await mutateActions();
    } catch (e: any) {
      setErr(e?.message || "Action request failed");
    } finally {
      setBusy(null);
    }
  };

  const createLink = () =>
    run(async () => {
      const proposed = await api.proposeAction(caseId);
      if (!proposed.action) throw new Error(proposed.proposal.reason);
      await api.executeAction(proposed.action.id);
    }, "create");

  const retry = () =>
    run(async () => {
      if (action) await api.executeAction(action.id);
    }, "retry");

  const approve = () =>
    run(async () => {
      if (action) await api.approveAction(action.id);
    }, "approve");

  const reject = () =>
    run(async () => {
      if (action) await api.rejectAction(action.id);
    }, "reject");

  const verifyUnknown = () =>
    run(async () => {
      if (!action) return;
      setReconcileMsg(null);
      const res = await api.verifyUnknownAction(action.id);
      setReconcileMsg(res.message);
    }, "verify-unknown");

  const confirmPayment = () =>
    run(async () => {
      if (!action) return;
      setReconcileMsg(null);
      const res = await api.reconcileAction(action.id);
      setReconcileMsg(res.message);
    }, "confirm");

  const simulatePaid = () =>
    run(async () => {
      if (action) await api.simulatePaymentLinkPaid(action.id);
    }, "simulate");

  const uiState = action?.ui_state || "READY";

  return (
    <div className="space-y-3 border-t border-border/60 pt-4">
      <div className="flex items-center justify-between">
        <SectionTitle>Action</SectionTitle>
        <span className="inline-flex items-center gap-1 text-[11px] font-mono text-fg-faint">
          <Zap className="w-3 h-3 text-status-warning" /> RAZORPAY TEST MODE
        </span>
      </div>

      {/* No action yet */}
      {!action && (
        <>
          {!eligible ? (
            <p className="text-[12px] text-fg-faint font-mono">
              No automated recovery action available for strategy{" "}
              <span className="text-fg-secondary">{strategyAction || "—"}</span>.
              Phase 3 executes CREATE_PAYMENT_LINK only.
            </p>
          ) : verdict === "NEEDS_APPROVAL" ? (
            <div className="rounded border border-status-warning-border/50 bg-status-warning-bg px-3 py-2">
              <p className="text-[12px] font-mono text-status-warning font-semibold">
                ACTION REQUIRES APPROVAL
              </p>
              <p className="text-[12px] text-fg-muted mt-0.5">
                {env.policy?.reason} — execution is blocked until a human approves.
              </p>
            </div>
          ) : verdict === "REJECTED" ? (
            <div className="rounded border border-status-danger-border/40 bg-status-danger-bg/40 px-3 py-2 space-y-1">
              <p className="text-[12px] font-mono text-status-danger font-semibold">
                POLICY: REJECTED
              </p>
              <p className="text-[12px] text-fg-muted">
                {env.policy?.reason} — ACTION: none created. No Payment Link, no
                Razorpay call, no money movement. AI can recommend a strategy;
                only the Policy Engine decides whether it is ever permitted.
              </p>
            </div>
          ) : (
            <>
              <div className="rounded-xl border border-hairline bg-surface-subtle/60 p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1 text-[11px] font-mono text-status-success">
                    <Check className="w-3 h-3" /> POLICY: APPROVED
                  </span>
                  <span className="text-[11px] font-mono text-fg-faint">
                    ACTION ENGINE: ready to execute
                  </span>
                </div>
                <div className="flex items-center justify-between text-[12px] font-mono">
                  <span className="text-fg-faint">Amount</span>
                  <span className="text-fg font-semibold tabular-nums">
                    {formatINR(amount)}
                  </span>
                </div>
                <p className="text-[11px] text-fg-faint font-mono leading-relaxed">
                  Policy has already authorized this recovery — a failed Razorpay
                  payment cannot be re-charged via API, so the Action Engine&apos;s
                  executable recovery is a Test Mode Payment Link the customer pays
                  on. The Action Engine independently re-checks Policy server-side
                  the instant before it ever calls Razorpay — this button only
                  triggers the SAME authorized path RECON runs automatically when
                  auto-execution is enabled; it does not decide anything itself.
                </p>
              </div>
              <button
                onClick={createLink}
                disabled={busy !== null}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 font-mono text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
              >
                {busy === "create" ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Action Engine executing…</>
                ) : (
                  <><Link2 className="w-4 h-4" /> Execute Approved Recovery</>
                )}
              </button>
            </>
          )}
        </>
      )}

      {/* Action exists */}
      {action && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-1 rounded border",
                actionStateStyle[uiState] || actionStateStyle.READY
              )}
            >
              {uiState === "RECOVERED" ? <CheckCircle2 className="w-3.5 h-3.5" /> :
               uiState === "UNKNOWN" ? <HelpCircle className="w-3.5 h-3.5" /> :
               ["BLOCKED", "FAILED", "EXPIRED", "CANCELLED"].includes(uiState) ? <Ban className="w-3.5 h-3.5" /> :
               ["NEEDS_APPROVAL", "PARTIAL"].includes(uiState) ? <AlertTriangle className="w-3.5 h-3.5" /> :
               <Activity className="w-3.5 h-3.5" />}
              {uiState.replace(/_/g, " ")}
            </span>
            <div className="flex items-center gap-2">
              {action.simulated && (
                <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-status-warning-bg border border-status-warning-border text-status-warning tracking-wider">
                  SIMULATED
                </span>
              )}
              <span className="text-[11px] font-mono text-fg-faint">{action.action_type}</span>
            </div>
          </div>

          {["EXECUTED", "EXECUTING", "WAITING_FOR_PAYMENT", "RECOVERED", "PARTIAL"].includes(uiState) && (
            <p className="text-[11px] font-mono text-fg-faint">
              ACTION ENGINE:{" "}
              <span className="text-fg-secondary">
                {action.automatic_execution_enabled
                  ? "automatically executed (Policy-approved, no manual trigger required)"
                  : "executed by the Action Engine on operator request"}
              </span>
            </p>
          )}

          {uiState === "RECOVERED" && action.simulated && (
            <p className="text-[12px] font-mono text-status-warning/90 bg-status-warning-bg border border-status-warning-border/50 rounded px-2 py-1.5">
              This recovery was produced by the SIMULATOR — no real payment was made.
              It is excluded from real &ldquo;Revenue Recovered&rdquo; metrics.
            </p>
          )}

          {uiState === "PARTIAL" && (
            <div className="rounded border border-status-warning-border/50 bg-status-warning-bg px-3 py-2">
              <p className="text-[12px] font-mono text-status-warning font-semibold">PARTIAL PAYMENT</p>
              <p className="text-[12px] text-fg-muted mt-0.5">
                Less than the expected amount was paid — the recovery case is NOT resolved and
                no revenue is counted as recovered.
              </p>
            </div>
          )}

          {uiState === "NEEDS_APPROVAL" && (
            <div className="rounded border border-status-warning-border/50 bg-status-warning-bg px-3 py-2 space-y-2">
              <p className="text-[12px] font-mono text-status-warning font-semibold">
                HUMAN APPROVAL REQUIRED
              </p>
              <p className="text-[12px] text-fg-muted">
                {env.policy?.reason || action.error_message || "This action requires a human decision before it can execute."}
              </p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] font-mono text-fg-faint pt-1 border-t border-status-warning-border/30">
                <span>Amount <span className="text-fg-secondary">{formatINR(amount)}</span></span>
                <span>Risk <span className={cn("font-semibold", riskTone[env.policy?.risk_level || ""])}>{env.policy?.risk_level || "—"}</span></span>
                <span>Strategy <span className="text-fg-secondary">{strategyAction || "—"}</span></span>
                <span>Recovery probability <span className="text-fg-secondary">{env.prediction ? `${Math.round(env.prediction.recovery_probability * 100)}%` : "—"}</span></span>
              </div>
            </div>
          )}

          {uiState === "UNKNOWN" && (
            <div className="rounded border border-status-warning-border/50 bg-status-warning-bg px-3 py-2 space-y-1">
              <p className="text-[12px] font-mono text-status-warning font-semibold flex items-center gap-1.5">
                <HelpCircle className="w-3.5 h-3.5" /> OUTCOME UNKNOWN
              </p>
              <p className="text-[12px] text-fg-muted">
                Outcome could not be confirmed. Recovery action is paused until
                verification — RECON will never guess or blindly retry a
                request that may have already reached Razorpay.
              </p>
              {action.error_message && (
                <p className="text-[11px] font-mono text-fg-faint">{action.error_message}</p>
              )}
            </div>
          )}

          {(uiState === "BLOCKED" || uiState === "FAILED") && (
            <div className="rounded border border-status-danger-border/40 bg-status-danger-bg/40 px-3 py-2">
              <p className="text-[12px] font-mono text-status-danger">
                {action.blocked_reason === "HUMAN_REJECTED"
                  ? "REJECTED BY OPERATOR"
                  : action.blocked_reason || action.error_code || "Execution did not complete"}
              </p>
              {action.error_message && (
                <p className="text-[12px] text-fg-muted mt-0.5">{action.error_message}</p>
              )}
              {action.blocked_reason === "HUMAN_REJECTED" && action.human_decided_at && (
                <p className="text-[11px] font-mono text-fg-faint mt-0.5">
                  {action.human_decided_by || "Operator"} · {formatDateTime(action.human_decided_at)}
                </p>
              )}
            </div>
          )}

          {action.payment_link_url && (
            <div className="rounded-xl border border-hairline bg-surface-subtle/60 p-3 space-y-2 text-[12px] font-mono">
              <div className="flex items-center justify-between">
                <span className="text-fg-faint">Payment Link</span>
                <a
                  href={action.payment_link_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-accent hover:text-accent-hover"
                >
                  Open Payment Link <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-fg-faint">Reference ID</span>
                <span className="text-fg-secondary">{action.reference_id}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-fg-faint">Amount</span>
                <span className="text-fg tabular-nums">{formatINR(action.amount)}</span>
              </div>
              {uiState === "RECOVERED" && (
                <div className="flex items-center justify-between border-t border-border/60 pt-2">
                  <span className="text-fg-faint">Recovered</span>
                  <span className="text-status-success font-semibold tabular-nums">
                    {formatINR(action.recovered_amount)}
                  </span>
                </div>
              )}
            </div>
          )}

          {(uiState === "WAITING_FOR_PAYMENT" || uiState === "PARTIAL") && (
            <p className="text-[11px] font-mono text-fg-faint leading-relaxed">
              PAYMENT: Awaiting customer payment on the Razorpay link. VERIFICATION:
              pending — RECON never marks a case RECOVERED on its own. After the
              customer pays (in this local demo, use{" "}
              <span className="text-fg-muted">Simulate Customer Payment</span> below), click{" "}
              <span className="text-fg-muted">Check Razorpay for Payment</span> to have RECON
              ask Razorpay directly; only a real Razorpay confirmation of the FULL amount can
              set <span className="text-fg-muted">VERIFICATION: RECOVERED</span>.
            </p>
          )}

          {reconcileMsg && (
            <p className="text-[12px] font-mono text-status-info bg-status-info-bg border border-status-info-border/50 rounded px-2 py-1.5">
              {reconcileMsg}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {uiState === "NEEDS_APPROVAL" && (
              <>
                <button
                  onClick={approve}
                  disabled={busy !== null}
                  className="inline-flex h-10 items-center gap-2 rounded-lg bg-status-success px-4 font-mono text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
                >
                  {busy === "approve" ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Approving…</>
                  ) : (
                    <><ThumbsUp className="w-4 h-4" /> Approve</>
                  )}
                </button>
                <button
                  onClick={reject}
                  disabled={busy !== null}
                  className="inline-flex h-10 items-center gap-2 rounded-lg border border-status-danger-border bg-surface-subtle px-4 font-mono text-sm font-medium text-status-danger transition-colors hover:bg-status-danger-bg disabled:opacity-50"
                >
                  {busy === "reject" ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> Rejecting…</>
                  ) : (
                    <><ThumbsDown className="w-4 h-4" /> Reject</>
                  )}
                </button>
              </>
            )}
            {uiState === "UNKNOWN" && (
              <button
                onClick={verifyUnknown}
                disabled={busy !== null}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 font-mono text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
              >
                {busy === "verify-unknown" ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Verifying with Razorpay…</>
                ) : (
                  <><HelpCircle className="w-4 h-4" /> Verify with Razorpay</>
                )}
              </button>
            )}
            {(uiState === "WAITING_FOR_PAYMENT" || uiState === "PARTIAL") && (
              <button
                onClick={confirmPayment}
                disabled={busy !== null}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 font-mono text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
              >
                {busy === "confirm" ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Checking Razorpay…</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4" /> Check Razorpay for Payment</>
                )}
              </button>
            )}
            {(uiState === "BLOCKED" || uiState === "FAILED") && action.blocked_reason !== "HUMAN_REJECTED" && (
              <button
                onClick={retry}
                disabled={busy !== null}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-surface-subtle px-3.5 font-mono text-xs text-fg-secondary transition-colors hover:bg-surface-elevated hover:text-fg disabled:opacity-50"
              >
                {busy === "retry" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Activity className="w-3 h-3" />}
                Re-run execution
              </button>
            )}
            {uiState === "WAITING_FOR_PAYMENT" && action.simulator_enabled && (
              <button
                onClick={simulatePaid}
                disabled={busy !== null}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-status-warning-border/60 bg-status-warning-bg px-3.5 font-mono text-xs text-status-warning transition-colors hover:bg-status-warning-bg/70 disabled:opacity-50"
                title="TEST/SIMULATED ONLY — sends a simulated Razorpay payment_link.paid event to RECON's real event pipeline. No real payment occurs."
              >
                {busy === "simulate" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                Simulate Customer Payment
              </button>
            )}
          </div>
        </div>
      )}

      {err && <p className="text-[12px] text-status-danger font-mono">{err}</p>}
    </div>
  );
}

/* ---------- main panel ------------------------------------------------- */

export function IntelligencePanel({ caseId, caseNumber }: Props) {
  const { data, error, mutate, isValidating } = useSWR<IntelligenceEnvelope>(
    caseId ? `/api/v1/recovery-cases/${caseId}/intelligence` : null,
    () => api.getCaseIntelligence(caseId)
  );
  // Shared SWR key with ActionSection — SWR dedupes, so this is one request.
  const { data: actionsData } = useSWR(
    caseId ? `/api/v1/recovery-cases/${caseId}/actions` : null,
    () => api.getCaseActions(caseId),
    { refreshInterval: 4000 }
  );
  const pipelineAction: RecoveryAction | undefined = actionsData?.items?.[0];
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const caseStages = data ? deriveCasePipeline(data, pipelineAction) : null;

  const lifecycleSteps: NumberedStep[] | null = caseStages
    ? caseStages.map((stage, i) => ({
        number: String(i + 1).padStart(2, "0"),
        label: stage.label,
        value: stage.value,
        description: [stage.sub, stage.note].filter(Boolean).join(" · ") || undefined,
        tone: stageTone[stage.status],
      }))
    : null;

  const lifecycle = lifecycleSteps ? (
    <div className="space-y-2">
      <SectionTitle>Case Lifecycle</SectionTitle>
      <NumberedSteps steps={lifecycleSteps} />
    </div>
  ) : null;

  const pipeline = caseStages ? (
    <RecoveryPipeline3D
      stages={caseStages}
      title={`CASE PIPELINE${caseNumber ? ` · ${caseNumber}` : ""}`}
      caption="Each stage reflects real backend state. Nothing shows as recovered unless Razorpay (or a clearly-labelled simulation) confirms it."
    />
  ) : null;

  const analyze = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const res = await api.analyzeCase(caseId);
      await mutate(res, { revalidate: false });
    } catch (e: any) {
      setRunError(e?.message || "Analysis request failed");
    } finally {
      setRunning(false);
    }
  };

  const header = (
    <div className="flex items-center justify-between border-b border-border pb-3">
      <div className="flex items-center gap-2">
        <BrainCircuit className="w-4 h-4 text-accent" />
        <div>
          <h3 className="text-sm font-semibold text-fg font-mono tracking-wide">
            RECON INTELLIGENCE
          </h3>
          <p className="text-[11px] font-mono text-fg-faint tracking-wider">
            PHASE 2.5 • THINK
          </p>
        </div>
      </div>
      {data?.analyzed && <SourceBadge source={data.diagnosis_source} />}
    </div>
  );

  // loading
  if (!data && !error) {
    return (
      <div className="rounded-2xl border border-hairline bg-surface-subtle/30 p-5 space-y-4">
        {header}
        <div className="flex items-center gap-2 text-xs text-fg-muted font-mono">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading intelligence…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-hairline bg-surface-subtle/30 p-5 space-y-4">
        {header}
        <p className="text-xs text-status-danger font-mono">
          Could not load intelligence for this case.
        </p>
      </div>
    );
  }

  const env = data as IntelligenceEnvelope;

  // not analysed yet (or intelligence disabled)
  if (!env.analyzed) {
    return (
      <div className="rounded-2xl border border-hairline bg-surface-subtle/30 p-5 space-y-4">
        {header}
        {lifecycle}
        {pipeline}
        {env.status === "FAILED" ? (
          <div className="space-y-2">
            <p className="text-xs text-status-danger font-mono">INTELLIGENCE RUN FAILED</p>
            {env.error_message && (
              <p className="text-[12px] text-fg-faint font-mono break-words">
                {env.error_message}
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            <p className="text-xs font-mono text-fg-secondary">INTELLIGENCE NOT RUN</p>
            <p className="text-[12px] text-fg-faint">
              {env.intelligence_enabled
                ? "This case has not been analysed yet."
                : "Automatic analysis is disabled — run it manually below."}
            </p>
          </div>
        )}
        {runError && (
          <p className="text-[12px] text-status-danger font-mono">{runError}</p>
        )}
        <button
          onClick={analyze}
          disabled={running}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 font-mono text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {running ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" /> Analyzing case…
            </>
          ) : (
            <>
              <Activity className="w-4 h-4" /> Analyze Case
            </>
          )}
        </button>
      </div>
    );
  }

  const d = env.diagnosis!;
  const p = env.prediction!;
  const s = env.strategy!;
  const pol = env.policy!;
  const vs = verdictStyle[pol.verdict] || verdictStyle.NEEDS_APPROVAL;
  const VIcon = vs.icon;

  return (
    <div className="rounded-2xl border border-hairline bg-surface-subtle/30 p-5 space-y-6">
      {header}
      {lifecycle}
      {pipeline}

      {/* DIAGNOSIS */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <SectionTitle>Diagnosis</SectionTitle>
          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-fg-faint">
            {env.diagnosis_source === "AI-ENHANCED" ? (
              <><Sparkles className="w-3 h-3 text-status-success" /> Provider: {d.provider_version || env.provider}</>
            ) : (
              <><Cpu className="w-3 h-3" /> Provider: deterministic engine</>
            )}
          </span>
        </div>
        {d.fallback_reason && (
          <div className="text-[12px] font-mono text-status-warning/90 bg-status-warning-bg border border-status-warning-border/50 rounded px-2 py-1.5">
            AI diagnosis unavailable — deterministic fallback used ({d.fallback_reason}).
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[11px] font-mono text-fg-faint uppercase">Failure Category</p>
            <p className="text-sm font-mono font-semibold text-fg mt-0.5">
              {d.failure_category}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-mono text-fg-faint uppercase">Probable Cause</p>
            <p className="text-xs text-fg mt-0.5">{d.probable_cause}</p>
          </div>
        </div>
        <ConfidenceRow
          label={env.diagnosis_source === "AI-ENHANCED" ? "AI diagnosis confidence" : "Diagnosis confidence"}
          value={d.confidence}
        />
        {d.evidence?.length > 0 && (
          <div>
            <p className="text-[11px] font-mono text-fg-faint uppercase mb-1">Evidence</p>
            <ul className="space-y-0.5">
              {d.evidence.slice(0, 6).map((e, i) => (
                <li key={i} className="text-[12px] text-fg-muted font-mono flex gap-1.5">
                  <span className="text-fg-faint">–</span>
                  <span className="break-words">{e}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* RECOVERY PREDICTION */}
      <div className="space-y-3 border-t border-border/60 pt-4">
        <SectionTitle>Recovery Prediction</SectionTitle>
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[11px] font-mono text-fg-faint uppercase">Recovery Probability</p>
            <p className="text-3xl font-bold font-mono text-fg tabular-nums mt-0.5">
              {Math.round(p.recovery_probability * 100)}%
            </p>
          </div>
          <span
            className={cn(
              "text-[12px] font-mono font-semibold px-2 py-1 rounded border",
              p.band === "HIGH" && "text-status-success border-status-success-border bg-status-success-bg",
              p.band === "MEDIUM" && "text-status-warning border-status-warning-border bg-status-warning-bg",
              p.band === "LOW" && "text-status-danger border-status-danger-border bg-status-danger-bg"
            )}
          >
            {p.band} BAND
          </span>
        </div>
        <Meter value={p.recovery_probability} tone={bandTone[p.band] || "bg-status-info/80"} />
        <div className="flex items-center justify-between text-[11px] font-mono text-fg-faint">
          <span>base rate {Math.round(p.base_rate * 100)}%</span>
          <span>model confidence {Math.round(p.confidence * 100)}%</span>
        </div>

        {p.features_used?.length > 0 && (
          <div className="space-y-1 pt-1">
            <p className="text-[11px] font-mono text-fg-faint uppercase mb-1">Contributing Factors</p>
            {p.features_used
              .filter((f) => f.feature !== "failure_category_base_rate")
              .map((f, i) => {
                const c = Math.round(f.contribution * 100);
                const sign = c > 0 ? "+" : c < 0 ? "−" : "±";
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between text-[12px] font-mono"
                  >
                    <span className="text-fg-muted">
                      {f.feature.replace(/_/g, " ")}
                      <span className="text-fg-faint"> · {f.value}</span>
                    </span>
                    <span
                      className={cn(
                        "tabular-nums",
                        f.direction === "positive" && "text-status-success",
                        f.direction === "negative" && "text-status-danger",
                        f.direction === "neutral" && "text-fg-faint"
                      )}
                    >
                      {sign}
                      {Math.abs(c)}%
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </div>

      {/* RECOMMENDED STRATEGY */}
      <div className="space-y-3 border-t border-border/60 pt-4">
        <SectionTitle>Recommended Strategy</SectionTitle>
        <div className="flex items-center justify-between">
          <span className="text-sm font-mono font-semibold text-status-info">{s.action}</span>
          <span className="text-[11px] font-mono text-fg-faint">
            confidence {Math.round(s.confidence * 100)}%
          </span>
        </div>
        <p className="text-[12px] text-fg-muted leading-relaxed">{s.rationale}</p>
        {s.params && Object.keys(s.params).length > 0 && (
          <div className="text-[11px] font-mono text-fg-faint">
            params: {JSON.stringify(s.params)}
          </div>
        )}
        {s.alternatives?.length > 0 && (
          <div className="space-y-1">
            <p className="text-[11px] font-mono text-fg-faint uppercase">Alternatives</p>
            {s.alternatives.map((a, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[12px] font-mono text-fg-muted">
                <ArrowRight className="w-3 h-3 mt-0.5 text-fg-faint shrink-0" />
                <span>
                  <span className="text-fg-secondary">{a.action}</span> — {a.reason}
                </span>
              </div>
            ))}
          </div>
        )}
        <p className="text-[11px] text-fg-faint font-mono">
          Recommendation only — gated by the Policy Engine and Action Executor below.
        </p>
      </div>

      {/* RECOVERY INTENT (Phase 10) */}
      <IntentSection intent={env.intent} />

      {/* POLICY DECISION */}
      <div className="space-y-3 border-t border-border/60 pt-4">
        <SectionTitle>Policy Decision</SectionTitle>
        <div className="flex items-center justify-between">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-1 rounded border",
              vs.tone
            )}
          >
            <VIcon className="w-3.5 h-3.5" />
            {vs.label}
          </span>
          <span className="text-[12px] font-mono">
            Risk <span className={cn("font-semibold", riskTone[pol.risk_level])}>{pol.risk_level}</span>
          </span>
        </div>
        <p className="text-[12px] text-fg-muted leading-relaxed">{pol.reason}</p>

        <div className="space-y-1.5">
          <p className="text-[11px] font-mono text-fg-faint uppercase">Rules Evaluated</p>
          {pol.evaluated_rules.map((r) => (
            <div key={r.rule_id} className="flex items-start gap-2 text-[12px] font-mono">
              {r.passed ? (
                <Check className="w-3.5 h-3.5 text-status-success mt-0.5 shrink-0" />
              ) : (
                <X className="w-3.5 h-3.5 text-status-danger mt-0.5 shrink-0" />
              )}
              <span className="flex-1">
                <span className={cn(r.passed ? "text-fg-secondary" : "text-status-danger")}>
                  {r.name}
                </span>
                <span className="text-fg-faint block">{r.detail}</span>
              </span>
            </div>
          ))}
        </div>

        {pol.allowed_actions?.length > 0 && (
          <p className="text-[11px] font-mono text-status-success/80">
            allowed for automated execution: {pol.allowed_actions.join(", ")}
          </p>
        )}
      </div>

      {/* AI MODEL PREDICTIONS (Phase 6 — advisory only) */}
      <AiPredictionsSection caseId={caseId} />

      {/* ACTION (Phase 3 — ACT) */}
      <ActionSection env={env} caseId={caseId} />

      {/* COMMUNICATIONS (Phase 5) */}
      <CommunicationsSection caseId={caseId} />

      {/* CASE TIMELINE — real audit trail, oldest first */}
      <CaseAuditTimeline caseId={env.case_id} />

      {/* SOURCE */}
      <div className="border-t border-border/60 pt-3 flex flex-wrap items-center justify-between gap-1 text-[11px] font-mono text-fg-faint">
        <span>
          DIAGNOSIS SOURCE: <span className="text-fg-secondary">{env.diagnosis_source || env.provider}</span>
          {env.provider_version ? ` · ${env.provider_version}` : ""}
          {env.intelligence_version ? ` · pipeline v${env.intelligence_version}` : ""}
          {" · analysis #"}{env.version}
        </span>
        <span>{env.analyzed_at ? formatDateTime(env.analyzed_at) : ""}</span>
      </div>
      <p className="text-[11px] font-mono text-fg-faint">
        Prediction, strategy and the Policy Engine are deterministic and are not
        influenced by the diagnosis source.
      </p>

      <div>
        <button
          onClick={analyze}
          disabled={running || isValidating}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-surface-subtle text-[12px] font-mono text-fg-secondary hover:text-fg hover:bg-surface-elevated transition-colors disabled:opacity-50"
        >
          {running ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin" /> Re-analyzing…
            </>
          ) : (
            <>
              <Activity className="w-3 h-3" /> Re-run Analysis
            </>
          )}
        </button>
        {runError && <p className="text-[12px] text-status-danger font-mono mt-2">{runError}</p>}
      </div>
    </div>
  );
}
