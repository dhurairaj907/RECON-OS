/**
 * RECON OS — pipeline model (pure).
 *
 * Maps REAL backend payloads to the spatial pipeline's stage list.
 * No fetching, no rendering, and — critically — NO fabrication:
 * anything the backend has not told us is `pending` / `UNKNOWN`, never a
 * guessed result. A recovery only shows as `done` when the data says so.
 */

import type {
  IntelligenceEnvelope,
  RecoveryAction,
  DashboardMetrics,
} from "@/lib/types";
import { formatINR } from "@/lib/utils";

export type StageStatus =
  | "done"
  | "active"
  | "pending"
  | "blocked"
  | "rejected";

export type Provenance = "verified" | "simulated";

/**
 * The ONLY strategies the backend can ever turn into a real, executable
 * RecoveryAction — an exact mirror of
 * apps/api/services/actions/common.py::PAYMENT_LINK_ELIGIBLE_STRATEGIES.
 * A strategy outside this set (MANUAL_REVIEW, NO_ACTION, ...) can never
 * produce a RecoveryAction, no matter what the policy verdict says — see
 * services/actions/proposal.py::build_proposal's STRATEGY_NOT_ELIGIBLE
 * path. Shared here (not duplicated) so every UI surface that needs to
 * know "is this strategy actionable" — IntelligencePanel's ActionSection
 * and this module's own deriveCasePipeline — agrees, by construction.
 */
export const ELIGIBLE_STRATEGIES = ["RETRY_NOW", "RETRY_DELAYED", "SEND_PAYMENT_LINK"];

export interface PipelineStage {
  key: string;
  label: string;
  status: StageStatus;
  /** Primary datum shown on the node (short). */
  value?: string;
  /** Secondary line (small). */
  sub?: string;
  /** Only meaningful on RAZORPAY / RECOVERED. */
  provenance?: Provenance;
  /** Extra caption, e.g. the simulated disclaimer. */
  note?: string;
}

const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${Math.round(n * 100)}%`;

/** Exactly one `active` node: the frontier right after the last `done`. */
function markFrontier(stages: PipelineStage[]): PipelineStage[] {
  const halt = stages.findIndex(
    (s) => s.status === "blocked" || s.status === "rejected"
  );
  if (halt !== -1) return stages;
  let lastDone = -1;
  stages.forEach((s, i) => {
    if (s.status === "done") lastDone = i;
  });
  const next = stages[lastDone + 1];
  if (next && next.status === "pending") next.status = "active";
  return stages;
}

/* ------------------------------------------------------------------ */
/* Single-case pipeline (Intelligence page + Recovery drawer)          */
/* ------------------------------------------------------------------ */

export function deriveCasePipeline(
  env: IntelligenceEnvelope | null | undefined,
  action?: RecoveryAction | null,
  caseStatus?: string | null
): PipelineStage[] {
  const d = env?.diagnosis;
  const p = env?.prediction;
  const s = env?.strategy;
  const pol = env?.policy;
  const analysisFailed = env?.status === "FAILED";
  const ui = (action?.ui_state || "").toUpperCase();

  // EVENT — the case exists because a payment failed.
  const event: PipelineStage = {
    key: "event",
    label: "EVENT",
    status: "done",
    value: "PAYMENT FAILED",
    sub: env?.case_number || undefined,
  };

  // DIAGNOSIS
  const diagnosis: PipelineStage = {
    key: "diagnosis",
    label: "AI DIAGNOSIS",
    status: analysisFailed ? "blocked" : d ? "done" : "pending",
    value: analysisFailed ? "RUN FAILED" : d ? d.failure_category : "NOT RUN",
    sub: d
      ? env?.diagnosis_source || env?.provider || undefined
      : analysisFailed
      ? env?.error_message?.slice(0, 60) || undefined
      : "awaiting analysis",
  };

  // PREDICTION
  const prediction: PipelineStage = {
    key: "prediction",
    label: "PREDICTION",
    status: p ? "done" : "pending",
    value: p ? pct(p.recovery_probability) : "—",
    sub: p ? `${p.band} band` : "not available",
  };

  // STRATEGY
  const strategy: PipelineStage = {
    key: "strategy",
    label: "STRATEGY",
    status: s ? "done" : "pending",
    value: s ? s.action : "—",
    sub: s ? `confidence ${pct(s.confidence)}` : "not available",
  };

  // POLICY
  const verdict = (pol?.verdict || "").toUpperCase();
  const policy: PipelineStage = {
    key: "policy",
    label: "POLICY",
    status: !pol
      ? "pending"
      : verdict === "APPROVED"
      ? "done"
      : verdict === "REJECTED"
      ? "rejected"
      : "blocked",
    value: pol ? verdict.replace("_", " ") : "—",
    sub: pol ? `risk ${pol.risk_level}` : "not evaluated",
  };

  // ACTION
  let action_: PipelineStage;
  if (!action) {
    // A policy verdict of NEEDS_APPROVAL does NOT by itself mean a
    // CREATE_PAYMENT_LINK action is pending approval — the Policy Engine
    // forces NEEDS_APPROVAL for ANY MANUAL_REVIEW strategy too (see
    // policy_engine.py), and MANUAL_REVIEW can never become a
    // RecoveryAction (not in ELIGIBLE_STRATEGIES). Only claim an
    // approvable payment-link action exists when the strategy is one
    // that's actually eligible to become one — otherwise this is a human-
    // review hold with no automated action at all, and must say so rather
    // than fabricating "AWAITING APPROVAL" / "CREATE_PAYMENT_LINK" for
    // something that was never proposed and never will be.
    const strategyEligible = !!s && ELIGIBLE_STRATEGIES.includes(s.action);
    const manualReviewHold = verdict === "NEEDS_APPROVAL" && !strategyEligible;
    action_ = {
      key: "action",
      label: "ACTION",
      status:
        verdict === "REJECTED"
          ? "rejected"
          : verdict === "NEEDS_APPROVAL"
          ? "blocked"
          : "pending",
      value:
        verdict === "REJECTED"
          ? "NO ACTION"
          : manualReviewHold
          ? "MANUAL REVIEW REQUIRED"
          : verdict === "NEEDS_APPROVAL"
          ? "AWAITING APPROVAL"
          : verdict === "APPROVED"
          ? "READY"
          : "—",
      sub: manualReviewHold ? "NO AUTOMATED ACTION" : "CREATE_PAYMENT_LINK",
    };
  } else {
    const st = (action.status || "").toUpperCase();
    action_ = {
      key: "action",
      label: "ACTION",
      status:
        st === "EXECUTED"
          ? "done"
          : st === "EXECUTING"
          ? "active"
          : st === "BLOCKED"
          ? "blocked"
          : st === "FAILED"
          ? "rejected"
          : "pending",
      value:
        st === "EXECUTED"
          ? "PAYMENT LINK SENT"
          : st === "BLOCKED"
          ? action.blocked_reason || "BLOCKED"
          : st === "FAILED"
          ? action.error_code || "FAILED"
          : action.action_type,
      sub: action.reference_id || undefined,
    };
  }

  // RAZORPAY — the provider interaction
  let razorpay: PipelineStage;
  if (!action || !action.provider_action_id) {
    razorpay = {
      key: "razorpay",
      label: "RAZORPAY",
      status: "pending",
      value: "—",
      sub: "no payment link yet",
    };
  } else if (ui === "RECOVERED") {
    razorpay = {
      key: "razorpay",
      label: "RAZORPAY",
      status: "done",
      value: action.simulated ? "SIMULATED EVENT" : "PROVIDER CONFIRMED",
      sub: action.provider_status || "paid",
      provenance: action.simulated ? "simulated" : "verified",
    };
  } else if (ui === "PARTIAL") {
    razorpay = {
      key: "razorpay",
      label: "RAZORPAY",
      status: "blocked",
      value: "PARTIALLY PAID",
      sub: action.provider_status || "partially_paid",
    };
  } else if (ui === "EXPIRED" || ui === "CANCELLED") {
    razorpay = {
      key: "razorpay",
      label: "RAZORPAY",
      status: "rejected",
      value: ui,
      sub: action.provider_status || ui.toLowerCase(),
    };
  } else {
    razorpay = {
      key: "razorpay",
      label: "RAZORPAY",
      status: "active",
      value: "LINK OPEN",
      sub: action.simulator_enabled ? "test mode · awaiting payment" : "awaiting payment",
    };
  }

  // RECOVERED
  let recovered: PipelineStage;
  if (ui === "RECOVERED") {
    recovered = {
      key: "recovered",
      label: "RECOVERED",
      status: "done",
      value: formatINR(action?.recovered_amount),
      provenance: action?.simulated ? "simulated" : "verified",
      note: action?.simulated
        ? "SIMULATED — not a real payment"
        : "Provider verified",
    };
  } else if (ui === "PARTIAL") {
    recovered = {
      key: "recovered",
      label: "RECOVERED",
      status: "blocked",
      value: "PARTIAL",
      note: "case not resolved — revenue not counted",
    };
  } else {
    const resolved = (caseStatus || "").toUpperCase() === "RESOLVED";
    recovered = {
      key: "recovered",
      label: "RECOVERED",
      status: resolved && !action ? "done" : "pending",
      value: resolved && !action ? "RESOLVED" : "PENDING",
      sub: resolved && !action ? "resolved outside Phase 3" : undefined,
    };
  }

  return markFrontier([
    event,
    diagnosis,
    prediction,
    strategy,
    policy,
    action_,
    razorpay,
    recovered,
  ]);
}

/* ------------------------------------------------------------------ */
/* System pipeline (Command Center) — aggregate, real counts only      */
/* ------------------------------------------------------------------ */

export function deriveSystemPipeline(
  m: DashboardMetrics | null | undefined
): PipelineStage[] {
  const intel = m?.intelligence;
  const act = m?.actions;
  const n = (v: number | undefined | null) => (v == null ? 0 : v);

  const eventsN = n(m?.events_processed);
  const analyzedN = n(intel?.cases_analyzed);
  const approvedN = n(intel?.policy_approved);
  const executedN = n(act?.actions_executed);
  const linksN = n(act?.payment_links_created);
  const recoveredReal = act?.revenue_recovered ?? "0";
  const simRecovered = Number(act?.simulated_revenue_recovered ?? 0);

  const stage = (
    key: string,
    label: string,
    count: number,
    value: string,
    sub?: string
  ): PipelineStage => ({
    key,
    label,
    status: count > 0 ? "done" : "pending",
    value,
    sub,
  });

  const stages: PipelineStage[] = [
    stage("event", "EVENTS", eventsN, `${eventsN}`, "processed"),
    stage("diagnosis", "DIAGNOSIS", analyzedN, `${analyzedN}`, "cases analyzed"),
    stage(
      "prediction",
      "PREDICTION",
      analyzedN,
      `${n(intel?.high_recovery_probability)}`,
      "high recovery band"
    ),
    stage("strategy", "STRATEGY", analyzedN, `${analyzedN}`, "strategies formed"),
    stage(
      "policy",
      "POLICY",
      analyzedN,
      `${approvedN}`,
      `${n(intel?.needs_approval)} hold · ${n(intel?.policy_rejected)} rejected`
    ),
    stage(
      "action",
      "ACTION",
      executedN,
      `${executedN}`,
      `${n(act?.actions_blocked)} blocked`
    ),
    stage(
      "razorpay",
      "RAZORPAY",
      linksN,
      `${linksN}`,
      `${n(act?.pending_recoveries)} pending · ${n(act?.partial_recoveries)} partial`
    ),
    {
      key: "recovered",
      label: "RECOVERED",
      status: Number(recoveredReal) > 0 ? "done" : "pending",
      value: formatINR(recoveredReal),
      sub:
        act && act.recovery_rate != null
          ? `${Math.round(act.recovery_rate * 100)}% recovery rate`
          : undefined,
      provenance: Number(recoveredReal) > 0 ? "verified" : undefined,
      note:
        simRecovered > 0
          ? `+ ${formatINR(simRecovered)} simulated (excluded)`
          : undefined,
    },
  ];

  return markFrontier(stages);
}

/* ------------------------------------------------------------------ */
/* Shared presentation metadata                                        */
/* ------------------------------------------------------------------ */

export const STATUS_META: Record<
  StageStatus,
  { label: string; dot: string; text: string; ring: string; chip: string }
> = {
  done: {
    label: "completed",
    dot: "bg-status-success",
    text: "text-status-success",
    ring: "border-status-success/40",
    chip: "bg-status-success-bg text-status-success border-status-success-border",
  },
  active: {
    label: "in progress",
    dot: "bg-accent",
    text: "text-accent",
    ring: "border-accent/50",
    chip: "bg-accent/10 text-accent border-accent/40",
  },
  pending: {
    label: "pending",
    dot: "bg-status-neutral",
    text: "text-fg-faint",
    ring: "border-border",
    chip: "bg-surface-elevated text-fg-faint border-border",
  },
  blocked: {
    label: "needs attention",
    dot: "bg-status-warning",
    text: "text-status-warning",
    ring: "border-status-warning/45",
    chip: "bg-status-warning-bg text-status-warning border-status-warning-border",
  },
  rejected: {
    label: "rejected",
    dot: "bg-status-danger",
    text: "text-status-danger",
    ring: "border-status-danger/45",
    chip: "bg-status-danger-bg text-status-danger border-status-danger-border",
  },
};
