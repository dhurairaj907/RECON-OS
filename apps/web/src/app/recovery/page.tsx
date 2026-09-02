"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, ShieldAlert, ChevronLeft, ChevronRight, TrendingDown, CheckCircle2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { StatCard } from "@/components/ui/StatCard";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { SkeletonCards } from "@/components/ui/SkeletonLoader";
import { IntelligencePanel } from "@/components/modules/IntelligencePanel";
import { ReconciliationPanel } from "@/components/modules/ReconciliationPanel";
import { CaseHeader } from "@/components/modules/CaseHeader";
import { Reveal } from "@/components/spatial/Reveal";
import { SectionBand } from "@/components/modules/SectionBand";
import type { GlowTone } from "@/components/spatial/AtmosphericGlow";
import { api } from "@/lib/api";
import { RecoveryCase, PaginatedResponse, DashboardMetrics } from "@/lib/types";
import { cn, formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

const priorityTone: Record<string, GlowTone> = {
  CRITICAL: "danger",
  HIGH: "warning",
  MEDIUM: "info",
  LOW: "info",
};

function caseTone(c: RecoveryCase | null): GlowTone {
  if (!c) return "idle";
  if ((c.status || "").toUpperCase() === "RESOLVED") return "success";
  return priorityTone[c.priority] || "info";
}

export default function RecoveryCasesPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null);

  const { data, error, mutate, isValidating } = useSWR<PaginatedResponse<RecoveryCase>>(
    [`/api/v1/recovery-cases`, page, statusFilter, priorityFilter, searchQuery],
    () =>
      api.getRecoveryCases({
        page,
        limit: 15,
        status: statusFilter || undefined,
        priority: priorityFilter || undefined,
        search: searchQuery || undefined,
      }),
    { refreshInterval: 3000 }
  );

  const { data: metrics } = useSWR<DashboardMetrics>(
    "/api/v1/dashboard/metrics",
    () => api.getDashboardMetrics(),
    { refreshInterval: 5000 }
  );

  const totalPages = data ? Math.ceil(data.total / 15) : 1;
  const isLoading = !data && !error;

  const pageTone: GlowTone = selectedCase
    ? caseTone(selectedCase)
    : (data?.items || []).some(
        (c) => c.priority === "CRITICAL" && (c.status || "").toUpperCase() !== "RESOLVED"
      )
    ? "danger"
    : (data?.items || []).some((c) => (c.status || "").toUpperCase() !== "RESOLVED")
    ? "warning"
    : "idle";

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating} tone={pageTone}>
      <SectionBand
        eyebrow="CASE MANAGEMENT"
        title="RECOVERY CASES"
        subtitle="Active and resolved recovery cases automatically generated from payment failures."
      />

      <div className="flex items-center justify-end">
        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Cases: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Case Network — live system-wide aggregates, not the paginated table below */}
      {!metrics ? (
        <SkeletonCards count={3} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard
            title="Revenue at Risk"
            value={metrics.revenue_at_risk}
            isCurrency
            icon={TrendingDown}
            variant="danger"
            subtitle="Across all open cases"
          />
          <StatCard
            title="Active Recovery Cases"
            value={metrics.active_recovery_cases}
            icon={ShieldAlert}
            variant="warning"
            subtitle="DETECTED + OPEN"
          />
          <StatCard
            title="Needs Approval"
            value={metrics.intelligence?.needs_approval ?? "—"}
            icon={CheckCircle2}
            variant="info"
            subtitle="Policy verdict pending a human"
          />
        </div>
      )}

      {/* Filter bar + table stay visually tight to each other — one operational unit */}
      <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface/60 p-4 backdrop-blur-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-faint" />
          <input
            type="text"
            placeholder="Search by case number (e.g. RC-10001) or failure reason..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full h-11 bg-surface-subtle border border-border rounded-lg pl-10 pr-4 text-sm text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
          />
        </div>

        <div className="flex items-center space-x-2 w-full md:w-auto">
          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Statuses</option>
            <option value="DETECTED">DETECTED</option>
            <option value="OPEN">OPEN</option>
            <option value="RESOLVED">RESOLVED</option>
            <option value="CLOSED">CLOSED</option>
          </select>

          {/* Priority Filter */}
          <select
            value={priorityFilter}
            onChange={(e) => {
              setPriorityFilter(e.target.value);
              setPage(1);
            }}
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Priorities</option>
            <option value="CRITICAL">CRITICAL (&ge; ₹50k)</option>
            <option value="HIGH">HIGH (&ge; ₹10k)</option>
            <option value="MEDIUM">MEDIUM (&ge; ₹2.5k)</option>
            <option value="LOW">LOW (&lt; ₹2.5k)</option>
          </select>
        </div>
      </div>

      {/* Recovery Cases Table */}
      <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow cols={8} />
            <SkeletonRow cols={8} />
            <SkeletonRow cols={8} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No recovery cases found"
            description="Payment failures automatically generate tracked recovery cases here."
            actionText="Simulate Payment Failure"
            actionHref="/simulator"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline backdrop-blur-sm">
                  <tr>
                    <th className="py-4 px-4">Case #</th>
                    <th className="py-4 px-4">Customer</th>
                    <th className="py-4 px-4">Amount at Risk</th>
                    <th className="py-4 px-4">Recovered</th>
                    <th className="py-4 px-4">Priority</th>
                    <th className="py-4 px-4">Status</th>
                    <th className="py-4 px-4">Intelligence</th>
                    <th className="py-4 px-4">Failure Reason</th>
                    <th className="py-4 px-4 text-right">Age</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {data.items.map((c) => (
                    <Reveal
                      key={c.id}
                      as="tr"
                      onClick={() => setSelectedCase(c)}
                      className={cn(
                        "group cursor-pointer border-l-2 border-transparent transition-colors hover:bg-surface-elevated/40",
                        c.priority === "CRITICAL" && "hover:border-status-danger",
                        c.priority === "HIGH" && "hover:border-status-warning",
                        (c.status || "").toUpperCase() === "RESOLVED" && "hover:border-status-success"
                      )}
                    >
                      <td className="py-4 px-4 font-mono font-medium text-status-info">
                        {c.case_number}
                      </td>
                      <td className="py-4 px-4 text-fg">
                        {c.customer?.name || c.customer?.email || "Unknown Customer"}
                      </td>
                      <td className="py-4 px-4 font-mono font-semibold text-status-danger tabular-nums">
                        {formatINR(c.amount_at_risk)}
                      </td>
                      <td className="py-4 px-4 font-mono text-status-success tabular-nums">
                        {formatINR(c.amount_recovered)}
                      </td>
                      <td className="py-4 px-4">
                        <StatusBadge status={c.priority} type="priority" />
                      </td>
                      <td className="py-4 px-4">
                        <StatusBadge status={c.status} type="case" />
                      </td>
                      <td className="py-4 px-4 font-mono text-[11px]">
                        {c.intelligence ? (
                          <div className="flex flex-col gap-0.5">
                            <span
                              className={
                                c.intelligence.policy_verdict === "APPROVED"
                                  ? "text-status-success"
                                  : c.intelligence.policy_verdict === "REJECTED"
                                  ? "text-status-danger"
                                  : "text-status-warning"
                              }
                            >
                              {c.intelligence.policy_verdict}
                            </span>
                            <span className="text-fg-faint">
                              {c.intelligence.failure_category} ·{" "}
                              {c.intelligence.recovery_probability != null
                                ? `${Math.round(c.intelligence.recovery_probability * 100)}%`
                                : "—"}
                            </span>
                          </div>
                        ) : (
                          <span className="text-fg-faint">not analyzed</span>
                        )}
                      </td>
                      <td className="py-4 px-4 text-fg-muted truncate max-w-xs">
                        {c.failure_reason || "N/A"}
                      </td>
                      <td className="py-4 px-4 text-right font-mono text-fg-muted">
                        {formatRelativeTime(c.opened_at)}
                      </td>
                    </Reveal>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-subtle text-xs font-mono text-fg-muted">
              <div>
                Page <span className="text-fg font-medium">{page}</span> of{" "}
                <span className="text-fg font-medium">{totalPages || 1}</span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
      </div>

      {/* Case Detail Drawer */}
      <DetailDrawer
        isOpen={!!selectedCase}
        onClose={() => setSelectedCase(null)}
        title={`RECOVERY CASE ${selectedCase?.case_number}`}
        subtitle={`Opened ${formatDateTime(selectedCase?.opened_at)}`}
        badge={selectedCase ? <StatusBadge status={selectedCase.status} /> : null}
      >
        {selectedCase && (
          <div className="space-y-6 text-xs">
            <CaseHeader
              caseNumber={selectedCase.case_number}
              amountAtRisk={selectedCase.amount_at_risk}
              amountRecovered={selectedCase.amount_recovered}
              failureCode={selectedCase.failure_code}
              failureReason={selectedCase.failure_reason}
              tone={
                (selectedCase.status || "").toUpperCase() === "RESOLVED"
                  ? "success"
                  : selectedCase.priority === "CRITICAL"
                  ? "danger"
                  : selectedCase.priority === "HIGH"
                  ? "warning"
                  : "info"
              }
              recovered={
                (selectedCase.status || "").toUpperCase() === "RESOLVED" &&
                Number(selectedCase.amount_recovered) > 0
              }
            />

            {/* Diagnostic Details */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                Failure Diagnostics (Phase 1)
              </h3>
              <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2.5">
                <div className="flex justify-between">
                  <span className="text-fg-muted">Failure Reason:</span>
                  <span className="text-fg font-medium">{selectedCase.failure_reason || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Error Code:</span>
                  <span className="font-mono text-status-warning">{selectedCase.failure_code || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Deterministic Priority:</span>
                  <StatusBadge status={selectedCase.priority} />
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Retry Counter:</span>
                  <span className="font-mono text-fg-secondary">
                    {selectedCase.attempt_count} of max {selectedCase.max_attempts}
                  </span>
                </div>
                {selectedCase.resolved_at && (
                  <div className="flex justify-between border-t border-border/60 pt-2">
                    <span className="text-fg-muted">Resolved Timestamp:</span>
                    <span className="font-mono text-status-success">{formatDateTime(selectedCase.resolved_at)}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Customer Details */}
            {selectedCase.customer && (
              <div className="space-y-3">
                <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                  Customer Context
                </h3>
                <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2.5">
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Customer Name:</span>
                    <span className="text-fg font-medium">{selectedCase.customer.name || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Email:</span>
                    <span className="font-mono text-status-info">{selectedCase.customer.email || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Phone:</span>
                    <span className="font-mono text-fg-secondary">{selectedCase.customer.phone || "N/A"}</span>
                  </div>
                  <div className="flex justify-between border-t border-border/60 pt-2">
                    <span className="text-fg-muted">Lifetime Secured Revenue:</span>
                    <span className="font-mono text-status-success font-semibold">
                      {formatINR(selectedCase.customer.total_payment_amount)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Phase 2 — THINK: RECON Intelligence */}
            <IntelligencePanel caseId={selectedCase.id} caseNumber={selectedCase.case_number} />

            {/* Phase 9 — payment reconciliation (only when a payment exists) */}
            {selectedCase.payment_id && (
              <ReconciliationPanel paymentId={selectedCase.payment_id} />
            )}
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
