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
  let colorClasses = "bg-surface-elevated text-slate-300 border-border";

  if (["CAPTURED", "RESOLVED", "PROCESSED", "SUCCESS", "SUCCESSFUL"].includes(normalized)) {
    colorClasses = "bg-status-success-bg text-emerald-400 border-status-success-border badge-glow-success";
  } else if (["FAILED", "CRITICAL", "HIGH"].includes(normalized)) {
    colorClasses = "bg-status-danger-bg text-rose-400 border-status-danger-border badge-glow-danger";
  } else if (["DETECTED", "OPEN", "PROCESSING", "MEDIUM", "WARNING"].includes(normalized)) {
    colorClasses = "bg-status-warning-bg text-amber-400 border-status-warning-border";
  } else if (["AUTHORIZED", "LOW", "RECEIVED", "INFO", "PAYMENT.FAILED"].includes(normalized)) {
    colorClasses = "bg-status-info-bg text-blue-400 border-status-info-border";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium border tracking-wide uppercase",
        colorClasses,
        className
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 opacity-80" />
      {status}
    </span>
  );
}
