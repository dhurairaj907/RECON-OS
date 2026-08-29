"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, ShieldAlert, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { IntelligencePanel } from "@/components/modules/IntelligencePanel";
import { api } from "@/lib/api";
import { RecoveryCase, PaginatedResponse } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

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

  const totalPages = data ? Math.ceil(data.total / 15) : 1;
  const isLoading = !data && !error;

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating}>
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-mono tracking-wider text-slate-400 uppercase">
              Case Management
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white font-mono mt-1">
            RECOVERY CASES
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Active and resolved recovery cases automatically generated from payment failures.
          </p>
        </div>

        <div className="text-xs font-mono text-slate-400 bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Cases: <span className="text-white font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-surface p-4 rounded-lg border border-border flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search by case number (e.g. RC-10001) or failure reason..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full bg-surface-subtle border border-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-accent"
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
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-accent font-mono"
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
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-accent font-mono"
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
      <div className="bg-surface rounded-lg border border-border overflow-hidden">
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
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-elevated/50 text-slate-400 font-mono text-[11px] uppercase border-b border-border">
                  <tr>
                    <th className="py-3 px-4">Case #</th>
                    <th className="py-3 px-4">Customer</th>
                    <th className="py-3 px-4">Amount at Risk</th>
                    <th className="py-3 px-4">Recovered</th>
                    <th className="py-3 px-4">Priority</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Intelligence</th>
                    <th className="py-3 px-4">Failure Reason</th>
                    <th className="py-3 px-4 text-right">Age</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.items.map((c) => (
                    <tr
                      key={c.id}
                      onClick={() => setSelectedCase(c)}
                      className="hover:bg-surface-elevated/40 cursor-pointer transition-colors"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-blue-400">
                        {c.case_number}
                      </td>
                      <td className="py-3 px-4 text-slate-200">
                        {c.customer?.name || c.customer?.email || "Unknown Customer"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-rose-400 tabular-nums">
                        {formatINR(c.amount_at_risk)}
                      </td>
                      <td className="py-3 px-4 font-mono text-emerald-400 tabular-nums">
                        {formatINR(c.amount_recovered)}
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge status={c.priority} type="priority" />
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge status={c.status} type="case" />
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px]">
                        {c.intelligence ? (
                          <div className="flex flex-col gap-0.5">
                            <span
                              className={
                                c.intelligence.policy_verdict === "APPROVED"
                                  ? "text-emerald-400"
                                  : c.intelligence.policy_verdict === "REJECTED"
                                  ? "text-rose-400"
                                  : "text-amber-400"
                              }
                            >
                              {c.intelligence.policy_verdict}
                            </span>
                            <span className="text-slate-500">
                              {c.intelligence.failure_category} ·{" "}
                              {c.intelligence.recovery_probability != null
                                ? `${Math.round(c.intelligence.recovery_probability * 100)}%`
                                : "—"}
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-600">not analyzed</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-400 truncate max-w-xs">
                        {c.failure_reason || "N/A"}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-slate-400">
                        {formatRelativeTime(c.opened_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-subtle text-xs font-mono text-slate-400">
              <div>
                Page <span className="text-white font-medium">{page}</span> of{" "}
                <span className="text-white font-medium">{totalPages || 1}</span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="p-1 rounded bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-slate-300"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1 rounded bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-slate-300"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
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
            {/* Financial Overview */}
            <div className="grid grid-cols-2 gap-4 p-4 rounded-lg bg-surface-subtle border border-border">
              <div>
                <span className="text-slate-400 font-mono">Amount at Risk</span>
                <div className="text-xl font-bold font-mono text-rose-400 mt-1">
                  {formatINR(selectedCase.amount_at_risk)}
                </div>
              </div>
              <div>
                <span className="text-slate-400 font-mono">Amount Recovered</span>
                <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                  {formatINR(selectedCase.amount_recovered)}
                </div>
              </div>
            </div>

            {/* Diagnostic Details */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-slate-300 uppercase tracking-wider">
                Failure Diagnostics (Phase 1)
              </h3>
              <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Failure Reason:</span>
                  <span className="text-white font-medium">{selectedCase.failure_reason || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Error Code:</span>
                  <span className="font-mono text-amber-400">{selectedCase.failure_code || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Deterministic Priority:</span>
                  <StatusBadge status={selectedCase.priority} />
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Retry Counter:</span>
                  <span className="font-mono text-slate-300">
                    {selectedCase.attempt_count} of max {selectedCase.max_attempts}
                  </span>
                </div>
                {selectedCase.resolved_at && (
                  <div className="flex justify-between border-t border-border/60 pt-2">
                    <span className="text-slate-400">Resolved Timestamp:</span>
                    <span className="font-mono text-emerald-400">{formatDateTime(selectedCase.resolved_at)}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Customer Details */}
            {selectedCase.customer && (
              <div className="space-y-3">
                <h3 className="text-xs font-mono font-semibold text-slate-300 uppercase tracking-wider">
                  Customer Context
                </h3>
                <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2.5">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Customer Name:</span>
                    <span className="text-white font-medium">{selectedCase.customer.name || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Email:</span>
                    <span className="font-mono text-blue-400">{selectedCase.customer.email || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Phone:</span>
                    <span className="font-mono text-slate-300">{selectedCase.customer.phone || "N/A"}</span>
                  </div>
                  <div className="flex justify-between border-t border-border/60 pt-2">
                    <span className="text-slate-400">Lifetime Secured Revenue:</span>
                    <span className="font-mono text-emerald-400 font-semibold">
                      {formatINR(selectedCase.customer.total_payment_amount)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Phase 2 — THINK: RECON Intelligence */}
            <IntelligencePanel caseId={selectedCase.id} caseNumber={selectedCase.case_number} />
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
