"use client";

import React from "react";
import useSWR from "swr";
import { AlertTriangle, ShieldCheck, HelpCircle, Landmark } from "lucide-react";
import { api } from "@/lib/api";
import { cn, formatDateTime, formatINR } from "@/lib/utils";

interface Props {
  paymentId: string;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[12px] font-mono font-semibold text-fg-secondary uppercase tracking-widest">
      {children}
    </h4>
  );
}

const reconciliationTone: Record<string, string> = {
  IN_SYNC: "text-status-success border-status-success-border bg-status-success-bg",
  MISMATCH: "text-status-danger border-status-danger-border bg-status-danger-bg",
  UNVERIFIED: "text-fg-muted border-border bg-surface-elevated",
};

const lifecycleTone: Record<string, string> = {
  CAPTURED: "text-status-success",
  SETTLED: "text-status-success",
  FAILED: "text-status-danger",
  REFUNDED: "text-status-warning",
  PARTIALLY_REFUNDED: "text-status-warning",
  DISPUTED: "text-status-danger",
  EXPIRED: "text-fg-muted",
  MISMATCHED: "text-status-danger",
  PENDING: "text-fg-muted",
  AUTHORIZED: "text-status-info",
};

/**
 * Phase 9 — read-only payment reconciliation status for the payment behind a
 * recovery case. Shows RECON's provider-neutral lifecycle_status (separate
 * from RecoveryCase.status — the recovery workflow), whether it agrees with
 * the last authoritative provider evidence seen (reconciliation_status),
 * and the correlated event/audit timeline. Nothing here is editable — the
 * only writer of this state is apps/api/services/reconciliation.py.
 */
export function ReconciliationPanel({ paymentId }: Props) {
  const { data, isLoading } = useSWR(
    paymentId ? `/api/v1/payments/${paymentId}/reconciliation` : null,
    () => api.getPaymentReconciliation(paymentId)
  );

  if (!paymentId) return null;
  if (isLoading || !data) {
    return (
      <div className="space-y-2 border-t border-border/60 pt-4">
        <SectionTitle>Payment Reconciliation</SectionTitle>
        <div className="h-16 rounded-xl border border-border bg-surface/60 animate-pulse" />
      </div>
    );
  }

  const mismatch = data.reconciliation_status === "MISMATCH";

  return (
    <div className="space-y-3 border-t border-border/60 pt-4">
      <div className="flex items-center gap-2">
        <Landmark className="w-4 h-4 text-fg-muted" />
        <SectionTitle>Payment Reconciliation</SectionTitle>
      </div>

      {mismatch && (
        <div className="flex items-start gap-2 rounded-lg border border-status-danger-border bg-status-danger-bg px-3 py-2">
          <AlertTriangle className="w-4 h-4 text-status-danger mt-0.5 shrink-0" />
          <p className="text-[12px] font-mono text-status-danger">
            RECON&apos;s recorded state disagrees with the last provider evidence for this
            payment — see the timeline below and{" "}
            <span className="font-semibold">GET /api/v1/reconciliation/mismatches</span>{" "}
            for the full audit detail. No state was changed automatically.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-[12px] font-mono">
        <div>
          <div className="text-fg-faint uppercase tracking-wide text-[10px] mb-0.5">Payment Status</div>
          <span className={cn("font-semibold", lifecycleTone[data.lifecycle_status || ""] || "text-fg-muted")}>
            {data.lifecycle_status || "UNOBSERVED"}
          </span>
          <span className="text-fg-faint ml-1">(raw: {data.raw_status})</span>
        </div>
        <div>
          <div className="text-fg-faint uppercase tracking-wide text-[10px] mb-0.5">Reconciliation Status</div>
          <span
            className={cn(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border font-semibold",
              reconciliationTone[data.reconciliation_status]
            )}
          >
            {data.reconciliation_status === "IN_SYNC" ? (
              <ShieldCheck className="w-3 h-3" />
            ) : data.reconciliation_status === "MISMATCH" ? (
              <AlertTriangle className="w-3 h-3" />
            ) : (
              <HelpCircle className="w-3 h-3" />
            )}
            {data.reconciliation_status}
          </span>
        </div>
        <div>
          <div className="text-fg-faint uppercase tracking-wide text-[10px] mb-0.5">Provider</div>
          <span className="text-fg">{data.provider}</span>
        </div>
        {data.refunded_amount_paise > 0 && (
          <div>
            <div className="text-fg-faint uppercase tracking-wide text-[10px] mb-0.5">Refunded</div>
            <span className="text-status-warning font-semibold">
              {formatINR(data.refunded_amount_paise / 100)}
            </span>
          </div>
        )}
        {data.dispute_status && (
          <div>
            <div className="text-fg-faint uppercase tracking-wide text-[10px] mb-0.5">Dispute</div>
            <span className="text-status-danger font-semibold">{data.dispute_status}</span>
          </div>
        )}
      </div>

      {data.timeline.length > 0 && (
        <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
          <div className="text-fg-faint uppercase tracking-wide text-[10px]">Provider Event Timeline</div>
          {data.timeline.map((entry, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] font-mono">
              <span className="text-fg-faint shrink-0 w-32">{formatDateTime(entry.timestamp)}</span>
              <span className="text-fg-secondary">
                {entry.source === "event"
                  ? `Event: ${entry.event_type} (${entry.processing_status})`
                  : `${entry.action}: ${entry.detail}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
