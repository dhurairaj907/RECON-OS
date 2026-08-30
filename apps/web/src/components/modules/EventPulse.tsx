"use client";

import React from "react";
import { cn, formatINR } from "@/lib/utils";
import type { RevenueEvent } from "@/lib/types";

function toneFor(evt: RevenueEvent): string {
  const type = (evt.event_type || "").toUpperCase();
  const status = (evt.processing_status || "").toUpperCase();
  if (status === "FAILED" || type.includes("FAILED")) return "bg-status-danger";
  if (type.includes("CAPTURED") || type.includes("PAID")) return "bg-status-success";
  if (type.includes("AUTHORIZED")) return "bg-status-info";
  return "bg-status-warning";
}

/**
 * Slim live-activity strip for Live Events — SVG/CSS, not WebGL. A raw event
 * list is a log, not a network; 3D is reserved for Command Center/Recovery/
 * Intelligence where it represents a real system concept. Reads the same
 * already-fetched page of events the table below renders — no new fetch.
 */
export function EventPulse({
  events,
  onSelect,
  className,
}: {
  events: RevenueEvent[];
  onSelect?: (event: RevenueEvent) => void;
  className?: string;
}) {
  if (events.length === 0) return null;
  const ticks = [...events].slice(0, 30).reverse(); // oldest -> newest, left to right

  return (
    <div
      className={cn(
        "flex items-end gap-1 overflow-x-auto rounded-xl border border-hairline bg-surface-subtle/40 p-4",
        className
      )}
      aria-label="Recent event activity"
    >
      {ticks.map((evt) => (
        <button
          key={evt.id}
          type="button"
          onClick={() => onSelect?.(evt)}
          title={`${evt.event_type} · ${
            evt.normalized_data?.customer_name || evt.normalized_data?.customer_email || "Customer"
          } · ${formatINR(evt.normalized_data?.amount || "0")}`}
          className={cn(
            "h-8 w-2 shrink-0 rounded-full transition-transform hover:scale-y-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            toneFor(evt)
          )}
        />
      ))}
    </div>
  );
}
