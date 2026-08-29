import React from "react";
import { cn, formatINR } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  isCurrency?: boolean;
  subtitle?: string;
  icon?: LucideIcon;
  variant?: "danger" | "success" | "warning" | "info" | "default";
  trend?: string;
  className?: string;
}

export function StatCard({
  title,
  value,
  isCurrency = false,
  subtitle,
  icon: Icon,
  variant = "default",
  trend,
  className,
}: StatCardProps) {
  const formattedValue = isCurrency ? formatINR(value) : value.toLocaleString();

  const variantBorders = {
    default: "border-border hover:border-border-highlight",
    danger: "border-status-danger-border/40 hover:border-status-danger-border",
    success: "border-status-success-border/40 hover:border-status-success-border",
    warning: "border-status-warning-border/40 hover:border-status-warning-border",
    info: "border-status-info-border/40 hover:border-status-info-border",
  };

  const iconColors = {
    default: "text-slate-400 bg-surface-subtle",
    danger: "text-rose-400 bg-status-danger-bg",
    success: "text-emerald-400 bg-status-success-bg",
    warning: "text-amber-400 bg-status-warning-bg",
    info: "text-blue-400 bg-status-info-bg",
  };

  return (
    <div
      className={cn(
        "bg-surface p-5 rounded-lg border transition-all duration-200 shadow-sm flex flex-col justify-between",
        variantBorders[variant],
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono uppercase tracking-wider text-slate-400 font-medium">
          {title}
        </span>
        {Icon && (
          <div className={cn("p-2 rounded-md", iconColors[variant])}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>

      <div className="mt-4">
        <div className="text-2xl lg:text-3xl font-bold tracking-tight text-white tabular-nums">
          {formattedValue}
        </div>
        {(subtitle || trend) && (
          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
            {subtitle && <span>{subtitle}</span>}
            {trend && <span className="font-mono text-slate-500">{trend}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
