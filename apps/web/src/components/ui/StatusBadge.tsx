import React from "react";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  type?: "payment" | "case" | "priority" | "event" | "default";
  className?: string;
}

export function StatusBadge({ status, type = "default", className }: StatusBadgeProps) {
  const normalized = status.toUpperCase();

  // Color mapping based on semantic meaning
  let colorClasses = "bg-surface-elevated text-fg-secondary border-border";
  let dashed = false;

  if (["SIMULATED"].includes(normalized)) {
    colorClasses = "bg-status-warning-bg text-status-warning border-status-warning-border";
    dashed = true;
  } else if (["CAPTURED", "RESOLVED", "RECOVERED", "PROCESSED", "SUCCESS", "SUCCESSFUL", "VERIFIED"].includes(normalized)) {
    colorClasses = "bg-status-success-bg text-status-success border-status-success-border badge-glow-success";
  } else if (["FAILED", "CRITICAL", "HIGH"].includes(normalized)) {
    colorClasses = "bg-status-danger-bg text-status-danger border-status-danger-border badge-glow-danger";
  } else if (["DETECTED", "OPEN", "PROCESSING", "MEDIUM", "WARNING"].includes(normalized)) {
    colorClasses = "bg-status-warning-bg text-status-warning border-status-warning-border";
  } else if (["AUTHORIZED", "LOW", "RECEIVED", "INFO", "PAYMENT.FAILED"].includes(normalized)) {
    colorClasses = "bg-status-info-bg text-status-info border-status-info-border";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 font-mono text-[11px] font-medium uppercase tracking-[0.08em]",
        dashed && "border-dashed",
        colorClasses,
        className
      )}
    >
      <span className="mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-80" />
      {status}
    </span>
  );
}
