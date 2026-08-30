"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { JsonViewer } from "@/components/ui/JsonViewer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { Reveal } from "@/components/spatial/Reveal";
import { SectionBand } from "@/components/modules/SectionBand";
import { EventPulse } from "@/components/modules/EventPulse";
import { api } from "@/lib/api";
import { RevenueEvent, PaginatedResponse } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

function streamTime(iso?: string | null) {
  if (!iso) return "--:--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

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
      <SectionBand
        eyebrow="EVENT INGESTION PLANE"
        title="LIVE REVENUE EVENTS"
        subtitle="Raw and normalized event logs received from Razorpay webhooks and simulation engines."
      />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="motion-safe-only relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-info opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-status-info" />
          </span>
          <span className="label-mono">Live</span>
        </div>
        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Total Ingested: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      {!isLoading && data && data.items.length > 0 && (
        <EventPulse events={data.items} onSelect={setSelectedEvent} />
      )}

      {/* Filter bar + table stay visually tight to each other — one operational unit */}
      <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface/60 p-4 backdrop-blur-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-fg-faint" />
          <input
            type="text"
            placeholder="Search by event ID (e.g. evt_...)"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full h-11 bg-surface-subtle border border-border rounded-lg pl-10 pr-4 text-sm text-fg placeholder-fg-faint focus:outline-none focus:border-accent"
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
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
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
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
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
      <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
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
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline backdrop-blur-sm">
                  <tr>
                    <th className="py-4 px-4 w-24">Time</th>
                    <th className="py-4 px-4">Event</th>
                    <th className="py-4 px-4">Customer</th>
                    <th className="py-4 px-4">Amount</th>
                    <th className="py-4 px-4">Source</th>
                    <th className="py-4 px-4">Status</th>
                    <th className="py-4 px-4 text-right">Event ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {data.items.map((event) => (
                    <Reveal
                      key={event.id}
                      as="tr"
                      onClick={() => setSelectedEvent(event)}
                      className="cursor-pointer border-l-2 border-transparent transition-colors hover:border-status-info hover:bg-surface-elevated/40"
                    >
                      <td className="py-4 px-4 font-mono font-semibold tabular-nums text-status-info">
                        {streamTime(event.received_at)}
                      </td>
                      <td className="py-4 px-4">
                        <StatusBadge status={event.event_type} type="event" />
                      </td>
                      <td className="py-4 px-4 text-fg">
                        {event.normalized_data?.customer_name || event.normalized_data?.customer_email || "N/A"}
                      </td>
                      <td className="py-4 px-4 font-mono font-semibold text-fg tabular-nums">
                        {formatINR(event.normalized_data?.amount || "0")}
                      </td>
                      <td className="py-4 px-4 font-mono uppercase text-fg-muted text-[11px]">
                        {event.source}
                      </td>
                      <td className="py-4 px-4">
                        <StatusBadge status={event.processing_status} />
                      </td>
                      <td className="py-4 px-4 text-right font-mono text-fg-faint text-[11px]">
                        {event.razorpay_event_id}
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
