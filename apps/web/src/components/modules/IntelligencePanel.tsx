"use client";

import React, { useState } from "react";
import useSWR from "swr";
import {
  BrainCircuit,
  Check,
  X,
  Loader2,
  Activity,
  ShieldCheck,
  AlertTriangle,
  Ban,
  ArrowRight,
  Sparkles,
  Cpu,
} from "lucide-react";
import { api } from "@/lib/api";
import { IntelligenceEnvelope } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

interface Props {
  caseId: string;
  caseNumber?: string;
}

/* ---------- small primitives ------------------------------------------- */

function Meter({ value, tone }: { value: number; tone: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="w-full h-2 rounded-full bg-surface-elevated overflow-hidden">
      <div
        className={cn("h-full rounded-full transition-all duration-500", tone)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function ConfidenceRow({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
        <span>{label}</span>
        <span className="text-slate-200 tabular-nums">{pct}%</span>
      </div>
      <Meter value={value} tone="bg-blue-500/80" />
    </div>
  );
}

const bandTone: Record<string, string> = {
  HIGH: "bg-emerald-500/80",
  MEDIUM: "bg-amber-500/80",
  LOW: "bg-rose-500/80",
};

const verdictStyle: Record<string, { tone: string; icon: any; label: string }> = {
  APPROVED: { tone: "text-emerald-400 border-status-success-border bg-status-success-bg", icon: ShieldCheck, label: "APPROVED" },
  NEEDS_APPROVAL: { tone: "text-amber-400 border-status-warning-border bg-status-warning-bg", icon: AlertTriangle, label: "NEEDS APPROVAL" },
  REJECTED: { tone: "text-rose-400 border-status-danger-border bg-status-danger-bg", icon: Ban, label: "REJECTED" },
};

const riskTone: Record<string, string> = {
  LOW: "text-emerald-400",
  MEDIUM: "text-amber-400",
  HIGH: "text-rose-400",
};

/** Backend-driven diagnosis source: "AI-ENHANCED" | "DETERMINISTIC FALLBACK" | "DETERMINISTIC" */
function SourceBadge({ source }: { source?: string | null }) {
  if (!source) return null;
  const isAI = source === "AI-ENHANCED";
  const isFallback = source === "DETERMINISTIC FALLBACK";
  const Icon = isAI ? Sparkles : Cpu;
  const tone = isAI
    ? "text-emerald-400 border-status-success-border bg-status-success-bg"
    : isFallback
    ? "text-amber-400 border-status-warning-border bg-status-warning-bg"
    : "text-slate-400 border-border bg-surface-elevated";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded border tracking-wide",
        tone
      )}
    >
      <Icon className="w-3 h-3" />
      {source}
    </span>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[11px] font-mono font-semibold text-slate-300 uppercase tracking-widest">
      {children}
    </h4>
  );
}

/* ---------- main panel ------------------------------------------------- */

export function IntelligencePanel({ caseId, caseNumber }: Props) {
  const { data, error, mutate, isValidating } = useSWR<IntelligenceEnvelope>(
    caseId ? `/api/v1/recovery-cases/${caseId}/intelligence` : null,
    () => api.getCaseIntelligence(caseId)
  );
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const analyze = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const res = await api.analyzeCase(caseId);
      await mutate(res, { revalidate: false });
    } catch (e: any) {
      setRunError(e?.message || "Analysis request failed");
    } finally {
      setRunning(false);
    }
  };

  const header = (
    <div className="flex items-center justify-between border-b border-border pb-3">
      <div className="flex items-center gap-2">
        <BrainCircuit className="w-4 h-4 text-accent" />
        <div>
          <h3 className="text-sm font-semibold text-white font-mono tracking-wide">
            RECON INTELLIGENCE
          </h3>
          <p className="text-[10px] font-mono text-slate-500 tracking-wider">
            PHASE 2.5 • THINK
          </p>
        </div>
      </div>
      {data?.analyzed && <SourceBadge source={data.diagnosis_source} />}
    </div>
  );

  // loading
  if (!data && !error) {
    return (
      <div className="rounded-lg border border-border bg-surface-subtle/40 p-5 space-y-4">
        {header}
        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading intelligence…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-border bg-surface-subtle/40 p-5 space-y-4">
        {header}
        <p className="text-xs text-rose-400 font-mono">
          Could not load intelligence for this case.
        </p>
      </div>
    );
  }

  const env = data as IntelligenceEnvelope;

  // not analysed yet (or intelligence disabled)
  if (!env.analyzed) {
    return (
      <div className="rounded-lg border border-border bg-surface-subtle/40 p-5 space-y-4">
        {header}
        {env.status === "FAILED" ? (
          <div className="space-y-2">
            <p className="text-xs text-rose-400 font-mono">INTELLIGENCE RUN FAILED</p>
            {env.error_message && (
              <p className="text-[11px] text-slate-500 font-mono break-words">
                {env.error_message}
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            <p className="text-xs font-mono text-slate-300">INTELLIGENCE NOT RUN</p>
            <p className="text-[11px] text-slate-500">
              {env.intelligence_enabled
                ? "This case has not been analysed yet."
                : "Automatic analysis is disabled — run it manually below."}
            </p>
          </div>
        )}
        {runError && (
          <p className="text-[11px] text-rose-400 font-mono">{runError}</p>
        )}
        <button
          onClick={analyze}
          disabled={running}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-accent text-white text-xs font-mono font-medium hover:bg-accent-hover transition-colors disabled:opacity-50"
        >
          {running ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Analyzing case…
            </>
          ) : (
            <>
              <Activity className="w-3.5 h-3.5" /> Analyze Case
            </>
          )}
        </button>
      </div>
    );
  }

  const d = env.diagnosis!;
  const p = env.prediction!;
  const s = env.strategy!;
  const pol = env.policy!;
  const vs = verdictStyle[pol.verdict] || verdictStyle.NEEDS_APPROVAL;
  const VIcon = vs.icon;

  return (
    <div className="rounded-lg border border-border bg-surface-subtle/40 p-5 space-y-6">
      {header}

      {/* DIAGNOSIS */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <SectionTitle>Diagnosis</SectionTitle>
          <span className="inline-flex items-center gap-1 text-[10px] font-mono text-slate-500">
            {env.diagnosis_source === "AI-ENHANCED" ? (
              <><Sparkles className="w-3 h-3 text-emerald-400" /> Provider: {d.provider_version || env.provider}</>
            ) : (
              <><Cpu className="w-3 h-3" /> Provider: deterministic engine</>
            )}
          </span>
        </div>
        {d.fallback_reason && (
          <div className="text-[11px] font-mono text-amber-400/90 bg-status-warning-bg border border-status-warning-border/50 rounded px-2 py-1.5">
            AI diagnosis unavailable — deterministic fallback used ({d.fallback_reason}).
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] font-mono text-slate-500 uppercase">Failure Category</p>
            <p className="text-sm font-mono font-semibold text-white mt-0.5">
              {d.failure_category}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-mono text-slate-500 uppercase">Probable Cause</p>
            <p className="text-xs text-slate-200 mt-0.5">{d.probable_cause}</p>
          </div>
        </div>
        <ConfidenceRow
          label={env.diagnosis_source === "AI-ENHANCED" ? "AI diagnosis confidence" : "Diagnosis confidence"}
          value={d.confidence}
        />
        {d.evidence?.length > 0 && (
          <div>
            <p className="text-[10px] font-mono text-slate-500 uppercase mb-1">Evidence</p>
            <ul className="space-y-0.5">
              {d.evidence.slice(0, 6).map((e, i) => (
                <li key={i} className="text-[11px] text-slate-400 font-mono flex gap-1.5">
                  <span className="text-slate-600">–</span>
                  <span className="break-words">{e}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* RECOVERY PREDICTION */}
      <div className="space-y-3 border-t border-border/60 pt-4">
        <SectionTitle>Recovery Prediction</SectionTitle>
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[10px] font-mono text-slate-500 uppercase">Recovery Probability</p>
            <p className="text-3xl font-bold font-mono text-white tabular-nums mt-0.5">
              {Math.round(p.recovery_probability * 100)}%
            </p>
          </div>
          <span
            className={cn(
              "text-[11px] font-mono font-semibold px-2 py-1 rounded border",
              p.band === "HIGH" && "text-emerald-400 border-status-success-border bg-status-success-bg",
              p.band === "MEDIUM" && "text-amber-400 border-status-warning-border bg-status-warning-bg",
              p.band === "LOW" && "text-rose-400 border-status-danger-border bg-status-danger-bg"
            )}
          >
            {p.band} BAND
          </span>
        </div>
        <Meter value={p.recovery_probability} tone={bandTone[p.band] || "bg-blue-500/80"} />
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
          <span>base rate {Math.round(p.base_rate * 100)}%</span>
          <span>model confidence {Math.round(p.confidence * 100)}%</span>
        </div>

        {p.features_used?.length > 0 && (
          <div className="space-y-1 pt-1">
            <p className="text-[10px] font-mono text-slate-500 uppercase mb-1">Contributing Factors</p>
            {p.features_used
              .filter((f) => f.feature !== "failure_category_base_rate")
              .map((f, i) => {
                const c = Math.round(f.contribution * 100);
                const sign = c > 0 ? "+" : c < 0 ? "−" : "±";
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between text-[11px] font-mono"
                  >
                    <span className="text-slate-400">
                      {f.feature.replace(/_/g, " ")}
                      <span className="text-slate-600"> · {f.value}</span>
                    </span>
                    <span
                      className={cn(
                        "tabular-nums",
                        f.direction === "positive" && "text-emerald-400",
                        f.direction === "negative" && "text-rose-400",
                        f.direction === "neutral" && "text-slate-500"
                      )}
                    >
                      {sign}
                      {Math.abs(c)}%
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </div>

      {/* RECOMMENDED STRATEGY */}
      <div className="space-y-3 border-t border-border/60 pt-4">
        <SectionTitle>Recommended Strategy</SectionTitle>
        <div className="flex items-center justify-between">
          <span className="text-sm font-mono font-semibold text-blue-400">{s.action}</span>
          <span className="text-[10px] font-mono text-slate-500">
            confidence {Math.round(s.confidence * 100)}%
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed">{s.rationale}</p>
        {s.params && Object.keys(s.params).length > 0 && (
          <div className="text-[10px] font-mono text-slate-500">
            params: {JSON.stringify(s.params)}
          </div>
        )}
        {s.alternatives?.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] font-mono text-slate-500 uppercase">Alternatives</p>
            {s.alternatives.map((a, i) => (
              <div key={i} className="flex items-start gap-1.5 text-[11px] font-mono text-slate-400">
                <ArrowRight className="w-3 h-3 mt-0.5 text-slate-600 shrink-0" />
                <span>
                  <span className="text-slate-300">{a.action}</span> — {a.reason}
                </span>
              </div>
            ))}
          </div>
        )}
        <p className="text-[10px] text-slate-600 font-mono">
          Recommendation only — execution is Phase 3 and gated by the Policy Engine below.
        </p>
      </div>

      {/* POLICY DECISION */}
      <div className="space-y-3 border-t border-border/60 pt-4">
        <SectionTitle>Policy Decision</SectionTitle>
        <div className="flex items-center justify-between">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-1 rounded border",
              vs.tone
            )}
          >
            <VIcon className="w-3.5 h-3.5" />
            {vs.label}
          </span>
          <span className="text-[11px] font-mono">
            Risk <span className={cn("font-semibold", riskTone[pol.risk_level])}>{pol.risk_level}</span>
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed">{pol.reason}</p>

        <div className="space-y-1.5">
          <p className="text-[10px] font-mono text-slate-500 uppercase">Rules Evaluated</p>
          {pol.evaluated_rules.map((r) => (
            <div key={r.rule_id} className="flex items-start gap-2 text-[11px] font-mono">
              {r.passed ? (
                <Check className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
              ) : (
                <X className="w-3.5 h-3.5 text-rose-400 mt-0.5 shrink-0" />
              )}
              <span className="flex-1">
                <span className={cn(r.passed ? "text-slate-300" : "text-rose-300")}>
                  {r.name}
                </span>
                <span className="text-slate-600 block">{r.detail}</span>
              </span>
            </div>
          ))}
        </div>

        {pol.allowed_actions?.length > 0 && (
          <p className="text-[10px] font-mono text-emerald-400/80">
            allowed for automated execution (Phase 3): {pol.allowed_actions.join(", ")}
          </p>
        )}
      </div>

      {/* SOURCE */}
      <div className="border-t border-border/60 pt-3 flex flex-wrap items-center justify-between gap-1 text-[10px] font-mono text-slate-500">
        <span>
          DIAGNOSIS SOURCE: <span className="text-slate-300">{env.diagnosis_source || env.provider}</span>
          {env.provider_version ? ` · ${env.provider_version}` : ""}
          {env.intelligence_version ? ` · pipeline v${env.intelligence_version}` : ""}
          {" · analysis #"}{env.version}
        </span>
        <span>{env.analyzed_at ? formatDateTime(env.analyzed_at) : ""}</span>
      </div>
      <p className="text-[10px] font-mono text-slate-600">
        Prediction, strategy and the Policy Engine are deterministic and are not
        influenced by the diagnosis source.
      </p>

      <div>
        <button
          onClick={analyze}
          disabled={running || isValidating}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-surface-subtle text-[11px] font-mono text-slate-300 hover:text-white hover:bg-surface-elevated transition-colors disabled:opacity-50"
        >
          {running ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin" /> Re-analyzing…
            </>
          ) : (
            <>
              <Activity className="w-3 h-3" /> Re-run Analysis
            </>
          )}
        </button>
        {runError && <p className="text-[11px] text-rose-400 font-mono mt-2">{runError}</p>}
      </div>
    </div>
  );
}
