import React from "react";
import { cn } from "@/lib/utils";

export function SkeletonRow({ cols = 5 }: { cols?: number }) {
  return (
    <div className="flex items-center space-x-4 py-4 px-4 border-b border-border/50 animate-pulse">
      {Array.from({ length: cols }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-4 bg-surface-elevated/70 rounded",
            i === 0 ? "w-28" : i === 1 ? "w-40" : "flex-1"
          )}
        />
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="bg-surface p-5 rounded-lg border border-border animate-pulse flex flex-col justify-between h-32"
        >
          <div className="flex justify-between">
            <div className="w-24 h-3.5 bg-surface-elevated rounded" />
            <div className="w-6 h-6 bg-surface-elevated rounded" />
          </div>
          <div className="w-36 h-7 bg-surface-elevated rounded mt-4" />
        </div>
      ))}
    </div>
  );
}
