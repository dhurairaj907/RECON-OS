"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, ScrollText, ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { JsonViewer } from "@/components/ui/JsonViewer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { api } from "@/lib/api";
import { AuditLog, PaginatedResponse } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export default function AuditLogsPage() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState<string>("");
  const [actorFilter, setActorFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedAudit, setSelectedAudit] = useState<AuditLog | null>(null);

  const { data, error, mutate, isValidating } = useSWR<PaginatedResponse<AuditLog>>(
    [`/api/v1/audit-logs`, page, actionFilter, actorFilter, searchQuery],
    () =>
      api.getAuditLogs({
        page,
        limit: 15,
        action: actionFilter || undefined,
        actor: actorFilter || undefined,
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
            <ScrollText className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-mono tracking-wider text-fg-muted uppercase">
              System Transparency
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-fg font-mono mt-1">
            AUDIT TRAIL
          </h1>
          <p className="text-xs text-fg-muted mt-1">
            Immutable log of all system decisions, state transitions, duplicate rejections, and actions.
          </p>
        </div>

        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Logs: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-surface p-4 rounded-lg border border-border flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-fg-faint" />
          <input
            type="text"
            placeholder="Search within audit log descriptions..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full bg-surface-subtle border border-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
          />
        </div>

        <div className="flex items-center space-x-2 w-full md:w-auto">
          {/* Action Filter */}
          <select
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setPage(1);
            }}
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Actions</option>
            <option value="EVENT_PROCESSED">EVENT_PROCESSED</option>
            <option value="RECOVERY_CASE_CREATED">RECOVERY_CASE_CREATED</option>
            <option value="RECOVERY_CASE_RESOLVED">RECOVERY_CASE_RESOLVED</option>
            <option value="DUPLICATE_EVENT_IGNORED">DUPLICATE_EVENT_IGNORED</option>
          </select>

          {/* Actor Filter */}
          <select
            value={actorFilter}
            onChange={(e) => {
              setActorFilter(e.target.value);
              setPage(1);
            }}
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Actors</option>
            <option value="RAZORPAY">RAZORPAY</option>
            <option value="SIMULATOR">SIMULATOR</option>
            <option value="RECON_ENGINE">RECON_ENGINE</option>
          </select>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="bg-surface rounded-lg border border-border overflow-hidden">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow cols={4} />
            <SkeletonRow cols={4} />
            <SkeletonRow cols={4} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No audit records found"
            description="System operations and event processing actions will be permanently recorded here."
            actionText="Simulate an Event"
            actionHref="/simulator"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-elevated/50 text-fg-muted font-mono text-[11px] uppercase border-b border-border">
                  <tr>
                    <th className="py-3 px-4">Actor</th>
                    <th className="py-3 px-4">Action</th>
                    <th className="py-3 px-4">Operation Detail</th>
                    <th className="py-3 px-4 text-right">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.items.map((log) => (
                    <tr
                      key={log.id}
                      onClick={() => setSelectedAudit(log)}
                      className="hover:bg-surface-elevated/40 cursor-pointer transition-colors"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-fg-secondary">
                        <span className="px-2 py-0.5 rounded bg-surface-elevated text-status-info border border-border">
                          {log.actor}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono font-medium text-status-warning">
                        {log.action}
                      </td>
                      <td className="py-3 px-4 text-fg truncate max-w-md">
                        {log.detail}
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-fg-muted">
                        {formatDateTime(log.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-subtle text-xs font-mono text-fg-muted">
              <div>
                Page <span className="text-fg font-medium">{page}</span> of{" "}
                <span className="text-fg font-medium">{totalPages || 1}</span>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="p-1 rounded bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1 rounded bg-surface border border-border disabled:opacity-40 hover:bg-surface-elevated text-fg-secondary"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Audit Detail Drawer */}
      <DetailDrawer
        isOpen={!!selectedAudit}
        onClose={() => setSelectedAudit(null)}
        title={selectedAudit?.action || "Audit Record"}
        subtitle={`Recorded ${formatDateTime(selectedAudit?.created_at)}`}
      >
        {selectedAudit && (
          <div className="space-y-6 text-xs font-mono">
            <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2">
              <div className="flex justify-between">
                <span className="text-fg-muted">Actor:</span>
                <span className="text-fg font-bold">{selectedAudit.actor}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-muted">Action:</span>
                <span className="text-status-warning">{selectedAudit.action}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-muted">Log ID:</span>
                <span className="text-fg-muted">{selectedAudit.id}</span>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-1">
              <span className="text-fg-muted uppercase text-[10px]">Detail Description:</span>
              <p className="text-fg text-sm font-sans leading-relaxed">{selectedAudit.detail}</p>
            </div>

            {selectedAudit.metadata_json && (
              <div className="space-y-2">
                <h3 className="text-fg-secondary uppercase tracking-wider text-[11px]">Structured Metadata</h3>
                <JsonViewer data={selectedAudit.metadata_json} title="AUDIT METADATA" maxHeight="300px" />
              </div>
            )}
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
