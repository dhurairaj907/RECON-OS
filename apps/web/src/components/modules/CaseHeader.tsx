"use client";

import React from "react";
import { cn, formatINR } from "@/lib/utils";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

type Tone = "info" | "success" | "warning" | "danger" | "neutral";

interface CaseHeaderProps {
  caseNumber?: string | null;
  amountAtRisk: string | number;
  amountRecovered?: string | number | null;
  failureCode?: string | null;
  failureReason?: string | null;
  /** Drives the accent line + glow. Derive from real case/recovery state. */
  tone?: Tone;
  recovered?: boolean;
  simulated?: boolean;
}

const toneBar: Record<Tone, string> = {
  info: "before:bg-status-info",
  success: "before:bg-status-success",
  warning: "before:bg-status-warning",
  danger: "before:bg-status-danger",
  neutral: "before:bg-border-highlight",
};

const toneGlow: Record<Tone, string> = {
  info: "glow-info",
  success: "glow-success",
  warning: "glow-warning",
  danger: "glow-danger",
  neutral: "",
};

/**
 * Cinematic case identity band for the top of a recovery / intelligence drawer.
 * Oversized case number + amount, restrained. All values are real; `recovered`
 * is only true when the caller has confirmed verified provider state.
 */
export function CaseHeader({
  caseNumber,
  amountAtRisk,
  amountRecovered,
  failureCode,
  failureReason,
  tone = "neutral",
  recovered = false,
  simulated = false,
}: CaseHeaderProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border border-border bg-surface-subtle/60 p-6",
        "before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:content-['']",
        toneBar[tone],
        toneGlow[tone]
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="label-mono">
            Recovery Case
          </div>
          <div className="display-lg display-mono mt-1 text-fg">
            {caseNumber || "—"}
          </div>
          {(failureCode || failureReason) && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {failureCode && (
                <span className="rounded-full border border-status-warning-border bg-status-warning-bg px-2 py-[3px] text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-status-warning">
                  {failureCode}
                </span>
              )}
              {failureReason && (
                <span className="text-[11px] font-mono text-fg-muted">
                  {failureReason}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="text-right">
          <div className="label-mono">
            {recovered ? "Amount Recovered" : "Amount at Risk"}
          </div>
          <AnimatedNumber
            as="div"
            value={recovered ? amountRecovered ?? 0 : amountAtRisk}
            format={(n) => formatINR(n)}
            className={cn(
              "display-lg mt-1 font-bold",
              recovered ? "text-status-success" : "text-status-danger"
            )}
          />
          {recovered && simulated && (
            <div className="mt-1 inline-block rounded border border-dashed border-status-warning-border bg-status-warning-bg px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wider text-status-warning">
              Simulated · not a real payment
            </div>
          )}
          {!recovered && amountRecovered != null && Number(amountRecovered) > 0 && (
            <div className="mt-1 text-[11px] font-mono text-status-success">
              {formatINR(amountRecovered)} recovered so far
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
