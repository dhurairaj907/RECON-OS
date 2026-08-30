"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { ClipboardCheck, ShieldAlert, TrendingDown } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatCard } from "@/components/ui/StatCard";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow, SkeletonCards } from "@/components/ui/SkeletonLoader";
import { IntelligencePanel } from "@/components/modules/IntelligencePanel";
import { CaseHeader } from "@/components/modules/CaseHeader";
import { Reveal } from "@/components/spatial/Reveal";
import { SectionBand } from "@/components/modules/SectionBand";
import { api } from "@/lib/api";
import { RecoveryCase, PaginatedResponse } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

/**
 * A dedicated queue of ONLY the cases whose latest policy verdict is
 * NEEDS_APPROVAL — everything else (Recovery, Intelligence) shows every
 * case; this page exists so an operator can see exactly what needs a human
 * decision, front and center. `RecoveryCaseResponse.intelligence` already
 * embeds `policy_verdict`/`recovery_probability`/`failure_category` (the
 * same field the Recovery page's Intelligence column reads), so this is a
 * client-side filter over the existing endpoints — no new backend route, and
 * the actual Approve/Reject controls are the exact ones already built into
 * IntelligencePanel's Action section (server-revalidated, never a frontend
 * decision).
 *
 * NOTE: the queue is built from the CURRENT action state (GET /actions,
 * blocked_reason === "NEEDS_APPROVAL"), not `case.intelligence.policy_verdict`
 * — that field is a snapshot from the last analysis run and goes stale the
 * moment an action is approved/rejected/executed, which would otherwise
 * leave already-decided cases sitting in the queue.
 */
export default function ApprovalsPage() {
  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null);

  const { data, error, mutate, isValidating } = useSWR<PaginatedResponse<RecoveryCase>>(
    "/api/v1/recovery-cases?limit=100:approvals-queue",
    () => api.getRecoveryCases({ limit: 100 }),
    { refreshInterval: 4000 }
  );
  const { data: blockedActions } = useSWR(
    "/api/v1/actions?status=BLOCKED&limit=200:approvals-queue",
    () => api.getAllActions({ status: "BLOCKED", limit: 200 }),
    { refreshInterval: 4000 }
  );

  const isLoading = (!data && !error) || !blockedActions;
  const needsApprovalCaseIds = new Set(
    (blockedActions?.items || [])
      .filter((a) => a.blocked_reason === "NEEDS_APPROVAL")
      .map((a) => a.recovery_case_id)
  );
  const queue = (data?.items || []).filter((c) => needsApprovalCaseIds.has(c.id));
  const totalAtRisk = queue.reduce((sum, c) => sum + Number(c.amount_at_risk || 0), 0);
  const highRiskCount = queue.filter((c) => c.intelligence?.risk_level === "HIGH").length;

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating} tone={queue.length > 0 ? "warning" : "idle"}>
      <SectionBand
        eyebrow="HUMAN APPROVAL QUEUE"
        title="APPROVALS"
        subtitle="Every case the Policy Engine has flagged as requiring a human decision before any recovery action executes."
      />

      {isLoading ? (
        <SkeletonCards count={3} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard
            title="Pending Approvals"
            value={queue.length}
            icon={ClipboardCheck}
            variant={queue.length > 0 ? "warning" : "default"}
            subtitle="Awaiting a human decision"
          />
          <StatCard
            title="Amount Awaiting Decision"
            value={totalAtRisk}
            isCurrency
            icon={TrendingDown}
            variant="danger"
            subtitle="Sum of amount at risk, queued cases"
          />
          <StatCard
            title="High Risk"
            value={highRiskCount}
            icon={ShieldAlert}
            variant={highRiskCount > 0 ? "danger" : "default"}
            subtitle="Risk level HIGH in this queue"
          />
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow cols={6} />
            <SkeletonRow cols={6} />
          </div>
        ) : queue.length === 0 ? (
          <EmptyState
            title="No pending approvals"
            description="Every analysed case is currently either auto-approved, rejected by policy, or already actioned. Cases needing a human decision will appear here."
            icon={ClipboardCheck}
            actionText="View Recovery Cases"
            actionHref="/recovery"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline backdrop-blur-sm">
                <tr>
                  <th className="py-4 px-4">Case #</th>
                  <th className="py-4 px-4">Customer</th>
                  <th className="py-4 px-4">Amount</th>
                  <th className="py-4 px-4">Risk</th>
                  <th className="py-4 px-4">Recovery Probability</th>
                  <th className="py-4 px-4 text-right">Waiting Since</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {queue.map((c) => (
                  <Reveal
                    key={c.id}
                    as="tr"
                    onClick={() => setSelectedCase(c)}
                    className="cursor-pointer border-l-2 border-transparent transition-colors hover:border-status-warning hover:bg-surface-elevated/40"
                  >
                    <td className="py-4 px-4 font-mono font-medium text-status-info">{c.case_number}</td>
                    <td className="py-4 px-4 text-fg">
                      {c.customer?.name || c.customer?.email || "Unknown Customer"}
                    </td>
                    <td className="py-4 px-4 font-mono font-semibold text-status-danger tabular-nums">
                      {formatINR(c.amount_at_risk)}
                    </td>
                    <td className="py-4 px-4">
                      <StatusBadge status={c.intelligence?.risk_level || "—"} />
                    </td>
                    <td className="py-4 px-4 font-mono text-fg-secondary">
                      {c.intelligence?.recovery_probability != null
                        ? `${Math.round(c.intelligence.recovery_probability * 100)}%`
                        : "—"}
                    </td>
                    <td className="py-4 px-4 text-right font-mono text-fg-muted">
                      {formatRelativeTime(c.opened_at)}
                    </td>
                  </Reveal>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <DetailDrawer
        isOpen={!!selectedCase}
        onClose={() => setSelectedCase(null)}
        title={`RECOVERY CASE ${selectedCase?.case_number}`}
        subtitle={`Opened ${formatDateTime(selectedCase?.opened_at)}`}
        badge={selectedCase ? <StatusBadge status="NEEDS_APPROVAL" /> : null}
      >
        {selectedCase && (
          <div className="space-y-6 text-xs">
            <CaseHeader
              caseNumber={selectedCase.case_number}
              amountAtRisk={selectedCase.amount_at_risk}
              amountRecovered={selectedCase.amount_recovered}
              failureCode={selectedCase.failure_code}
              failureReason={selectedCase.failure_reason}
              tone="warning"
              recovered={false}
            />
            {selectedCase.customer && (
              <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2.5">
                <div className="flex justify-between">
                  <span className="text-fg-muted">Customer:</span>
                  <span className="text-fg font-medium">{selectedCase.customer.name || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Email:</span>
                  <span className="font-mono text-status-info">{selectedCase.customer.email || "N/A"}</span>
                </div>
              </div>
            )}
            {/* Full THINK breakdown + the real Approve/Reject controls */}
            <IntelligencePanel caseId={selectedCase.id} caseNumber={selectedCase.case_number} />
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
