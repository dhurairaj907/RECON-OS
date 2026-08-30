"use client";

import React, { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  ShieldAlert,
  CheckCircle2,
  TrendingDown,
  Activity,
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
import { CommandCenterHero } from "@/components/modules/CommandCenterHero";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { Reveal } from "@/components/spatial/Reveal";
import { deriveSystemPipeline } from "@/components/spatial/pipeline-model";
import type { GlowTone } from "@/components/spatial/AtmosphericGlow";
import { api } from "@/lib/api";
import { DashboardMetrics, RecoveryCase, RevenueEvent } from "@/lib/types";
import { formatINR, formatDateTime, formatRelativeTime } from "@/lib/utils";

const SpatialField = dynamic(
  () =>
    import("@/components/spatial/three/SpatialPipeline").then(
      (m) => m.SpatialField
    ),
  { ssr: false }
);

const RecoveryPipeline3D = dynamic(
  () =>
    import("@/components/spatial/RecoveryPipeline3D").then(
      (m) => m.RecoveryPipeline3D
    ),
  {
    ssr: false,
    loading: () => (
      <div className="h-40 animate-pulse rounded-xl border border-border bg-surface/60" />
    ),
  }
);

export default function CommandCenterPage() {
  const { data: metrics, error, mutate, isValidating } = useSWR<DashboardMetrics>(
    "/api/v1/dashboard/metrics",
    () => api.getDashboardMetrics(),
    { refreshInterval: 3000 } // Poll every 3 seconds for live operations
  );

  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<RevenueEvent | null>(null);

  const isLoading = !metrics && !error;

  const tone: GlowTone = React.useMemo(() => {
    if (!metrics) return "idle";
    const critical = (metrics.recent_cases || []).some(
      (c) =>
        c.priority === "CRITICAL" &&
        !["RESOLVED", "CLOSED"].includes((c.status || "").toUpperCase())
    );
    if (critical) return "danger";
    if ((metrics.active_recovery_cases ?? 0) > 0) return "warning";
    if (Number(metrics.actions?.revenue_recovered ?? 0) > 0) return "success";
    if ((metrics.events_processed ?? 0) > 0) return "info";
    return "idle";
  }, [metrics]);

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating} tone={tone} transparentHeader>
      <CommandCenterHero
        metrics={metrics}
        tone={tone}
        scene={
          !isLoading ? (
            <SpatialField stages={deriveSystemPipeline(metrics)} />
          ) : null
        }
      />

      {/* KPI Cards Grid */}
      {isLoading ? (
        <SkeletonCards count={4} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
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

      {/* Operational recovery flow — real aggregate counts only */}
      {!isLoading && (
        <Reveal>
          <RecoveryPipeline3D
            stages={deriveSystemPipeline(metrics)}
            title="OPERATIONAL RECOVERY FLOW"
            caption="Live pipeline state across every case — counts are real backend metrics, not projections."
          />
        </Reveal>
      )}

      {/* Phase 2 — THINK: Intelligence decision metrics (real data only) */}
      <Reveal className="block rounded-2xl border border-border bg-surface/60 p-6 depth-highlight backdrop-blur-sm">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="label-mono text-fg-secondary">RECON Intelligence</h2>
              <span
                className={`rounded-full border px-2 py-[3px] font-mono text-[10px] font-semibold uppercase tracking-[0.1em] ${
                  metrics?.intelligence?.ai_configured
                    ? "border-status-success-border bg-status-success-bg text-status-success"
                    : "border-hairline bg-surface-elevated text-fg-muted"
                }`}
              >
                {metrics?.intelligence?.ai_configured ? "AI-Enhanced" : "Deterministic"}
              </span>
            </div>
            <p className="mt-1.5 text-xs text-fg-muted">
              {metrics?.intelligence?.ai_configured
                ? "AI-assisted diagnosis → deterministic prediction → strategy → policy · Phase 2.5"
                : "Deterministic diagnosis → prediction → strategy → policy · Phase 2.5 (THINK)"}
            </p>
          </div>
          <Link
            href="/intelligence"
            className="flex shrink-0 items-center gap-1 font-mono text-xs text-accent transition-colors hover:text-accent-hover"
          >
            View analyses <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        {!metrics?.intelligence ? (
          <p className="py-3 font-mono text-xs text-fg-faint">
            No intelligence decisions yet. Open a recovery case and run{" "}
            <span className="text-fg-secondary">Analyze Case</span>.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            {[
              { label: "Cases Analyzed", value: metrics.intelligence.cases_analyzed, tone: "text-fg" },
              { label: "High Recovery Probability", value: metrics.intelligence.high_recovery_probability, tone: "text-status-success" },
              { label: "Needs Approval", value: metrics.intelligence.needs_approval, tone: "text-status-warning" },
              { label: "Policy Rejected", value: metrics.intelligence.policy_rejected, tone: "text-status-danger" },
            ].map((m) => (
              <div key={m.label}>
                <div className="label-mono">{m.label}</div>
                <AnimatedNumber
                  as="div"
                  value={m.value}
                  className={`mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums ${m.tone}`}
                />
              </div>
            ))}
          </div>
        )}

        {/* Phase 3 — ACT: recovery action metrics (real data only) */}
        <div className="mt-6 border-t border-hairline pt-5">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <h3 className="label-mono text-fg-secondary">Recovery Actions</h3>
            <span className="rounded-full border border-status-warning-border/50 bg-status-warning-bg px-2 py-[3px] font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-status-warning">
              Razorpay {metrics?.actions?.test_mode === false ? "Live" : "Test Mode"}
            </span>
            {metrics?.actions?.simulator_enabled && (
              <span className="rounded-full border border-status-warning-border/50 bg-status-warning-bg px-2 py-[3px] font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-status-warning">
                Simulator On
              </span>
            )}
          </div>
          {!metrics?.actions ? (
            <p className="py-2 font-mono text-xs text-fg-faint">
              No recovery actions yet. Open a policy-approved case and{" "}
              <span className="text-fg-secondary">Create Payment Link</span>.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
                {[
                  { label: "Actions Executed", value: metrics.actions.actions_executed, tone: "text-fg" },
                  { label: "Pending Recoveries", value: metrics.actions.pending_recoveries, tone: "text-status-info" },
                  { label: "Revenue Recovered", value: formatINR(metrics.actions.revenue_recovered), tone: "text-status-success" },
                  { label: "Recovery Rate", value: `${Math.round((metrics.actions.recovery_rate || 0) * 100)}%`, tone: "text-fg" },
                ].map((m) => (
                  <div key={m.label}>
                    <div className="label-mono">{m.label}</div>
                    <div className={`mt-1.5 text-[1.7rem] font-bold leading-none tabular-nums ${m.tone}`}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>
              {Number(metrics.actions.simulated_revenue_recovered) > 0 && (
                <p className="mt-3 font-mono text-[10px] text-status-warning/80">
                  + {formatINR(metrics.actions.simulated_revenue_recovered)} simulated (excluded from Revenue Recovered)
                  {metrics.actions.partial_recoveries > 0 && ` · ${metrics.actions.partial_recoveries} partial`}
                </p>
              )}
            </>
          )}
        </div>
      </Reveal>

      {/* Main Grid: Revenue Dynamics + Live Activity Feed */}
      <Reveal as="div" className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Revenue Chart + Active Cases Snapshot */}
        <div className="lg:col-span-2 min-w-0 space-y-6">
          {/* Revenue Chart Panel */}
          <div className="rounded-2xl border border-border bg-surface/60 p-6 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="label-mono text-fg-secondary">
                  REVENUE DYNAMICS
                </h2>
                <p className="text-xs text-fg-muted mt-0.5">
                  Comparison of failed revenue at risk vs captured revenue
                </p>
              </div>
            </div>
            <RevenueChart data={metrics?.daily_trends || []} />
          </div>

          {/* Active Recovery Cases Table */}
          <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
            <div className="flex items-center justify-between border-b border-hairline p-5">
              <div>
                <h2 className="label-mono text-fg-secondary">
                  ACTIVE RECOVERY CASES
                </h2>
                <p className="text-xs text-fg-muted mt-0.5">
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
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-hairline font-mono text-xs uppercase tracking-[0.1em] text-fg-faint">
                    <tr>
                      <th className="px-4 py-3.5 font-medium">Case Number</th>
                      <th className="py-3.5 px-4">Customer</th>
                      <th className="py-3.5 px-4">Amount at Risk</th>
                      <th className="py-3.5 px-4">Priority</th>
                      <th className="py-3.5 px-4">Status</th>
                      <th className="py-3.5 px-4 text-right">Age</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {metrics.recent_cases.slice(0, 5).map((c) => (
                      <tr
                        key={c.id}
                        onClick={() => setSelectedCase(c)}
                        className="cursor-pointer transition-colors hover:bg-surface-hover/50"
                      >
                        <td className="py-4 px-4 font-mono font-medium text-status-info">
                          {c.case_number}
                        </td>
                        <td className="py-4 px-4 text-fg">
                          {c.customer?.name || c.customer?.email || "Unknown"}
                        </td>
                        <td className="py-4 px-4 font-mono font-semibold text-fg tabular-nums">
                          {formatINR(c.amount_at_risk)}
                        </td>
                        <td className="py-4 px-4">
                          <StatusBadge status={c.priority} type="priority" />
                        </td>
                        <td className="py-4 px-4">
                          <StatusBadge status={c.status} type="case" />
                        </td>
                        <td className="py-4 px-4 text-right font-mono text-fg-muted">
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
        <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
          <div className="flex items-center justify-between border-b border-hairline p-5">
            <div className="flex items-center space-x-2">
              <span className="motion-safe-only h-2 w-2 animate-ping rounded-full bg-status-success"></span>
              <h2 className="label-mono text-fg-secondary">LIVE ACTIVITY FEED</h2>
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
                  className="cursor-pointer space-y-1.5 rounded-xl border border-hairline bg-surface-subtle/40 p-3 transition-colors hover:bg-surface-hover/60"
                >
                  <div className="flex items-center justify-between">
                    <StatusBadge status={evt.event_type} type="event" />
                    <span className="text-[11px] font-mono text-fg-muted">
                      {formatRelativeTime(evt.received_at)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs pt-1">
                    <span className="font-mono text-fg-secondary truncate max-w-[160px]">
                      {evt.normalized_data?.customer_name || evt.normalized_data?.customer_email || "Customer"}
                    </span>
                    <span className="font-mono font-semibold text-fg tabular-nums">
                      {formatINR(evt.normalized_data?.amount || "0")}
                    </span>
                  </div>

                  <div className="text-[10px] font-mono text-fg-faint truncate">
                    ID: {evt.razorpay_event_id}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </Reveal>

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
            <div className="grid grid-cols-2 gap-4 p-4 rounded-xl bg-surface-subtle/50 border border-hairline">
              <div>
                <span className="text-fg-muted font-mono">Amount at Risk</span>
                <div className="text-xl font-bold font-mono text-status-danger mt-1">
                  {formatINR(selectedCase.amount_at_risk)}
                </div>
              </div>
              <div>
                <span className="text-fg-muted font-mono">Amount Recovered</span>
                <div className="text-xl font-bold font-mono text-status-success mt-1">
                  {formatINR(selectedCase.amount_recovered)}
                </div>
              </div>
            </div>

            {/* Diagnostic Details */}
            <div className="space-y-3">
              <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                Failure Information (Deterministic Phase 1)
              </h3>
              <div className="p-3.5 rounded-xl bg-surface-subtle/50 border border-hairline space-y-2">
                <div className="flex justify-between">
                  <span className="text-fg-muted">Failure Reason:</span>
                  <span className="text-fg font-medium">{selectedCase.failure_reason || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Error Code:</span>
                  <span className="font-mono text-status-warning">{selectedCase.failure_code || "N/A"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Priority Level:</span>
                  <StatusBadge status={selectedCase.priority} />
                </div>
                <div className="flex justify-between">
                  <span className="text-fg-muted">Recovery Attempts:</span>
                  <span className="font-mono text-fg-secondary">{selectedCase.attempt_count} / {selectedCase.max_attempts}</span>
                </div>
              </div>
            </div>

            {/* Customer Information */}
            {selectedCase.customer && (
              <div className="space-y-3">
                <h3 className="text-xs font-mono font-semibold text-fg-secondary uppercase tracking-wider">
                  Associated Customer
                </h3>
                <div className="p-3.5 rounded-xl bg-surface-subtle/50 border border-hairline space-y-2">
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Name:</span>
                    <span className="text-fg font-medium">{selectedCase.customer.name || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Email:</span>
                    <span className="font-mono text-status-info">{selectedCase.customer.email || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Total Lifetime Revenue:</span>
                    <span className="font-mono text-status-success font-semibold">
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
            <div className="p-4 rounded-xl bg-surface-subtle/50 border border-hairline space-y-2 font-mono">
              <div className="flex justify-between">
                <span className="text-fg-muted">Event ID:</span>
                <span className="text-fg">{selectedEvent.razorpay_event_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-muted">Source:</span>
                <span className="text-status-info uppercase">{selectedEvent.source}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-fg-muted">Status:</span>
                <StatusBadge status={selectedEvent.processing_status} />
              </div>
            </div>

            {/* Normalized Data */}
            <div className="space-y-2">
              <h3 className="font-mono text-fg-secondary uppercase tracking-wider">Normalized Schema</h3>
              <JsonViewer data={selectedEvent.normalized_data} title="NORMALIZED EVENT DATA" maxHeight="200px" />
            </div>

            {/* Raw Webhook Payload */}
            <div className="space-y-2">
              <h3 className="font-mono text-fg-secondary uppercase tracking-wider">Raw Razorpay Webhook Payload</h3>
              <JsonViewer data={selectedEvent.raw_payload} title="RAW PAYLOAD" maxHeight="300px" />
            </div>
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
