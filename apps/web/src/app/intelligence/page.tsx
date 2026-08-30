"use client";

import React, { useState } from "react";
import useSWR from "swr";
import dynamic from "next/dynamic";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { IntelligencePanel } from "@/components/modules/IntelligencePanel";
import { CaseHeader } from "@/components/modules/CaseHeader";
import { SectionBand } from "@/components/modules/SectionBand";
import { NumberedSteps, type NumberedStep } from "@/components/modules/NumberedSteps";
import { deriveSystemPipeline } from "@/components/spatial/pipeline-model";
import { Reveal } from "@/components/spatial/Reveal";
import { api } from "@/lib/api";
import { DashboardMetrics, IntelligenceListItem, PaginatedResponse } from "@/lib/types";
import { formatINR, formatRelativeTime, cn } from "@/lib/utils";

const SpatialPipeline = dynamic(
  () =>
    import("@/components/spatial/three/SpatialPipeline").then((m) => m.SpatialPipeline),
  {
    ssr: false,
    loading: () => (
      <div className="h-40 rounded-2xl border border-border bg-surface/60 animate-pulse" />
    ),
  }
);

const verdictTone: Record<string, string> = {
  APPROVED: "text-status-success",
  NEEDS_APPROVAL: "text-status-warning",
  REJECTED: "text-status-danger",
};
const bandTone: Record<string, string> = {
  HIGH: "text-status-success",
  MEDIUM: "text-status-warning",
  LOW: "text-status-danger",
};

export default function IntelligencePage() {
  const [page, setPage] = useState(1);
  const [verdict, setVerdict] = useState("");
  const [band, setBand] = useState("");
  const [selected, setSelected] = useState<IntelligenceListItem | null>(null);

  const { data, error, isValidating } = useSWR<PaginatedResponse<IntelligenceListItem>>(
    [`/api/v1/intelligence`, page, verdict, band],
    () => api.getIntelligenceList({ page, limit: 15, verdict: verdict || undefined, band: band || undefined }),
    { refreshInterval: 4000 }
  );

  const { data: metrics } = useSWR<DashboardMetrics>(
    "/api/v1/dashboard/metrics",
    () => api.getDashboardMetrics(),
    { refreshInterval: 4000 }
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / 15)) : 1;
  const isLoading = !data && !error;

  const intel = metrics?.intelligence;
  const act = metrics?.actions;

  const observeToActSteps: NumberedStep[] = [
    {
      number: "01",
      label: "OBSERVE",
      value: intel?.cases_analyzed ?? "—",
      description: "Recovery cases observed for analysis.",
      tone: intel ? "default" : "muted",
    },
    {
      number: "02",
      label: "DIAGNOSE",
      value: intel?.ai_enhanced ?? "—",
      description: intel ? `${intel.deterministic} deterministic fallback` : undefined,
      tone: intel ? "success" : "muted",
    },
    {
      number: "03",
      label: "SCORE",
      value: intel?.high_recovery_probability ?? "—",
      description: "Cases scored in the HIGH recovery band.",
      tone: intel ? "info" : "muted",
    },
    {
      number: "04",
      label: "RECOMMEND",
      value: intel?.policy_approved ?? "—",
      description: intel
        ? `${intel.needs_approval} awaiting human · ${intel.policy_rejected} rejected`
        : undefined,
      tone: intel ? "default" : "muted",
    },
    {
      number: "05",
      label: "ACT",
      value: act?.actions_executed ?? "—",
      description: act ? `${act.payment_links_created} payment links created` : undefined,
      tone: act ? "success" : "muted",
    },
  ];

  const pageTone = selected
    ? "info"
    : (intel?.needs_approval ?? 0) > 0
    ? "warning"
    : (intel?.policy_rejected ?? 0) > 0
    ? "danger"
    : (intel?.cases_analyzed ?? 0) > 0
    ? "info"
    : "idle";

  return (
    <AppShell tone={pageTone}>
      <SectionBand
        eyebrow="PHASE 2 · THINK"
        title="RECON INTELLIGENCE"
        subtitle="Deterministic diagnosis, recovery prediction, strategy and policy evaluation for each recovery case."
      />

      <div className="flex items-center justify-end">
        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Analyzed Cases: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      <div className="space-y-2">
        <h2 className="label-mono text-fg-secondary">OBSERVE → DIAGNOSE → SCORE → RECOMMEND → ACT</h2>
        <NumberedSteps steps={observeToActSteps} />
      </div>

      {metrics && (
        <Reveal>
          <SpatialPipeline
            stages={deriveSystemPipeline(metrics)}
            title="INTELLIGENCE FLOW"
            caption="The living pipeline behind the numbers above — real-time state across every analysed case. The Policy Engine remains authoritative."
          />
        </Reveal>
      )}

      {/* Filter bar + table stay visually tight to each other — one operational unit */}
      <div className="space-y-3">
      <div className="rounded-2xl border border-border bg-surface/60 p-4 backdrop-blur-sm flex flex-col md:flex-row items-center gap-3">
        <div className="flex items-center gap-2 w-full md:w-auto">
          <select
            value={verdict}
            onChange={(e) => { setVerdict(e.target.value); setPage(1); }}
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Verdicts</option>
            <option value="APPROVED">APPROVED</option>
            <option value="NEEDS_APPROVAL">NEEDS_APPROVAL</option>
            <option value="REJECTED">REJECTED</option>
          </select>
          <select
            value={band}
            onChange={(e) => { setBand(e.target.value); setPage(1); }}
            className="h-11 bg-surface-subtle border border-border rounded-lg px-3.5 text-sm text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Bands</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
          </select>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">
        {isLoading ? (
          <div className="p-4 space-y-2">
            <SkeletonRow cols={10} />
            <SkeletonRow cols={10} />
            <SkeletonRow cols={10} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No intelligence decisions yet"
            description="Open a recovery case and run Analyze Case, or enable automatic analysis (INTELLIGENCE_ENABLED)."
            actionText="Go to Recovery Cases"
            actionHref="/recovery"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-surface-elevated/80 font-mono text-xs uppercase tracking-[0.08em] text-fg-faint border-b border-hairline backdrop-blur-sm">
                  <tr>
                    <th className="py-4 px-4">Case #</th>
                    <th className="py-4 px-4">Customer</th>
                    <th className="py-4 px-4">Amount</th>
                    <th className="py-4 px-4">Source</th>
                    <th className="py-4 px-4">Diagnosis</th>
                    <th className="py-4 px-4">Recovery P</th>
                    <th className="py-4 px-4">Strategy</th>
                    <th className="py-4 px-4">Policy</th>
                    <th className="py-4 px-4">Risk</th>
                    <th className="py-4 px-4 text-right">Analyzed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {data.items.map((it) => (
                    <Reveal
                      key={it.case_id}
                      as="tr"
                      onClick={() => setSelected(it)}
                      className="cursor-pointer border-l-2 border-transparent transition-colors hover:border-accent hover:bg-surface-elevated/40"
                    >
                      <td className="py-4 px-4 font-mono font-medium text-status-info">{it.case_number}</td>
                      <td className="py-4 px-4 text-fg">{it.customer_name || "Unknown"}</td>
                      <td className="py-4 px-4 font-mono font-semibold text-fg tabular-nums">
                        {formatINR(it.amount_at_risk)}
                      </td>
                      <td className="py-4 px-4 font-mono text-[11px]">
                        <span
                          className={
                            it.diagnosis_source === "AI-ENHANCED"
                              ? "text-status-success"
                              : it.diagnosis_source === "DETERMINISTIC FALLBACK"
                              ? "text-status-warning"
                              : "text-fg-faint"
                          }
                        >
                          {it.diagnosis_source || it.provider}
                        </span>
                      </td>
                      <td className="py-4 px-4 font-mono text-fg-secondary">{it.failure_category || "—"}</td>
                      <td className="py-4 px-4 font-mono">
                        <span className={cn("font-semibold", bandTone[it.prediction_band || ""])}>
                          {it.recovery_probability != null ? `${Math.round(it.recovery_probability * 100)}%` : "—"}
                        </span>
                        <span className="text-fg-faint"> {it.prediction_band}</span>
                      </td>
                      <td className="py-4 px-4 font-mono text-status-info">{it.recommended_action || "—"}</td>
                      <td className="py-4 px-4 font-mono">
                        <span className={cn("font-semibold", verdictTone[it.policy_verdict || ""])}>
                          {it.policy_verdict || "—"}
                        </span>
                      </td>
                      <td className="py-4 px-4 font-mono text-fg-muted">{it.risk_level || "—"}</td>
                      <td className="py-4 px-4 text-right font-mono text-fg-muted">
                        {it.analyzed_at ? formatRelativeTime(it.analyzed_at) : "—"}
                      </td>
                    </Reveal>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-surface-subtle text-xs font-mono text-fg-muted">
              <div>
                Page <span className="text-fg font-medium">{page}</span> of{" "}
                <span className="text-fg font-medium">{totalPages}</span>
                {isValidating && <span className="ml-2 text-fg-faint">· syncing</span>}
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

      <DetailDrawer
        isOpen={!!selected}
        onClose={() => setSelected(null)}
        title={`RECOVERY CASE ${selected?.case_number || ""}`}
        subtitle={selected?.customer_name || undefined}
      >
        {selected && (
          <div className="space-y-6">
            <CaseHeader
              caseNumber={selected.case_number}
              amountAtRisk={selected.amount_at_risk}
              failureReason={selected.failure_category}
              tone={
                selected.policy_verdict === "REJECTED"
                  ? "danger"
                  : selected.policy_verdict === "NEEDS_APPROVAL"
                  ? "warning"
                  : selected.policy_verdict === "APPROVED"
                  ? "success"
                  : "info"
              }
            />
            <IntelligencePanel caseId={selected.case_id} caseNumber={selected.case_number} />
          </div>
        )}
      </DetailDrawer>
    </AppShell>
  );
}
