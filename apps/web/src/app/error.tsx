"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <AppShell>
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-status-danger-border bg-status-danger-bg text-status-danger">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <div className="label-mono text-status-danger">SYSTEM ERROR</div>
        <h1 className="display-lg font-bold text-fg">SOMETHING WENT WRONG</h1>
        <p className="max-w-md text-sm text-fg-muted">
          RECON OS hit an unexpected error rendering this page. It has been logged to the
          browser console — no recovery case data was affected.
        </p>
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={reset}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
          >
            <RefreshCw className="h-4 w-4" /> Try again
          </button>
          <Link
            href="/"
            className="inline-flex h-10 items-center rounded-lg border border-border bg-surface-subtle px-4 text-sm text-fg-secondary transition-colors hover:bg-surface-elevated"
          >
            Command Center
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
