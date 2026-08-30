"use client";

import React from "react";
import useSWR from "swr";
import {
  TrendingDown,
  TrendingUp,
  Wallet,
  Percent,
  Bot,
  UserCheck,
  UserX,
  HelpCircle,
  Ban,
  Clock,
  RotateCw,
  Target,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { SectionBand } from "@/components/modules/SectionBand";
import { StatCard } from "@/components/ui/StatCard";
import { FeatureGrid } from "@/components/modules/FeatureGrid";
import { SkeletonCards } from "@/components/ui/SkeletonLoader";
import { api } from "@/lib/api";
import { AnalyticsMetrics } from "@/lib/types";
import { cn, formatINR } from "@/lib/utils";

function pct(v: number | null | undefined): string {
  return v == null ? "Not yet available" : `${Math.round(v * 100)}%`;
}

function pctValue(v: number | null | undefined): number {
  return v == null ? 0 : Math.round(v * 100);
}

/**
 * RECON OS revenue recovery analytics — every number here comes from
 * services/analytics_service.py, computed live from RecoveryCase/
 * RecoveryAction/CaseIntelligence rows. A metric with no honest basis in
 * current data (e.g. no recovered actions yet) renders as "Not yet
 * available", never as a fabricated zero.
 */
export default function AnalyticsPage() {
  const { data, error, mutate, isValidating } = useSWR<AnalyticsMetrics>(
    "/api/v1/analytics",
    () => api.getAnalytics(),
    { refreshInterval: 5000 }
  );
  const isLoading = !data && !error;

  return (
    <AppShell onRefresh={() => mutate()} isRefreshing={isValidating}>
      <SectionBand
        eyebrow="PHASE 4 · PROVE"
        title="REVENUE RECOVERY ANALYTICS"
        subtitle="What RECON OS actually recovered, how much of it was automatic, and where policy drew the line — computed live, never fabricated."
      />

      {isLoading ? (
        <SkeletonCards count={4} />
      ) : error || !data ? (
        <p className="text-sm text-status-danger font-mono">Could not load analytics.</p>
      ) : (
        <>
          {/* Hero KPI row */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Revenue at Risk"
              value={data.revenue_at_risk}
              isCurrency
              icon={TrendingDown}
              variant="danger"
              subtitle="Across all active cases"
            />
            <StatCard
              title="Potential Recoverable"
              value={data.potential_recoverable_revenue}
              isCurrency
              icon={Target}
              variant="warning"
              subtitle="Excludes policy-rejected dead ends"
            />
            <StatCard
              title="Revenue Recovered"
              value={data.revenue_recovered}
              isCurrency
              icon={Wallet}
              variant="success"
              subtitle="Real, Razorpay-verified only"
            />
            <StatCard
              title="Recovery Rate"
              value={`${Math.round(data.recovery_rate * 100)}%`}
              icon={Percent}
              variant="info"
              subtitle="Real recoveries ÷ executed actions"
            />
          </div>

          {/* Automation vs human intervention (left, dominant) + safety signals (right) */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div className="lg:col-span-3 rounded-2xl border border-hairline bg-surface-subtle/40 p-6 space-y-5">
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
                Automation vs. Human Intervention
              </h3>

              {data.automation_rate == null ? (
                <p className="text-xs text-fg-faint font-mono">Not yet available — no actions executed.</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-elevated">
                    <div
                      className="h-full bg-status-info"
                      style={{ width: `${pctValue(data.automation_rate)}%` }}
                      title="Automated"
                    />
                    <div
                      className="h-full bg-status-warning"
                      style={{ width: `${100 - pctValue(data.automation_rate)}%` }}
                      title="Human-decided"
                    />
                  </div>
                  <div className="flex items-center justify-between font-mono text-[11px] text-fg-faint">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-status-info" /> Automated {pct(data.automation_rate)}
                    </span>
                    <span className="flex items-center gap-1.5">
                      Human-decided {pct(1 - (data.automation_rate ?? 0))}
                      <span className="h-2 w-2 rounded-full bg-status-warning" />
                    </span>
                  </div>
                </div>
              )}

              <FeatureGrid
                items={[
                  { icon: Bot, label: "Actions Needing Approval", value: data.actions_needing_approval_total },
                  {
                    icon: UserCheck,
                    label: "Approved by Human",
                    value: `${data.actions_approved_by_human} (${pct(data.human_approval_rate)})`,
                    tone: "success",
                  },
                  {
                    icon: UserX,
                    label: "Rejected by Human",
                    value: `${data.actions_rejected_by_human} (${pct(data.human_rejection_rate)})`,
                    tone: "danger",
                  },
                  {
                    icon: Percent,
                    label: "Avg. Recovery Probability",
                    value: pct(data.average_recovery_probability),
                    tone: "info",
                  },
                ]}
              />
            </div>

            <div className="lg:col-span-2 rounded-2xl border border-hairline bg-surface-subtle/40 p-6 space-y-4">
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
                Safety Signals
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between rounded-xl border border-hairline bg-surface-subtle/50 p-3.5">
                  <span className="flex items-center gap-2 text-xs text-fg-muted">
                    <HelpCircle className="h-4 w-4 text-status-warning" /> UNKNOWN Cases
                  </span>
                  <span className={cn("font-mono font-semibold", data.unknown_cases > 0 ? "text-status-warning" : "text-fg")}>
                    {data.unknown_cases}
                  </span>
                </div>
                <div className="flex items-center justify-between rounded-xl border border-hairline bg-surface-subtle/50 p-3.5">
                  <span className="flex items-center gap-2 text-xs text-fg-muted">
                    <Ban className="h-4 w-4 text-status-danger" /> Policy Rejections
                  </span>
                  <span className="font-mono font-semibold text-fg">{data.policy_rejection_count}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl border border-hairline bg-surface-subtle/50 p-3.5">
                  <span className="flex items-center gap-2 text-xs text-fg-muted">
                    <TrendingDown className="h-4 w-4 text-status-danger" /> Recovery Failure Rate
                  </span>
                  <span className="font-mono font-semibold text-fg">{pct(data.recovery_failure_rate)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Strategy performance */}
          <div className="space-y-3">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-fg-secondary">
              Strategy Performance
            </h3>
            {data.strategy_performance.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-border/80 bg-surface/40 p-6 text-center text-xs text-fg-faint font-mono">
                Not yet available — no executed actions with a recorded strategy.
              </p>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
                <table className="w-full text-left text-sm">
                  <thead className="bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline">
                    <tr>
                      <th className="py-3.5 px-4">Strategy</th>
                      <th className="py-3.5 px-4">Executed</th>
                      <th className="py-3.5 px-4">Recovered</th>
                      <th className="py-3.5 px-4">Success Rate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {data.strategy_performance.map((s) => (
                      <tr key={s.strategy}>
                        <td className="py-3.5 px-4 font-mono font-medium text-status-info">{s.strategy}</td>
                        <td className="py-3.5 px-4 font-mono text-fg-secondary tabular-nums">{s.executed}</td>
                        <td className="py-3.5 px-4 font-mono text-status-success tabular-nums">{s.recovered}</td>
                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-elevated">
                              <div
                                className="h-full rounded-full bg-status-success"
                                style={{ width: `${Math.round(s.success_rate * 100)}%` }}
                              />
                            </div>
                            <span className="font-mono text-xs tabular-nums text-fg-muted">
                              {Math.round(s.success_rate * 100)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Operational footer metrics */}
          <FeatureGrid
            items={[
              {
                icon: Clock,
                label: "Avg. Recovery Time",
                value: data.average_recovery_time_hours != null ? `${data.average_recovery_time_hours}h` : "Not yet available",
              },
              { icon: RotateCw, label: "Avg. Recovery Attempts / Case", value: data.average_recovery_attempts },
              { icon: TrendingUp, label: "Total Recovery Attempts", value: data.total_recovery_attempts },
              { icon: Wallet, label: "Simulated Revenue (excluded)", value: formatINR(data.simulated_revenue_recovered), tone: "warning" },
            ]}
          />

          <p className="text-[11px] font-mono text-fg-faint">
            {data.cases_analyzed} cases analysed · {data.actions_total} recovery actions total · generated{" "}
            {new Date(data.generated_at).toLocaleString("en-IN")}
          </p>
        </>
      )}
    </AppShell>
  );
}
