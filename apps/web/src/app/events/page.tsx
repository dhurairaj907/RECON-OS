"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, Filter, RefreshCw, Zap, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { JsonViewer } from "@/components/ui/JsonViewer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { api } from "@/lib/api";
import { RevenueEvent, PaginatedResponse } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

export default function LiveEventsPage() {
  const [page, setPage] = useState(1);
  const [eventTypeFilter, setEventTypeFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedEvent, setSelectedEvent] = useState<RevenueEvent | null>(null);

  const { data, error, mutate, isValidating } = useSWR<PaginatedResponse<RevenueEvent>>(
    [`/api/v1/events`, page, eventTypeFilter, statusFilter, searchQuery],
    () =>
      api.getEvents({
        page,
        limit: 15,
        event_type: eventTypeFilter || undefined,
        status: statusFilter || undefined,
        search: searchQuery || undefined,
      }),
    { refreshInterval: 3000 }
  );

  const totalPages = data ? Math.ceil(data.total / 15) : 1;
  const isLoading = !data && !error;

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating}>
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <Zap className="w-4 h-4 text-status-info" />
            <span className="text-xs font-mono tracking-wider text-fg-muted uppercase">
              Event Ingestion Plane
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-fg font-mono mt-1">
            LIVE REVENUE EVENTS
          </h1>
          <p className="text-xs text-fg-muted mt-1">
            Raw and normalized event logs received from Razorpay webhooks and simulation engines.
          </p>
        </div>

        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Ingested: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-surface p-4 rounded-lg border border-border flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-fg-faint" />
          <input
            type="text"
            placeholder="Search by event ID (e.g. evt_...)"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full bg-surface-subtle border border-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
          />
        </div>

        <div className="flex items-center space-x-2 w-full md:w-auto">
          {/* Event Type Filter */}
          <select
            value={eventTypeFilter}
            onChange={(e) => {
              setEventTypeFilter(e.target.value);
              setPage(1);
            }}
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Event Types</option>
            <option value="payment.failed">payment.failed</option>
            <option value="payment.captured">payment.captured</option>
            <option value="payment.authorized">payment.authorized</option>
          </select>

          {/* Processing Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Statuses</option>
            <option value="processed">Processed</option>
            <option value="processing">Processing</option>
            <option value="received">Received</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {/* Events Data Table */}
      <div className="bg-surface rounded-lg border border-border overflow-hidden">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow cols={6} />
            <SkeletonRow cols={6} />
            <SkeletonRow cols={6} />
            <SkeletonRow cols={6} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No events matching filters"
            description="Trigger an event from the simulator or send a Razorpay test webhook to see records here."
            actionText="Simulate Payment Event"
            actionHref="/simulator"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-elevated/50 text-fg-muted font-mono text-[11px] uppercase border-b border-border">
                  <tr>
                    <th className="py-3 px-4">Event ID</th>
                    <th className="py-3 px-4">Event Type</th>
                    <th className="py-3 px-4">Customer</th>
                    <th className="py-3 px-4">Amount</th>
                    <th className="py-3 px-4">Source</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.items.map((event) => (
                    <tr
                      key={event.id}
                      onClick={() => setSelectedEvent(event)}
                      className="hover:bg-surface-elevated/40 cursor-pointer transition-colors"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-status-info">
                        {event.razorpay_event_id}
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge status={event.event_type} type="event" />
                      </td>
                      <td className="py-3 px-4 text-fg">
                        {event.normalized_data?.customer_name || event.normalized_data?.customer_email || "N/A"}
                      </td>
                      <td className="py-3 px-4 font-mono font-semibold text-fg tabular-nums">
                        {formatINR(event.normalized_data?.amount || "0")}
                      </td>
                      <td className="py-3 px-4 font-mono uppercase text-fg-muted text-[11px]">
                        {event.source}
                      </td>
                      <td className="py-3 px-4">
                        <StatusBadge status={event.processing_status} />
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-fg-muted">
                        {formatDateTime(event.received_at)}
                      </td>
                    </tr>
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

      {/* Detail Drawer */}
      <DetailDrawer
        isOpen={!!selectedEvent}
        onClose={() => setSelectedEvent(null)}
        title={selectedEvent?.event_type || "Event Inspector"}
        subtitle={`ID: ${selectedEvent?.razorpay_event_id}`}
        badge={selectedEvent ? <StatusBadge status={selectedEvent.processing_status} /> : null}
      >
        {selectedEvent && (
          <div className="space-y-6 text-xs">
            {/* Metadata Summary */}
            <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2 font-mono">
              <div className="flex justify-between">
                <span className="text-fg-muted">Received Timestamp:</span>
                <span className="text-fg">{formatDateTime(selectedEvent.received_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-muted">Processed Timestamp:</span>
                <span className="text-fg">{formatDateTime(selectedEvent.processed_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-muted">Pipeline Ingestion Source:</span>
                <span className="text-status-info uppercase">{selectedEvent.source}</span>
              </div>
            </div>

            {/* Normalized Data */}
            <div className="space-y-2">
              <h3 className="font-mono text-fg-secondary uppercase tracking-wider">Normalized Schema</h3>
              <JsonViewer data={selectedEvent.normalized_data} title="NORMALIZED SCHEMA" maxHeight="200px" />
            </div>

            {/* Raw Webhook Payload */}
            <div className="space-y-2">
              <h3 className="font-mono text-fg-secondary uppercase tracking-wider">Raw Payload (Preserved for Audit)</h3>
              <JsonViewer data={selectedEvent.raw_payload} title="RAW PAYLOAD" maxHeight="320px" />
            </div>
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
