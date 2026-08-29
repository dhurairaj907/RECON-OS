"use client";

import React, { useState, useEffect } from "react";
import useSWR from "swr";
import Link from "next/link";
import {
  ShieldAlert,
  CheckCircle2,
  TrendingDown,
  Activity,
  Layers,
  ArrowUpRight,
  ExternalLink,
  ChevronRight,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { StatCard } from "@/components/ui/StatCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { JsonViewer } from "@/components/ui/JsonViewer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCards } from "@/components/ui/SkeletonLoader";
import { RevenueChart } from "@/components/modules/RevenueChart";
import { api } from "@/lib/api";
import { DashboardMetrics, RecoveryCase, RevenueEvent } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

export default function CommandCenterPage() {
  const { data: metrics, error, mutate, isValidating } = useSWR<DashboardMetrics>(
    "/api/v1/dashboard/metrics",
    () => api.getDashboardMetrics(),
    { refreshInterval: 3000 } // Poll every 3 seconds for live operations
  );

  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<RevenueEvent | null>(null);

  const isLoading = !metrics && !error;

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating}>
      {/* Top Header & Context */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span className="text-xs font-mono tracking-wider text-slate-400 uppercase">
              Financial Control System
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white font-mono mt-1">
            REVENUE COMMAND CENTER
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time detection, observation, and lifecycle monitoring for Razorpay payment infrastructure.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/simulator"
            className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg bg-accent text-white text-xs font-mono font-medium hover:bg-accent-hover transition-colors shadow-sm"
          >
            <span>Open Event Simulator</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* KPI Cards Grid */}
      {isLoading ? (
        <SkeletonCards count={4} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Revenue at Risk"
            value={metrics?.revenue_at_risk || "0.00"}
            isCurrency={true}
            icon={TrendingDown}
            variant="danger"
            subtitle={`${metrics?.active_recovery_cases || 0} active cases open`}
          />
          <StatCard
            title="Revenue Secured"
            value={metrics?.revenue_secured || "0.00"}
            isCurrency={true}
            icon={CheckCircle2}
            variant="success"
            subtitle={`${metrics?.successful_payments || 0} captured payments`}
          />
          <StatCard
            title="Active Recovery Cases"
            value={metrics?.active_recovery_cases || 0}
            icon={ShieldAlert}
            variant="warning"
            subtitle="Phase 1: Deterministic cases"
          />
          <StatCard
            title="Events Processed"
            value={metrics?.events_processed || 0}
            icon={Activity}
            variant="info"
            subtitle="Idempotent pipeline active"
          />
        </div>
      )}

      {/* Phase 2 — THINK: Intelligence decision metrics (real data only) */}
      <div className="bg-surface rounded-lg border border-border p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-white tracking-wide font-mono">
              RECON INTELLIGENCE
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Deterministic diagnosis → prediction → strategy → policy · Phase 2 (THINK)
            </p>
          </div>
          <Link
            href="/intelligence"
            className="text-xs font-mono text-accent hover:text-accent-hover flex items-center gap-1 transition-colors"
          >
            View analyses <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>
        {!metrics?.intelligence ? (
          <p className="text-xs text-slate-500 font-mono py-3">
            No intelligence decisions yet. Open a recovery case and run{" "}
            <span className="text-slate-300">Analyze Case</span>.
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Cases Analyzed", value: metrics.intelligence.cases_analyzed, tone: "text-white" },
              { label: "High Recovery Probability", value: metrics.intelligence.high_recovery_probability, tone: "text-emerald-400" },
              { label: "Needs Approval", value: metrics.intelligence.needs_approval, tone: "text-amber-400" },
              { label: "Policy Rejected", value: metrics.intelligence.policy_rejected, tone: "text-rose-400" },
            ].map((m) => (
              <div key={m.label} className="rounded-lg border border-border bg-surface-subtle p-4">
                <div className={`text-2xl font-bold font-mono tabular-nums ${m.tone}`}>
                  {m.value}
                </div>
                <div className="text-[11px] font-mono text-slate-400 mt-1 uppercase tracking-wider">
                  {m.label}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main Grid: Revenue Dynamics + Live Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Revenue Chart + Active Cases Snapshot */}
        <div className="lg:col-span-2 space-y-6">
          {/* Revenue Chart Panel */}
          <div className="bg-surface p-6 rounded-lg border border-border">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-semibold text-white tracking-wide font-mono">
                  REVENUE DYNAMICS
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Comparison of failed revenue at risk vs captured revenue
                </p>
              </div>
            </div>
            <RevenueChart data={metrics?.daily_trends || []} />
          </div>

          {/* Active Recovery Cases Table */}
          <div className="bg-surface rounded-lg border border-border overflow-hidden">
            <div className="flex items-center justify-between p-5 border-b border-border bg-surface-subtle">
              <div>
                <h2 className="text-sm font-semibold text-white tracking-wide font-mono">
                  ACTIVE RECOVERY CASES
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  High-priority payment failures requiring tracking
                </p>
              </div>
              <Link
                href="/recovery"
                className="text-xs font-mono text-accent hover:text-accent-hover flex items-center gap-1 transition-colors"
              >
                View all cases <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {!metrics?.recent_cases || metrics.recent_cases.length === 0 ? (
              <EmptyState
                title="All clear — no active recovery cases"
                description="When a payment failure occurs, RECON OS will automatically create and prioritize a recovery case."
                actionText="Trigger Test Failure"
                actionHref="/simulator"
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-elevated/50 text-slate-400 font-mono text-[11px] uppercase border-b border-border">
                    <tr>
                      <th className="py-3 px-4">Case Number</th>
                      <th className="py-3 px-4">Customer</th>
                      <th className="py-3 px-4">Amount at Risk</th>
                      <th className="py-3 px-4">Priority</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Age</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {metrics.recent_cases.slice(0, 5).map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => setSelectedCase(c)}
                        className="hover:bg-surface-elevated/40 cursor-pointer transition-colors"
                      >
                        <td className="py-3 px-4 font-mono font-medium text-blue-400">
                          {c.case_number}
                        </td>
                        <td className="py-3 px-4 text-slate-200">
                          {c.customer?.name || c.customer?.email || "Unknown"}
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-white tabular-nums">
                          {formatINR(c.amount_at_risk)}
                        </td>
                        <td className="py-3 px-4">
                          <StatusBadge status={c.priority} type="priority" />
                        </td>
                        <td className="py-3 px-4">
                          <StatusBadge status={c.status} type="case" />
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-slate-400">
                          {formatRelativeTime(c.opened_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Col: Live RECON Activity Stream */}
        <div className="bg-surface rounded-lg border border-border flex flex-col h-full overflow-hidden">
          <div className="flex items-center justify-between p-5 border-b border-border bg-surface-subtle">
            <div className="flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              <h2 className="text-sm font-semibold text-white tracking-wide font-mono">
                LIVE ACTIVITY FEED
              </h2>
            </div>
            <Link
              href="/events"
              className="text-xs font-mono text-accent hover:text-accent-hover flex items-center gap-1 transition-colors"
            >
              Full Feed <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="p-4 flex-1 overflow-y-auto space-y-3 max-h-[640px]">
            {!metrics?.recent_events || metrics.recent_events.length === 0 ? (
              <EmptyState
                title="Waiting for revenue events..."
                description="Inbound Razorpay webhooks or simulated events will stream into this console live."
                actionText="Simulate First Event"
                actionHref="/simulator"
              />
            ) : (
              metrics.recent_events.map((evt) => (
                <div
                  key={evt.id}
                  onClick={() => setSelectedEvent(evt)}
                  className="p-3 rounded-lg border border-border/80 bg-surface-subtle/50 hover:bg-surface-elevated/70 cursor-pointer transition-all space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <StatusBadge status={evt.event_type} type="event" />
                    <span className="text-[11px] font-mono text-slate-400">
                      {formatRelativeTime(evt.received_at)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs pt-1">
                    <span className="font-mono text-slate-300 truncate max-w-[160px]">
                      {evt.normalized_data?.customer_name || evt.normalized_data?.customer_email || "Customer"}
                    </span>
                    <span className="font-mono font-semibold text-white tabular-nums">
                      {formatINR(evt.normalized_data?.amount || "0")}
                    </span>
                  </div>

                  <div className="text-[10px] font-mono text-slate-500 truncate">
                    ID: {evt.razorpay_event_id}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Recovery Case Detail Drawer */}
      <DetailDrawer
        isOpen={!!selectedCase}
        onClose={() => setSelectedCase(null)}
        title={`CASE ${selectedCase?.case_number}`}
        subtitle={`Opened ${formatDateTime(selectedCase?.opened_at)}`}
        badge={selectedCase ? <StatusBadge status={selectedCase.status} /> : null}
      >
        {selectedCase && (
          <div className="space-y-6 text-xs">
            {/* Financial Overview Card */}
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
                Failure Information (Deterministic Phase 1)
              </h3>
              <div className="p-3.5 rounded-lg bg-surface-subtle border border-border space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Failure Reason:</span>
                  <span className="text-white font-medium">{selectedCase.failure_reason || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Error Code:</span>
                  <span className="font-mono text-amber-400">{selectedCase.failure_code || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Priority Level:</span>
                  <StatusBadge status={selectedCase.priority} />
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Recovery Attempts:</span>
                  <span className="font-mono text-slate-300">{selectedCase.attempt_count} / {selectedCase.max_attempts}</span>
                </div>
              </div>
            </div>

            {/* Customer Information */}
            {selectedCase.customer && (
              <div className="space-y-3">
                <h3 className="text-xs font-mono font-semibold text-slate-300 uppercase tracking-wider">
                  Associated Customer
                </h3>
                <div className="p-3.5 rounded-lg bg-surface-subtle border border-border space-y-2">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Name:</span>
                    <span className="text-white font-medium">{selectedCase.customer.name || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Email:</span>
                    <span className="font-mono text-blue-400">{selectedCase.customer.email || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Lifetime Revenue:</span>
                    <span className="font-mono text-emerald-400 font-semibold">
                      {formatINR(selectedCase.customer.total_payment_amount)}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </DetailDrawer>

      {/* Event Detail Drawer */}
      <DetailDrawer
        isOpen={!!selectedEvent}
        onClose={() => setSelectedEvent(null)}
        title={selectedEvent?.event_type || "Event Details"}
        subtitle={`Received ${formatDateTime(selectedEvent?.received_at)}`}
        badge={selectedEvent ? <StatusBadge status={selectedEvent.processing_status} /> : null}
      >
        {selectedEvent && (
          <div className="space-y-6 text-xs">
            <div className="p-4 rounded-lg bg-surface-subtle border border-border space-y-2 font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Event ID:</span>
                <span className="text-white">{selectedEvent.razorpay_event_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Source:</span>
                <span className="text-blue-400 uppercase">{selectedEvent.source}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Status:</span>
                <StatusBadge status={selectedEvent.processing_status} />
              </div>
            </div>

            {/* Normalized Data */}
            <div className="space-y-2">
              <h3 className="font-mono text-slate-300 uppercase tracking-wider">Normalized Schema</h3>
              <JsonViewer data={selectedEvent.normalized_data} title="NORMALIZED EVENT DATA" maxHeight="200px" />
            </div>

            {/* Raw Webhook Payload */}
            <div className="space-y-2">
              <h3 className="font-mono text-slate-300 uppercase tracking-wider">Raw Razorpay Webhook Payload</h3>
              <JsonViewer data={selectedEvent.raw_payload} title="RAW PAYLOAD" maxHeight="300px" />
            </div>
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
