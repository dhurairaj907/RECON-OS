import React from "react";
import { LucideIcon, Inbox } from "lucide-react";
import Link from "next/link";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: LucideIcon;
  actionText?: string;
  actionHref?: string;
}

export function EmptyState({
  title = "No data available",
  description = "Incoming events and cases will automatically appear here.",
  icon: Icon = Inbox,
  actionText,
  actionHref,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-lg border border-dashed border-border/80 bg-surface/40 my-4">
      <div className="p-3 rounded-full bg-surface-subtle border border-border text-fg-muted mb-3">
        <Icon className="w-6 h-6" />
      </div>
      <h3 className="text-sm font-semibold text-fg tracking-wide">{title}</h3>
      <p className="text-xs text-fg-muted mt-1 max-w-sm">{description}</p>
      {actionText && actionHref && (
        <Link
          href={actionHref}
          className="mt-4 inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          {actionText}
        </Link>
      )}
    </div>
  );
}
