import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FeatureGridItem {
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}

const toneClass: Record<NonNullable<FeatureGridItem["tone"]>, string> = {
  default: "text-fg-muted",
  success: "text-status-success",
  warning: "text-status-warning",
  danger: "text-status-danger",
  info: "text-status-info",
};

/**
 * The reference's icon-chip feature grid, reused for identity/financial
 * summaries (Customers drawer) instead of plain key/value rows. Purely
 * presentational — every value passed in is already-fetched real data.
 */
export function FeatureGrid({ items, className }: { items: FeatureGridItem[]; className?: string }) {
  return (
    <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2", className)}>
      {items.map((item, i) => {
        const Icon = item.icon;
        return (
          <div
            key={i}
            className="flex items-start gap-3 rounded-xl border border-hairline bg-surface-subtle/50 p-4"
          >
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-elevated",
                toneClass[item.tone ?? "default"]
              )}
            >
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="label-mono">{item.label}</div>
              <div className="mt-0.5 truncate text-sm font-semibold text-fg">{item.value}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
