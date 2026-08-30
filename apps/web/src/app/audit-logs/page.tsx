"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { JsonViewer } from "@/components/ui/JsonViewer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { Reveal } from "@/components/spatial/Reveal";
import { SectionBand } from "@/components/modules/SectionBand";
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
      <SectionBand
        eyebrow="SYSTEM TRANSPARENCY"
        title="AUDIT TRAIL"
        subtitle="Immutable log of all system decisions, state transitions, duplicate rejections, and actions."
      />

      <div className="flex items-center justify-end">
        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Logs: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Filter bar + table stay visually tight to each other — one operational unit */}
      <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface/60 p-4 backdrop-blur-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-faint" />
          <input
            type="text"
            placeholder="Search within audit log descriptions..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full h-11 bg-surface-subtle border border-border rounded-lg pl-10 pr-4 text-sm text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
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
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
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
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Actors</option>
            <option value="RAZORPAY">RAZORPAY</option>
            <option value="SIMULATOR">SIMULATOR</option>
            <option value="RECON_ENGINE">RECON_ENGINE</option>
          </select>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
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
              <table className="w-full text-left text-sm font-mono">
                <thead className="sticky top-0 z-10 bg-surface-elevated/80 text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline backdrop-blur-sm">
                  <tr>
                    <th className="py-3.5 px-4">Timestamp</th>
                    <th className="py-3.5 px-4">Actor</th>
                    <th className="py-3.5 px-4">Action</th>
                    <th className="py-3.5 px-4">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {data.items.map((log) => (
                    <Reveal
                      key={log.id}
                      as="tr"
                      onClick={() => setSelectedAudit(log)}
                      className="cursor-pointer border-l-2 border-transparent transition-colors hover:border-accent hover:bg-surface-elevated/40"
                    >
                      <td className="py-3.5 px-4 text-fg-muted whitespace-nowrap tabular-nums">
                        {formatDateTime(log.created_at)}
                      </td>
                      <td className="py-3.5 px-4 font-medium">
                        <span
                          className={
                            "px-1.5 py-0.5 rounded border text-[11px] " +
                            (log.actor === "SIMULATOR"
                              ? "border-dashed border-status-warning-border bg-status-warning-bg text-status-warning"
                              : "border-border bg-surface-elevated text-status-info")
                          }
                        >
                          {log.actor}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-fg tracking-tight">
                        {log.action}
                      </td>
                      <td className="py-3.5 px-4 text-fg-secondary truncate max-w-md font-sans">
                        {log.detail}
                      </td>
                    </Reveal>
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
