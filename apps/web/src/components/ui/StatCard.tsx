import React from "react";
import { cn, formatINR } from "@/lib/utils";
import { LucideIcon } from "lucide-react";
import { DepthCard } from "@/components/spatial/DepthCard";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

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

const glowFor: Record<string, "info" | "success" | "warning" | "danger" | undefined> = {
  danger: "danger",
  success: "success",
  warning: "warning",
  info: "info",
  default: undefined,
};

const valueTone: Record<string, string> = {
  default: "text-fg",
  danger: "text-status-danger",
  success: "text-status-success",
  warning: "text-status-warning",
  info: "text-status-info",
};

/**
 * KPI surface in the reference's editorial style: a tiny recessive mono label
 * above, an oversized figure below, a faint mono sub-line. The value animates
 * only when the real number changes.
 */
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
  const numeric =
    typeof value === "number" ||
    (typeof value === "string" && value.trim() !== "" && !isNaN(Number(value)));

  return (
    <DepthCard
      highlight
      glow={glowFor[variant]}
      className={cn(
        "flex flex-col gap-4 p-5 transition-transform hover:-translate-y-px hover:border-border-highlight",
        className
      )}
    >
      <div className="flex items-start justify-between">
        <span className="label-mono">{title}</span>
        {Icon && (
          <Icon
            className={cn(
              "h-4 w-4 shrink-0 opacity-70",
              variant === "default" ? "text-fg-faint" : valueTone[variant]
            )}
          />
        )}
      </div>

      <div>
        <div
          className={cn(
            "text-2xl font-bold leading-none tracking-tight tabular-nums sm:text-[1.7rem] lg:text-[2rem]",
            valueTone[variant]
          )}
        >
          {numeric ? (
            <AnimatedNumber
              value={value}
              format={
                isCurrency
                  ? (n) => formatINR(n)
                  : (n) => Math.round(n).toLocaleString()
              }
            />
          ) : isCurrency ? (
            formatINR(value)
          ) : (
            value
          )}
        </div>
        {(subtitle || trend) && (
          <div className="mt-2.5 flex items-center justify-between font-mono text-xs text-fg-faint">
            {subtitle && <span>{subtitle}</span>}
            {trend && <span>{trend}</span>}
          </div>
        )}
      </div>
    </DepthCard>
  );
}
