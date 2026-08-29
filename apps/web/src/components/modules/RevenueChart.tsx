"use client";

import React from "react";
import { DailyTrendItem } from "@/lib/types";
import { formatINR } from "@/lib/utils";

interface RevenueChartProps {
  data: DailyTrendItem[];
}

export function RevenueChart({ data }: RevenueChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-xs text-fg-faint font-mono">
        Awaiting historical payment data...
      </div>
    );
  }

  // Calculate max amount for scaling
  const maxAmount = Math.max(
    ...data.map((d) => Math.max(parseFloat(d.failed_amount || "0"), parseFloat(d.captured_amount || "0"))),
    1000 // minimum scale baseline
  );

  return (
    <div className="space-y-4">
      {/* Legend */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center space-x-4 font-mono">
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-status-danger"></span>
            <span className="text-fg-secondary">Revenue at Risk (Failed)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-status-success"></span>
            <span className="text-fg-secondary">Revenue Secured (Captured)</span>
          </div>
        </div>
        <span className="text-fg-faint text-[11px] font-mono">Past 7 Days Activity</span>
      </div>

      {/* SVG Bar / Area Chart */}
      <div className="h-56 w-full flex items-end justify-between gap-2 pt-6 pb-2 border-b border-border/80">
        {data.map((item, index) => {
          const failed = parseFloat(item.failed_amount || "0");
          const captured = parseFloat(item.captured_amount || "0");
          const failedHeight = maxAmount > 0 ? (failed / maxAmount) * 100 : 0;
          const capturedHeight = maxAmount > 0 ? (captured / maxAmount) * 100 : 0;

          // Format date for label (e.g. "Aug 29")
          const dateLabel = new Date(item.date).toLocaleDateString("en-IN", {
            month: "short",
            day: "numeric",
          });

          return (
            <div key={index} className="flex-1 flex flex-col items-center h-full justify-end group relative">
              {/* Tooltip on Hover */}
              <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-12 z-20 pointer-events-none bg-surface-elevated border border-border p-2 rounded shadow-xl text-[10px] font-mono whitespace-nowrap">
                <div className="text-fg font-semibold">{dateLabel}</div>
                <div className="text-status-danger">At Risk: {formatINR(failed)}</div>
                <div className="text-status-success">Secured: {formatINR(captured)}</div>
              </div>

              {/* Bars */}
              <div className="w-full max-w-[28px] flex items-end gap-1 h-full">
                {/* Failed Bar */}
                <div
                  style={{ height: `${Math.max(failedHeight, 4)}%` }}
                  className="w-1/2 bg-status-danger/80 hover:bg-status-danger rounded-t transition-all duration-300"
                />
                {/* Captured Bar */}
                <div
                  style={{ height: `${Math.max(capturedHeight, 4)}%` }}
                  className="w-1/2 bg-status-success/80 hover:bg-status-success rounded-t transition-all duration-300"
                />
              </div>

              {/* Day Label */}
              <span className="text-[10px] font-mono text-fg-muted mt-2">
                {dateLabel}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
