import React from "react";
import { cn } from "@/lib/utils";

export interface NumberedStep {
  number: string;
  label: string;
  description?: string;
  value?: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "info" | "muted";
}

const toneClass: Record<NonNullable<NumberedStep["tone"]>, string> = {
  default: "text-accent",
  success: "text-status-success",
  warning: "text-status-warning",
  danger: "text-status-danger",
  info: "text-status-info",
  muted: "text-fg-faint",
};

/**
 * The reference's "01 / 02 / ..." numbered-step grid: huge accent numerals,
 * a hairline rule filling the rest of the header row, optional real value
 * and description below. Cells sit in a true hairline grid (background-color
 * "seam" trick via `gap-px` + a `bg-surface` cell fill) so any item count —
 * including an odd one out — still lines up cleanly, no manual border math.
 */
export function NumberedSteps({ steps, className }: { steps: NumberedStep[]; className?: string }) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-hairline bg-[color:var(--hairline)] sm:grid-cols-2",
        className
      )}
    >
      {steps.map((step) => (
        <div key={step.number} className="bg-surface p-6 sm:p-8">
          <div className="flex items-baseline gap-3">
            <span
              className={cn(
                "display-md font-bold leading-none tabular-nums",
                toneClass[step.tone ?? "default"]
              )}
            >
              {step.number}
            </span>
            <span className="flex-1 border-b border-hairline pb-1.5 text-sm font-semibold text-fg">
              {step.label}
            </span>
          </div>
          {step.value != null && (
            <div className="mt-3 text-xl font-bold tabular-nums text-fg">{step.value}</div>
          )}
          {step.description && (
            <p className="mt-2 text-xs leading-relaxed text-fg-muted">{step.description}</p>
          )}
        </div>
      ))}
    </div>
  );
}
