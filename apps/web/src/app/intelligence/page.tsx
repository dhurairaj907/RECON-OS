"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { BrainCircuit, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DetailDrawer } from "@/components/layout/DetailDrawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { IntelligencePanel } from "@/components/modules/IntelligencePanel";
import { api } from "@/lib/api";
import { IntelligenceListItem, PaginatedResponse } from "@/lib/types";
import { formatINR, formatRelativeTime, cn } from "@/lib/utils";

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

  const totalPages = data ? Math.max(1, Math.ceil(data.total / 15)) : 1;
  const isLoading = !data && !error;

  return (
    <AppShell>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center space-x-2">
            <BrainCircuit className="w-4 h-4 text-accent" />
            <span className="text-xs font-mono tracking-wider text-fg-muted uppercase">
              Phase 2 • THINK
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-fg font-mono mt-1">
            RECON INTELLIGENCE
          </h1>
          <p className="text-xs text-fg-muted mt-1">
            Deterministic diagnosis, recovery prediction, strategy and policy evaluation for each recovery case.
          </p>
        </div>
        <div className="text-xs font-mono text-fg-muted bg-surface px-3 py-1.5 rounded-lg border border-border">
          Analyzed Cases: <span className="text-fg font-bold">{data?.total || 0}</span>
        </div>
      </div>

      <div className="bg-surface p-4 rounded-lg border border-border flex flex-col md:flex-row items-center gap-3">
        <div className="flex items-center gap-2 w-full md:w-auto">
          <select
            value={verdict}
            onChange={(e) => { setVerdict(e.target.value); setPage(1); }}
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Verdicts</option>
            <option value="APPROVED">APPROVED</option>
            <option value="NEEDS_APPROVAL">NEEDS_APPROVAL</option>
            <option value="REJECTED">REJECTED</option>
          </select>
          <select
            value={band}
            onChange={(e) => { setBand(e.target.value); setPage(1); }}
            className="bg-surface-subtle border border-border rounded-lg px-3 py-1.5 text-xs text-fg-secondary focus:outline-none focus:border-accent font-mono"
          >
            <option value="">All Bands</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
          </select>
        </div>
      </div>

      <div className="bg-surface rounded-lg border border-border overflow-hidden">
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
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-elevated/50 text-fg-muted font-mono text-[11px] uppercase border-b border-border">
                  <tr>
                    <th className="py-3 px-4">Case #</th>
                    <th className="py-3 px-4">Customer</th>
                    <th className="py-3 px-4">Amount</th>
                    <th className="py-3 px-4">Source</th>
                    <th className="py-3 px-4">Diagnosis</th>
                    <th className="py-3 px-4">Recovery P</th>
                    <th className="py-3 px-4">Strategy</th>
                    <th className="py-3 px-4">Policy</th>
                    <th className="py-3 px-4">Risk</th>
                    <th className="py-3 px-4 text-right">Analyzed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {data.items.map((it) => (
                    <tr
                      key={it.case_id}
                      onClick={() => setSelected(it)}
                      className="hover:bg-surface-elevated/40 cursor-pointer transition-colors"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-status-info">{it.case_number}</td>
                      <td className="py-3 px-4 text-fg">{it.customer_name || "Unknown"}</td>
                      <td className="py-3 px-4 font-mono font-semibold text-fg tabular-nums">
                        {formatINR(it.amount_at_risk)}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px]">
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
                      <td className="py-3 px-4 font-mono text-fg-secondary">{it.failure_category || "—"}</td>
                      <td className="py-3 px-4 font-mono">
                        <span className={cn("font-semibold", bandTone[it.prediction_band || ""])}>
                          {it.recovery_probability != null ? `${Math.round(it.recovery_probability * 100)}%` : "—"}
                        </span>
                        <span className="text-fg-faint"> {it.prediction_band}</span>
                      </td>
                      <td className="py-3 px-4 font-mono text-status-info">{it.recommended_action || "—"}</td>
                      <td className="py-3 px-4 font-mono">
                        <span className={cn("font-semibold", verdictTone[it.policy_verdict || ""])}>
                          {it.policy_verdict || "—"}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-fg-muted">{it.risk_level || "—"}</td>
                      <td className="py-3 px-4 text-right font-mono text-fg-muted">
                        {it.analyzed_at ? formatRelativeTime(it.analyzed_at) : "—"}
                      </td>
                    </tr>
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

      <DetailDrawer
        isOpen={!!selected}
        onClose={() => setSelected(null)}
        title={`RECOVERY CASE ${selected?.case_number || ""}`}
        subtitle={selected?.customer_name || undefined}
      >
        {selected && (
          <IntelligencePanel caseId={selected.case_id} caseNumber={selected.case_number} />
        )}
      </DetailDrawer>
    </AppShell>
  );
}
